import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { ExpedientesPage } from "./ExpedientesPage";
import * as caseLinksApi from "../api/caseLinks";

vi.mock("../api/caseLinks");

const ITEM = {
  id: 5,
  source_names: ["Consejo de Estado", "Tribunal Administrativo del Atlántico"],
  radicados: ["08001233300020260014600", "08001233300020260014601"],
  stage_count: 2,
  document_count: 3,
  f_public_min: "2026-07-16",
  f_public_max: "2026-07-31",
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ExpedientesPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ExpedientesPage", () => {
  beforeEach(() => {
    vi.mocked(caseLinksApi.fetchCaseLinks).mockResolvedValue([ITEM]);
  });

  it("shows the process radicado as the heading, with sources and counts", async () => {
    renderPage();
    // Radicado del proceso (primeros 21 dígitos formateados, sin la instancia).
    expect(await screen.findByText("08001-23-33-000-2026-00146")).toBeInTheDocument();
    expect(screen.getByText("Tribunal Administrativo del Atlántico", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Consejo de Estado", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/3 documentos/)).toBeInTheDocument();
  });

  it("links each expediente to its timeline", async () => {
    renderPage();
    const link = await screen.findByRole("link", { name: /ver expediente/i });
    expect(link).toHaveAttribute("href", "/expedientes/5");
  });

  it("shows an empty state when there are no expedientes", async () => {
    vi.mocked(caseLinksApi.fetchCaseLinks).mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText(/no hay expedientes/i)).toBeInTheDocument();
  });
});
