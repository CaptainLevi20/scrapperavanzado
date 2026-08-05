import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { CaseLinksPage } from "./CaseLinksPage";
import * as caseLinksApi from "../api/caseLinks";
import * as sourcesApi from "../api/sources";

vi.mock("../api/caseLinks");
vi.mock("../api/sources");

const SOURCES = [
  { id: 1, family_key: "samai", name: "Tribunal Administrativo de Antioquia", family_params: {}, active: true },
  { id: 2, family_key: "samai", name: "Consejo de Estado", family_params: {}, active: true },
  { id: 3, family_key: "rama_judicial", name: "Juzgado X", family_params: {}, active: true },
];

const SUGGESTION = {
  id: 1,
  matched_digits: 22,
  status: "pending",
  created_at: "2026-07-29T00:00:00Z",
  case_a: {
    source_id: 1, source_name: "Tribunal Administrativo de Antioquia", radicado: "25000234200020200000801",
    document_count: 2, f_public_min: "2023-01-01", f_public_max: "2023-06-01",
  },
  case_b: {
    source_id: 2, source_name: "Consejo de Estado", radicado: "25000234200020200000802",
    document_count: 1, f_public_min: "2024-11-01", f_public_max: "2024-11-01",
  },
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/casos-por-confirmar"]}>
        <Routes>
          <Route path="/casos-por-confirmar" element={<CaseLinksPage />} />
          <Route path="/casos-por-confirmar/expedientes/:caseLinkId" element={<div>Página del expediente</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CaseLinksPage", () => {
  beforeEach(() => {
    vi.mocked(caseLinksApi.fetchCaseLinkSuggestions).mockResolvedValue([SUGGESTION]);
    vi.mocked(sourcesApi.fetchSources).mockResolvedValue(SOURCES);
  });

  it("lists pending suggestions with both tribunals", async () => {
    renderPage();
    expect(await screen.findByText("Tribunal Administrativo de Antioquia", { ignore: "script, style, option" })).toBeInTheDocument();
    expect(screen.getByText("Consejo de Estado", { ignore: "script, style, option" })).toBeInTheDocument();
    expect(screen.getByText(/22 dígitos/)).toBeInTheDocument();
  });

  it("confirms a suggestion and navigates to the confirmed expedient", async () => {
    vi.mocked(caseLinksApi.confirmCaseLinkSuggestion).mockResolvedValue({ id: 5, stages: [] });
    renderPage();
    await screen.findByText("Tribunal Administrativo de Antioquia", { ignore: "script, style, option" });

    await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(caseLinksApi.confirmCaseLinkSuggestion).toHaveBeenCalledWith(1));
    expect(await screen.findByText("Página del expediente")).toBeInTheDocument();
  });

  it("dismisses a suggestion", async () => {
    vi.mocked(caseLinksApi.dismissCaseLinkSuggestion).mockResolvedValue({ status: "dismissed" });
    renderPage();
    await screen.findByText("Tribunal Administrativo de Antioquia", { ignore: "script, style, option" });

    await userEvent.click(screen.getByRole("button", { name: "Descartar" }));

    await waitFor(() => expect(caseLinksApi.dismissCaseLinkSuggestion).toHaveBeenCalledWith(1));
  });

  it("shows an empty state when there are no pending suggestions", async () => {
    vi.mocked(caseLinksApi.fetchCaseLinkSuggestions).mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText(/no hay casos pendientes/i)).toBeInTheDocument();
  });

  it("creates a manual link by picking samai sources from dropdowns instead of typing raw ids", async () => {
    vi.mocked(caseLinksApi.createManualCaseLink).mockResolvedValue({ id: 9, stages: [] });
    renderPage();
    await screen.findByText("Tribunal Administrativo de Antioquia", { ignore: "script, style, option" });

    const [sourceASelect, sourceBSelect] = screen.getAllByRole("combobox");
    // Only samai sources should be offered — "Juzgado X" (rama_judicial) is excluded.
    expect(screen.queryByText("Juzgado X")).not.toBeInTheDocument();

    await userEvent.selectOptions(sourceASelect, "Tribunal Administrativo de Antioquia");
    await userEvent.type(screen.getByPlaceholderText("Radicado A"), "25000234200020200000801");
    await userEvent.selectOptions(sourceBSelect, "Consejo de Estado");
    await userEvent.type(screen.getByPlaceholderText("Radicado B"), "25000234200020200000802");
    await userEvent.click(screen.getByRole("button", { name: "Vincular" }));

    await waitFor(() =>
      expect(caseLinksApi.createManualCaseLink).toHaveBeenCalledWith(
        {
          source_id_a: 1,
          radicado_a: "25000234200020200000801",
          source_id_b: 2,
          radicado_b: "25000234200020200000802",
        },
        expect.anything()
      )
    );
  });
});
