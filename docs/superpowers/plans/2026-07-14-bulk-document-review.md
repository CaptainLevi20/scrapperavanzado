# Marcado en lote de documentos (útil/no útil) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir seleccionar varios documentos en `DocumentsPage` y marcarlos todos como "útil" o "no útil" con una sola acción, en vez de uno por uno.

**Architecture:** Un nuevo endpoint `PATCH /documents/bulk-review` (respaldado por un único `UPDATE ... WHERE id IN (...)`, no un loop) recibe una lista de ids + el estado deseado. El frontend agrega una columna de checkboxes a `DocumentsPage`, una barra de acción que aparece con la selección activa, y una mutation que llama al endpoint nuevo. La selección vive solo en memoria del componente y se resetea al cambiar de filtro o de página.

**Tech Stack:** FastAPI + SQLAlchemy Core + pytest (backend), React + TanStack Query + Vitest/Testing Library + MSW (frontend).

## Global Constraints

- Valores válidos de `review_status`: exactamente `"pending"`, `"useful"`, `"not_useful"` (ya establecido por la feature de revisión individual, sin cambios).
- **Orden de rutas en `api/routers/documents.py` es obligatorio, no estilístico**: la nueva ruta `PATCH /documents/bulk-review` DEBE registrarse (con su decorador `@router.patch(...)`) ANTES de la ruta existente `PATCH /documents/{document_id}`. FastAPI/Starlette hace matching de rutas en el orden en que se registran; si `{document_id}` se registrara primero, una petición a `/documents/bulk-review` matchearía esa ruta con `document_id="bulk-review"`, fallaría la validación de `int` y jamás llegaría al handler de lote.
- `document_ids` en el body debe rechazar listas vacías con 422 automático (Pydantic `Field(min_length=1)`), no un chequeo manual en el handler.
- La selección de la UI se resetea (no persiste) al cambiar cualquier filtro o de página — mismo patrón ya usado para resetear `page` a `0` en cada `onChange`, sin introducir un `useEffect` nuevo.
- No se agrega un tercer botón de lote para revertir a `"pending"`, ni una opción de "seleccionar todos los N resultados del filtro" más allá de la página actual — fuera de alcance según el spec (`docs/superpowers/specs/2026-07-14-bulk-document-review-design.md`).

---

### Task 1: Backend — endpoint y función de marcado en lote

**Files:**
- Modify: `core/db/repository.py` (agregar `bulk_update_document_review_status`, junto a `update_document_review_status`)
- Modify: `api/schemas.py` (agregar `BulkDocumentReviewUpdate`, junto a `DocumentReviewUpdate`)
- Modify: `api/routers/documents.py` (agregar `PATCH /documents/bulk-review`, **antes** de `PATCH /documents/{document_id}`)
- Test: `tests/test_repository.py`, `tests/test_api_documents.py`

**Interfaces:**
- Consumes: `Document` model, `db.execute`/`db.commit` (ya usados en el archivo).
- Produces: `repository.bulk_update_document_review_status(db: Session, document_ids: list[int], review_status: str) -> int` (devuelve la cantidad de filas actualizadas); `BulkDocumentReviewUpdate` (`document_ids: list[int]` con mínimo 1 elemento, `review_status: Literal["pending", "useful", "not_useful"]`); endpoint `PATCH /documents/bulk-review` que devuelve `{"updated": N}`.

- [ ] **Step 1: Escribir los tests de repositorio que fallan**

Agregar al final de `tests/test_repository.py`:

```python
def test_bulk_update_document_review_status_updates_matching_rows(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    doc1 = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Uno",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    doc2 = repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="Dos",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    doc3 = repository.insert_document(
        db_session, doc_id="doc-3", source_id=source.id, title="Tres",
        storage_bucket="iurisync-test", storage_key="c.pdf",
    )

    updated_count = repository.bulk_update_document_review_status(db_session, [doc1.id, doc2.id], "useful")

    assert updated_count == 2
    db_session.refresh(doc1)
    db_session.refresh(doc2)
    db_session.refresh(doc3)
    assert doc1.review_status == "useful"
    assert doc1.reviewed_at is not None
    assert doc2.review_status == "useful"
    assert doc3.review_status == "pending"


def test_bulk_update_document_review_status_ignores_nonexistent_ids(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    doc1 = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Uno",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )

    updated_count = repository.bulk_update_document_review_status(db_session, [doc1.id, 999999], "not_useful")

    assert updated_count == 1
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv\Scripts\pytest tests/test_repository.py -v`
Expected: los 2 tests nuevos FAIL con `AttributeError: module 'core.db.repository' has no attribute 'bulk_update_document_review_status'`.

- [ ] **Step 3: Implementar `bulk_update_document_review_status`**

En `core/db/repository.py`, cambiar la primera línea de import de sqlalchemy de:

```python
from sqlalchemy import select
```

a:

```python
from sqlalchemy import select, update
```

Y agregar esta función justo después de `update_document_review_status` (antes de `get_document`):

```python
def bulk_update_document_review_status(db: Session, document_ids: list[int], review_status: str) -> int:
    stmt = (
        update(Document)
        .where(Document.id.in_(document_ids))
        .values(review_status=review_status, reviewed_at=datetime.now(timezone.utc))
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount
```

- [ ] **Step 4: Confirmar que los tests de repositorio pasan**

Run: `.venv\Scripts\pytest tests/test_repository.py -v`
Expected: todos los tests PASS, incluyendo los 2 nuevos.

- [ ] **Step 5: Escribir los tests de API que fallan**

Agregar al final de `tests/test_api_documents.py`:

```python
def test_bulk_patch_document_review_status_updates_multiple(api_client, api_key_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    doc1 = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Uno",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    doc2 = repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="Dos",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.patch(
        "/documents/bulk-review",
        json={"document_ids": [doc1.id, doc2.id], "review_status": "useful"},
        headers=api_key_header,
    )

    assert response.status_code == 200
    assert response.json() == {"updated": 2}


def test_bulk_patch_document_review_status_rejects_empty_list(api_client, api_key_header):
    response = api_client.patch(
        "/documents/bulk-review",
        json={"document_ids": [], "review_status": "useful"},
        headers=api_key_header,
    )

    assert response.status_code == 422


def test_bulk_patch_document_review_status_rejects_invalid_value(api_client, api_key_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    doc1 = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Uno",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )

    response = api_client.patch(
        "/documents/bulk-review",
        json={"document_ids": [doc1.id], "review_status": "maybe"},
        headers=api_key_header,
    )

    assert response.status_code == 422


def test_bulk_patch_document_review_status_does_not_collide_with_single_patch_route(api_client, api_key_header, db_session):
    # Regresión del orden de rutas: /documents/bulk-review no debe ser
    # capturada por /documents/{document_id} (que intentaría parsear
    # "bulk-review" como int y fallaría con un 422 distinto/incorrecto).
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    doc1 = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Uno",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )

    response = api_client.patch(
        "/documents/bulk-review",
        json={"document_ids": [doc1.id], "review_status": "useful"},
        headers=api_key_header,
    )

    assert response.status_code == 200
    assert response.json() == {"updated": 1}
```

- [ ] **Step 6: Confirmar que fallan**

Run: `.venv\Scripts\pytest tests/test_api_documents.py -v`
Expected: los 4 tests nuevos FAIL. Nota: como la ruta `/documents/{document_id}` ya existe, Starlette la matchea contra `/documents/bulk-review` tratando `"bulk-review"` como el valor de `document_id`, y FastAPI la rechaza por no ser un `int` válido — así que **todas** las peticiones a `/documents/bulk-review` devuelven 422 en este punto, incluso `test_bulk_patch_document_review_status_updates_multiple` (que espera 200). Es un 422 por la razón equivocada (path param inválido, no el body de bulk-review), pero de todas formas confirma que el endpoint real todavía no existe. Esto se corrige por completo recién en el Step 8, y la prueba de regresión del Step 5 (`test_bulk_patch_document_review_status_does_not_collide_with_single_patch_route`) es la que verifica explícitamente que, una vez implementado, se llega al handler correcto.

- [ ] **Step 7: Agregar `BulkDocumentReviewUpdate`**

En `api/schemas.py`, cambiar la línea de import de pydantic de:

```python
from pydantic import BaseModel, ConfigDict
```

a:

```python
from pydantic import BaseModel, ConfigDict, Field
```

Y agregar esta clase justo después de `DocumentReviewUpdate`:

```python
class BulkDocumentReviewUpdate(BaseModel):
    document_ids: list[int] = Field(min_length=1)
    review_status: Literal["pending", "useful", "not_useful"]
```

- [ ] **Step 8: Agregar el endpoint, respetando el orden de rutas**

En `api/routers/documents.py`, cambiar el import de:

```python
from api.schemas import DocumentOut, DocumentReviewUpdate, PaginatedDocuments
```

a:

```python
from api.schemas import BulkDocumentReviewUpdate, DocumentOut, DocumentReviewUpdate, PaginatedDocuments
```

Y agregar este endpoint nuevo **inmediatamente antes** de `patch_document_review_status` (el `PATCH /documents/{document_id}` existente) — el orden importa, ver Global Constraints:

```python
@router.patch("/documents/bulk-review")
def patch_bulk_document_review_status(payload: BulkDocumentReviewUpdate, db: Session = Depends(get_db)):
    updated = repository.bulk_update_document_review_status(db, payload.document_ids, payload.review_status)
    return {"updated": updated}
```

Después de este cambio, el archivo debe tener las rutas `PATCH` en este orden: `/documents/bulk-review` primero, `/documents/{document_id}` después.

- [ ] **Step 9: Confirmar que los tests de API pasan**

Run: `.venv\Scripts\pytest tests/test_api_documents.py -v`
Expected: todos los tests PASS, incluyendo los 4 nuevos.

- [ ] **Step 10: Correr toda la suite de backend**

Run: `.venv\Scripts\pytest -v`
Expected: mismo resultado que antes de este plan más los tests nuevos (1 falla preexistente no relacionada en `test_migrations.py`, el resto PASS).

- [ ] **Step 11: Commit**

```bash
git add core/db/repository.py api/schemas.py api/routers/documents.py tests/test_repository.py tests/test_api_documents.py
git commit -m "feat: add PATCH /documents/bulk-review endpoint for bulk document review marking"
```

---

### Task 2: Frontend — selección múltiple y barra de acción en lote

**Files:**
- Modify: `frontend/src/api/documents.ts` (nueva `bulkUpdateDocumentReviewStatus`)
- Modify: `frontend/src/pages/DocumentsPage.tsx` (columna de checkboxes, barra de acción, reseteo de selección)
- Modify: `frontend/src/pages/DocumentsPage.test.tsx`

**Interfaces:**
- Consumes: `PATCH /documents/bulk-review` (Task 1), devuelve `{"updated": number}`.
- Produces: nada consumido por otras tareas (última tarea del plan).

- [ ] **Step 1: Agregar la función de API**

En `frontend/src/api/documents.ts`, agregar esta función justo después de `updateDocumentReviewStatus`:

```typescript
export function bulkUpdateDocumentReviewStatus(
  documentIds: number[],
  review_status: DocumentReviewStatus
): Promise<{ updated: number }> {
  return apiFetch<{ updated: number }>("/documents/bulk-review", {
    method: "PATCH",
    body: JSON.stringify({ document_ids: documentIds, review_status }),
  });
}
```

- [ ] **Step 2: Escribir los tests que fallan**

En `frontend/src/pages/DocumentsPage.test.tsx`, agregar una segunda constante de documento justo después de la constante `DOCUMENT` existente:

```typescript
const DOCUMENT_2 = {
  ...DOCUMENT,
  id: 2,
  doc_id: "def",
  title: "Sentencia C-002-26",
};
```

Y agregar estos tests dentro del `describe("DocumentsPage", ...)`, después del test `"refetches with the source and family filters applied"`:

```typescript
  it("selects individual rows and shows the bulk action bar", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({ items: [DOCUMENT, DOCUMENT_2], total: 2, limit: 50, offset: 0 })
      )
    );
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Sentencia C-001-26");
    expect(screen.queryByText(/seleccionados/i)).not.toBeInTheDocument();

    await user.click(screen.getByLabelText('Seleccionar "Sentencia C-001-26"'));

    expect(await screen.findByText("1 seleccionados")).toBeInTheDocument();
  });

  it("selects and deselects all visible rows with the header checkbox", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({ items: [DOCUMENT, DOCUMENT_2], total: 2, limit: 50, offset: 0 })
      )
    );
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Sentencia C-001-26");
    const selectAll = screen.getByLabelText("Seleccionar todos los documentos visibles");

    await user.click(selectAll);
    expect(await screen.findByText("2 seleccionados")).toBeInTheDocument();

    await user.click(selectAll);
    expect(screen.queryByText(/seleccionados/i)).not.toBeInTheDocument();
  });

  it("marks the selected documents as useful in bulk and clears the selection", async () => {
    mockFilterEndpoints();
    const user = userEvent.setup();
    let bulkBody: unknown = null;
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({ items: [DOCUMENT, DOCUMENT_2], total: 2, limit: 50, offset: 0 })
      ),
      http.patch(`${BASE_URL}/documents/bulk-review`, async ({ request }) => {
        bulkBody = await request.json();
        return HttpResponse.json({ updated: 2 });
      })
    );
    renderPage();

    await screen.findByText("Sentencia C-001-26");
    await user.click(screen.getByLabelText("Seleccionar todos los documentos visibles"));
    await screen.findByText("2 seleccionados");

    await user.click(screen.getByText("Marcar como útil"));

    await waitFor(() => expect(bulkBody).toEqual({ document_ids: [1, 2], review_status: "useful" }));
    await waitFor(() => expect(screen.queryByText(/seleccionados/i)).not.toBeInTheDocument());
  });

  it("clears the selection when a filter changes", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({ items: [DOCUMENT, DOCUMENT_2], total: 2, limit: 50, offset: 0 })
      )
    );
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Sentencia C-001-26");
    await user.click(screen.getByLabelText('Seleccionar "Sentencia C-001-26"'));
    await screen.findByText("1 seleccionados");

    await user.type(screen.getByPlaceholderText(/buscar por t.tulo/i), "algo");

    await waitFor(() => expect(screen.queryByText(/seleccionados/i)).not.toBeInTheDocument());
  });
```

- [ ] **Step 3: Confirmar que fallan**

Run: `cd frontend && npm test -- --run`
Expected: FAIL — no existen los checkboxes de selección, la barra de acción ni la mutation de lote todavía.

- [ ] **Step 4: Implementar la selección y la barra de acción**

Reemplazar el contenido completo de `frontend/src/pages/DocumentsPage.tsx` por:

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  buildDownloadFilename,
  bulkUpdateDocumentReviewStatus,
  downloadDocumentFile,
  fetchDocuments,
  updateDocumentReviewStatus,
} from "../api/documents";
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
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

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

  const [bulkError, setBulkError] = useState<string | null>(null);
  const bulkReviewMutation = useMutation({
    mutationFn: ({ ids, status }: { ids: number[]; status: DocumentReviewStatus }) =>
      bulkUpdateDocumentReviewStatus(ids, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      setSelectedIds(new Set());
    },
    onError: () => setBulkError("Error al marcar los documentos seleccionados"),
  });

  function toggleSelected(id: number) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  const visibleIds = documentsQuery.data?.items.map((document) => document.id) ?? [];
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));

  function toggleSelectAll() {
    setSelectedIds((current) => {
      if (allVisibleSelected) {
        const next = new Set(current);
        visibleIds.forEach((id) => next.delete(id));
        return next;
      }
      return new Set([...current, ...visibleIds]);
    });
  }

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
            setSelectedIds(new Set());
          }}
          className="rounded border px-2 py-1"
        />
        <input
          placeholder="Tipo"
          value={tipo}
          onChange={(event) => {
            setTipo(event.target.value);
            setPage(0);
            setSelectedIds(new Set());
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
              setSelectedIds(new Set());
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
              setSelectedIds(new Set());
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
              setSelectedIds(new Set());
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
      {bulkError && <ErrorBanner message={bulkError} onRetry={() => setBulkError(null)} />}

      {selectedIds.size > 0 && (
        <div className="flex items-center gap-3 rounded border bg-gray-50 px-3 py-2">
          <span className="text-sm">{selectedIds.size} seleccionados</span>
          <button
            onClick={() => bulkReviewMutation.mutate({ ids: Array.from(selectedIds), status: "useful" })}
            className="rounded border px-2 py-1 text-xs"
          >
            Marcar como útil
          </button>
          <button
            onClick={() => bulkReviewMutation.mutate({ ids: Array.from(selectedIds), status: "not_useful" })}
            className="rounded border px-2 py-1 text-xs"
          >
            Marcar como no útil
          </button>
        </div>
      )}

      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b">
            <th className="py-2">
              <input
                type="checkbox"
                aria-label="Seleccionar todos los documentos visibles"
                checked={allVisibleSelected}
                onChange={toggleSelectAll}
              />
            </th>
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
              <td className="py-2">
                <input
                  type="checkbox"
                  aria-label={`Seleccionar "${document.title}"`}
                  checked={selectedIds.has(document.id)}
                  onChange={() => toggleSelected(document.id)}
                />
              </td>
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
                    aria-pressed={document.review_status === "useful"}
                    className={`rounded border px-2 py-1 text-xs ${
                      document.review_status === "useful" ? "bg-green-600 text-white" : ""
                    }`}
                  >
                    Útil
                  </button>
                  <button
                    onClick={() => reviewMutation.mutate({ id: document.id, status: "not_useful" })}
                    aria-label={`Marcar "${document.title}" como no útil`}
                    aria-pressed={document.review_status === "not_useful"}
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
            onClick={() => {
              setPage((current) => current - 1);
              setSelectedIds(new Set());
            }}
            className="rounded border px-3 py-1 disabled:opacity-50"
          >
            Anterior
          </button>
          <button
            disabled={(documentsQuery.data?.items.length ?? 0) < PAGE_SIZE}
            onClick={() => {
              setPage((current) => current + 1);
              setSelectedIds(new Set());
            }}
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
Expected: todos los tests PASS, incluyendo los 4 nuevos.

- [ ] **Step 6: Verificar que el build de TypeScript queda limpio**

Run: `cd frontend && npm run build`
Expected: sin errores de `tsc -b`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/documents.ts frontend/src/pages/DocumentsPage.tsx frontend/src/pages/DocumentsPage.test.tsx
git commit -m "feat: add multi-select and bulk útil/no útil marking to DocumentsPage"
```
