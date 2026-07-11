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
  f_public: null,
  f_providencia: "2026-01-15",
  storage_bucket: "iurisync-documents",
  storage_key: "abc.pdf",
  content_type: "application/pdf",
  file_size_bytes: 204800,
  downloaded_at: "2026-07-10T00:00:00Z",
};

describe("DocumentsPage", () => {
  it("renders fetched documents with formatted size", async () => {
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 }))
    );

    renderPage();

    expect(await screen.findByText("Sentencia C-001-26")).toBeInTheDocument();
    expect(screen.getByText("200.0 KB")).toBeInTheDocument();
  });

  it("refetches with the title filter applied", async () => {
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
    const user = userEvent.setup();
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 })),
      http.get(`${BASE_URL}/documents/1/download`, () => new HttpResponse(new Blob(["x"], { type: "application/pdf" })))
    );
    renderPage();

    await user.click(await screen.findByText("Descargar"));

    await waitFor(() => expect(screen.queryByText(/error al descargar/i)).not.toBeInTheDocument());
  });
});
