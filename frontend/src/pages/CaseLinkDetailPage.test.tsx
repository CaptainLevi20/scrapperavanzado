import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { CaseLinkDetailPage } from "./CaseLinkDetailPage";
import * as caseLinksApi from "../api/caseLinks";
import * as documentsApi from "../api/documents";

vi.mock("../api/caseLinks");
vi.mock("../api/documents");

const CASE_LINK = {
  id: 5,
  stages: [
    {
      stage_id: 11, source_id: 1, source_name: "Tribunal Administrativo del Atlántico",
      radicado: "08001233300020260014600", f_public_min: "2026-07-16", f_public_max: "2026-07-16",
      documents: [{ id: 10, title: "T_ATLA_08001_23_33_000_2026_00146_00", f_public: "2026-07-16", f_providencia: "2026-07-15" }],
    },
    {
      stage_id: 12, source_id: 2, source_name: "Consejo de Estado",
      radicado: "08001233300020260014601", f_public_min: "2026-07-31", f_public_max: "2026-07-31",
      documents: [{ id: 20, title: "08001-23-33-000-2026-00146-01(NE)", f_public: "2026-07-31", f_providencia: "2026-07-30" }],
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/expedientes/5"]}>
        <Routes>
          <Route path="/expedientes/:caseLinkId" element={<CaseLinkDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CaseLinkDetailPage", () => {
  beforeEach(() => {
    vi.mocked(caseLinksApi.fetchCaseLink).mockResolvedValue(CASE_LINK);
  });

  it("shows each stage's documents", async () => {
    renderPage();
    expect(await screen.findByText("T_ATLA_08001_23_33_000_2026_00146_00")).toBeInTheDocument();
    expect(screen.getByText("08001-23-33-000-2026-00146-01(NE)")).toBeInTheDocument();
  });

  it("opens a document when its button is clicked", async () => {
    vi.mocked(documentsApi.fetchDocumentBlob).mockResolvedValue(new Blob(["x"]));
    vi.mocked(documentsApi.downloadBlob).mockImplementation(() => {});
    renderPage();
    await screen.findByText("T_ATLA_08001_23_33_000_2026_00146_00");

    const [openButton] = screen.getAllByRole("button", { name: /abrir/i });
    await userEvent.click(openButton);

    await waitFor(() => expect(documentsApi.fetchDocumentBlob).toHaveBeenCalledWith(10));
  });

  it("removes a stage when 'Quitar del expediente' is clicked and confirmed", async () => {
    vi.mocked(caseLinksApi.separateCaseLinkStage).mockResolvedValue({ dissolved: false, case_link_id: 5 });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage();
    await screen.findByText("T_ATLA_08001_23_33_000_2026_00146_00");

    const [removeButton] = screen.getAllByRole("button", { name: /quitar del expediente/i });
    await userEvent.click(removeButton);

    await waitFor(() => expect(caseLinksApi.separateCaseLinkStage).toHaveBeenCalledWith(5, 11));
  });
});
