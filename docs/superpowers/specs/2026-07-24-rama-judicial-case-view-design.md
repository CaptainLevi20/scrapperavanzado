# Vista de caso (radicado) para Rama Judicial — Diseño

Fecha: 2026-07-24

## Contexto y objetivo

Los documentos de Rama Judicial (tribunales) suelen representar **actuaciones individuales** de un mismo proceso judicial: distintos autos, sentencias, salvamentos de voto, etc., todos bajo el mismo número de radicado (23 dígitos), publicados en fechas distintas. Hoy en la página de Documentos, cada actuación aparece como una fila suelta, y la única forma de verlas juntas es hacer click en el título para filtrar la tabla por texto — quedan dispersas entre el resto de resultados, sin orden cronológico explícito ni forma de navegar entre ellas.

Este diseño agrega una "vista de caso": cuando varias actuaciones comparten el mismo radicado, la fila lo indica con una insignia, y al hacer click se abre el mismo modal de previsualización que ya existe (el usado hoy para navegar documentos y ver versiones de Corte Constitucional), cargado solo con las actuaciones de ese caso, ordenadas cronológicamente, navegables con las flechas ←/→ que el modal ya tiene.

Explícitamente en alcance:
- Familia **`rama_judicial` únicamente** — no JEP, CNDJ, ni SAMAI (aunque las 4 usan el radicado como título, no se ha validado que agrupar tenga el mismo valor ahí; se deja como extensión futura).
- Detección de "es un radicado" vía patrón — el `title` de Rama Judicial es literalmente el radicado formateado (`core/scrapers/families/rama_judicial.py::_normalize_title`): `T_{CODIGO}_{5}_{2}_{2}_{3}_{4}_{5}_{2}` dígitos segmentados. Cuando el scraper no logra parsear el radicado del nombre de archivo, cae a otro texto (nombre de magistrado, etc.) — esos títulos **no** deben agruparse como si fueran el mismo caso, aunque se repitan.
- Insignia visible en la tabla de Documentos solo cuando el caso tiene **más de 1** actuación.
- Al hacer click en el título de una fila con insignia, se abre el modal existente (`DocumentPreviewDialog`) con las actuaciones del caso, ordenadas por `f_public` ascendente (de la más antigua a la más reciente), posicionado inicialmente en la actuación que se clickeó.
- Filas sin insignia (radicado único, o título que cayó al fallback) mantienen el comportamiento actual sin cambios (click en título sigue filtrando la tabla por texto).

Explícitamente fuera de alcance:
- Cambiar el diseño de la tabla (fila expandible, acordeón) — se reusa el modal existente tal cual.
- Aplicar esto a JEP/CNDJ/SAMAI.
- Persistir el radicado en una columna nueva de `documents` — se sigue derivando de `title` en tiempo de consulta.

## Backend

### `core/utils.py` — detección del patrón de radicado

```python
import re

# Espejo del formato que produce core/scrapers/families/rama_judicial.py::_normalize_title
# (T_{CODIGO}_{radicado segmentado en 23 dígitos}). No importa TRIBUNAL_CODES desde el
# módulo del scraper para no acoplar esta capa a uno de familia específico — el rango de
# 2-5 letras mayúsculas cubre los códigos reales (3-4 letras) con margen.
RADICADO_TITLE_PATTERN = re.compile(r"^T_[A-Z]{2,5}_\d{5}_\d{2}_\d{2}_\d{3}_\d{4}_\d{5}_\d{2}$")


def is_radicado_title(title: str) -> bool:
    return bool(RADICADO_TITLE_PATTERN.match(title))
```

### `core/db/repository.py` — dos helpers nuevos, sin tocar `list_documents`

`list_documents` se usa desde muchos endpoints con filtros variados — esta funcionalidad se mantiene deliberadamente fuera de ella, como lógica de presentación específica de un endpoint, no una responsabilidad genérica de la capa de repositorio.

```python
def get_source_family_keys(db: Session, source_ids: list[int]) -> dict[int, str]:
    if not source_ids:
        return {}
    stmt = select(Source.id, Source.family_key).where(Source.id.in_(source_ids))
    return dict(db.execute(stmt).all())


def count_rama_judicial_documents_by_title(db: Session, titles: list[str]) -> dict[str, int]:
    if not titles:
        return {}
    stmt = (
        select(Document.title, func.count(Document.id))
        .join(Source, Source.id == Document.source_id)
        .where(Source.family_key == "rama_judicial", Document.title.in_(titles))
        .group_by(Document.title)
    )
    return dict(db.execute(stmt).all())
```

### `core/db/repository.py` — `title_exact`, agregado a `list_documents` igual que los filtros previos

`title_exact` es un filtro SQL real, añadido a `list_documents` con el mismo patrón aditivo y opcional ya usado para `f_public_from/to`, `downloaded_from/to` y `has_documents` (parámetro `Optional[str] = None`, no rompe a ningún llamador existente):

```python
if title_exact is not None:
    stmt = stmt.where(Document.title == title_exact)
```

`title_exact` y `title_contains` son mutuamente excluyentes en la práctica (el endpoint solo manda uno u otro), pero nada en `list_documents` los fuerza a serlo — ambos son simplemente filtros `WHERE` adicionales que se combinan con AND si alguna vez se mandan juntos.

### `api/routers/documents.py` — enriquecer la respuesta de `GET /documents`

Después de obtener `items` de `repository.list_documents(...)`, antes de retornar:

```python
from core.utils import is_radicado_title

@router.get("/documents", response_model=PaginatedDocuments)
def get_documents(
    ...,
    title_exact: Optional[str] = None,
    db: Session = Depends(get_db),
):
    items, total = repository.list_documents(
        db,
        ...,
        title_contains=title,
        title_exact=title_exact,
        limit=limit,
        offset=offset,
    )

    family_keys = repository.get_source_family_keys(db, [d.source_id for d in items])
    radicado_titles = [
        d.title for d in items
        if family_keys.get(d.source_id) == "rama_judicial" and is_radicado_title(d.title)
    ]
    counts = repository.count_rama_judicial_documents_by_title(db, radicado_titles)
    for d in items:
        count = counts.get(d.title)
        d.case_document_count = count if count and count > 1 else None

    return {"items": items, "total": total, "limit": limit, "offset": offset}
```

`case_document_count` es `None` salvo que haya **más de 1** actuación bajo ese radicado — un radicado único que solo hace match del patrón pero no tiene hermanos no es un "caso" a mostrar, así que no vale la pena distinguirlo de "no es un radicado" desde la perspectiva del frontend (ambos son `None`, ninguno pinta insignia). Se asigna como atributo dinámico sobre la instancia ORM de `Document` — Pydantic (`from_attributes=True`) lo lee vía `getattr`, igual que cualquier columna mapeada.

### `api/schemas.py`

```python
class DocumentOut(BaseModel):
    ...
    downloaded_at: datetime
    case_document_count: Optional[int] = None
```

## Frontend

### `frontend/src/api/types.ts` / `documents.ts`

- `Document` gana `case_document_count: number | null`.
- `ListDocumentsParams` gana `title_exact?: string`.

### `frontend/src/pages/DocumentsPage.tsx`

- Nueva insignia junto al título, visible solo cuando `document.case_document_count` es mayor a 1 (mismo patrón visual que los badges de revisión ya existentes en este archivo — pill con borde, ej. `"5 actuaciones"`).
- Nuevo estado local para el "caso" abierto (lista de documentos del caso + índice inicial), independiente del estado de `documentsQuery`.
- El `onClick` del título se bifurca:
  - Si `case_document_count > 1`: en vez de `setTitle(...)`, dispara un fetch de `fetchDocuments({ family_key: "rama_judicial", title_exact: document.title, limit: 50 })`, invierte el array (la API devuelve `f_public DESC`, se necesita ascendente), calcula el índice del documento clickeado dentro de ese array ya ordenado, y abre `DocumentPreviewDialog` con esa lista + ese índice inicial.
  - Si no: comportamiento actual sin cambios (`setTitle(document.title); setPage(0)`).
- `DocumentPreviewDialog` no cambia — ya soporta múltiples documentos + navegación ← /→ + previsualización individual; solo cambia qué arreglo de documentos se le pasa.

## Testing

- **Backend**: `core/utils.py` — casos para `is_radicado_title` (título válido de cada longitud de código, título que cae al fallback tipo nombre de magistrado, título vacío). `tests/test_api_documents.py` — caso con 3 documentos del mismo radicado (`case_document_count == 3` en los 3), 1 documento de radicado único (`case_document_count is None`), 1 documento con título tipo fallback repetido pero de familia `rama_judicial` (no debe agruparse, `case_document_count is None`), y un caso con el mismo título pero de otra familia (no debe contarse junto).
- **Frontend**: `DocumentsPage.test.tsx` — la insignia se muestra solo cuando `case_document_count > 1`; el click en un título con insignia abre el modal con los documentos correctos, en el orden correcto, en el índice correcto (no solo verificar que "algo" se abre); el click en un título sin insignia mantiene el comportamiento de filtro existente sin romperse.
