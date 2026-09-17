import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { delay, http, HttpResponse } from "msw";
import { server } from "../test/server";
import { ReportsPage } from "./ReportsPage";

const BASE_URL = "http://localhost:8000";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ReportsPage />
    </QueryClientProvider>
  );
}

const COMPLETED = {
  id: 1,
  period: "2026-08-01",
  status: "completed",
  triggered_by: "scheduled",
  error_message: null,
  started_at: "2026-09-01T03:30:00Z",
  finished_at: "2026-09-01T03:31:00Z",
  created_at: "2026-09-01T03:30:00Z",
};

describe("ReportsPage", () => {
  it("renders the fetched reports with month and status", async () => {
    server.use(http.get(`${BASE_URL}/reports`, () => HttpResponse.json([COMPLETED])));

    renderPage();

    expect(await screen.findByText("Agosto 2026")).toBeInTheDocument();
    expect(screen.getByText("Completado")).toBeInTheDocument();
  });

  it("shows an empty state when there is no history yet", async () => {
    server.use(http.get(`${BASE_URL}/reports`, () => HttpResponse.json([])));

    renderPage();

    expect(await screen.findByText(/todav.a no se ha generado ning.n reporte/i)).toBeInTheDocument();
  });

  it("does not show the empty state while the first request is still in flight", async () => {
    server.use(
      http.get(`${BASE_URL}/reports`, async () => {
        await delay(50);
        return HttpResponse.json([]);
      })
    );

    renderPage();

    expect(screen.queryByText(/todav.a no se ha generado ning.n reporte/i)).not.toBeInTheDocument();
    expect(await screen.findByText(/todav.a no se ha generado ning.n reporte/i)).toBeInTheDocument();
  });

  it("generates a report for the selected month", async () => {
    let posted: unknown = null;
    server.use(
      http.get(`${BASE_URL}/reports`, () => HttpResponse.json([])),
      http.post(`${BASE_URL}/reports`, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json({ ...COMPLETED, id: 2, status: "pending", period: "2026-07-01" }, { status: 202 });
      })
    );
    const user = userEvent.setup();
    renderPage();

    const monthInput = await screen.findByLabelText(/mes/i);
    await user.clear(monthInput);
    await user.type(monthInput, "2026-07");
    await user.click(screen.getByRole("button", { name: /generar/i }));

    await waitFor(() => expect(posted).toEqual({ period: "2026-07-01" }));
  });

  it("shows an error banner when generation is rejected", async () => {
    server.use(
      http.get(`${BASE_URL}/reports`, () => HttpResponse.json([])),
      http.post(`${BASE_URL}/reports`, () =>
        HttpResponse.json({ detail: "No se puede generar el reporte de un mes que no ha terminado." }, { status: 400 })
      )
    );
    const user = userEvent.setup();
    renderPage();

    const monthInput = await screen.findByLabelText(/mes/i);
    await user.clear(monthInput);
    await user.type(monthInput, "2026-07");
    await user.click(screen.getByRole("button", { name: /generar/i }));

    expect(await screen.findByText("No se puede generar el reporte de un mes que no ha terminado.")).toBeInTheDocument();
  });

  it("shows a Descargar button only when completed, wired to the presigned url", async () => {
    server.use(
      http.get(`${BASE_URL}/reports`, () => HttpResponse.json([COMPLETED])),
      http.get(`${BASE_URL}/reports/1/download`, () => HttpResponse.json({ url: "https://signed.example.com/1.pdf" }))
    );
    server.use(http.get("https://signed.example.com/1.pdf", () => HttpResponse.text("contenido")));
    const clickSpy = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    const createElementSpy = vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const element = originalCreateElement(tag);
      if (tag === "a") element.click = clickSpy;
      return element;
    });

    const user = userEvent.setup();
    renderPage();

    const button = await screen.findByRole("button", { name: /descargar/i });
    await user.click(button);

    await waitFor(() => expect(clickSpy).toHaveBeenCalledOnce());
    createElementSpy.mockRestore();
  });

  it("shows the error message instead of a download button for a failed report", async () => {
    server.use(
      http.get(`${BASE_URL}/reports`, () =>
        HttpResponse.json([{ ...COMPLETED, status: "failed", error_message: "No se pudo generar el PDF" }])
      )
    );

    renderPage();

    expect(await screen.findByText("No se pudo generar el PDF")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /descargar/i })).not.toBeInTheDocument();
  });

  it("polls again while a report is not in a terminal state, and stops once it is", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let callCount = 0;
    server.use(
      http.get(`${BASE_URL}/reports`, () => {
        callCount += 1;
        return HttpResponse.json([{ ...COMPLETED, status: callCount >= 2 ? "completed" : "running" }]);
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
