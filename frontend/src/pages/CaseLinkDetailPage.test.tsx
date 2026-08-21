import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { CaseLinkDetailPage } from "./CaseLinkDetailPage";
import * as caseLinksApi from "../api/caseLinks";

vi.mock("../api/caseLinks");

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

function DocumentsStub() {
  const location = useLocation();
  return <div>Documentos: {JSON.stringify(location.state)}</div>;
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/expedientes/5"]}>
        <Routes>
          <Route path="/expedientes/:caseLinkId" element={<CaseLinkDetailPage />} />
          <Route path="/documents" element={<DocumentsStub />} />
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

  it("orders stages by ascending publication date, regardless of the incoming order", async () => {
    // Caso real (San Andrés): la apelación del Consejo de Estado se publicó el
    // 14 jul y la providencia del tribunal el 24 jul. Las etapas llegan en
    // orden inverso al de fecha; la línea de tiempo debe reordenarlas por
    // publicación ascendente (14 jul primero) — el mismo orden que el subtítulo
    // del listado.
    vi.mocked(caseLinksApi.fetchCaseLink).mockResolvedValue({
      id: 9,
      stages: [
        {
          stage_id: 91, source_id: 1, source_name: "Tribunal Administrativo de San Andrés",
          radicado: "88001233300020260000300", f_public_min: "2026-07-24", f_public_max: "2026-07-24",
          documents: [{ id: 31, title: "T_SAND_88001_23_33_000_2026_00003_00", f_public: "2026-07-24", f_providencia: "2026-07-23" }],
        },
        {
          stage_id: 90, source_id: 2, source_name: "Consejo de Estado",
          radicado: "88001233300020260000303", f_public_min: "2026-07-14", f_public_max: "2026-07-14",
          documents: [{ id: 30, title: "88001-23-33-000-2026-00003-03(NE)", f_public: "2026-07-14", f_providencia: "2026-07-13" }],
        },
      ],
    });
    renderPage();
    const headings = await screen.findAllByRole("heading", { level: 2 });
    expect(headings.map((heading) => heading.textContent)).toEqual([
      "Consejo de Estado",
      "Tribunal Administrativo de San Andrés",
    ]);
  });

  it("navigates to Documents with the document's preview requested, instead of downloading it", async () => {
    renderPage();
    await screen.findByText("T_ATLA_08001_23_33_000_2026_00146_00");

    const [openButton] = screen.getAllByRole("button", { name: /abrir/i });
    await userEvent.click(openButton);

    // stage_id 11's source_id is 1 (see CASE_LINK fixture) — the timeline
    // route itself has no full Document, only id/title per stage document
    // plus the stage's own source_id, so that's exactly what gets passed on.
    await waitFor(() =>
      expect(screen.getByText('Documentos: {"openDocument":{"id":10,"source_id":1,"title":"T_ATLA_08001_23_33_000_2026_00146_00"}}')).toBeInTheDocument()
    );
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
