import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
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

function renderDialog(
  documents: Document[],
  initialIndex: number,
  onOpenChange = vi.fn(),
  showCaseActuaciones = false
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <DocumentPreviewDialog
        documents={documents}
        initialIndex={initialIndex}
        open
        onOpenChange={onOpenChange}
        showCaseActuaciones={showCaseActuaciones}
      />
    </QueryClientProvider>
  );
  return { onOpenChange };
}

function mockPreviewUrl(id: number, url = `https://signed.example.com/doc${id}.pdf`) {
  server.use(http.get(`${BASE_URL}/documents/${id}/preview`, () => HttpResponse.json({ url })));
}

describe("DocumentPreviewDialog", () => {
  beforeEach(() => clearStoredToken());

  it("renders an iframe for a PDF document", async () => {
    const documents = [makeDocument({ id: 1, title: "Doc PDF" })];
    mockPreviewUrl(1);

    renderDialog(documents, 0);

    expect(await screen.findByTitle("Vista previa de Doc PDF")).toBeInTheDocument();
  });

  it("shows a fallback message and download button for a non-previewable document", async () => {
    const documents = [makeDocument({ id: 2, title: "Doc Binario", content_type: "application/octet-stream" })];

    renderDialog(documents, 0);

    expect(await screen.findByText("Vista previa no disponible para este tipo de archivo.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /descargar/i })).toBeInTheDocument();
  });

  it("marking a non-last document as useful advances to the next document", async () => {
    const documents = [makeDocument({ id: 1, title: "Doc 1" }), makeDocument({ id: 2, title: "Doc 2" })];
    mockPreviewUrl(1);
    mockPreviewUrl(2);
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
    mockPreviewUrl(1);
    mockPreviewUrl(2);
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
    mockPreviewUrl(1);
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
    mockPreviewUrl(1);
    mockPreviewUrl(2);
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
    mockPreviewUrl(1);
    mockPreviewUrl(2);

    renderDialog(documents, 0);
    await screen.findByTitle("Vista previa de Doc 1");

    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeEnabled();
  });

  it("disables Siguiente on the last document", async () => {
    const documents = [makeDocument({ id: 1, title: "Doc 1" }), makeDocument({ id: 2, title: "Doc 2" })];
    mockPreviewUrl(1);
    mockPreviewUrl(2);

    renderDialog(documents, 1);
    await screen.findByTitle("Vista previa de Doc 2");

    expect(screen.getByRole("button", { name: "Siguiente" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Anterior" })).toBeEnabled();
  });

  it("keeps navigating the originally-opened list even if the documents prop changes after a mark (e.g. a parent refetch under a review_status filter)", async () => {
    const documents = [
      makeDocument({ id: 1, title: "Doc A" }),
      makeDocument({ id: 2, title: "Doc B" }),
      makeDocument({ id: 3, title: "Doc C" }),
    ];
    mockPreviewUrl(1);
    mockPreviewUrl(2);
    server.use(
      http.patch(`${BASE_URL}/documents/1`, () => HttpResponse.json({ ...documents[0], review_status: "useful" }))
    );
    const onOpenChange = vi.fn();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <DocumentPreviewDialog documents={documents} initialIndex={0} open onOpenChange={onOpenChange} />
      </QueryClientProvider>
    );
    await screen.findByTitle("Vista previa de Doc A");

    await user.click(screen.getByRole("button", { name: "Útil" }));

    // Simulate the parent's list shrinking after the invalidation-triggered refetch
    // (Doc A no longer matches a "pending" filter, so it drops out and later
    // documents shift down by one index). The dialog must NOT be affected by this —
    // it should still be showing Doc B (the document it actually advanced to),
    // not Doc C (which is what a naive documents[currentIndex] read would show).
    const refetchedDocuments = [documents[1], documents[2]];
    rerender(
      <QueryClientProvider client={queryClient}>
        <DocumentPreviewDialog documents={refetchedDocuments} initialIndex={0} open onOpenChange={onOpenChange} />
      </QueryClientProvider>
    );

    expect(await screen.findByTitle("Vista previa de Doc B")).toBeInTheDocument();
  });

  it("shows a retry option when loading the preview fails, and retrying refetches it", async () => {
    const documents = [makeDocument({ id: 1, title: "Doc 1" })];
    let attempts = 0;
    server.use(
      http.get(`${BASE_URL}/documents/1/preview`, () => {
        attempts += 1;
        if (attempts === 1) return new HttpResponse(null, { status: 500 });
        return HttpResponse.json({ url: "https://signed.example.com/doc1.pdf" });
      })
    );
    const user = userEvent.setup();

    renderDialog(documents, 0);

    await screen.findByText("No se pudo cargar la vista previa");
    await user.click(screen.getByText("Reintentar"));

    await screen.findByTitle("Vista previa de Doc 1");
  });

  it("renders an iframe for a previewable RTF document (via /preview, not /download)", async () => {
    const documents = [makeDocument({ id: 9, title: "Doc RTF", content_type: "application/rtf" })];
    mockPreviewUrl(9);

    renderDialog(documents, 0);

    expect(await screen.findByTitle("Vista previa de Doc RTF")).toBeInTheDocument();
  });

  it("still shows the fallback message for a genuinely non-previewable type", async () => {
    const documents = [makeDocument({ id: 10, title: "Doc Texto", content_type: "text/plain" })];

    renderDialog(documents, 0);

    expect(await screen.findByText("Vista previa no disponible para este tipo de archivo.")).toBeInTheDocument();
  });

  it("points the iframe at the presigned URL with the native pdf viewer toolbar suppressed", async () => {
    // #toolbar=0 hides the browser's own built-in pdf viewer chrome (including its
    // download button) — downloading is offered via our own explicit "Descargar RTF"
    // / "Descargar PDF" buttons instead, which can express the RTF-vs-PDF choice a
    // single native button couldn't.
    const documents = [makeDocument({ id: 11, title: "SAI-AOI-RC-PMA-320-2026", content_type: "application/rtf" })];
    mockPreviewUrl(11, "https://signed.example.com/SAI-AOI-RC-PMA-320-2026.preview.pdf");

    renderDialog(documents, 0);

    const iframe = await screen.findByTitle("Vista previa de SAI-AOI-RC-PMA-320-2026");
    expect(iframe).toHaveAttribute("src", "https://signed.example.com/SAI-AOI-RC-PMA-320-2026.preview.pdf#toolbar=0");
  });

  it("shows both Descargar RTF and Descargar PDF for a native RTF document", async () => {
    const documents = [makeDocument({ id: 12, title: "Doc RTF", content_type: "application/rtf" })];
    mockPreviewUrl(12);

    renderDialog(documents, 0);
    await screen.findByTitle("Vista previa de Doc RTF");

    expect(screen.getByRole("button", { name: /descargar rtf/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /descargar pdf/i })).toBeInTheDocument();
  });

  it("hides Descargar RTF (but keeps Descargar PDF) for a native PDF document", async () => {
    const documents = [makeDocument({ id: 13, title: "Doc PDF nativo", content_type: "application/pdf" })];
    mockPreviewUrl(13);

    renderDialog(documents, 0);
    await screen.findByTitle("Vista previa de Doc PDF nativo");

    expect(screen.queryByRole("button", { name: /descargar rtf/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /descargar pdf/i })).toBeInTheDocument();
  });

  it("Descargar RTF downloads the stored file via /download with the title as filename", async () => {
    const documents = [
      makeDocument({ id: 14, title: "Doc RTF", content_type: "application/rtf", storage_key: "carpeta/archivo.rtf" }),
    ];
    mockPreviewUrl(14);
    server.use(
      http.get(`${BASE_URL}/documents/14/download`, () => new HttpResponse(new Blob(["contenido rtf"], { type: "application/rtf" })))
    );
    const clickSpy = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    const createElementSpy = vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const element = originalCreateElement(tag);
      if (tag === "a") element.click = clickSpy;
      return element;
    });
    const user = userEvent.setup();

    renderDialog(documents, 0);
    await screen.findByTitle("Vista previa de Doc RTF");

    await user.click(screen.getByRole("button", { name: /descargar rtf/i }));

    await waitFor(() => expect(clickSpy).toHaveBeenCalledOnce());
    createElementSpy.mockRestore();
  });

  it("Descargar PDF fetches the previewed URL and downloads it under the title as .pdf", async () => {
    const documents = [makeDocument({ id: 15, title: "Doc RTF", content_type: "application/rtf" })];
    mockPreviewUrl(15, "https://signed.example.com/doc15.preview.pdf");
    server.use(
      http.get("https://signed.example.com/doc15.preview.pdf", () => new HttpResponse(new Blob(["contenido pdf"], { type: "application/pdf" })))
    );
    const clickSpy = vi.fn();
    let capturedFilename: string | null = null;
    const originalCreateElement = document.createElement.bind(document);
    const createElementSpy = vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const element = originalCreateElement(tag);
      if (tag === "a") {
        element.click = clickSpy;
        clickSpy.mockImplementation(function (this: HTMLAnchorElement) {
          capturedFilename = this.download;
        });
      }
      return element;
    });
    const user = userEvent.setup();

    renderDialog(documents, 0);
    await screen.findByTitle("Vista previa de Doc RTF");

    await user.click(screen.getByRole("button", { name: /descargar pdf/i }));

    await waitFor(() => expect(capturedFilename).toBe("Doc RTF.pdf"));
    createElementSpy.mockRestore();
  });

  it("lets the user rename the title by hand, for cases the automated rules don't cover", async () => {
    const documents = [makeDocument({ id: 30, title: "1842" })];
    mockPreviewUrl(30);
    let patchedBody: { title: string } | null = null;
    server.use(
      http.patch(`${BASE_URL}/documents/30/title`, async ({ request }) => {
        patchedBody = (await request.json()) as { title: string };
        return HttpResponse.json({ ...documents[0], title: patchedBody.title });
      })
    );
    const user = userEvent.setup();

    renderDialog(documents, 0);
    await screen.findByTitle("Vista previa de 1842");

    await user.click(screen.getByRole("button", { name: /renombrar título/i }));
    const input = screen.getByLabelText(/nuevo título del documento/i);
    expect(input).toHaveValue("1842");

    await user.clear(input);
    await user.type(input, "R_SDSJ-1842_2026");
    await user.click(screen.getByRole("button", { name: /guardar título/i }));

    await waitFor(() => expect(patchedBody).toEqual({ title: "R_SDSJ-1842_2026" }));
    expect(await screen.findByTitle("Vista previa de R_SDSJ-1842_2026")).toBeInTheDocument();
  });

  it("cancels the rename with Escape without saving", async () => {
    const documents = [makeDocument({ id: 31, title: "Título original" })];
    mockPreviewUrl(31);
    let patchCalled = false;
    server.use(
      http.patch(`${BASE_URL}/documents/31/title`, () => {
        patchCalled = true;
        return HttpResponse.json(documents[0]);
      })
    );
    const user = userEvent.setup();

    renderDialog(documents, 0);
    await screen.findByTitle("Vista previa de Título original");

    await user.click(screen.getByRole("button", { name: /renombrar título/i }));
    await user.type(screen.getByLabelText(/nuevo título del documento/i), " editado");
    await user.keyboard("{Escape}");

    expect(screen.queryByLabelText(/nuevo título del documento/i)).not.toBeInTheDocument();
    expect(patchCalled).toBe(false);
    expect(screen.getByText("Título original")).toBeInTheDocument();
  });

  it("does not call the API when saving an unchanged title", async () => {
    const documents = [makeDocument({ id: 32, title: "Sin cambios" })];
    mockPreviewUrl(32);
    let patchCalled = false;
    server.use(
      http.patch(`${BASE_URL}/documents/32/title`, () => {
        patchCalled = true;
        return HttpResponse.json(documents[0]);
      })
    );
    const user = userEvent.setup();

    renderDialog(documents, 0);
    await screen.findByTitle("Vista previa de Sin cambios");

    await user.click(screen.getByRole("button", { name: /renombrar título/i }));
    await user.click(screen.getByRole("button", { name: /guardar título/i }));

    expect(screen.queryByLabelText(/nuevo título del documento/i)).not.toBeInTheDocument();
    expect(patchCalled).toBe(false);
  });

  it("shows an error and keeps editing open when the rename fails", async () => {
    const documents = [makeDocument({ id: 33, title: "Título con error" })];
    mockPreviewUrl(33);
    server.use(http.patch(`${BASE_URL}/documents/33/title`, () => new HttpResponse(null, { status: 500 })));
    const user = userEvent.setup();

    renderDialog(documents, 0);
    await screen.findByTitle("Vista previa de Título con error");

    await user.click(screen.getByRole("button", { name: /renombrar título/i }));
    const input = screen.getByLabelText(/nuevo título del documento/i);
    await user.clear(input);
    await user.type(input, "Nuevo título");
    await user.click(screen.getByRole("button", { name: /guardar título/i }));

    await screen.findByText("Error al renombrar el documento");
    expect(screen.getByLabelText(/nuevo título del documento/i)).toBeInTheDocument();
  });

  it("shows the case's other actuaciones (excluding the currently displayed one) when showCaseActuaciones is true", async () => {
    const documents = [
      makeDocument({ id: 40, title: "Caso X", detalle: "Auto Actual", f_public: "2026-07-17" }),
      makeDocument({ id: 41, title: "Caso X", detalle: "Auto Anterior", f_public: "2026-06-30" }),
      makeDocument({ id: 42, title: "Caso X", detalle: "Sentencia Previa", f_public: "2026-06-16" }),
    ];
    mockPreviewUrl(40);

    renderDialog(documents, 0, vi.fn(), true);

    await screen.findByTitle("Vista previa de Caso X");
    expect(screen.getByText(/Auto Anterior/)).toBeInTheDocument();
    expect(screen.getByText(/Sentencia Previa/)).toBeInTheDocument();
    // The currently-displayed document's own detalle must not be duplicated in the list.
    expect(screen.queryByText(/Auto Actual/)).not.toBeInTheDocument();
  });

  it("does not show the case-actuaciones list when showCaseActuaciones is not set, even with multiple documents", async () => {
    const documents = [
      makeDocument({ id: 43, title: "Doc 1", detalle: "Detalle 1" }),
      makeDocument({ id: 44, title: "Doc 2", detalle: "Detalle 2" }),
    ];
    mockPreviewUrl(43);

    renderDialog(documents, 0);

    await screen.findByTitle("Vista previa de Doc 1");
    expect(screen.queryByText(/Detalle 2/)).not.toBeInTheDocument();
  });

  it("clicking Previsualizar on another actuación switches the main preview to it", async () => {
    const documents = [
      makeDocument({ id: 50, title: "Actual" }),
      makeDocument({ id: 51, title: "Otra Actuación", detalle: "Auto Anterior" }),
    ];
    mockPreviewUrl(50);
    mockPreviewUrl(51);
    const user = userEvent.setup();

    renderDialog(documents, 0, vi.fn(), true);
    await screen.findByTitle("Vista previa de Actual");

    await user.click(screen.getByRole("button", { name: /previsualizar/i }));

    expect(await screen.findByTitle("Vista previa de Otra Actuación")).toBeInTheDocument();
  });

  it("marking another actuación as useful from the list updates only that document, without advancing past the current one", async () => {
    const documents = [
      makeDocument({ id: 60, title: "Actual" }),
      makeDocument({ id: 61, title: "Otra Actuación", detalle: "Auto Anterior", review_status: "pending" }),
    ];
    mockPreviewUrl(60);
    let patchedId: number | null = null;
    server.use(
      http.patch(`${BASE_URL}/documents/61`, async ({ request }) => {
        patchedId = 61;
        const body = (await request.json()) as { review_status: string };
        return HttpResponse.json({ ...documents[1], review_status: body.review_status });
      })
    );
    const user = userEvent.setup();

    renderDialog(documents, 0, vi.fn(), true);
    await screen.findByTitle("Vista previa de Actual");

    // Scoped to the list row: the footer also has an "Útil" button for the
    // currently-displayed document, which a bare screen.getByRole would match too.
    const listRow = screen.getByText(/Auto Anterior/).closest("li")!;
    await user.click(within(listRow).getByRole("button", { name: /^útil$/i }));

    await waitFor(() => expect(patchedId).toBe(61));
    // The dialog must still show "Actual" — marking a sibling from the list must
    // not advance currentIndex or close the dialog (unlike marking the current
    // document via the footer's Útil/No útil buttons).
    expect(screen.getByTitle("Vista previa de Actual")).toBeInTheDocument();
  });

  it("downloading another actuación's file from the list works independently of the currently displayed one", async () => {
    const documents = [
      makeDocument({ id: 70, title: "Actual" }),
      makeDocument({ id: 71, title: "Otra Actuación", detalle: "Auto Anterior", storage_key: "otra.pdf" }),
    ];
    mockPreviewUrl(70);
    server.use(
      http.get(`${BASE_URL}/documents/71/download`, () => new HttpResponse(new Blob(["contenido"], { type: "application/pdf" })))
    );
    const clickSpy = vi.fn();
    let capturedFilename: string | null = null;
    const originalCreateElement = document.createElement.bind(document);
    const createElementSpy = vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const element = originalCreateElement(tag);
      if (tag === "a") {
        element.click = clickSpy;
        clickSpy.mockImplementation(function (this: HTMLAnchorElement) {
          capturedFilename = this.download;
        });
      }
      return element;
    });
    const user = userEvent.setup();

    renderDialog(documents, 0, vi.fn(), true);
    await screen.findByTitle("Vista previa de Actual");

    await user.click(screen.getByRole("button", { name: /^descargar$/i }));

    await waitFor(() => expect(capturedFilename).toBe("Otra Actuación.pdf"));
    createElementSpy.mockRestore();
  });

  it("does not show a version history section when the document has no prior versions", async () => {
    const documents = [makeDocument({ id: 20, title: "Sin historial" })];
    mockPreviewUrl(20);
    server.use(http.get(`${BASE_URL}/documents/20/versions`, () => HttpResponse.json([])));

    renderDialog(documents, 0);

    await screen.findByTitle("Vista previa de Sin historial");
    expect(screen.queryByText(/versiones anteriores/i)).not.toBeInTheDocument();
  });

  it("shows the version history with a working download button", async () => {
    const documents = [makeDocument({ id: 21, title: "Con historial" })];
    mockPreviewUrl(21);
    server.use(
      http.get(`${BASE_URL}/documents/21/versions`, () =>
        HttpResponse.json([
          { id: 1, document_id: 21, file_size_bytes: 76245, content_type: "application/rtf", downloaded_at: "2026-06-01T00:00:00Z", superseded_at: "2026-07-01T00:00:00Z" },
        ])
      ),
      http.get(`${BASE_URL}/documents/21/versions/1/download`, () =>
        HttpResponse.json({ url: "https://signed.example.com/versions/1.rtf" })
      ),
      http.get("https://signed.example.com/versions/1.rtf", () => new HttpResponse(new Blob(["contenido viejo"])))
    );
    const clickSpy = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    const createElementSpy = vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const element = originalCreateElement(tag);
      if (tag === "a") element.click = clickSpy;
      return element;
    });
    const user = userEvent.setup();

    renderDialog(documents, 0);
    await screen.findByTitle("Vista previa de Con historial");

    // Scoped with within(): the default makeDocument() content_type is "application/pdf",
    // so the header already renders its own "Descargar PDF" button — a bare
    // screen.getByRole("button", { name: /descargar/i }) would match both that one and
    // the version row's "Descargar" button and throw for multiple matches.
    const versionsHeading = await screen.findByText(/1 versi.n anterior/i);
    const versionsSection = versionsHeading.closest("div") as HTMLElement;
    await user.click(within(versionsSection).getByRole("button", { name: /descargar/i }));

    await waitFor(() => expect(clickSpy).toHaveBeenCalledOnce());
    createElementSpy.mockRestore();
  });
});
