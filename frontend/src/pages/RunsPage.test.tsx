import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { RunsPage } from "./RunsPage";

const BASE_URL = "http://localhost:8000";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RunsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const RUN = {
  id: 1,
  triggered_by: "manual",
  status: "running",
  fini: null,
  ffin: null,
  cancel_requested: false,
  started_at: null,
  finished_at: null,
  created_at: "2026-07-10T00:00:00Z",
};

describe("RunsPage", () => {
  it("renders the fetched runs with a status badge", async () => {
    server.use(
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/runs`, () => HttpResponse.json([RUN]))
    );

    renderPage();

    expect(await screen.findByText("running")).toBeInTheDocument();
  });

  it("polls again while a run is not completed, and stops once it is", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let callCount = 0;
    server.use(
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/runs`, () => {
        callCount += 1;
        return HttpResponse.json([{ ...RUN, status: callCount >= 2 ? "completed" : "running" }]);
      })
    );

    renderPage();
    await waitFor(() => expect(callCount).toBe(1));

    await vi.advanceTimersByTimeAsync(4100);
    await waitFor(() => expect(callCount).toBe(2));

    await vi.advanceTimersByTimeAsync(4100);
    expect(callCount).toBe(2);

    vi.useRealTimers();
  });
});

describe("RunsPage — new run", () => {
  function mockSourceFamilies() {
    server.use(
      http.get(`${BASE_URL}/source-families`, () =>
        HttpResponse.json([
          { key: "jep", display_name: "JEP", description: null, filters_by_publication_date: true },
          { key: "constitucional", display_name: "Corte Constitucional", description: null, filters_by_publication_date: false },
        ])
      )
    );
  }

  it("creates a run with the selected sources and navigates to its detail page", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    let createdBody: unknown;
    mockSourceFamilies();
    server.use(
      http.get(`${BASE_URL}/sources`, () =>
        HttpResponse.json([{ id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: true }])
      ),
      http.get(`${BASE_URL}/runs`, () => HttpResponse.json([])),
      http.post(`${BASE_URL}/runs`, async ({ request }) => {
        createdBody = await request.json();
        return HttpResponse.json({ ...RUN, id: 42 }, { status: 202 });
      })
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Nuevo run"));
    await user.click(screen.getByLabelText("Corte Constitucional"));
    await user.click(screen.getByText("Iniciar run"));

    await waitFor(() => expect(createdBody).toMatchObject({ source_ids: [1] }));
  });

  it("indicates whether each source filters by fecha de publicación or providencia", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    mockSourceFamilies();
    server.use(
      http.get(`${BASE_URL}/sources`, () =>
        HttpResponse.json([
          { id: 1, family_key: "jep", name: "JEP", family_params: {}, active: true },
          { id: 2, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: true },
        ])
      ),
      http.get(`${BASE_URL}/runs`, () => HttpResponse.json([]))
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Nuevo run"));
    await screen.findByLabelText("JEP");

    const jepRow = screen.getByLabelText("JEP").closest("label") as HTMLElement;
    const constitucionalRow = screen.getByLabelText("Corte Constitucional").closest("label") as HTMLElement;

    expect(jepRow).toHaveTextContent("Filtra por fecha de publicación");
    expect(constitucionalRow).toHaveTextContent("Filtra por fecha de providencia");
  });
});
