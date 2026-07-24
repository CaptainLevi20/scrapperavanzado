import { describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { DashboardPage } from "./DashboardPage";
import type { Document } from "../api/types";

const BASE_URL = "http://localhost:8000";

const SOURCES = [
  { id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: true },
  { id: 2, family_key: "samai", name: "Consejo de Estado", family_params: {}, active: true },
];

function makeDoc(overrides: Partial<Document> = {}): Document {
  return {
    id: 1,
    doc_id: "doc-1",
    source_id: 1,
    title: "Sentencia C-001-26",
    tipo: "Resolución",
    seccion: null,
    especialidad: null,
    magistrado: null,
    detalle: null,
    f_public: "2026-06-01",
    f_providencia: null,
    source_url: null,
    storage_bucket: "bucket",
    storage_key: "key.pdf",
    content_type: "application/pdf",
    file_size_bytes: 1024,
    review_status: "pending",
    reviewed_at: null,
    downloaded_at: new Date().toISOString(),
    ...overrides,
  };
}

// Novedades table fixture — separate from the (now server-aggregated) stats.
const DOCS: Document[] = [
  makeDoc({ id: 1, title: "Resolución 1", tipo: "Resolución", source_id: 1, f_public: "2026-06-01" }),
  makeDoc({ id: 2, title: "Resolución 2", tipo: "Resolución", source_id: 1, f_public: "2026-06-15" }),
  makeDoc({ id: 3, title: "Circular 1", tipo: "Circular", source_id: 2, f_public: "2026-01-10", review_status: "useful" }),
];

const STATS = {
  by_family: [
    { key: "constitucional", display_name: "Corte Constitucional", count: 2 },
    { key: "samai", display_name: "SAMAI", count: 1 },
  ],
  by_tipo: [
    { tipo: "Resolución", count: 2 },
    { tipo: "Circular", count: 1 },
  ],
  by_month: Array.from({ length: 12 }, (_, index) => (index === 0 ? 1 : index === 5 ? 2 : 0)),
  year: 2026,
  available_years: [2026],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function mockDocuments() {
  server.use(
    http.get(`${BASE_URL}/documents/stats`, ({ request }) => {
      const url = new URL(request.url);
      const yearParam = url.searchParams.get("year");
      return HttpResponse.json({ ...STATS, year: yearParam ? Number(yearParam) : STATS.year });
    }),
    http.get(`${BASE_URL}/documents`, ({ request }) => {
      const url = new URL(request.url);
      if (url.searchParams.get("review_status") === "pending") {
        return HttpResponse.json({ items: [], total: 2, limit: 1, offset: 0 });
      }
      if (url.searchParams.get("limit") === "1") {
        return HttpResponse.json({ items: [], total: 12, limit: 1, offset: 0 });
      }
      // novedades fetch (limit=8)
      return HttpResponse.json({ items: DOCS, total: DOCS.length, limit: 8, offset: 0 });
    })
  );
}

function mockBaselines() {
  server.use(
    http.get(`${BASE_URL}/sources`, () => HttpResponse.json(SOURCES)),
    http.get(`${BASE_URL}/runs`, () => HttpResponse.json([]))
  );
}

function statCardValue(label: string): HTMLElement {
  // StatCard labels are always <p> tags; scoping by selector disambiguates
  // from the same words appearing elsewhere (e.g. "Sin revisar" also shows
  // up as a <span> review stamp in the Novedades table).
  const labelNode = screen.getByText(label, { selector: "p" });
  const card = labelNode.closest(".rounded-lg");
  if (!card) throw new Error(`Could not find the StatCard containing "${label}"`);
  return within(card as HTMLElement).getByText(/^\d|^—$/);
}

describe("DashboardPage", () => {
  it("renders KPI cards with real counts, including Sin revisar", async () => {
    mockBaselines();
    mockDocuments();

    renderPage();

    await screen.findByText("Documentos totales");
    await waitFor(() => expect(statCardValue("Documentos totales")).toHaveTextContent("12"));
    await waitFor(() => expect(statCardValue("Sin revisar")).toHaveTextContent("2"));
  });

  it("renders the Documentos por tipo and por familia charts from the aggregated stats endpoint", async () => {
    mockBaselines();
    mockDocuments();

    renderPage();

    const tipoHeading = await screen.findByText("Documentos por tipo");
    const tipoCard = tipoHeading.closest(".rounded-lg") as HTMLElement;
    await waitFor(() => expect(within(tipoCard).getByText("Resolución")).toBeInTheDocument());
    expect(within(tipoCard).getByText("Circular")).toBeInTheDocument();

    const familyHeading = screen.getByText("Documentos por familia");
    const familyCard = familyHeading.closest(".rounded-lg") as HTMLElement;
    await waitFor(() => expect(within(familyCard).getByText("Corte Constitucional")).toBeInTheDocument());
    expect(within(familyCard).getByText("SAMAI")).toBeInTheDocument();
  });

  it("offers only the years the stats endpoint reports as available", async () => {
    mockBaselines();
    mockDocuments();

    renderPage();

    await screen.findByText("Actividad mensual");
    const yearSelect = await screen.findByLabelText("Año");
    expect(yearSelect).toHaveValue("2026");

    // Only one year (2026) is present in the STATS fixture, so this just
    // confirms the selector is wired to the actual data range.
    expect(within(yearSelect).getAllByRole("option")).toHaveLength(1);
  });

  it("renders the Novedades table with the most recent documents", async () => {
    mockBaselines();
    mockDocuments();

    renderPage();

    const novedadesHeading = await screen.findByText("Novedades");
    const novedadesSection = novedadesHeading.closest("div.space-y-3") as HTMLElement;
    await waitFor(() => expect(within(novedadesSection).getByText("Circular 1")).toBeInTheDocument());
    expect(within(novedadesSection).getByText("Consejo de Estado")).toBeInTheDocument();
    expect(within(novedadesSection).getByText("Útil")).toBeInTheDocument();
  });

  it("requests Novedades scoped to today's downloaded_at range, and shows a today-specific empty state", async () => {
    mockBaselines();
    server.use(
      http.get(`${BASE_URL}/documents/stats`, () => HttpResponse.json(STATS)),
      http.get(`${BASE_URL}/documents`, ({ request }) => {
        const url = new URL(request.url);
        if (url.searchParams.get("review_status") === "pending") {
          return HttpResponse.json({ items: [], total: 2, limit: 1, offset: 0 });
        }
        if (url.searchParams.get("limit") === "1") {
          return HttpResponse.json({ items: [], total: 12, limit: 1, offset: 0 });
        }
        // novedades fetch (limit=8) — assert it now carries the today range
        expect(url.searchParams.get("downloaded_from")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
        expect(url.searchParams.get("downloaded_to")).toBe(url.searchParams.get("downloaded_from"));
        return HttpResponse.json({ items: [], total: 0, limit: 8, offset: 0 });
      })
    );

    renderPage();

    const novedadesHeading = await screen.findByText("Novedades");
    const novedadesSection = novedadesHeading.closest("div.space-y-3") as HTMLElement;
    await waitFor(() => expect(within(novedadesSection).getByText("No han llegado documentos hoy.")).toBeInTheDocument());
  });

  it("renders the most recent runs", async () => {
    server.use(
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json(SOURCES)),
      http.get(`${BASE_URL}/runs`, () =>
        HttpResponse.json([
          {
            id: 1,
            triggered_by: "manual",
            status: "completed",
            fini: null,
            ffin: null,
            cancel_requested: false,
            started_at: null,
            finished_at: null,
            created_at: new Date().toISOString(),
          },
        ])
      )
    );
    mockDocuments();

    renderPage();

    expect(await screen.findByText("#1")).toBeInTheDocument();
  });

  it("paginates through all active sources instead of capping the count at 100", async () => {
    server.use(
      http.get(`${BASE_URL}/sources`, ({ request }) => {
        const url = new URL(request.url);
        const offset = Number(url.searchParams.get("offset") ?? "0");
        if (offset === 0) {
          return HttpResponse.json(
            Array.from({ length: 100 }, (_, index) => ({
              id: index + 1,
              family_key: "constitucional",
              name: `Fuente ${index + 1}`,
              family_params: {},
              active: true,
            }))
          );
        }
        return HttpResponse.json([
          { id: 101, family_key: "constitucional", name: "Fuente 101", family_params: {}, active: true },
        ]);
      }),
      http.get(`${BASE_URL}/runs`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/documents/stats`, () => HttpResponse.json({ ...STATS, by_family: [], by_tipo: [] })),
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [], total: 0, limit: 1, offset: 0 }))
    );

    renderPage();

    await waitFor(() => expect(statCardValue("Fuentes activas")).toHaveTextContent("101"));
  });
});
