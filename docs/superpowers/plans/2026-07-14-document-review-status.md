# Estado de revisión de documentos (útil/no útil) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir marcar cada documento como "útil" o "no útil" desde la tabla de Documentos, y exponer en esa misma tabla las columnas que ya existen en la base (`especialidad`, `magistrado`, `detalle`, `source_url`) pero no se mostraban todavía.

**Architecture:** Dos columnas nuevas en `documents` (`review_status`, `reviewed_at`) vía una migración de Alembic; el filtro/actualización se expone a través del `GET /documents` existente (nuevo parámetro `review_status`) y un nuevo `PATCH /documents/{id}`; el frontend agrega columnas, dos botones por fila y un filtro más a `DocumentsPage`. No se toca el pipeline de scraping/descarga ni el dedup por `doc_id`.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + pytest (backend), React + TanStack Query + Vitest/Testing Library + MSW (frontend).

## Global Constraints

- Valores válidos de `review_status`: exactamente `"pending"`, `"useful"`, `"not_useful"` (sin mayúsculas, sin otros valores).
- La migración nueva debe encadenar (`down_revision`) desde `4bffcba11b73` (la única migración existente); se crea con `alembic revision -m "..."` (sin `--autogenerate`) y su contenido se escribe a mano según este plan.
- La columna `review_status` es `NOT NULL` con default `"pending"` tanto a nivel de modelo (`Column(default=...)`, para inserts vía ORM/Core) como a nivel de base de datos (`server_default=...` en la migración, porque la tabla `documents` ya tiene filas en despliegues reales y un `ALTER TABLE ... NOT NULL` sin default fallaría).
- No se toca `worker/tasks.py`, `core/downloader.py`, ni la lógica de dedup por `doc_id` (`repository.document_exists`) — el estado de revisión es puramente informativo.
- No se agrega tabla nueva, botón para revertir a `"pending"` desde la UI, ni marcado en lote — fuera de alcance según el spec (`docs/superpowers/specs/2026-07-14-document-review-status-design.md`).

---

### Task 1: Columnas de revisión — modelo, migración y repositorio

**Files:**
- Modify: `core/db/models.py:81-103` (clase `Document`)
- Modify: `core/db/repository.py:166-193` (`list_documents`) y agregar función nueva junto a ella
- Create: `alembic/versions/<revision_id>_add_document_review_status.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Produces: `Document.review_status: str` (default `"pending"`), `Document.reviewed_at: Optional[datetime]`; `repository.list_documents(db, ..., review_status: Optional[str] = None, ...)`; `repository.update_document_review_status(db: Session, document_id: int, review_status: str) -> Optional[Document]`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_repository.py`:

```python
def test_update_document_review_status_sets_status_and_timestamp(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-review-1",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.rtf",
    )

    assert document.review_status == "pending"
    assert document.reviewed_at is None

    updated = repository.update_document_review_status(db_session, document.id, "useful")

    assert updated is not None
    assert updated.review_status == "useful"
    assert updated.reviewed_at is not None


def test_update_document_review_status_returns_none_when_missing(db_session):
    from core.db import repository

    assert repository.update_document_review_status(db_session, 999999, "useful") is None


def test_list_documents_filters_by_review_status(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    useful_doc = repository.insert_document(
        db_session,
        doc_id="doc-useful",
        source_id=source.id,
        title="Útil",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )
    repository.insert_document(
        db_session,
        doc_id="doc-pending",
        source_id=source.id,
        title="Pendiente",
        storage_bucket="iurisync-test",
        storage_key="b.pdf",
    )
    repository.update_document_review_status(db_session, useful_doc.id, "useful")

    items, total = repository.list_documents(db_session, review_status="useful")

    assert total == 1
    assert items[0].doc_id == "doc-useful"
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv\Scripts\pytest tests/test_repository.py -v`
Expected: los 3 tests nuevos FAIL — los dos primeros con `AttributeError: module 'core.db.repository' has no attribute 'update_document_review_status'`, y `test_list_documents_filters_by_review_status` con `TypeError: list_documents() got an unexpected keyword argument 'review_status'`.

- [ ] **Step 3: Agregar las columnas al modelo**

En `core/db/models.py`, dentro de la clase `Document`, agregar estas dos líneas al final (después de `downloaded_at`):

```python
    downloaded_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    review_status = Column(String, nullable=False, default="pending")
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Extender `list_documents` y agregar `update_document_review_status`**

En `core/db/repository.py`, reemplazar la firma y el cuerpo de `list_documents` por:

```python
def list_documents(
    db: Session,
    source_id: Optional[int] = None,
    family_key: Optional[str] = None,
    tipo: Optional[str] = None,
    review_status: Optional[str] = None,
    f_public_from: Optional[date] = None,
    f_public_to: Optional[date] = None,
    title_contains: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Document], int]:
    stmt = select(Document)
    if source_id is not None:
        stmt = stmt.where(Document.source_id == source_id)
    if family_key is not None:
        stmt = stmt.join(Source, Source.id == Document.source_id).where(Source.family_key == family_key)
    if tipo is not None:
        stmt = stmt.where(Document.tipo == tipo)
    if review_status is not None:
        stmt = stmt.where(Document.review_status == review_status)
    if f_public_from is not None:
        stmt = stmt.where(Document.f_public >= f_public_from)
    if f_public_to is not None:
        stmt = stmt.where(Document.f_public <= f_public_to)
    if title_contains is not None:
        stmt = stmt.where(Document.title.ilike(f"%{title_contains}%"))

    total = len(list(db.scalars(stmt).all()))
    stmt = stmt.order_by(Document.downloaded_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all()), total
```

Y agregar esta función nueva justo después (antes de `get_document` si existe, o al final del archivo):

```python
def update_document_review_status(db: Session, document_id: int, review_status: str) -> Optional[Document]:
    document = db.get(Document, document_id)
    if document is None:
        return None
    document.review_status = review_status
    document.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(document)
    return document
```

(`datetime` y `timezone` ya están importados en la primera línea del archivo: `from datetime import date, datetime, timezone`.)

- [ ] **Step 5: Confirmar que los tests de repositorio pasan**

Run: `.venv\Scripts\pytest tests/test_repository.py -v`
Expected: todos los tests PASS, incluyendo los 3 nuevos.

- [ ] **Step 6: Crear y completar la migración de Alembic**

Run: `.venv\Scripts\alembic revision -m "add document review status"`

Esto crea un archivo en `alembic/versions/<hash>_add_document_review_status.py` con `down_revision` ya apuntando a `4bffcba11b73` (la migración actual). Reemplazar el cuerpo de `upgrade()` y `downgrade()` por:

```python
def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('review_status', sa.String(), nullable=False, server_default='pending'))
    op.add_column('documents', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'reviewed_at')
    op.drop_column('documents', 'review_status')
```

- [ ] **Step 7: Aplicar la migración contra la base local y verificar**

Run: `.venv\Scripts\alembic upgrade head`
Expected: sin errores; termina en la nueva revisión.

Run: `docker compose exec postgres psql -U iurisync -d iurisync -c "\d documents"`
Expected: la tabla muestra las columnas `review_status` y `reviewed_at`.

- [ ] **Step 8: Commit**

```bash
git add core/db/models.py core/db/repository.py tests/test_repository.py alembic/versions/*_add_document_review_status.py
git commit -m "feat: add review_status/reviewed_at columns and repository support for document review"
```

---

### Task 2: Endpoints de la API — filtro y marcado

**Files:**
- Modify: `api/schemas.py` (`DocumentOut`, nuevo `DocumentReviewUpdate`)
- Modify: `api/routers/documents.py` (parámetro `review_status` en `GET /documents`, nuevo `PATCH /documents/{document_id}`)
- Test: `tests/test_api_documents.py`

**Interfaces:**
- Consumes: `repository.list_documents(db, ..., review_status=...)`, `repository.update_document_review_status(db, document_id, review_status)` (Task 1).
- Produces: `DocumentOut` con `especialidad`, `magistrado`, `detalle`, `source_url`, `review_status`, `reviewed_at`; `DocumentReviewUpdate` (`review_status: Literal["pending", "useful", "not_useful"]`); endpoint `PATCH /documents/{document_id}`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_api_documents.py`:

```python
def test_list_documents_filters_by_review_status(api_client, api_key_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    useful_doc = repository.insert_document(
        db_session,
        doc_id="doc-useful",
        source_id=source.id,
        title="Útil",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )
    repository.insert_document(
        db_session,
        doc_id="doc-pending",
        source_id=source.id,
        title="Pendiente",
        storage_bucket="iurisync-test",
        storage_key="b.pdf",
    )
    repository.update_document_review_status(db_session, useful_doc.id, "useful")

    response = api_client.get("/documents", params={"review_status": "useful"}, headers=api_key_header)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-useful"
    assert body["items"][0]["review_status"] == "useful"


def test_patch_document_review_status_updates_and_returns_document(api_client, api_key_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    response = api_client.patch(
        f"/documents/{document.id}", json={"review_status": "not_useful"}, headers=api_key_header
    )

    assert response.status_code == 200
    body = response.json()
    assert body["review_status"] == "not_useful"
    assert body["reviewed_at"] is not None


def test_patch_document_review_status_returns_404_when_missing(api_client, api_key_header):
    response = api_client.patch("/documents/999999", json={"review_status": "useful"}, headers=api_key_header)
    assert response.status_code == 404


def test_patch_document_review_status_rejects_invalid_value(api_client, api_key_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    response = api_client.patch(
        f"/documents/{document.id}", json={"review_status": "maybe"}, headers=api_key_header
    )

    assert response.status_code == 422
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv\Scripts\pytest tests/test_api_documents.py -v`
Expected: los 4 tests nuevos FAIL (`test_list_documents_filters_by_review_status` con `AssertionError` porque el filtro se ignora; los otros 3 con `405 Method Not Allowed` porque `PATCH /documents/{id}` no existe todavía — el path ya existe para `GET`, pero no para `PATCH`).

- [ ] **Step 3: Extender `DocumentOut` y agregar `DocumentReviewUpdate`**

En `api/schemas.py`, cambiar la primera línea de:

```python
from typing import Optional
```

a:

```python
from typing import Literal, Optional
```

Y reemplazar la clase `DocumentOut` completa por:

```python
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    doc_id: str
    source_id: int
    title: str
    tipo: Optional[str] = None
    seccion: Optional[str] = None
    especialidad: Optional[str] = None
    magistrado: Optional[str] = None
    detalle: Optional[str] = None
    f_public: Optional[date] = None
    f_providencia: Optional[date] = None
    source_url: Optional[str] = None
    storage_bucket: str
    storage_key: str
    content_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    review_status: str
    reviewed_at: Optional[datetime] = None
    downloaded_at: datetime


class DocumentReviewUpdate(BaseModel):
    review_status: Literal["pending", "useful", "not_useful"]
```

- [ ] **Step 4: Agregar el parámetro `review_status` y el endpoint PATCH**

En `api/routers/documents.py`, cambiar el import de:

```python
from api.schemas import DocumentOut, PaginatedDocuments
```

a:

```python
from api.schemas import DocumentOut, DocumentReviewUpdate, PaginatedDocuments
```

Reemplazar `get_documents` por:

```python
@router.get("/documents", response_model=PaginatedDocuments)
def get_documents(
    source_id: Optional[int] = None,
    family_key: Optional[str] = None,
    tipo: Optional[str] = None,
    title: Optional[str] = None,
    review_status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    items, total = repository.list_documents(
        db,
        source_id=source_id,
        family_key=family_key,
        tipo=tipo,
        review_status=review_status,
        title_contains=title,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}
```

Y agregar este endpoint nuevo justo después de `get_document`:

```python
@router.patch("/documents/{document_id}", response_model=DocumentOut)
def patch_document_review_status(document_id: int, payload: DocumentReviewUpdate, db: Session = Depends(get_db)):
    document = repository.update_document_review_status(db, document_id, payload.review_status)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return document
```

- [ ] **Step 5: Confirmar que los tests pasan**

Run: `.venv\Scripts\pytest tests/test_api_documents.py -v`
Expected: todos los tests PASS, incluyendo los 4 nuevos.

- [ ] **Step 6: Correr toda la suite de backend**

Run: `.venv\Scripts\pytest -v`
Expected: mismo resultado que antes de este plan más los tests nuevos (1 falla preexistente no relacionada en `test_migrations.py`, el resto PASS).

- [ ] **Step 7: Commit**

```bash
git add api/schemas.py api/routers/documents.py tests/test_api_documents.py
git commit -m "feat: expose review_status filter, richer document fields, and PATCH /documents/{id}"
```

---

### Task 3: Frontend — columnas, marcado útil/no útil y filtro

**Files:**
- Modify: `frontend/src/api/types.ts` (interfaz `Document`, nuevo tipo `DocumentReviewStatus`)
- Modify: `frontend/src/api/documents.ts` (`ListDocumentsParams`, nueva `updateDocumentReviewStatus`)
- Modify: `frontend/src/pages/DocumentsPage.tsx`
- Modify: `frontend/src/pages/DocumentsPage.test.tsx`

**Interfaces:**
- Consumes: `GET /documents?review_status=...` y `PATCH /documents/{id}` (Task 2).
- Produces: nada consumido por otras tareas (última tarea del plan).

- [ ] **Step 1: Actualizar tipos y cliente de API**

En `frontend/src/api/types.ts`, agregar antes de la interfaz `Document` (o donde estén los demás tipos de union, junto a `RunStatus`):

```typescript
export type DocumentReviewStatus = "pending" | "useful" | "not_useful";
```

Y reemplazar la interfaz `Document` completa por:

```typescript
export interface Document {
  id: number;
  doc_id: string;
  source_id: number;
  title: string;
  tipo: string | null;
  seccion: string | null;
  especialidad: string | null;
  magistrado: string | null;
  detalle: string | null;
  f_public: string | null;
  f_providencia: string | null;
  source_url: string | null;
  storage_bucket: string;
  storage_key: string;
  content_type: string | null;
  file_size_bytes: number | null;
  review_status: DocumentReviewStatus;
  reviewed_at: string | null;
  downloaded_at: string;
}
```

En `frontend/src/api/documents.ts`, cambiar el import de:

```typescript
import type { Document, PaginatedDocuments } from "./types";
```

a:

```typescript
import type { Document, DocumentReviewStatus, PaginatedDocuments } from "./types";
```

Reemplazar `ListDocumentsParams` por:

```typescript
export interface ListDocumentsParams {
  source_id?: number;
  family_key?: string;
  tipo?: string;
  title?: string;
  review_status?: DocumentReviewStatus;
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}
```

Y agregar esta función nueva justo después de `fetchDocument`:

```typescript
export function updateDocumentReviewStatus(id: number, review_status: DocumentReviewStatus): Promise<Document> {
  return apiFetch<Document>(`/documents/${id}`, { method: "PATCH", body: JSON.stringify({ review_status }) });
}
```

- [ ] **Step 2: Actualizar el fixture de test y escribir los tests que fallan**

En `frontend/src/pages/DocumentsPage.test.tsx`, reemplazar la constante `DOCUMENT` por:

```typescript
const DOCUMENT = {
  id: 1,
  doc_id: "abc",
  source_id: 1,
  title: "Sentencia C-001-26",
  tipo: "sentencia",
  seccion: null,
  especialidad: null,
  magistrado: null,
  detalle: null,
  f_public: null,
  f_providencia: "2026-01-15",
  source_url: null,
  storage_bucket: "iurisync-documents",
  storage_key: "abc.pdf",
  content_type: "application/pdf",
  file_size_bytes: 204800,
  review_status: "pending",
  reviewed_at: null,
  downloaded_at: "2026-07-10T00:00:00Z",
};
```

Y agregar estos tests dentro del bloque `describe("DocumentsPage", ...)`, después del test `"renders the Sección column"`:

```typescript
  it("renders the Especialidad and Magistrado columns", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({
          items: [{ ...DOCUMENT, especialidad: "Civil", magistrado: "Juan Pérez" }],
          total: 1,
          limit: 50,
          offset: 0,
        })
      )
    );

    renderPage();

    expect(await screen.findByText("Civil")).toBeInTheDocument();
    expect(screen.getByText("Juan Pérez")).toBeInTheDocument();
  });

  it("shows detalle as a tooltip on the title and a link to source_url when present", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({
          items: [{ ...DOCUMENT, detalle: "Resumen del fallo", source_url: "https://example.com/original" }],
          total: 1,
          limit: 50,
          offset: 0,
        })
      )
    );

    renderPage();

    expect(await screen.findByTitle("Resumen del fallo")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /ver original/i });
    expect(link).toHaveAttribute("href", "https://example.com/original");
  });

  it("does not render a 'Ver original' link when source_url is null", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 }))
    );

    renderPage();

    await screen.findByText("Sentencia C-001-26");
    expect(screen.queryByRole("link", { name: /ver original/i })).not.toBeInTheDocument();
  });

  it("marks a document as useful and refetches the list", async () => {
    mockFilterEndpoints();
    const user = userEvent.setup();
    let patchBody: unknown = null;
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 })),
      http.patch(`${BASE_URL}/documents/1`, async ({ request }) => {
        patchBody = await request.json();
        return HttpResponse.json({ ...DOCUMENT, review_status: "useful" });
      })
    );
    renderPage();

    await user.click(await screen.findByLabelText(/marcar .* como útil/i));

    await waitFor(() => expect(patchBody).toEqual({ review_status: "useful" }));
  });

  it("refetches with the review status filter applied", async () => {
    mockFilterEndpoints();
    let lastUrl = "";
    server.use(
      http.get(`${BASE_URL}/documents`, ({ request }) => {
        lastUrl = request.url;
        return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
      })
    );
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(lastUrl).toContain("/documents"));
    await user.selectOptions(screen.getByLabelText("Revisión"), "useful");

    await waitFor(() => expect(lastUrl).toContain("review_status=useful"));
  });
```

- [ ] **Step 3: Confirmar que fallan**

Run: `cd frontend && npm test -- --run`
Expected: FAIL — `tsc`/vitest reportan que faltan las columnas Especialidad/Magistrado, el enlace "Ver original", los botones de marcado y el filtro de Revisión (no existen en el DOM todavía).

- [ ] **Step 4: Implementar `DocumentsPage.tsx`**

Reemplazar el contenido completo de `frontend/src/pages/DocumentsPage.tsx` por:

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { buildDownloadFilename, downloadDocumentFile, fetchDocuments, updateDocumentReviewStatus } from "../api/documents";
import { fetchSourceFamilies } from "../api/sourceFamilies";
import { fetchAllActiveSources } from "../api/sources";
import type { DocumentReviewStatus } from "../api/types";
import { ErrorBanner } from "../components/ErrorBanner";
import { formatBytes, formatDate } from "../lib/formatters";

const PAGE_SIZE = 50;

export function DocumentsPage() {
  const [title, setTitle] = useState("");
  const [tipo, setTipo] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [familyKey, setFamilyKey] = useState("");
  const [reviewStatus, setReviewStatus] = useState<DocumentReviewStatus | "">("");
  const [page, setPage] = useState(0);

  const queryClient = useQueryClient();

  const sourcesQuery = useQuery({
    queryKey: ["sources", "for-documents-filter"],
    queryFn: fetchAllActiveSources,
  });

  const familiesQuery = useQuery({ queryKey: ["source-families"], queryFn: fetchSourceFamilies });

  const documentsQuery = useQuery({
    queryKey: ["documents", title, tipo, sourceId, familyKey, reviewStatus, page],
    queryFn: () =>
      fetchDocuments({
        title: title || undefined,
        tipo: tipo || undefined,
        source_id: sourceId ? Number(sourceId) : undefined,
        family_key: familyKey || undefined,
        review_status: reviewStatus || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  });

  const [downloadError, setDownloadError] = useState<string | null>(null);
  const downloadMutation = useMutation({
    mutationFn: ({ id, filename }: { id: number; filename: string }) => downloadDocumentFile(id, filename),
    onError: () => setDownloadError("Error al descargar el documento"),
  });

  const [reviewError, setReviewError] = useState<string | null>(null);
  const reviewMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: DocumentReviewStatus }) => updateDocumentReviewStatus(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents"] }),
    onError: () => setReviewError("Error al marcar el documento"),
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Documentos</h1>

      <div className="flex gap-3">
        <input
          placeholder="Buscar por título"
          value={title}
          onChange={(event) => {
            setTitle(event.target.value);
            setPage(0);
          }}
          className="rounded border px-2 py-1"
        />
        <input
          placeholder="Tipo"
          value={tipo}
          onChange={(event) => {
            setTipo(event.target.value);
            setPage(0);
          }}
          className="rounded border px-2 py-1"
        />
        <label className="flex items-center gap-2 text-sm">
          Fuente
          <select
            value={sourceId}
            onChange={(event) => {
              setSourceId(event.target.value);
              setPage(0);
            }}
            className="rounded border px-2 py-1"
          >
            <option value="">Todas</option>
            {sourcesQuery.data?.map((source) => (
              <option key={source.id} value={String(source.id)}>
                {source.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          Familia
          <select
            value={familyKey}
            onChange={(event) => {
              setFamilyKey(event.target.value);
              setPage(0);
            }}
            className="rounded border px-2 py-1"
          >
            <option value="">Todas</option>
            {familiesQuery.data?.map((family) => (
              <option key={family.key} value={family.key}>
                {family.display_name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          Revisión
          <select
            value={reviewStatus}
            onChange={(event) => {
              setReviewStatus(event.target.value as DocumentReviewStatus | "");
              setPage(0);
            }}
            className="rounded border px-2 py-1"
          >
            <option value="">Todos</option>
            <option value="pending">Sin revisar</option>
            <option value="useful">Útil</option>
            <option value="not_useful">No útil</option>
          </select>
        </label>
      </div>

      {documentsQuery.isError && (
        <ErrorBanner message="No se pudieron cargar los documentos." onRetry={() => documentsQuery.refetch()} />
      )}
      {downloadError && <ErrorBanner message={downloadError} onRetry={() => setDownloadError(null)} />}
      {reviewError && <ErrorBanner message={reviewError} onRetry={() => setReviewError(null)} />}

      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b">
            <th className="py-2">Título</th>
            <th className="py-2">Tipo</th>
            <th className="py-2">Sección</th>
            <th className="py-2">Especialidad</th>
            <th className="py-2">Magistrado</th>
            <th className="py-2">Fecha providencia</th>
            <th className="py-2">Tamaño</th>
            <th className="py-2">Revisión</th>
            <th className="py-2">Descargar</th>
          </tr>
        </thead>
        <tbody>
          {documentsQuery.data?.items.map((document) => (
            <tr key={document.id} className="border-b">
              <td className="py-2" title={document.detalle ?? undefined}>
                {document.title}
                {document.source_url && (
                  <a
                    href={document.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-2 text-xs text-blue-600 underline"
                  >
                    Ver original ↗
                  </a>
                )}
              </td>
              <td className="py-2">{document.tipo ?? "—"}</td>
              <td className="py-2">{document.seccion ?? "—"}</td>
              <td className="py-2">{document.especialidad ?? "—"}</td>
              <td className="py-2">{document.magistrado ?? "—"}</td>
              <td className="py-2">{formatDate(document.f_providencia)}</td>
              <td className="py-2">{formatBytes(document.file_size_bytes)}</td>
              <td className="py-2">
                <div className="flex gap-1">
                  <button
                    onClick={() => reviewMutation.mutate({ id: document.id, status: "useful" })}
                    aria-label={`Marcar "${document.title}" como útil`}
                    className={`rounded border px-2 py-1 text-xs ${
                      document.review_status === "useful" ? "bg-green-600 text-white" : ""
                    }`}
                  >
                    Útil
                  </button>
                  <button
                    onClick={() => reviewMutation.mutate({ id: document.id, status: "not_useful" })}
                    aria-label={`Marcar "${document.title}" como no útil`}
                    className={`rounded border px-2 py-1 text-xs ${
                      document.review_status === "not_useful" ? "bg-red-600 text-white" : ""
                    }`}
                  >
                    No útil
                  </button>
                </div>
              </td>
              <td className="py-2">
                <button
                  onClick={() => downloadMutation.mutate({ id: document.id, filename: buildDownloadFilename(document) })}
                  className="text-sm text-blue-600 underline"
                >
                  Descargar
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">Total: {documentsQuery.data?.total ?? 0}</p>
        <div className="flex gap-2">
          <button
            disabled={page === 0}
            onClick={() => setPage((current) => current - 1)}
            className="rounded border px-3 py-1 disabled:opacity-50"
          >
            Anterior
          </button>
          <button
            disabled={(documentsQuery.data?.items.length ?? 0) < PAGE_SIZE}
            onClick={() => setPage((current) => current + 1)}
            className="rounded border px-3 py-1 disabled:opacity-50"
          >
            Siguiente
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Confirmar que los tests pasan**

Run: `cd frontend && npm test -- --run`
Expected: todos los tests PASS, incluyendo los 5 nuevos.

- [ ] **Step 6: Verificar que el build de TypeScript queda limpio**

Run: `cd frontend && npm run build`
Expected: sin errores de `tsc -b` (todos los usos de `Document`/`DocumentReviewStatus` son consistentes con los tipos nuevos).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/documents.ts frontend/src/pages/DocumentsPage.tsx frontend/src/pages/DocumentsPage.test.tsx
git commit -m "feat: show especialidad/magistrado/source_url and add útil/no útil marking to DocumentsPage"
```
