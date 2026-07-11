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

describe("SourcesPage — create and edit", () => {
  it("creates a source and refreshes the list", async () => {
    let createdBody: unknown;
    server.use(
      http.get(`${BASE_URL}/source-families`, () =>
        HttpResponse.json([{ key: "constitucional", display_name: "Corte Constitucional", description: null }])
      ),
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json([])),
      http.post(`${BASE_URL}/sources`, async ({ request }) => {
        createdBody = await request.json();
        return HttpResponse.json({ id: 2, ...(createdBody as object) }, { status: 201 });
      })
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Nueva fuente"));
    await user.selectOptions(screen.getByLabelText("Familia de la fuente"), "constitucional");
    await user.type(screen.getByLabelText(/nombre/i), "Corte Constitucional");
    await user.click(screen.getByText("Crear"));

    await waitFor(() => expect(createdBody).toMatchObject({ family_key: "constitucional", name: "Corte Constitucional" }));
  });

  it("toggles a source's active state", async () => {
    let patchedBody: unknown;
    server.use(
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])),
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

  it("edits a source's family_params via the inline dialog", async () => {
    let patchedBody: unknown;
    server.use(
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/sources`, () =>
        HttpResponse.json([
          { id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: { foo: "bar" }, active: true },
        ])
      ),
      http.patch(`${BASE_URL}/sources/1`, async ({ request }) => {
        patchedBody = await request.json();
        return HttpResponse.json({
          id: 1,
          family_key: "constitucional",
          name: "Corte Constitucional",
          family_params: { foo: "baz" },
          active: true,
        });
      })
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Editar parámetros"));

    const textarea = screen.getByLabelText(/parámetros \(json\)/i);
    expect(textarea).toHaveValue(JSON.stringify({ foo: "bar" }, null, 2));

    await user.clear(textarea);
    await user.type(textarea, '{{"foo": "baz"}');
    await user.click(screen.getByText("Guardar"));

    await waitFor(() => expect(patchedBody).toMatchObject({ family_params: { foo: "baz" } }));
  });

  it("shows a validation error and does not call the API when the edited params are invalid JSON", async () => {
    let patchCalled = false;
    server.use(
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/sources`, () =>
        HttpResponse.json([
          { id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: { foo: "bar" }, active: true },
        ])
      ),
      http.patch(`${BASE_URL}/sources/1`, () => {
        patchCalled = true;
        return HttpResponse.json({ id: 1 });
      })
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Editar parámetros"));

    const textarea = screen.getByLabelText(/parámetros \(json\)/i);
    await user.clear(textarea);
    await user.type(textarea, "{{not valid json");
    await user.click(screen.getByText("Guardar"));

    expect(await screen.findByText("Los parámetros deben ser JSON válido")).toBeInTheDocument();
    expect(patchCalled).toBe(false);
  });
});
