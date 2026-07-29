import { describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { delay, http, HttpResponse } from "msw";
import { server } from "../test/server";
import { SourcesPage } from "./SourcesPage";

const BASE_URL = "http://localhost:8000";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SourcesPage />
    </QueryClientProvider>
  );
}

describe("SourcesPage", () => {
  it("renders the fetched sources", async () => {
    server.use(
      http.get(`${BASE_URL}/sources`, () =>
        HttpResponse.json([{ id: 1, family_key: "constitucional", name: "Sala Plena", family_params: {}, active: true }])
      )
    );

    renderPage();

    const table = screen.getByRole("table");
    expect(await within(table).findByText("Sala Plena")).toBeInTheDocument();
  });

  it("does not show 'no sources' while the first request is still in flight", async () => {
    server.use(
      http.get(`${BASE_URL}/sources`, async () => {
        await delay(50);
        return HttpResponse.json([]);
      })
    );

    renderPage();

    expect(screen.queryByText("No hay fuentes que coincidan con estos filtros.")).not.toBeInTheDocument();
    expect(await screen.findByText("No hay fuentes que coincidan con estos filtros.")).toBeInTheDocument();
  });

  it("enables Siguiente when there really is another page, and only renders one page's worth of rows", async () => {
    // Regression test: /sources has no total count to compare against, so
    // "Siguiente" used to just check whether the current page happened to come
    // back full — the frontend now asks for one extra row (PAGE_SIZE + 1) to
    // find out whether a next page genuinely exists.
    const sources = Array.from({ length: 21 }, (_, i) => ({
      id: i + 1,
      family_key: "constitucional",
      name: `Fuente ${i + 1}`,
      family_params: {},
      active: true,
    }));
    const requestedUrls: string[] = [];
    server.use(
      http.get(`${BASE_URL}/sources`, ({ request }) => {
        requestedUrls.push(request.url);
        return HttpResponse.json(sources);
      })
    );

    renderPage();

    const table = await screen.findByRole("table");
    await within(table).findByText("Fuente 1");
    // The page-size-aware fetch (PAGE_SIZE + 1) is one of two /sources calls —
    // the other is the filter dropdown's unrelated fetch-everything call.
    expect(requestedUrls.some((url) => new URL(url).searchParams.get("limit") === "21")).toBe(true);
    expect(within(table).queryByText("Fuente 21")).not.toBeInTheDocument(); // the extra row is never rendered
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeEnabled();
  });

  it("disables Siguiente when the response doesn't fill a whole extra row past the page size", async () => {
    const sources = Array.from({ length: 5 }, (_, i) => ({
      id: i + 1,
      family_key: "constitucional",
      name: `Fuente ${i + 1}`,
      family_params: {},
      active: true,
    }));
    server.use(http.get(`${BASE_URL}/sources`, () => HttpResponse.json(sources)));

    renderPage();

    const table = await screen.findByRole("table");
    await within(table).findByText("Fuente 1");
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeDisabled();
  });

  it("refetches with the active filter applied when changed", async () => {
    let lastUrl = "";
    server.use(
      http.get(`${BASE_URL}/sources`, ({ request }) => {
        lastUrl = request.url;
        return HttpResponse.json([]);
      })
    );
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(lastUrl).toContain("/sources"));
    await user.selectOptions(screen.getByLabelText(/estado/i), "true");

    await waitFor(() => expect(lastUrl).toContain("active=true"));
  });

  it("shows an error banner when the sources request fails", async () => {
    server.use(http.get(`${BASE_URL}/sources`, () => new HttpResponse(null, { status: 500 })));

    renderPage();

    expect(await screen.findByText(/no se pudieron cargar las fuentes/i)).toBeInTheDocument();
  });
});

describe("SourcesPage — toggle active state", () => {
  it("toggles a source's active state", async () => {
    let patchedBody: unknown;
    server.use(
      http.get(`${BASE_URL}/sources`, () =>
        HttpResponse.json([{ id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: true }])
      ),
      http.patch(`${BASE_URL}/sources/1`, async ({ request }) => {
        patchedBody = await request.json();
        return HttpResponse.json({ id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: false });
      })
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Desactivar"));

    await waitFor(() => expect(patchedBody).toMatchObject({ active: false }));
  });
});
