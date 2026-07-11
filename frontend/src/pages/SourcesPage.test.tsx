import { describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
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
      http.get(`${BASE_URL}/source-families`, () =>
        HttpResponse.json([{ key: "constitucional", display_name: "Corte Constitucional", description: null }])
      ),
      http.get(`${BASE_URL}/sources`, () =>
        HttpResponse.json([{ id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: true }])
      )
    );

    renderPage();

    expect(await within(screen.getByRole("table")).findByText("Corte Constitucional")).toBeInTheDocument();
  });

  it("refetches with the active filter applied when changed", async () => {
    let lastUrl = "";
    server.use(
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])),
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
    server.use(
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/sources`, () => new HttpResponse(null, { status: 500 }))
    );

    renderPage();

    expect(await screen.findByText(/no se pudieron cargar las fuentes/i)).toBeInTheDocument();
  });
});
