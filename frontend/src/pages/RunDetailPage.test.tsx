import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { RunDetailPage } from "./RunDetailPage";

const BASE_URL = "http://localhost:8000";

function renderPage(runId = "1") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/runs/${runId}`]}>
        <Routes>
          <Route path="/runs/:runId" element={<RunDetailPage />} />
        </Routes>
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
  started_at: "2026-07-10T00:00:00Z",
  finished_at: null,
  created_at: "2026-07-10T00:00:00Z",
};

const RUN_SOURCE = { id: 1, run_id: 1, source_id: 5, status: "failed", docs_new: 2, docs_errors: 1, error_message: "timeout" };

describe("RunDetailPage", () => {
  it("renders the run header and its sources table", async () => {
    server.use(
      http.get(`${BASE_URL}/runs/1`, () => HttpResponse.json(RUN)),
      http.get(`${BASE_URL}/runs/1/sources`, () => HttpResponse.json([RUN_SOURCE]))
    );

    renderPage();

    expect(await screen.findByText("Run #1")).toBeInTheDocument();
    expect(screen.getByText("timeout")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shows the cancel button only while the run is not completed", async () => {
    server.use(
      http.get(`${BASE_URL}/runs/1`, () => HttpResponse.json({ ...RUN, status: "completed" })),
      http.get(`${BASE_URL}/runs/1/sources`, () => HttpResponse.json([]))
    );

    renderPage();

    await screen.findByText("Run #1");
    expect(screen.queryByText("Cancelar run")).not.toBeInTheDocument();
  });

  it("requests cancellation and disables the button afterwards", async () => {
    // The GET /runs/1 mock must be stateful: the button's label reads run.cancel_requested
    // from this query, and it only changes after the mutation's onSuccess invalidates and
    // refetches it — a static mock would never reflect the cancellation.
    let cancelRequested = false;
    server.use(
      http.get(`${BASE_URL}/runs/1`, () => HttpResponse.json({ ...RUN, cancel_requested: cancelRequested })),
      http.get(`${BASE_URL}/runs/1/sources`, () => HttpResponse.json([])),
      http.post(`${BASE_URL}/runs/1/cancel`, () => {
        cancelRequested = true;
        return HttpResponse.json({ ...RUN, cancel_requested: true });
      })
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Cancelar run"));

    expect(await screen.findByText("Cancelación solicitada")).toBeInTheDocument();
  });

  it("keeps polling run_sources even when the first response is an empty array", async () => {
    // Real bug found by running the app end-to-end: orchestrate_run is queued as a
    // separate Celery task, so GET /runs/:id/sources can return [] before any
    // RunSource rows exist yet. If polling stopped on "no active items" without
    // also checking whether the run itself is still in progress, an empty first
    // response would permanently freeze the table even after real rows appear.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let sourcesCallCount = 0;
    server.use(
      http.get(`${BASE_URL}/runs/1`, () => HttpResponse.json({ ...RUN, status: "running" })),
      http.get(`${BASE_URL}/runs/1/sources`, () => {
        sourcesCallCount += 1;
        if (sourcesCallCount === 1) return HttpResponse.json([]);
        return HttpResponse.json([RUN_SOURCE]);
      })
    );

    renderPage();
    await waitFor(() => expect(sourcesCallCount).toBe(1));

    await vi.advanceTimersByTimeAsync(4100);
    await waitFor(() => expect(sourcesCallCount).toBeGreaterThan(1));

    expect(await screen.findByText("timeout")).toBeInTheDocument();
    vi.useRealTimers();
  });

  it("does not fire queries when runId is not a valid number", async () => {
    // The component does `Number(runId)`, so an invalid runId like "abc" becomes NaN.
    // If the `enabled: !Number.isNaN(id)` guard were missing or broken, the real
    // requests fired would be GET /runs/NaN and /runs/NaN/sources — NOT /runs/abc.
    // These handlers must watch those actual URLs, or the test proves nothing.
    let runQueryCalled = false;
    let sourcesQueryCalled = false;

    server.use(
      http.get(`${BASE_URL}/runs/NaN`, () => {
        runQueryCalled = true;
        return HttpResponse.json(RUN);
      }),
      http.get(`${BASE_URL}/runs/NaN/sources`, () => {
        sourcesQueryCalled = true;
        return HttpResponse.json([RUN_SOURCE]);
      })
    );

    renderPage("abc");

    // Wait for the error message to appear
    expect(await screen.findByText("Run inválido.")).toBeInTheDocument();

    // Verify that neither endpoint was called
    expect(runQueryCalled).toBe(false);
    expect(sourcesQueryCalled).toBe(false);
  });
});
