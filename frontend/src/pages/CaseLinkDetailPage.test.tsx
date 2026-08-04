import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { CaseLinkDetailPage } from "./CaseLinkDetailPage";
import * as caseLinksApi from "../api/caseLinks";

vi.mock("../api/caseLinks");

const CASE_LINK = {
  id: 5,
  stages: [
    {
      source_id: 2, source_name: "Consejo de Estado", radicado: "25000234200020200000802",
      f_public_min: "2024-11-01", f_public_max: "2024-11-01",
      documents: [{ id: 20, title: "25000234200020200000802(NRD)", f_public: "2024-11-01", f_providencia: "2024-10-20" }],
    },
    {
      source_id: 1, source_name: "Tribunal Administrativo de Antioquia", radicado: "25000234200020200000801",
      f_public_min: "2023-01-01", f_public_max: "2023-06-01",
      documents: [{ id: 10, title: "25000234200020200000801(NRD)", f_public: "2023-01-01", f_providencia: "2022-12-15" }],
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/casos-por-confirmar/expedientes/5"]}>
        <Routes>
          <Route path="/casos-por-confirmar/expedientes/:caseLinkId" element={<CaseLinkDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CaseLinkDetailPage", () => {
  beforeEach(() => {
    vi.mocked(caseLinksApi.fetchCaseLink).mockResolvedValue(CASE_LINK);
  });

  it("orders stages by earliest publication date first", async () => {
    renderPage();
    const stageNames = await screen.findAllByRole("heading", { level: 2 });
    expect(stageNames.map((el) => el.textContent)).toEqual([
      "Tribunal Administrativo de Antioquia",
      "Consejo de Estado",
    ]);
  });

  it("shows each stage's documents", async () => {
    renderPage();
    expect(await screen.findByText("25000234200020200000801(NRD)")).toBeInTheDocument();
    expect(screen.getByText("25000234200020200000802(NRD)")).toBeInTheDocument();
  });
});
