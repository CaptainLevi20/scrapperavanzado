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

  it("does not advance or close the dialog when the mark mutation fails", async () => {
    const documents = [makeDocument({ id: 1, title: "Doc 1" }), makeDocument({ id: 2, title: "Doc 2" })];
    mockBlob(1);
    mockBlob(2);
    server.use(http.patch(`${BASE_URL}/documents/1`, () => new HttpResponse(null, { status: 500 })));
    const user = userEvent.setup();

    const { onOpenChange } = renderDialog(documents, 0);
    await screen.findByTitle("Vista previa de Doc 1");

    await user.click(screen.getByRole("button", { name: "Útil" }));

    await screen.findByText("Error al marcar el documento");
    expect(screen.getByTitle("Vista previa de Doc 1")).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();
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
