import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { delay, http, HttpResponse } from "msw";
import { server } from "../test/server";
import { DocumentsPage } from "./DocumentsPage";
import { todayDateString, formatDate } from "../lib/formatters";

// The preview dialog renders PdfViewer, which pulls in pdf.js — unrunnable under
// jsdom. These tests only exercise the table/filters/pagination and (for the
// preview) the dialog header, never the PDF canvas, so stub the viewer out.
vi.mock("../components/PdfViewer", () => ({
  PdfViewer: ({ title }: { title: string }) => <div title={`Vista previa de ${title}`} />,
}));

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
  nombre: "Sentencia C-001-26",
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
  nombre: "Sentencia C-002-26",
};

const CASE_DOCUMENT_1 = {
  ...DOCUMENT,
  id: 10,
  doc_id: "case-1",
  title: "T_BTA_11001_31_03_048_2022_00418_02",
  nombre: "T_BTA_11001_31_03_048_2022_00418_02",
  f_public: "2026-06-16",
  case_document_count: 3,
};

const CASE_DOCUMENT_2 = {
  ...DOCUMENT,
  id: 11,
  doc_id: "case-2",
  title: "T_BTA_11001_31_03_048_2022_00418_02",
  nombre: "T_BTA_11001_31_03_048_2022_00418_02",
  f_public: "2026-06-30",
  case_document_count: 3,
};

const CASE_DOCUMENT_3 = {
  ...DOCUMENT,
  id: 12,
  doc_id: "case-3",
  title: "T_BTA_11001_31_03_048_2022_00418_02",
  nombre: "T_BTA_11001_31_03_048_2022_00418_02",
  f_public: "2026-07-17",
  case_document_count: 3,
};

const CASE_B_DOCUMENT_1 = {
  ...DOCUMENT,
  id: 20,
  doc_id: "case-b-1",
  title: "T_BTA_11001_99_99_099_2022_00999_02",
  nombre: "T_BTA_11001_99_99_099_2022_00999_02",
  f_public: "2026-05-01",
  case_document_count: 2,
};

const CASE_B_DOCUMENT_2 = {
  ...DOCUMENT,
  id: 21,
  doc_id: "case-b-2",
  title: "T_BTA_11001_99_99_099_2022_00999_02",
  nombre: "T_BTA_11001_99_99_099_2022_00999_02",
  f_public: "2026-05-15",
  case_document_count: 2,
};

const SOURCE = { id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: true };
const FAMILY = { key: "constitucional", display_name: "Corte Constitucional", description: null };

function mockFilterEndpoints() {
  server.use(
    http.get(`${BASE_URL}/sources`, () => HttpResponse.json([SOURCE])),
    http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([FAMILY])),
    http.get(`${BASE_URL}/documents/tipos`, () => HttpResponse.json(["Auto", "Sentencia"])),
    http.get(`${BASE_URL}/documents/secciones`, () => HttpResponse.json([])),
    http.get(`${BASE_URL}/documents/especialidades`, () => HttpResponse.json([])),
    http.get(`${BASE_URL}/documents/magistrados`, () => HttpResponse.json([]))
  );
}

describe("DocumentsPage", () => {
  it("shows the nombre canónico in the table's name cell, not the raw title field", async () => {
    mockFilterEndpoints();
    const document = { ...DOCUMENT, title: "Título de trabajo crudo", nombre: "11001_20260731_v1" };
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [document], total: 1, limit: 50, offset: 0 }))
    );

    renderPage();

    expect(await screen.findByText("11001_20260731_v1")).toBeInTheDocument();
    expect(screen.queryByText("Título de trabajo crudo")).not.toBeInTheDocument();
  });

  it("renders fetched documents", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 }))
    );

    renderPage();

    expect(await screen.findByText("Sentencia C-001-26")).toBeInTheDocument();
  });

  it("disables Siguiente on a full last page, even though the page itself came back full", async () => {
    // Regression test: the button used to only check whether the CURRENT page
    // came back full (items.length < PAGE_SIZE) — a full last page (total
    // exactly divisible by PAGE_SIZE, e.g. exactly 50 of 50) used to leave it
    // wrongly enabled, leading to an empty page if clicked. The backend does
    // return a real `total`, which the button now compares against instead.
    mockFilterEndpoints();
    const items = Array.from({ length: 50 }, (_, i) => ({ ...DOCUMENT, id: i + 1, doc_id: `doc-${i + 1}` }));
    server.use(http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items, total: 50, limit: 50, offset: 0 })));

    renderPage();

    expect(await screen.findAllByText("Sentencia C-001-26")).toHaveLength(50);
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeDisabled();
  });

  it("enables Siguiente when there are more matching documents beyond the current page", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [DOCUMENT], total: 120, limit: 50, offset: 0 }))
    );

    renderPage();

    await screen.findByText("Sentencia C-001-26");
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeEnabled();
  });

  it("does not show 'no documents' while the first request is still in flight", async () => {
    // Regression test: the empty-state check used to only look at
    // data?.items.length, which is 0/undefined while loading too — so it
    // flashed "No hay documentos" for every page load, even ones that end up
    // with real results.
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, async () => {
        await delay(50);
        return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
      })
    );

    renderPage();

    expect(screen.queryByText("No hay documentos que coincidan con estos filtros.")).not.toBeInTheDocument();
    expect(await screen.findByText("No hay documentos que coincidan con estos filtros.")).toBeInTheDocument();
  });

  it("shows skeleton placeholder rows before the results while the documents are loading", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, async () => {
        await delay(50);
        return HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 });
      })
    );

    const { container } = renderPage();

    // Before the results arrive, the table body shows placeholder rows — not a
    // blank table — so the user gets immediate feedback that documents are on
    // their way.
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);

    // Once the real rows load, the placeholders are gone.
    expect(await screen.findByText("Sentencia C-001-26")).toBeInTheDocument();
    expect(container.querySelectorAll('[data-slot="skeleton"]')).toHaveLength(0);
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

  it("debounces the title search so typing a term fires one request, not one per keystroke", async () => {
    mockFilterEndpoints();
    let documentsRequests = 0;
    let lastUrl = "";
    server.use(
      http.get(`${BASE_URL}/documents`, ({ request }) => {
        documentsRequests += 1;
        lastUrl = request.url;
        return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
      })
    );
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(documentsRequests).toBeGreaterThan(0));
    const beforeTyping = documentsRequests;

    await user.type(screen.getByPlaceholderText(/buscar por t.tulo/i), "constitucional");

    await waitFor(() => expect(lastUrl).toContain("title=constitucional"));
    // A per-keystroke implementation would have fired ~14 requests for this
    // 14-character term; debounced, the burst collapses to a single trailing one.
    expect(documentsRequests - beforeTyping).toBeLessThanOrEqual(2);
  });

  it("shows the current range and total (thousands-grouped) in the pagination footer", async () => {
    mockFilterEndpoints();
    const items = Array.from({ length: 50 }, (_, i) => ({ ...DOCUMENT, id: i + 1, doc_id: `d${i}`, title: `Doc ${i + 1}` }));
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items, total: 9608, limit: 50, offset: 0 }))
    );
    const user = userEvent.setup();
    renderPage();

    // Page 1 of many: "Mostrando 1–50 de 9.608" (es-CO groups thousands with a dot).
    expect(await screen.findByText("1–50")).toBeInTheDocument();
    expect(screen.getByText("9.608")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Siguiente" }));

    // Advancing a page shifts the range, keeping the same total.
    expect(await screen.findByText("51–100")).toBeInTheDocument();
    expect(screen.getByText("9.608")).toBeInTheDocument();
  });

  it("shows 'Sin documentos' in the footer when there are no results", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }))
    );
    renderPage();

    expect(await screen.findByText("Sin documentos")).toBeInTheDocument();
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

  it("renders the Especialidad/Proceso and Magistrado columns", async () => {
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

    // Consejo de Estado stores its "Clase de Proceso" in this same column, so
    // the header covers both meanings — not just medical/legal "especialidad".
    // Scoped to the columnheader role since the Task 5 filter bar now also has
    // an "Especialidad/Proceso" filter label with the same text.
    expect(screen.getByRole("columnheader", { name: "Especialidad/Proceso" })).toBeInTheDocument();
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
      http.get(`${BASE_URL}/documents/secciones`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/documents/especialidades`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/documents/magistrados`, () => HttpResponse.json([])),
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

  it("scopes the Sección dropdown to the selected Tipo, and resets Sección/Especialidad in cascade when they become invalid (nested filters)", async () => {
    let lastSeccionesUrl = "";
    server.use(
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json([SOURCE])),
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([FAMILY])),
      http.get(`${BASE_URL}/documents/tipos`, () => HttpResponse.json(["Auto", "Sentencia"])),
      http.get(`${BASE_URL}/documents/secciones`, ({ request }) => {
        lastSeccionesUrl = request.url;
        return lastSeccionesUrl.includes("tipo=Sentencia")
          ? HttpResponse.json(["SECCION PRIMERA"])
          : HttpResponse.json(["SECCION PRIMERA", "SECCION SEGUNDA"]);
      }),
      http.get(`${BASE_URL}/documents/especialidades`, ({ request }) => {
        const url = request.url;
        return url.includes("seccion=SECCION+SEGUNDA")
          ? HttpResponse.json(["Conciliación"])
          : HttpResponse.json(["Nulidad"]);
      }),
      http.get(`${BASE_URL}/documents/magistrados`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }))
    );
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByLabelText("Sección")).toHaveTextContent("SECCION SEGUNDA"));

    await user.selectOptions(screen.getByLabelText("Sección"), "SECCION SEGUNDA");
    await waitFor(() => expect(screen.getByLabelText("Especialidad/Proceso")).toHaveTextContent("Conciliación"));
    await user.selectOptions(screen.getByLabelText("Especialidad/Proceso"), "Conciliación");
    expect((screen.getByLabelText("Especialidad/Proceso") as HTMLSelectElement).value).toBe("Conciliación");

    await user.selectOptions(screen.getByLabelText("Tipo"), "Sentencia");

    await waitFor(() => expect(lastSeccionesUrl).toContain("tipo=Sentencia"));
    // "SECCION SEGUNDA" ya no es una opción válida bajo Tipo="Sentencia" (solo
    // queda "SECCION PRIMERA"), así que el filtro de Sección debe resetearse a
    // "Todas" — y ese reseteo, a su vez, invalida "Conciliación" en Especialidad
    // (que solo aplicaba bajo "SECCION SEGUNDA"), reseteándolo también en cascada.
    await waitFor(() => expect((screen.getByLabelText("Sección") as HTMLSelectElement).value).toBe(""));
    await waitFor(() => expect((screen.getByLabelText("Especialidad/Proceso") as HTMLSelectElement).value).toBe(""));
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

  it("shows the most recently clicked case, not a stale response from a case clicked just before it", async () => {
    // Regression test: opening a case dialog was a loose async call with no
    // token identifying the latest request. Clicking case A and then quickly
    // case B — with A's response arriving LATER than B's — used to let A's
    // stale response overwrite B's dialog once it finally resolved.
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, async ({ request }) => {
        const url = new URL(request.url);
        const titleExact = url.searchParams.get("title_exact");
        if (titleExact === CASE_DOCUMENT_1.title) {
          await delay(50); // case A: clicked first, resolves LAST
          return HttpResponse.json({
            items: [CASE_DOCUMENT_3, CASE_DOCUMENT_2, CASE_DOCUMENT_1],
            total: 3,
            limit: 50,
            offset: 0,
          });
        }
        if (titleExact === CASE_B_DOCUMENT_1.title) {
          return HttpResponse.json({
            items: [CASE_B_DOCUMENT_2, CASE_B_DOCUMENT_1],
            total: 2,
            limit: 50,
            offset: 0,
          });
        }
        return HttpResponse.json({ items: [CASE_DOCUMENT_2, CASE_B_DOCUMENT_1], total: 2, limit: 50, offset: 0 });
      }),
      http.get(`${BASE_URL}/documents/:id/preview`, () => HttpResponse.json({ url: "https://example.com/preview.pdf" })),
      http.get(`${BASE_URL}/documents/:id/versions`, () => HttpResponse.json([]))
    );

    renderPage();
    const user = userEvent.setup();

    const caseAButton = await screen.findByRole("button", { name: CASE_DOCUMENT_1.title });
    const caseBButton = screen.getByRole("button", { name: CASE_B_DOCUMENT_1.title });

    // Click A (slow), then click B (fast) without waiting for A's click to
    // finish first — this is what reproduces the race.
    void user.click(caseAButton);
    await user.click(caseBButton);

    const dialog = await screen.findByRole("dialog");
    // Must show case B's content (the last click), not case A's — even though
    // A's response resolves after B's.
    expect(within(dialog).getByText(formatDate(CASE_B_DOCUMENT_1.f_public), { exact: false })).toBeInTheDocument();

    // Give A's delayed response time to resolve too, and confirm it never
    // overwrote the dialog once it finally arrived.
    await new Promise((resolve) => setTimeout(resolve, 80));
    expect(within(dialog).getByText(formatDate(CASE_B_DOCUMENT_1.f_public), { exact: false })).toBeInTheDocument();
  });

  it("shows an error instead of silently doing nothing when opening a case fails", async () => {
    // Regression test: openCaseDialog had no try/catch — a failed fetch just
    // became an unhandled promise rejection, and the click appeared to do
    // nothing at all from the user's perspective.
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, ({ request }) => {
        const url = new URL(request.url);
        if (url.searchParams.get("title_exact")) {
          return HttpResponse.error();
        }
        return HttpResponse.json({ items: [CASE_DOCUMENT_2], total: 1, limit: 50, offset: 0 });
      })
    );

    renderPage();
    const user = userEvent.setup();

    const caseButton = await screen.findByRole("button", { name: CASE_DOCUMENT_2.title });
    await user.click(caseButton);

    expect(await screen.findByText(/no se pudo abrir el expediente/i)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
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

  it("shows a case-link note with a link to the timeline", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({
          items: [{ ...DOCUMENT, case_link_id: 5, case_link_other_source_name: "Consejo de Estado" }],
          total: 1,
          limit: 50,
          offset: 0,
        })
      )
    );

    renderPage();

    expect(await screen.findByText(/también aparece en: consejo de estado/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /ver línea de tiempo/i })).toHaveAttribute(
      "href",
      "/expedientes/5"
    );
  });

  it("shows no case-link note when the document has no case_link_id", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 })
      )
    );

    renderPage();

    await screen.findByText("Sentencia C-001-26");
    expect(screen.queryByText(/también aparece en:/i)).not.toBeInTheDocument();
  });
});
