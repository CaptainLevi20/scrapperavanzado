import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { delay, http, HttpResponse } from "msw";
import { server } from "../test/server";
import { BulkDownloadsPage } from "./BulkDownloadsPage";

const BASE_URL = "http://localhost:8000";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <BulkDownloadsPage />
    </QueryClientProvider>
  );
}

const COMPLETED = {
  id: 1,
  status: "completed",
  document_count: 12,
  failed_count: 2,
  error_message: null,
  started_at: "2026-07-16T00:00:00Z",
  finished_at: "2026-07-16T00:01:00Z",
  created_at: "2026-07-16T00:00:00Z",
};

describe("BulkDownloadsPage", () => {
  it("renders the fetched bulk downloads with status and document count", async () => {
    server.use(http.get(`${BASE_URL}/bulk-downloads`, () => HttpResponse.json([COMPLETED])));

    renderPage();

    expect(await screen.findByText("completed")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText(/2 omitidos/)).toBeInTheDocument();
  });

  it("does not show 'no bulk downloads' while the first request is still in flight", async () => {
    server.use(
      http.get(`${BASE_URL}/bulk-downloads`, async () => {
        await delay(50);
        return HttpResponse.json([]);
      })
    );

    renderPage();

    expect(screen.queryByText("Todavía no se ha generado ninguna descarga masiva.")).not.toBeInTheDocument();
    expect(await screen.findByText("Todavía no se ha generado ninguna descarga masiva.")).toBeInTheDocument();
  });

  it("shows a Descargar button only when completed, wired to the presigned url", async () => {
    server.use(
      http.get(`${BASE_URL}/bulk-downloads`, () => HttpResponse.json([COMPLETED])),
      http.get(`${BASE_URL}/bulk-downloads/1/download`, () =>
        HttpResponse.json({ url: "https://signed.example.com/1.zip" })
      )
    );
    // downloadFromUrl does a real fetch()+Blob — stub it so this test only
    // verifies the click is wired to the right endpoint, not the browser download mechanics.
    server.use(http.get("https://signed.example.com/1.zip", () => HttpResponse.text("contenido")));
    // Stub the anchor's click() (same convention as DocumentPreviewDialog.test.tsx) so
    // jsdom doesn't log a "Not implemented: navigation" error for the real <a download> click.
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

  it("shows an error banner instead of doing nothing when the download fails", async () => {
    // Regression test: handleDownload had no try/catch — a failure (e.g. the
    // presigned URL expired, or the ZIP is no longer available) made the click
    // silently do nothing, with no feedback at all.
    server.use(
      http.get(`${BASE_URL}/bulk-downloads`, () => HttpResponse.json([COMPLETED])),
      http.get(`${BASE_URL}/bulk-downloads/1/download`, () => new HttpResponse(null, { status: 404 }))
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /descargar/i }));

    expect(await screen.findByText(/no se pudo descargar el archivo/i)).toBeInTheDocument();
  });

  it("shows the error message instead of a download button for a failed job", async () => {
    server.use(
      http.get(`${BASE_URL}/bulk-downloads`, () =>
        HttpResponse.json([
          { ...COMPLETED, status: "failed", error_message: "No hay documentos marcados como Útil para descargar" },
        ])
      )
    );

    renderPage();

    expect(await screen.findByText("No hay documentos marcados como Útil para descargar")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /descargar/i })).not.toBeInTheDocument();
  });

  it("polls again while a job is not in a terminal state, and stops once it is", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let callCount = 0;
    server.use(
      http.get(`${BASE_URL}/bulk-downloads`, () => {
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

  it("shows an empty state when there is no history yet", async () => {
    server.use(http.get(`${BASE_URL}/bulk-downloads`, () => HttpResponse.json([])));

    renderPage();

    expect(await screen.findByText(/todav.a no se ha generado ninguna descarga masiva/i)).toBeInTheDocument();
  });
});
