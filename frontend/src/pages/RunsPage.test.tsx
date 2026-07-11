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
