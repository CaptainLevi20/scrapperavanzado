# Marcar documentos como "útil" / "no útil" — Diseño

Fecha: 2026-07-14

## Contexto y objetivo

La tabla `documents` ya guarda metadatos ricos por documento (`tipo`, `seccion`, `especialidad`, `magistrado`, `detalle`, `source_url`), pero la página `DocumentsPage` del frontend solo muestra un subconjunto (`tipo`, `seccion`, `f_providencia`). Además, no existe ningún concepto de revisión manual: no hay forma de marcar un documento como útil o no útil para el trabajo jurídico que se hace con él.

El dedup de descargas ya funciona de forma independiente a esto — `worker/tasks.py` salta cualquier documento cuyo `doc_id` ya exista en la base (`repository.document_exists`), sin importar si fue marcado útil o no. Este diseño no toca esa lógica: es puramente un estado de revisión manual, informativo, sobre documentos ya descargados.

Este diseño cubre dos cosas juntas, porque tocan la misma página y el mismo endpoint:

1. Exponer en la UI las columnas que ya existen en la base pero no se muestran.
2. Agregar un estado de revisión de 3 valores (`pending` / `useful` / `not_useful`) por documento, marcable desde la tabla, con filtro.

Explícitamente fuera de alcance: cambios al pipeline de scraping/descarga, cambios al dedup por `doc_id`, borrado o exclusión automática de documentos marcados `not_useful` (el estado es solo informativo).

## Modelo de datos

Dos columnas nuevas en `documents` (`core/db/models.py`), vía una migración de Alembic (la segunda del proyecto, después de `4bffcba11b73_initial_schema`):

- `review_status: String, nullable=False, default="pending"` — valores permitidos: `"pending"`, `"useful"`, `"not_useful"`. Sigue la misma convención que `runs.status`/`run_sources.status` (strings en inglés en la base, con etiquetas en español en la UI: "Sin revisar" / "Útil" / "No útil").
- `reviewed_at: DateTime(timezone=True), nullable=True` — se fija a la hora actual cada vez que el estado cambia vía el nuevo endpoint (incluyendo un cambio de vuelta a `"pending"`); permanece `NULL` mientras nadie lo haya tocado.

No se crea tabla nueva ni se toca `doc_id`/la unicidad existente — es un valor más sobre la fila ya existente.

## Backend

### `GET /documents`

Gana un parámetro opcional `review_status` (`"pending" | "useful" | "not_useful"`) que filtra por el nuevo campo. Se agrega a `core/db/repository.list_documents(...)` como un `where` adicional cuando se provee, siguiendo el mismo patrón que los filtros existentes (`tipo`, `source_id`, etc.).

### `DocumentOut` (`api/schemas.py`)

Se agregan los campos ya existentes en la base pero no expuestos (`especialidad: Optional[str]`, `magistrado: Optional[str]`, `detalle: Optional[str]`, `source_url: Optional[str]`), más los dos nuevos (`review_status: str`, `reviewed_at: Optional[datetime]`).

### `PATCH /documents/{document_id}`

Nuevo endpoint, mismo patrón que el ya existente `PATCH /sources/{source_id}`:

- Body: `DocumentReviewUpdate { review_status: Literal["pending", "useful", "not_useful"] }` — un valor fuera de esas 3 opciones devuelve 422 automático (validación de Pydantic).
- `repository.update_document_review_status(db, document_id, review_status) -> Optional[Document]`: actualiza `review_status` y `reviewed_at = now()`, devuelve `None` si el id no existe.
- El router devuelve 404 si `update_document_review_status` devuelve `None`; si no, devuelve el `DocumentOut` actualizado.

## Frontend

### Tipo `Document` (`frontend/src/api/types.ts`)

Gana los mismos campos que `DocumentOut`: `especialidad`, `magistrado`, `detalle`, `source_url`, `review_status`, `reviewed_at`.

### `frontend/src/api/documents.ts`

Nueva función `updateDocumentReviewStatus(id: number, status: "pending" | "useful" | "not_useful"): Promise<Document>` que hace el `PATCH`.

### `DocumentsPage.tsx`

- **Columnas nuevas en la tabla**: "Especialidad" y "Magistrado" (mismo tratamiento que las columnas actuales — `"—"` cuando el valor es `null`).
- **`detalle`**: no se vuelve columna (texto libre, largo) — se muestra como atributo `title` (tooltip nativo del navegador) sobre la celda de "Título".
- **`source_url`**: no se vuelve columna — si existe, aparece como enlace pequeño "Ver original ↗" junto al título, con `target="_blank" rel="noopener noreferrer"`, apuntando a la página pública de la entidad.
- **Columna "Revisión"**: dos botones por fila, "Útil" y "No útil". El botón que coincide con el `review_status` actual del documento queda visualmente resaltado (ej. fondo distinto); el otro queda sin resaltar. Un clic en cualquiera de los dos dispara el `PATCH` con ese valor — no hay un tercer botón para volver a "pending" manualmente (si se necesita en el futuro, se agrega como iteración separada).
- **Filtro "Revisión"**: nuevo `<select>` junto a los filtros existentes (Título, Tipo, Fuente, Familia): "Todos" (sin filtro) / "Sin revisar" / "Útil" / "No útil". Cambia el parámetro `review_status` de `fetchDocuments` y resetea `page` a 0, igual que los demás filtros.
- La mutation de marcado invalida la query `["documents", ...]` de React Query al completarse, para refrescar la fila con el nuevo estado.

## Manejo de errores

- `PATCH /documents/{id}` con `id` inexistente → 404, mismo patrón que `PATCH /sources/{id}`.
- `review_status` fuera de las 3 opciones válidas → 422 automático (Pydantic `Literal`), sin código adicional.
- Fallo de red al marcar desde la UI: se reutiliza el patrón ya existente de `ErrorBanner` (igual que el error de descarga ya manejado en la página).
- Sin cambios al manejo de errores del pipeline de scraping/descarga — este diseño no lo toca.

## Testing y validación

- **Backend** (`tests/test_api_documents.py`): filtro por `review_status` en `GET /documents`; `PATCH /documents/{id}` cambia el estado y `reviewed_at`; 404 con id inexistente; 422 con valor inválido. Test unitario de `repository.update_document_review_status`.
- **Frontend** (`DocumentsPage.test.tsx`): las columnas nuevas se renderizan con los valores correctos (incluyendo `"—"` para `null`); clic en "Útil"/"No útil" llama al mock de `updateDocumentReviewStatus` con el id y valor correctos; el filtro de Revisión pasa el parámetro correcto a `fetchDocuments`; el enlace "Ver original" solo aparece cuando `source_url` no es `null`.

## Fuera de alcance

- Cambios al pipeline de scraping/descarga o al dedup por `doc_id` — el estado de revisión es puramente informativo, no afecta qué se descarga o se vuelve a descargar.
- Exclusión automática de documentos `not_useful` de listados/búsquedas futuras — solo se agrega el filtro manual descrito arriba.
- Un tercer botón para revertir a `"pending"` desde la UI, o marcado en lote (bulk) de varios documentos a la vez.
- Auditoría de quién marcó cada documento (no hay identidad de usuario individual en este sistema, solo API keys nombradas) — `reviewed_at` alcanza para el alcance actual.
