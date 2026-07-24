import { describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { DocumentsPage } from "./DocumentsPage";
import { todayDateString, formatDate } from "../lib/formatters";

const BASE_URL = "http://localhost:8000";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DocumentsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderPageWithTodayState() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[{ pathname: "/documents", state: { downloadedToday: true } }]}>
        <DocumentsPage />
      </MemoryRouter>
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

const DOCUMENT_2 = {
  ...DOCUMENT,
  id: 2,
  doc_id: "def",
  title: "Sentencia C-002-26",
};

const CASE_DOCUMENT_1 = {
  ...DOCUMENT,
  id: 10,
  doc_id: "case-1",
  title: "T_BTA_11001_31_03_048_2022_00418_02",
  f_public: "2026-06-16",
  case_document_count: 3,
};

const CASE_DOCUMENT_2 = {
  ...DOCUMENT,
  id: 11,
  doc_id: "case-2",
  title: "T_BTA_11001_31_03_048_2022_00418_02",
  f_public: "2026-06-30",
  case_document_count: 3,
};

const CASE_DOCUMENT_3 = {
  ...DOCUMENT,
  id: 12,
  doc_id: "case-3",
  title: "T_BTA_11001_31_03_048_2022_00418_02",
  f_public: "2026-07-17",
  case_document_count: 3,
};

const SOURCE = { id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: true };
const FAMILY = { key: "constitucional", display_name: "Corte Constitucional", description: null };

function mockFilterEndpoints() {
  server.use(
    http.get(`${BASE_URL}/sources`, () => HttpResponse.json([SOURCE])),
    http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([FAMILY])),
    http.get(`${BASE_URL}/documents/tipos`, () => HttpResponse.json(["Auto", "Sentencia"]))
  );
}

describe("DocumentsPage", () => {
  it("renders fetched documents", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 }))
    );

    renderPage();

    expect(await screen.findByText("Sentencia C-001-26")).toBeInTheDocument();
  });

  it("does not show a file size column — it's tracked but not meant to be displayed here", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 }))
    );

    renderPage();

    await screen.findByText("Sentencia C-001-26");
    expect(screen.queryByText("Tamaño")).not.toBeInTheDocument();
    expect(screen.queryByText("200.0 KB")).not.toBeInTheDocument();
  });

  it("renders the Fuente column with the document's source name", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 }))
    );

    renderPage();

    await screen.findByText("Sentencia C-001-26");
    const row = screen.getByText("Sentencia C-001-26").closest("tr") as HTMLElement;
    expect(within(row).getByText("Corte Constitucional")).toBeInTheDocument();
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

  it("only shows Previsualizar in Acciones — no direct download button in the table", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 }))
    );
    renderPage();

    await screen.findByText("Sentencia C-001-26");
    const row = screen.getByText("Sentencia C-001-26").closest("tr") as HTMLElement;
    expect(within(row).getByRole("button", { name: /previsualizar/i })).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: /descargar/i })).not.toBeInTheDocument();
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

  it("renders the Fecha de publicación column separately from Fecha providencia", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({
          items: [{ ...DOCUMENT, f_public: "2026-01-15", f_providencia: "2026-07-20" }],
          total: 1,
          limit: 50,
          offset: 0,
        })
      )
    );

    renderPage();

    await screen.findByText("Sentencia C-001-26");
    // Distinct months (Jan vs Jul) so this doesn't depend on the exact day
    // number, which shifts by a day depending on the runner's timezone.
    expect(screen.getByText(/ene/i)).toBeInTheDocument();
    expect(screen.getByText(/jul/i)).toBeInTheDocument();
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

  it("shows detalle as a tooltip on the title", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({
          items: [{ ...DOCUMENT, detalle: "Resumen del fallo" }],
          total: 1,
          limit: 50,
          offset: 0,
        })
      )
    );

    renderPage();

    expect(await screen.findByTitle("Resumen del fallo")).toBeInTheDocument();
  });

  it("shows the review status as a read-only badge, not an interactive control", async () => {
    // Marking useful/not-useful now happens exclusively inside the preview modal —
    // the table only needs to show the current status at a glance.
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({ items: [{ ...DOCUMENT, review_status: "useful" }], total: 1, limit: 50, offset: 0 })
      )
    );
    renderPage();

    await screen.findByText("Sentencia C-001-26");
    const row = screen.getByText("Sentencia C-001-26").closest("tr") as HTMLElement;
    expect(within(row).getByText("Útil")).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: /útil/i })).not.toBeInTheDocument();
  });

  it("shows 'Sin revisar' for a pending document", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 }))
    );
    renderPage();

    await screen.findByText("Sentencia C-001-26");
    const row = screen.getByText("Sentencia C-001-26").closest("tr") as HTMLElement;
    expect(within(row).getByText("Sin revisar")).toBeInTheDocument();
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

  it("refetches with the source filter applied", async () => {
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
  });

  it("clicking a document's title filters the table to that exact title", async () => {
    mockFilterEndpoints();
    let lastUrl = "";
    server.use(
      http.get(`${BASE_URL}/documents`, ({ request }) => {
        lastUrl = request.url;
        return HttpResponse.json({ items: [DOCUMENT, DOCUMENT_2], total: 2, limit: 50, offset: 0 });
      })
    );
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Sentencia C-001-26");
    await user.click(screen.getByText("Sentencia C-001-26"));

    await waitFor(() => {
      const url = new URL(lastUrl);
      expect(url.searchParams.get("title")).toBe("Sentencia C-001-26");
    });
    expect(screen.getByPlaceholderText("Buscar por título")).toHaveValue("Sentencia C-001-26");
  });

  it("does not show a Familia filter", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }))
    );
    renderPage();

    await waitFor(() => expect(screen.getByLabelText("Fuente")).toHaveTextContent("Corte Constitucional"));
    expect(screen.queryByLabelText("Familia")).not.toBeInTheDocument();
  });

  it("scopes the Tipo dropdown to the selected Fuente (nested filters)", async () => {
    let lastTiposUrl = "";
    server.use(
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json([SOURCE])),
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([FAMILY])),
      http.get(`${BASE_URL}/documents/tipos`, ({ request }) => {
        lastTiposUrl = request.url;
        return lastTiposUrl.includes("source_id=1")
          ? HttpResponse.json(["Sentencia"])
          : HttpResponse.json(["Auto", "Sentencia"]);
      }),
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }))
    );
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByLabelText("Tipo")).toHaveTextContent("Auto"));

    await user.selectOptions(screen.getByLabelText("Fuente"), "1");

    await waitFor(() => expect(lastTiposUrl).toContain("source_id=1"));
    await waitFor(() => expect(screen.getByLabelText("Tipo")).not.toHaveTextContent("Auto"));
    expect(screen.getByLabelText("Tipo")).toHaveTextContent("Sentencia");
  });

  it("refetches with the tipo filter applied, using a dropdown populated from the API", async () => {
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

    await waitFor(() => expect(screen.getByLabelText("Tipo")).toHaveTextContent("Auto"));
    expect(screen.getByLabelText("Tipo")).toHaveTextContent("Sentencia");

    await user.selectOptions(screen.getByLabelText("Tipo"), "Sentencia");
    await waitFor(() => expect(lastUrl).toContain("tipo=Sentencia"));
  });

  it("shows a date filter button and refetches with the publication date range applied", async () => {
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
    await user.click(screen.getByRole("button", { name: /fecha de publicación/i }));

    const desde = screen.getByLabelText("Desde");
    const hasta = screen.getByLabelText("Hasta");
    await user.type(desde, "2026-06-01");
    await waitFor(() => expect(lastUrl).toContain("f_public_from=2026-06-01"));

    await user.type(hasta, "2026-06-30");
    await waitFor(() => expect(lastUrl).toContain("f_public_to=2026-06-30"));
  });

  it("clears the date filter", async () => {
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
    await user.click(screen.getByRole("button", { name: /fecha de publicación/i }));
    await user.type(screen.getByLabelText("Desde"), "2026-06-01");
    await waitFor(() => expect(lastUrl).toContain("f_public_from=2026-06-01"));

    await user.click(screen.getByText("Limpiar"));

    await waitFor(() => expect(lastUrl).not.toContain("f_public_from"));
  });

  it("opens the preview dialog with the correct document when Previsualizar is clicked", async () => {
    mockFilterEndpoints();
    const user = userEvent.setup();
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({ items: [DOCUMENT, DOCUMENT_2], total: 2, limit: 50, offset: 0 })
      ),
      http.get(`${BASE_URL}/documents/2/preview`, () => HttpResponse.json({ url: "https://signed.example.com/doc2.pdf" }))
    );
    renderPage();

    await screen.findByText("Sentencia C-002-26");
    const row = screen.getByText("Sentencia C-002-26").closest("tr") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: /previsualizar/i }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Sentencia C-002-26")).toBeInTheDocument();
  });

  it("creates a bulk download and navigates to /bulk-downloads when 'Descarga masiva' is clicked", async () => {
    mockFilterEndpoints();
    let bulkDownloadCreated = false;
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 })),
      http.post(`${BASE_URL}/bulk-downloads`, () => {
        bulkDownloadCreated = true;
        return HttpResponse.json(
          { id: 1, status: "pending", document_count: 0, failed_count: 0, error_message: null, started_at: null, finished_at: null, created_at: "2026-07-16T00:00:00Z" },
          { status: 202 }
        );
      })
    );
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/documents"]}>
          <Routes>
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/bulk-downloads" element={<div>Página de descargas masivas</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await user.click(screen.getByRole("button", { name: /descarga masiva/i }));

    await waitFor(() => expect(bulkDownloadCreated).toBe(true));
    expect(await screen.findByText("Página de descargas masivas")).toBeInTheDocument();
  });

  it("seeds the Agregado filter with today's date when arriving with downloadedToday state, and sends it to the API", async () => {
    mockFilterEndpoints();
    let capturedUrl: URL | undefined;
    server.use(
      http.get(`${BASE_URL}/documents`, ({ request }) => {
        capturedUrl = new URL(request.url);
        return HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 });
      })
    );

    renderPageWithTodayState();

    await screen.findByText("Sentencia C-001-26");

    const today = todayDateString();
    const todayFormatted = formatDate(today);

    await waitFor(() => expect(capturedUrl?.searchParams.get("downloaded_from")).toBe(today));
    expect(capturedUrl?.searchParams.get("downloaded_to")).toBe(today);

    const agregadoButton = screen.getByRole("button", { name: /Agregado/ });
    expect(agregadoButton.className).toMatch(/border-sello/);
    expect(agregadoButton.textContent).toContain(todayFormatted);
  });

  it("shows a case badge only for documents with case_document_count over 1, and opens the preview dialog with the case's members in chronological order on click", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, ({ request }) => {
        const url = new URL(request.url);
        if (url.searchParams.get("title_exact")) {
          // The API returns newest-first by default — the frontend must reverse this.
          return HttpResponse.json({
            items: [CASE_DOCUMENT_3, CASE_DOCUMENT_2, CASE_DOCUMENT_1],
            total: 3,
            limit: 50,
            offset: 0,
          });
        }
        // CASE_DOCUMENT_2 (the middle document chronologically, not the first
        // or last) is the row rendered/clicked here — this proves the dialog's
        // initial index is computed from the clicked document's own position,
        // not hardcoded to 0 (which CASE_DOCUMENT_1, the oldest, could mask).
        return HttpResponse.json({
          items: [CASE_DOCUMENT_2, DOCUMENT],
          total: 2,
          limit: 50,
          offset: 0,
        });
      }),
      // Opening DocumentPreviewDialog fires these two queries (content_type is
      // "application/pdf", so the preview query is enabled) — both must be mocked
      // or MSW's onUnhandledRequest: "error" setup (src/test/setup.ts) fails the test
      // on the real click, independent of whether the case-grouping logic is correct.
      http.get(`${BASE_URL}/documents/:id/preview`, () => HttpResponse.json({ url: "https://example.com/preview.pdf" })),
      http.get(`${BASE_URL}/documents/:id/versions`, () => HttpResponse.json([]))
    );

    renderPage();

    const user = userEvent.setup();
    const caseTitleButton = await screen.findByRole("button", { name: "T_BTA_11001_31_03_048_2022_00418_02" });

    // Exactly one badge among the two rendered rows (CASE_DOCUMENT_2 has a case,
    // the plain DOCUMENT fixture has no case_document_count set at all) — proves
    // the badge is conditional, not just present in the fixture, and doesn't fire
    // when case_document_count is undefined.
    expect(screen.getAllByText(/^\d+ actuaciones$/)).toHaveLength(1);
    expect(screen.getByText("3 actuaciones")).toBeInTheDocument();

    await user.click(caseTitleButton);

    const dialog = await screen.findByRole("dialog");
    // CASE_DOCUMENT_2 (2026-06-30) is the middle document chronologically —
    // index 1 after reversing the newest-first [CASE_DOCUMENT_3, CASE_DOCUMENT_2,
    // CASE_DOCUMENT_1] array to [CASE_DOCUMENT_1, CASE_DOCUMENT_2, CASE_DOCUMENT_3].
    // Asserting on its exact formatted date (not just "jun", which both June dates
    // share) proves findIndex located the clicked document itself rather than a
    // hardcoded 0 (which would show CASE_DOCUMENT_1's 2026-06-16 instead).
    expect(within(dialog).getByText(formatDate(CASE_DOCUMENT_2.f_public), { exact: false })).toBeInTheDocument();

    // Clicking "next" from the middle document must move forward chronologically
    // to CASE_DOCUMENT_3 (2026-07-17, the newest). If the array were left in its
    // original newest-first API order (i.e. .reverse() were removed), "next" from
    // index 1 would instead move toward CASE_DOCUMENT_1 (the oldest), so this
    // assertion would fail — unlike asserting only the initial index, which can't
    // distinguish the two orderings.
    await user.click(within(dialog).getByRole("button", { name: "Siguiente" }));

    expect(
      await within(dialog).findByText(formatDate(CASE_DOCUMENT_3.f_public), { exact: false })
    ).toBeInTheDocument();
  });

  it("opens the case dialog (not the single-document one) when clicking Previsualizar on a case row", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, ({ request }) => {
        const url = new URL(request.url);
        if (url.searchParams.get("title_exact")) {
          return HttpResponse.json({
            items: [CASE_DOCUMENT_3, CASE_DOCUMENT_2, CASE_DOCUMENT_1],
            total: 3,
            limit: 50,
            offset: 0,
          });
        }
        // The general listing is already collapsed to just this one row for the
        // case (server-side behavior) — this is the only item, so if the
        // "Previsualizar" button opened the OLD single-document dialog (bound to
        // this list), there would be nothing to navigate to at all.
        return HttpResponse.json({ items: [CASE_DOCUMENT_2], total: 1, limit: 50, offset: 0 });
      }),
      http.get(`${BASE_URL}/documents/:id/preview`, () => HttpResponse.json({ url: "https://example.com/preview.pdf" })),
      http.get(`${BASE_URL}/documents/:id/versions`, () => HttpResponse.json([]))
    );

    renderPage();

    const user = userEvent.setup();
    const previsualizarButton = await screen.findByRole("button", { name: /Previsualizar/ });
    await user.click(previsualizarButton);

    const dialog = await screen.findByRole("dialog");
    // Proves the dialog opened with the whole case, not just CASE_DOCUMENT_2 alone:
    // "Siguiente" must move to CASE_DOCUMENT_3, which is only possible if the
    // dialog's document list came from the title_exact fetch (3 items), not the
    // single-item general listing.
    await user.click(within(dialog).getByRole("button", { name: "Siguiente" }));

    expect(
      await within(dialog).findByText(formatDate(CASE_DOCUMENT_3.f_public), { exact: false })
    ).toBeInTheDocument();
  });

  it("keeps the existing filter-by-title click behavior for documents without a case", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 })
      )
    );

    renderPage();

    const user = userEvent.setup();
    const titleButton = await screen.findByRole("button", { name: DOCUMENT.title });
    await user.click(titleButton);

    const searchInput = screen.getByPlaceholderText("Buscar por título");
    expect(searchInput).toHaveValue(DOCUMENT.title);
  });
});
