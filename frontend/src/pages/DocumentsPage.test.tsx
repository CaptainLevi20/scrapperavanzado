import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { DocumentsPage } from "./DocumentsPage";

const BASE_URL = "http://localhost:8000";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <DocumentsPage />
    </QueryClientProvider>
  );
}

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

const SOURCE = { id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: true };
const FAMILY = { key: "constitucional", display_name: "Corte Constitucional", description: null };

function mockFilterEndpoints() {
  server.use(
    http.get(`${BASE_URL}/sources`, () => HttpResponse.json([SOURCE])),
    http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([FAMILY]))
  );
}

describe("DocumentsPage", () => {
  it("renders fetched documents with formatted size", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 }))
    );

    renderPage();

    expect(await screen.findByText("Sentencia C-001-26")).toBeInTheDocument();
    expect(screen.getByText("200.0 KB")).toBeInTheDocument();
  });

  it("refetches with the title filter applied", async () => {
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
    await user.type(screen.getByPlaceholderText(/buscar por t.tulo/i), "sentencia");

    await waitFor(() => expect(lastUrl).toContain("title=sentencia"));
  });

  it("triggers a download when the download button is clicked", async () => {
    mockFilterEndpoints();
    const user = userEvent.setup();
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 })),
      http.get(`${BASE_URL}/documents/1/download`, () => new HttpResponse(new Blob(["x"], { type: "application/pdf" })))
    );
    renderPage();

    await user.click(await screen.findByText("Descargar"));

    await waitFor(() => expect(screen.queryByText(/error al descargar/i)).not.toBeInTheDocument());
  });

  it("renders the Sección column", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({ items: [{ ...DOCUMENT, seccion: "Sala Plena" }], total: 1, limit: 50, offset: 0 })
      )
    );

    renderPage();

    expect(await screen.findByText("Sala Plena")).toBeInTheDocument();
  });

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

  it("refetches with the source and family filters applied", async () => {
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

    await waitFor(() => expect(screen.getByLabelText("Fuente")).toHaveTextContent("Corte Constitucional"));

    await user.selectOptions(screen.getByLabelText("Fuente"), "1");
    await waitFor(() => expect(lastUrl).toContain("source_id=1"));

    await user.selectOptions(screen.getByLabelText("Familia"), "constitucional");
    await waitFor(() => expect(lastUrl).toContain("family_key=constitucional"));
  });
});
