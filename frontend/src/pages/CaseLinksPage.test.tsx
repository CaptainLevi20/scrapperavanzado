import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { CaseLinksPage } from "./CaseLinksPage";
import * as caseLinksApi from "../api/caseLinks";

vi.mock("../api/caseLinks");

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
      <MemoryRouter>
        <CaseLinksPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CaseLinksPage", () => {
  beforeEach(() => {
    vi.mocked(caseLinksApi.fetchCaseLinkSuggestions).mockResolvedValue([SUGGESTION]);
  });

  it("lists pending suggestions with both tribunals", async () => {
    renderPage();
    expect(await screen.findByText("Tribunal Administrativo de Antioquia")).toBeInTheDocument();
    expect(screen.getByText("Consejo de Estado")).toBeInTheDocument();
    expect(screen.getByText(/22 dígitos/)).toBeInTheDocument();
  });

  it("confirms a suggestion and removes it from the list", async () => {
    vi.mocked(caseLinksApi.confirmCaseLinkSuggestion).mockResolvedValue({ id: 5, stages: [] });
    renderPage();
    await screen.findByText("Tribunal Administrativo de Antioquia");

    await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(caseLinksApi.confirmCaseLinkSuggestion).toHaveBeenCalledWith(1));
  });

  it("dismisses a suggestion", async () => {
    vi.mocked(caseLinksApi.dismissCaseLinkSuggestion).mockResolvedValue({ status: "dismissed" });
    renderPage();
    await screen.findByText("Tribunal Administrativo de Antioquia");

    await userEvent.click(screen.getByRole("button", { name: "Descartar" }));

    await waitFor(() => expect(caseLinksApi.dismissCaseLinkSuggestion).toHaveBeenCalledWith(1));
  });

  it("shows an empty state when there are no pending suggestions", async () => {
    vi.mocked(caseLinksApi.fetchCaseLinkSuggestions).mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText(/no hay casos pendientes/i)).toBeInTheDocument();
  });
});
