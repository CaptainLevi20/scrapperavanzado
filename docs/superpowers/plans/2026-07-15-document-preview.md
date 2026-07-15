# Previsualizador de documentos — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar un botón "Previsualizar" por documento en `DocumentsPage` que abre un modal con el archivo renderizado inline (PDF nativo del navegador) junto con los botones Útil/No útil, Anterior y Siguiente, para revisar y marcar documentos sin salir de la página.

**Architecture:** Cambio puramente de frontend. Se extrae la lógica de fetch-con-token que ya usa `downloadDocumentFile` a una función reutilizable (`fetchDocumentBlob`), se construye un componente de modal (`DocumentPreviewDialog`) que la consume para mostrar el PDF en un `<iframe>` (o un fallback de descarga para tipos no soportados), y se conecta desde `DocumentsPage` con un botón nuevo por fila.

**Tech Stack:** React + TypeScript, TanStack Query (`useQuery`/`useMutation`), Radix Dialog (vía los componentes ya existentes en `components/ui/dialog.tsx`), Vitest + Testing Library + MSW.

## Global Constraints

- Sin cambios de backend — se reutiliza el endpoint `/documents/{id}/download` existente (autenticado, redirige a una URL firmada de MinIO).
- La previsualización inline solo aplica cuando `content_type === "application/pdf"`. Cualquier otro tipo (Word, RTF, etc.) muestra el mensaje "Vista previa no disponible para este tipo de archivo." con un botón de descarga, sin intentar cargar el blob.
- Marcar Útil o No útil avanza automáticamente al siguiente documento de la lista que se le pasó al modal; si es el último, el modal se cierra. Si la mutación de marcado falla, el modal NO avanza.
- "Siguiente" avanza sin marcar (no llama a la mutación de revisión); "Anterior" retrocede uno. Ambos se deshabilitan en los extremos de la lista (Anterior en el primer documento, Siguiente en el último).
- El modal opera únicamente sobre los documentos ya cargados en la página actual de la tabla (`documentsQuery.data.items`) — no dispara ningún fetch de página siguiente.
- Cada `Object URL` creado para el `<iframe>` debe liberarse (`URL.revokeObjectURL`) al cambiar de documento o al desmontar, para no acumular blobs en memoria.
- **Gotcha de MSW verificado en este entorno:** pasar un `Blob` directamente como body de `new HttpResponse(new Blob([...]))` corrompe el contenido en esta combinación de MSW/Vitest/jsdom — el fetch resultante devuelve la cadena literal `"[object Blob]"` en vez de los bytes reales. En todos los mocks de descarga/preview de este plan, el body debe pasarse como **string plano** con un header `Content-Type` explícito: `new HttpResponse("contenido", { headers: { "Content-Type": "application/pdf" } })` — nunca `new HttpResponse(new Blob([...]))`.

---

### Task 1: `fetchDocumentBlob` reutilizable en `api/documents.ts`

**Files:**
- Modify: `frontend/src/api/documents.ts`
- Test: `frontend/src/api/documents.test.ts`

**Interfaces:**
- Produces: `fetchDocumentBlob(id: number): Promise<Blob>` — usada por `DocumentPreviewDialog` (Task 2) para cargar el contenido del PDF, y por `downloadDocumentFile` (ya existente, refactorizado aquí para reutilizarla).

- [ ] **Step 1: Escribir el test que falla**

En `frontend/src/api/documents.test.ts`, agregar (después del `describe("downloadDocumentFile", ...)` existente, antes de `function makeDocument(...)`):

```typescript
describe("fetchDocumentBlob", () => {
  it("fetches the raw file content as a Blob", async () => {
    server.use(
      http.get(`${BASE_URL}/documents/5/download`, () => new HttpResponse("contenido", { headers: { "Content-Type": "application/pdf" } }))
    );

    const blob = await fetchDocumentBlob(5);

    expect(blob).toBeInstanceOf(Blob);
    expect(await blob.text()).toBe("contenido");
  });

  it("throws when the request fails", async () => {
    server.use(http.get(`${BASE_URL}/documents/6/download`, () => new HttpResponse(null, { status: 404 })));

    await expect(fetchDocumentBlob(6)).rejects.toThrow();
  });
});
```

Y actualizar el import de la línea 5 de:

```typescript
import { buildDownloadFilename, downloadDocumentFile, fetchDocument, fetchDocuments } from "./documents";
```

a:

```typescript
import { buildDownloadFilename, downloadDocumentFile, fetchDocument, fetchDocumentBlob, fetchDocuments } from "./documents";
```

- [ ] **Step 2: Confirmar que falla**

Run: `cd frontend && npm test -- --run src/api/documents.test.ts`
Expected: FAIL — `fetchDocumentBlob` no existe todavía en `./documents`.

- [ ] **Step 3: Extraer `fetchDocumentBlob` e implementarla en `documents.ts`**

En `frontend/src/api/documents.ts`, reemplazar la función `downloadDocumentFile` completa (líneas 95-114) por:

```typescript
export async function fetchDocumentBlob(id: number): Promise<Blob> {
  const token = getStoredToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${BASE_URL}/documents/${id}/download`, { headers });
  if (!response.ok) {
    throw new Error("No se pudo cargar el documento");
  }
  return response.blob();
}

export async function downloadDocumentFile(id: number, filename: string): Promise<void> {
  const blob = await fetchDocumentBlob(id);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
```

- [ ] **Step 4: Confirmar que los tests pasan**

Run: `cd frontend && npm test -- --run src/api/documents.test.ts`
Expected: todos PASS, incluyendo los 2 tests nuevos y los ya existentes de `downloadDocumentFile` (que ahora usa `fetchDocumentBlob` internamente pero mantiene el mismo comportamiento observable).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/documents.ts frontend/src/api/documents.test.ts
git commit -m "feat: extract fetchDocumentBlob for reuse by the upcoming preview dialog"
```

---

### Task 2: Componente `DocumentPreviewDialog`

**Files:**
- Create: `frontend/src/components/DocumentPreviewDialog.tsx`
- Test: `frontend/src/components/DocumentPreviewDialog.test.tsx`

**Interfaces:**
- Consumes: `fetchDocumentBlob(id): Promise<Blob>`, `downloadDocumentFile(id, filename): Promise<void>`, `buildDownloadFilename(document): string` (todas de `../api/documents`, Task 1 y ya existentes); `updateDocumentReviewStatus(id, status): Promise<Document>` (ya existe en `../api/documents`); `Document`, `DocumentReviewStatus` (de `../api/types`); `ErrorBanner` (de `./ErrorBanner`); `Button`, `Dialog`, `DialogContent`, `DialogFooter`, `DialogHeader`, `DialogTitle` (de `./ui/button` y `./ui/dialog`); `formatDate` (de `../lib/formatters`).
- Produces: `DocumentPreviewDialog({ documents: Document[], initialIndex: number, open: boolean, onOpenChange: (open: boolean) => void })` — consumido por `DocumentsPage` en la Task 3.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `frontend/src/components/DocumentPreviewDialog.test.tsx`:

```tsx
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredToken } from "../api/client";
import type { Document } from "../api/types";
import { DocumentPreviewDialog } from "./DocumentPreviewDialog";

const BASE_URL = "http://localhost:8000";

function makeDocument(overrides: Partial<Document> = {}): Document {
  return {
    id: 1,
    doc_id: "abc",
    source_id: 1,
    title: "Documento 1",
    tipo: "Resolución",
    seccion: null,
    especialidad: null,
    magistrado: null,
    detalle: null,
    f_public: "2026-06-01",
    f_providencia: null,
    source_url: null,
    storage_bucket: "iurisync-documents",
    storage_key: "abc.pdf",
    content_type: "application/pdf",
    file_size_bytes: 1024,
    review_status: "pending",
    reviewed_at: null,
    downloaded_at: "2026-07-10T00:00:00Z",
    ...overrides,
  };
}

function renderDialog(documents: Document[], initialIndex: number, onOpenChange = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <DocumentPreviewDialog documents={documents} initialIndex={initialIndex} open onOpenChange={onOpenChange} />
    </QueryClientProvider>
  );
  return { onOpenChange };
}

function mockBlob(id: number, content = "contenido") {
  server.use(
    http.get(`${BASE_URL}/documents/${id}/download`, () => new HttpResponse(content, { headers: { "Content-Type": "application/pdf" } }))
  );
}

describe("DocumentPreviewDialog", () => {
  beforeEach(() => clearStoredToken());

  it("renders an iframe for a PDF document", async () => {
    const documents = [makeDocument({ id: 1, title: "Doc PDF" })];
    mockBlob(1);

    renderDialog(documents, 0);

    expect(await screen.findByTitle("Vista previa de Doc PDF")).toBeInTheDocument();
  });

  it("shows a fallback message and download button for a non-PDF document", async () => {
    const documents = [makeDocument({ id: 2, title: "Doc Word", content_type: "application/msword" })];

    renderDialog(documents, 0);

    expect(await screen.findByText("Vista previa no disponible para este tipo de archivo.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /descargar/i })).toBeInTheDocument();
  });

  it("marking a non-last document as useful advances to the next document", async () => {
    const documents = [makeDocument({ id: 1, title: "Doc 1" }), makeDocument({ id: 2, title: "Doc 2" })];
    mockBlob(1);
    mockBlob(2);
    let patchedId: number | null = null;
    server.use(
      http.patch(`${BASE_URL}/documents/1`, async ({ request }) => {
        patchedId = 1;
        const body = (await request.json()) as { review_status: string };
        return HttpResponse.json({ ...documents[0], review_status: body.review_status });
      })
    );
    const user = userEvent.setup();

    renderDialog(documents, 0);
    await screen.findByTitle("Vista previa de Doc 1");

    await user.click(screen.getByRole("button", { name: "Útil" }));

    await screen.findByTitle("Vista previa de Doc 2");
    expect(patchedId).toBe(1);
  });

  it("marking the last document closes the dialog", async () => {
    const documents = [makeDocument({ id: 1, title: "Doc 1" })];
    mockBlob(1);
    server.use(
      http.patch(`${BASE_URL}/documents/1`, () => HttpResponse.json({ ...documents[0], review_status: "not_useful" }))
    );
    const user = userEvent.setup();

    const { onOpenChange } = renderDialog(documents, 0);
    await screen.findByTitle("Vista previa de Doc 1");

    await user.click(screen.getByRole("button", { name: "No útil" }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("Siguiente advances without marking the document", async () => {
    const documents = [makeDocument({ id: 1, title: "Doc 1" }), makeDocument({ id: 2, title: "Doc 2" })];
    mockBlob(1);
    mockBlob(2);
    let patchCalled = false;
    server.use(
      http.patch(`${BASE_URL}/documents/1`, () => {
        patchCalled = true;
        return HttpResponse.json(documents[0]);
      })
    );
    const user = userEvent.setup();

    renderDialog(documents, 0);
    await screen.findByTitle("Vista previa de Doc 1");

    await user.click(screen.getByRole("button", { name: "Siguiente" }));

    await screen.findByTitle("Vista previa de Doc 2");
    expect(patchCalled).toBe(false);
  });

  it("disables Anterior on the first document", async () => {
    const documents = [makeDocument({ id: 1, title: "Doc 1" }), makeDocument({ id: 2, title: "Doc 2" })];
    mockBlob(1);
    mockBlob(2);

    renderDialog(documents, 0);
    await screen.findByTitle("Vista previa de Doc 1");

    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeEnabled();
  });

  it("disables Siguiente on the last document", async () => {
    const documents = [makeDocument({ id: 1, title: "Doc 1" }), makeDocument({ id: 2, title: "Doc 2" })];
    mockBlob(1);
    mockBlob(2);

    renderDialog(documents, 1);
    await screen.findByTitle("Vista previa de Doc 2");

    expect(screen.getByRole("button", { name: "Siguiente" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Anterior" })).toBeEnabled();
  });

  it("shows a retry option when loading the preview fails, and retrying refetches it", async () => {
    const documents = [makeDocument({ id: 1, title: "Doc 1" })];
    let attempts = 0;
    server.use(
      http.get(`${BASE_URL}/documents/1/download`, () => {
        attempts += 1;
        if (attempts === 1) return new HttpResponse(null, { status: 500 });
        return new HttpResponse("contenido", { headers: { "Content-Type": "application/pdf" } });
      })
    );
    const user = userEvent.setup();

    renderDialog(documents, 0);

    await screen.findByText("No se pudo cargar la vista previa");
    await user.click(screen.getByText("Reintentar"));

    await screen.findByTitle("Vista previa de Doc 1");
  });
});
```

- [ ] **Step 2: Confirmar que fallan**

Run: `cd frontend && npm test -- --run src/components/DocumentPreviewDialog.test.tsx`
Expected: FAIL — el módulo `./DocumentPreviewDialog` no existe todavía.

- [ ] **Step 3: Crear `DocumentPreviewDialog.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { buildDownloadFilename, downloadDocumentFile, fetchDocumentBlob, updateDocumentReviewStatus } from "../api/documents";
import type { Document, DocumentReviewStatus } from "../api/types";
import { formatDate } from "../lib/formatters";
import { ErrorBanner } from "./ErrorBanner";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "./ui/dialog";

interface DocumentPreviewDialogProps {
  documents: Document[];
  initialIndex: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DocumentPreviewDialog({ documents, initialIndex, open, onOpenChange }: DocumentPreviewDialogProps) {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [markError, setMarkError] = useState<string | null>(null);
  const [lastMarkAttempt, setLastMarkAttempt] = useState<DocumentReviewStatus | null>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (open) setCurrentIndex(initialIndex);
  }, [open, initialIndex]);

  useEffect(() => {
    setMarkError(null);
  }, [currentIndex]);

  const currentDocument = documents[currentIndex];
  const isPdf = currentDocument?.content_type === "application/pdf";
  const isFirst = currentIndex === 0;
  const isLast = currentIndex === documents.length - 1;

  const blobQuery = useQuery({
    queryKey: ["document-blob", currentDocument?.id],
    queryFn: () => fetchDocumentBlob(currentDocument!.id),
    enabled: open && !!currentDocument && isPdf,
  });

  useEffect(() => {
    if (!blobQuery.data) {
      setObjectUrl(null);
      return;
    }
    const url = URL.createObjectURL(blobQuery.data);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [blobQuery.data]);

  const markMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: DocumentReviewStatus }) => updateDocumentReviewStatus(id, status),
    onSuccess: () => {
      setMarkError(null);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      if (isLast) {
        onOpenChange(false);
      } else {
        setCurrentIndex((index) => index + 1);
      }
    },
    onError: () => setMarkError("Error al marcar el documento"),
  });

  if (!currentDocument) return null;

  const busy = markMutation.isPending;

  function handleMark(status: DocumentReviewStatus) {
    setLastMarkAttempt(status);
    markMutation.mutate({ id: currentDocument.id, status });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[85vh] flex-col sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle className="font-display">{currentDocument.title}</DialogTitle>
          <p className="text-sm text-muted-foreground">
            {currentDocument.tipo ?? "—"} · {formatDate(currentDocument.f_public)}
          </p>
        </DialogHeader>

        <div className="flex-1 overflow-hidden rounded-md border border-border bg-secondary">
          {isPdf ? (
            blobQuery.isError ? (
              <div className="flex h-full items-center justify-center p-6">
                <ErrorBanner message="No se pudo cargar la vista previa" onRetry={() => blobQuery.refetch()} />
              </div>
            ) : objectUrl ? (
              <iframe title={`Vista previa de ${currentDocument.title}`} src={objectUrl} className="size-full" />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Cargando…</div>
            )
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
              <p className="text-sm text-muted-foreground">Vista previa no disponible para este tipo de archivo.</p>
              <Button
                variant="outline"
                onClick={() => downloadDocumentFile(currentDocument.id, buildDownloadFilename(currentDocument))}
              >
                <Download className="size-3.5" aria-hidden="true" />
                Descargar
              </Button>
            </div>
          )}
        </div>

        {markError && (
          <ErrorBanner message={markError} onRetry={() => lastMarkAttempt && handleMark(lastMarkAttempt)} />
        )}

        <DialogFooter className="flex-row items-center justify-between sm:justify-between">
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={isFirst || busy}
              onClick={() => setCurrentIndex((index) => index - 1)}
            >
              Anterior
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={isLast || busy}
              onClick={() => setCurrentIndex((index) => index + 1)}
            >
              Siguiente
            </Button>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => handleMark("useful")}
              className="border-verde/50 text-verde hover:bg-verde-bg"
            >
              Útil
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => handleMark("not_useful")}
              className="border-rojo/50 text-rojo hover:bg-rojo-bg"
            >
              No útil
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Confirmar que los tests pasan**

Run: `cd frontend && npm test -- --run src/components/DocumentPreviewDialog.test.tsx`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DocumentPreviewDialog.tsx frontend/src/components/DocumentPreviewDialog.test.tsx
git commit -m "feat: add DocumentPreviewDialog with inline PDF preview and review actions"
```

---

### Task 3: Conectar el botón "Previsualizar" en `DocumentsPage`

**Files:**
- Modify: `frontend/src/pages/DocumentsPage.tsx`
- Test: `frontend/src/pages/DocumentsPage.test.tsx`

**Interfaces:**
- Consumes: `DocumentPreviewDialog` (Task 2).

- [ ] **Step 1: Escribir el test que falla**

En `frontend/src/pages/DocumentsPage.test.tsx`, cambiar el import de la línea 2 de:

```typescript
import { render, screen, waitFor } from "@testing-library/react";
```

a:

```typescript
import { render, screen, waitFor, within } from "@testing-library/react";
```

Y agregar este test al final del `describe("DocumentsPage", ...)`, antes del cierre `});` final:

```typescript
  it("opens the preview dialog with the correct document when Previsualizar is clicked", async () => {
    mockFilterEndpoints();
    const user = userEvent.setup();
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({ items: [DOCUMENT, DOCUMENT_2], total: 2, limit: 50, offset: 0 })
      ),
      http.get(`${BASE_URL}/documents/2/download`, () => new HttpResponse("x", { headers: { "Content-Type": "application/pdf" } }))
    );
    renderPage();

    await screen.findByText("Sentencia C-002-26");
    const row = screen.getByText("Sentencia C-002-26").closest("tr") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: /previsualizar/i }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Sentencia C-002-26")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Confirmar que falla**

Run: `cd frontend && npm test -- --run src/pages/DocumentsPage.test.tsx`
Expected: FAIL — no existe ningún botón "Previsualizar" todavía.

- [ ] **Step 3: Agregar el botón y el estado del modal en `DocumentsPage.tsx`**

Cambiar el import de la línea 3 de:

```tsx
import { Download, FileStack, Search } from "lucide-react";
```

a:

```tsx
import { Download, Eye, FileStack, Search } from "lucide-react";
```

Agregar el import del componente nuevo, después de la línea 4 (`import { Button } from "../components/ui/button";`):

```tsx
import { DocumentPreviewDialog } from "../components/DocumentPreviewDialog";
```

Agregar el estado del modal, después de la línea 32 (`const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());`):

```tsx
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
```

Cambiar el encabezado de la columna (línea 258) de:

```tsx
              <th className={TH}>Descargar</th>
```

a:

```tsx
              <th className={TH}>Acciones</th>
```

Cambiar la celda de acciones (líneas 321-330) de:

```tsx
                <td className={TD}>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => downloadMutation.mutate({ id: document.id, filename: buildDownloadFilename(document) })}
                  >
                    <Download className="size-3.5" aria-hidden="true" />
                    Descargar
                  </Button>
                </td>
```

a (usando el `index` que ya provee `.map((document) => (` — cambiarlo a `.map((document, index) => (` en la línea 262):

```tsx
                <td className={TD}>
                  <div className="flex gap-1.5">
                    <Button variant="outline" size="sm" onClick={() => setPreviewIndex(index)}>
                      <Eye className="size-3.5" aria-hidden="true" />
                      Previsualizar
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => downloadMutation.mutate({ id: document.id, filename: buildDownloadFilename(document) })}
                    >
                      <Download className="size-3.5" aria-hidden="true" />
                      Descargar
                    </Button>
                  </div>
                </td>
```

(Recordar cambiar `{documentsQuery.data?.items.map((document) => (` por `{documentsQuery.data?.items.map((document, index) => (` en la línea 262, ya que `index` es lo que identifica la posición del documento dentro de la lista que recibirá `DocumentPreviewDialog`.)

Agregar el render del modal, justo antes del cierre final `</div>` del componente (después del bloque de paginación, líneas 341-367):

```tsx
      {previewIndex !== null && documentsQuery.data && (
        <DocumentPreviewDialog
          documents={documentsQuery.data.items}
          initialIndex={previewIndex}
          open={previewIndex !== null}
          onOpenChange={(nextOpen) => {
            if (!nextOpen) setPreviewIndex(null);
          }}
        />
      )}
```

- [ ] **Step 4: Confirmar que los tests pasan**

Run: `cd frontend && npm test -- --run src/pages/DocumentsPage.test.tsx`
Expected: todos PASS, incluyendo el test nuevo. (El test existente `"triggers a download when the download button is clicked"` sigue pasando porque el botón "Descargar" no cambió de texto ni de comportamiento.)

- [ ] **Step 5: Correr toda la suite de frontend y el build**

Run: `cd frontend && npm test -- --run`
Expected: todos PASS.

Run: `cd frontend && npm run build`
Expected: `tsc -b` y `vite build` sin errores.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/DocumentsPage.tsx frontend/src/pages/DocumentsPage.test.tsx
git commit -m "feat: add Previsualizar action to DocumentsPage rows"
```
