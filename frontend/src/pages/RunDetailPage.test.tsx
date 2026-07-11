import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
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
});
