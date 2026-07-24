# Novedades del día — Diseño

Fecha: 2026-07-23

## Contexto y objetivo

El panel "Novedades" del Dashboard (`frontend/src/pages/DashboardPage.tsx:222-258`) hoy muestra los 8 documentos más recientes según `GET /documents?limit=8` — sin ningún filtro de fecha, ordenados por el backend según `f_public DESC NULLS LAST, id DESC` (`core/db/repository.py:286`, fecha de **publicación** del documento, no de ingesta). El link "Ver todos →" lleva a `/documents` (la página general de archivo), sin ningún filtro pre-aplicado.

Esto tiene dos problemas para el uso real de la herramienta:

1. **No hay forma de ver "qué entró hoy"** — el panel puede mostrar documentos publicados hace meses si su `f_public` es el más reciente entre los 8 primeros, y no hay ninguna vista que aísle lo ingresado en un día concreto.
2. Con runs periódicos automáticos (la dirección a la que va el proyecto — ya existe `worker.trigger_scheduled_run`), la fecha de publicación de un documento casi nunca coincide con el día en que el scraper lo bajó (los tribunales publican con rezago), así que filtrar por `f_public = hoy` dejaría el panel vacío casi todos los días.

Este diseño:
- Limita el panel "Novedades" a los documentos **ingresados hoy** (`downloaded_at`), no publicados hoy.
- Hace que "Ver todos →" lleve a la página de Documentos con ese mismo filtro de "hoy" pre-aplicado, ajustable o eliminable por el usuario ahí mismo.

Explícitamente en alcance:
- Nuevo filtro `downloaded_from`/`downloaded_to` en `GET /documents` y `repository.list_documents`, análogo al `f_public_from/to` ya existente.
- Actualizar el panel "Novedades" del Dashboard para usar ese filtro con "hoy" como rango.
- Nuevo control de filtro "Agregado" en la página de Documentos (mismo patrón visual que el filtro "Fecha de publicación" ya existente: botón + popover con Desde/Hasta/Limpiar).
- Navegación desde "Ver todos →" que pre-carga ese filtro en "hoy" vía `react-router` `Link state` (no query string).

Explícitamente fuera de alcance (por ahora):
- Filtros de rango rápido tipo "ayer" / "última semana" en la UI — solo Desde/Hasta manual, igual que el filtro de publicación existente.
- Cambiar el orden de resultados de `list_documents` (sigue siendo `f_public DESC, id DESC` incluso cuando se filtra por `downloaded_at`).
- Sincronizar filtros de Documentos con la URL (query params) de forma general — el estado del filtro sigue siendo local a la página, como hoy; solo se agrega una forma de sembrar su valor inicial al llegar desde el Dashboard.
- Zona horaria configurable server-side: "hoy" se calcula con la fecha local del navegador y se compara contra `downloaded_at` (que se guarda en UTC) tomando esa fecha como un día UTC. Puede haber un desfase de pocas horas justo alrededor de medianoche; no se corrige con lógica de zona horaria adicional.

## Backend

### `api/routers/documents.py` — `get_documents`

Dos parámetros nuevos, mismo estilo que los de `f_public`:

```python
@router.get("/documents", response_model=PaginatedDocuments)
def get_documents(
    source_id: Optional[int] = None,
    family_key: Optional[str] = None,
    tipo: Optional[str] = None,
    title: Optional[str] = None,
    review_status: Optional[str] = None,
    f_public_from: Optional[date] = None,
    f_public_to: Optional[date] = None,
    downloaded_from: Optional[date] = None,
    downloaded_to: Optional[date] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    items, total = repository.list_documents(
        db,
        ...,
        downloaded_from=downloaded_from,
        downloaded_to=downloaded_to,
        ...
    )
```

### `core/db/repository.py` — `list_documents`

`downloaded_at` es `DateTime(timezone=True)`, así que un `date` de entrada se traduce a un rango medio-abierto en vez de una igualdad directa:

```python
from datetime import date, datetime, time, timedelta, timezone

def list_documents(
    db: Session,
    ...,
    downloaded_from: Optional[date] = None,
    downloaded_to: Optional[date] = None,
    ...
) -> tuple[list[Document], int]:
    stmt = select(Document)
    ...
    if downloaded_from is not None:
        stmt = stmt.where(
            Document.downloaded_at >= datetime.combine(downloaded_from, time.min, tzinfo=timezone.utc)
        )
    if downloaded_to is not None:
        stmt = stmt.where(
            Document.downloaded_at < datetime.combine(downloaded_to, time.min, tzinfo=timezone.utc) + timedelta(days=1)
        )
    ...
    # el ORDER BY no cambia
```

No se toca el `ORDER BY` — sigue siendo `f_public DESC NULLS LAST, id DESC`, tanto para el uso general de Documentos como para el panel de Novedades filtrado a "hoy".

## Frontend

### `frontend/src/api/documents.ts`

`ListDocumentsParams` gana `downloaded_from?: string` y `downloaded_to?: string` (mismo tipo/tratamiento que `f_public_from/to` — strings `YYYY-MM-DD`, pasan tal cual por `buildQuery`).

### Cálculo de "hoy" (frontend)

**No usar `new Date().toISOString().slice(0, 10)`** — trunca a UTC, y ya hay un bug documentado en este mismo repo (`frontend/src/lib/formatters.ts:8-21`) sobre el desfase de un día que esto produce en zona horaria de Colombia (UTC-5). Se agrega un helper que arma la fecha local explícitamente por componentes, junto a `parseDateOnlyAsLocal` en `formatters.ts`:

```typescript
export function todayDateString(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
```

### `frontend/src/pages/DashboardPage.tsx`

```typescript
const today = todayDateString();
const novedadesQuery = useQuery({
  queryKey: ["documents", "novedades", today],
  queryFn: () => fetchDocuments({ downloaded_from: today, downloaded_to: today, limit: 8 }),
});
```

- Mensaje de `EmptyState` para esta tabla cambia de "Todavía no ha llegado ningún documento." a **"No han llegado documentos hoy."**
- El link "Ver todos →" pasa de `<Link to="/documents">` a:

```tsx
<Link to="/documents" state={{ downloadedToday: true }} className="...">
  Ver todos →
</Link>
```

### `frontend/src/pages/DocumentsPage.tsx`

- Nuevo estado `downloadedFrom`/`downloadedTo` (mismo patrón que `fPublicFrom`/`fPublicTo`), con su propio popover "Agregado" al lado del de "Fecha de publicación" (mismo componente visual: botón + Desde/Hasta + "Limpiar" condicional).
- Al montar, vía `useLocation()`:

```typescript
const location = useLocation();
const [downloadedFrom, setDownloadedFrom] = useState(
  () => (location.state as { downloadedToday?: boolean } | null)?.downloadedToday ? todayDateString() : ""
);
const [downloadedTo, setDownloadedTo] = useState(
  () => (location.state as { downloadedToday?: boolean } | null)?.downloadedToday ? todayDateString() : ""
);
```

Una vez montado, este estado es independiente del `location.state` — el usuario lo ajusta o limpia libremente como cualquier otro filtro de la página, sin ningún comportamiento especial de "modo bloqueado".
- `documentsQuery` incluye `downloaded_from`/`downloaded_to` tanto en el `queryKey` como en los parámetros de `fetchDocuments`.

## Testing

- **Backend** (`tests/test_repository.py`, `tests/test_api_documents.py`): casos análogos a los que ya existen para `f_public_from/to` — documento dentro del rango aparece, fuera del rango no aparece, límites inclusive/exclusive del rango de un día.
- **Frontend** (`DashboardPage.test.tsx`): actualizar `mockDocuments()` para verificar que la query de Novedades ahora manda `downloaded_from`/`downloaded_to` (no solo `limit=8`); actualizar el mensaje de `EmptyState` esperado en el caso de lista vacía.
- **Frontend** (`DocumentsPage.test.tsx`): nuevo caso — renderizar con `location.state={{ downloadedToday: true }}` (vía `initialEntries`/`initialIndex` de `MemoryRouter`, o envolviendo con un componente que haga `navigate(..., { state })`) y verificar que el filtro "Agregado" arranca en la fecha de hoy y que la request incluye `downloaded_from`/`downloaded_to`.
