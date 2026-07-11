import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { OverviewPage } from "./OverviewPage";

const BASE_URL = "http://localhost:8000";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("OverviewPage", () => {
  it("renders summary counts and the most recent runs", async () => {
    server.use(
      http.get(`${BASE_URL}/sources`, () =>
        HttpResponse.json([
          { id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: true },
          { id: 2, family_key: "consejo_estado", name: "Consejo de Estado", family_params: {}, active: true },
        ])
      ),
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
      ),
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [], total: 12, limit: 1, offset: 0 }))
    );

    renderPage();

    expect(await screen.findByText("1")).toBeInTheDocument();
    expect(await screen.findByText("12")).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument();
  });
});
