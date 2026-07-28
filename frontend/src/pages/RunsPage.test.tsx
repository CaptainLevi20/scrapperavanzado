import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { delay, http, HttpResponse } from "msw";
import { server } from "../test/server";
import { MAX_POLL_AGE_MS } from "../lib/runStatus";
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
  // Freshly created — well under the 30-minute stale-poll cutoff, so tests
  // that expect polling to keep going aren't accidentally starved by it.
  created_at: new Date().toISOString(),
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

  it("does not show 'no runs' while the first request is still in flight", async () => {
    server.use(
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/runs`, async () => {
        await delay(50);
        return HttpResponse.json([]);
      })
    );

    renderPage();

    expect(screen.queryByText("No hay runs que coincidan con este filtro.")).not.toBeInTheDocument();
    expect(await screen.findByText("No hay runs que coincidan con este filtro.")).toBeInTheDocument();
  });

  it("enables Siguiente when there really is another page, and only renders one page's worth of rows", async () => {
    // Regression test: /runs has no total count to compare against, so
    // "Siguiente" used to just check whether the current page happened to come
    // back full — the frontend now asks for one extra row (PAGE_SIZE + 1) to
    // find out whether a next page genuinely exists.
    const runs = Array.from({ length: 21 }, (_, i) => ({ ...RUN, id: i + 1, status: "completed" }));
    let lastUrl = "";
    server.use(
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/runs`, ({ request }) => {
        lastUrl = request.url;
        return HttpResponse.json(runs);
      })
    );

    renderPage();

    await screen.findByText("#1");
    expect(new URL(lastUrl).searchParams.get("limit")).toBe("21"); // PAGE_SIZE (20) + 1
    expect(screen.queryByText("#21")).not.toBeInTheDocument(); // the extra row is never rendered
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeEnabled();
  });

  it("disables Siguiente when the response doesn't fill a whole extra row past the page size", async () => {
    const runs = Array.from({ length: 5 }, (_, i) => ({ ...RUN, id: i + 1, status: "completed" }));
    server.use(
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/runs`, () => HttpResponse.json(runs))
    );

    renderPage();

    await screen.findByText("#1");
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeDisabled();
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

  it("also stops polling once a run is failed, not just completed", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let callCount = 0;
    server.use(
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/runs`, () => {
        callCount += 1;
        return HttpResponse.json([{ ...RUN, status: callCount >= 2 ? "failed" : "running" }]);
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

  it("stops polling and warns instead of hammering the server when a run is stuck", async () => {
    // Regression test: a worker process that dies outright (killed, crashed,
    // container restarted) never writes "failed" — the run just stays
    // "running" forever. Before this fix, polling every 4s would continue
    // for as long as the tab stayed open.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const staleCreatedAt = new Date(Date.now() - MAX_POLL_AGE_MS - 60_000).toISOString();
    let callCount = 0;
    server.use(
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/runs`, () => {
        callCount += 1;
        return HttpResponse.json([{ ...RUN, status: "running", created_at: staleCreatedAt }]);
      })
    );

    renderPage();
    await waitFor(() => expect(callCount).toBe(1));
    expect(
      await screen.findByText(/lleva mucho tiempo sin actualizarse/)
    ).toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(4100);
    expect(callCount).toBe(1); // no repitió la consulta automática

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
