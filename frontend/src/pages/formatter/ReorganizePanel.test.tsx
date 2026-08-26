import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { ReorganizePanel } from "./ReorganizePanel";

const BASE_URL = "http://localhost:8000";

describe("ReorganizePanel", () => {
  it("keeps Aplicar disabled until a row is both filled in and explicitly approved", async () => {
    server.use(
      http.post(`${BASE_URL}/reorganize/analyze`, () =>
        HttpResponse.json({
          root_path: "D:/LOTE 2",
          total_files: 1,
          tipos: [{ tipo: "DECRETOS", total_files: 1, exception_count: 1 }],
          exceptions: [
            {
              tipo: "DECRETOS",
              kind: "missing_entity_folder",
              current_path: "DECRETOS/2022/D_MSPS_0017AJ_2022.pdf",
              detected_entity: null,
              detected_year: 2022,
              mtime_year_hint: null,
              proposed_path: null,
            },
          ],
          extra_depth: [],
          extra_depth_total: 0,
          folder_renames: [],
        })
      )
    );
    const user = userEvent.setup();
    render(<ReorganizePanel />);

    await user.type(screen.getByLabelText("Ruta de la carpeta"), "D:\\LOTE 2");
    await user.click(screen.getByRole("button", { name: "Analizar" }));

    expect(await screen.findByText("DECRETOS/2022/D_MSPS_0017AJ_2022.pdf")).toBeInTheDocument();
    expect(screen.getByLabelText("Año para DECRETOS/2022/D_MSPS_0017AJ_2022.pdf")).toHaveValue("2022");
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeDisabled();
    // detected_year came from the filename, not a guess — no "unconfirmed" warning.
    expect(screen.queryByText(/Sin confirmar/)).not.toBeInTheDocument();

    const tipoSummaryTable = screen.getAllByRole("table")[0];
    expect(within(tipoSummaryTable).getByText("DECRETOS")).toBeInTheDocument();
    expect(within(tipoSummaryTable).getAllByText("1")).toHaveLength(2);

    // Approving before the entity is filled in still leaves the row invalid.
    await user.click(screen.getByRole("button", { name: "Aprobar" }));
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeDisabled();

    await user.type(screen.getByLabelText("Entidad para DECRETOS/2022/D_MSPS_0017AJ_2022.pdf"), "MSPS");

    expect(screen.getByText("DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();
  });

  it("counts extra-depth files in the summary only, without listing them", async () => {
    server.use(
      http.post(`${BASE_URL}/reorganize/analyze`, () =>
        HttpResponse.json({
          root_path: "D:/LOTE 2",
          total_files: 1,
          tipos: [],
          exceptions: [],
          extra_depth: [{ tipo: "Gacetas", current_path: "Gacetas/GC/1992/AC/AC_0001_1992.pdf" }],
          extra_depth_total: 1,
          folder_renames: [],
        })
      )
    );
    const user = userEvent.setup();
    render(<ReorganizePanel />);

    await user.type(screen.getByLabelText("Ruta de la carpeta"), "D:\\LOTE 2");
    await user.click(screen.getByRole("button", { name: "Analizar" }));

    expect(await screen.findByText(/1 archivo\(s\) con profundidad extra/)).toBeInTheDocument();
    expect(screen.queryByText("Gacetas/GC/1992/AC/AC_0001_1992.pdf")).not.toBeInTheDocument();
  });

  it("pre-fills the year from the mtime hint and applies only after approval", async () => {
    server.use(
      http.post(`${BASE_URL}/reorganize/analyze`, () =>
        HttpResponse.json({
          root_path: "D:/LOTE 2",
          total_files: 1,
          tipos: [{ tipo: "RESOLUCIONES", total_files: 1, exception_count: 1 }],
          exceptions: [
            {
              tipo: "RESOLUCIONES",
              kind: "missing_year_folder",
              current_path: "RESOLUCIONES/SGCANDINA/RSG2058.docx",
              detected_entity: "SGCANDINA",
              detected_year: null,
              mtime_year_hint: 2022,
              proposed_path: null,
            },
          ],
          extra_depth: [],
          extra_depth_total: 0,
          folder_renames: [],
        })
      ),
      http.post(`${BASE_URL}/reorganize/apply`, async ({ request }) => {
        const body = (await request.json()) as { root_path: string; moves: { current_path: string; target_path: string }[] };
        // Intentionally the analyzed root ("D:/LOTE 2", from the mocked
        // analyze response above), not the raw textbox value the user typed
        // ("D:\LOTE 2") — see handleApply's fix for the root-path bug.
        expect(body.root_path).toBe("D:/LOTE 2");
        expect(body.moves).toEqual([
          {
            current_path: "RESOLUCIONES/SGCANDINA/RSG2058.docx",
            target_path: "RESOLUCIONES/SGCANDINA/2022/RSG2058.docx",
          },
        ]);
        return HttpResponse.json({
          results: [
            {
              current_path: "RESOLUCIONES/SGCANDINA/RSG2058.docx",
              target_path: "RESOLUCIONES/SGCANDINA/2022/RSG2058.docx",
              moved: true,
              skip_reason: null,
            },
          ],
          folder_rename_results: [],
        });
      })
    );
    const user = userEvent.setup();
    render(<ReorganizePanel />);

    await user.type(screen.getByLabelText("Ruta de la carpeta"), "D:\\LOTE 2");
    await user.click(screen.getByRole("button", { name: "Analizar" }));
    await screen.findByText("RESOLUCIONES/SGCANDINA/RSG2058.docx");

    expect(screen.getByLabelText("Año para RESOLUCIONES/SGCANDINA/RSG2058.docx")).toHaveValue("2022");
    // detected_year is null here — 2022 is only the file's mtime, not a
    // year read from its name — so the "unconfirmed" warning must show.
    expect(screen.getByText(/Sin confirmar/)).toBeInTheDocument();
    // Filled in, but not yet approved — still can't apply.
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Aprobar" }));
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Aplicar" }));

    expect(await screen.findByText(/1 archivo\(s\) movido\(s\)/)).toBeInTheDocument();
  });

  it("shows an entity_mismatch exception with the correct entity pre-filled, still requiring approval", async () => {
    server.use(
      http.post(`${BASE_URL}/reorganize/analyze`, () =>
        HttpResponse.json({
          root_path: "D:/LOTE 2",
          total_files: 1,
          tipos: [{ tipo: "ACUERDOS", total_files: 1, exception_count: 1 }],
          exceptions: [
            {
              tipo: "ACUERDOS",
              kind: "entity_mismatch",
              current_path: "ACUERDOS/ARCHIVO/2003/A_AGN_0015_2003.pdf",
              detected_entity: "AGN",
              detected_year: 2003,
              mtime_year_hint: null,
              proposed_path: "ACUERDOS/AGN/2003/A_AGN_0015_2003.pdf",
            },
          ],
          extra_depth: [],
          extra_depth_total: 0,
          folder_renames: [],
        })
      )
    );
    const user = userEvent.setup();
    render(<ReorganizePanel />);

    await user.type(screen.getByLabelText("Ruta de la carpeta"), "D:\\LOTE 2");
    await user.click(screen.getByRole("button", { name: "Analizar" }));

    expect(await screen.findByText("ACUERDOS/ARCHIVO/2003/A_AGN_0015_2003.pdf")).toBeInTheDocument();
    expect(screen.getByLabelText("Entidad para ACUERDOS/ARCHIVO/2003/A_AGN_0015_2003.pdf")).toHaveValue("AGN");
    expect(screen.getByLabelText("Año para ACUERDOS/ARCHIVO/2003/A_AGN_0015_2003.pdf")).toHaveValue("2003");
    expect(screen.getByText("ACUERDOS/AGN/2003/A_AGN_0015_2003.pdf")).toBeInTheDocument();
    // detected_year came from the existing (correct) year folder, not a
    // guess — the mismatch is only about the entity, so no year warning.
    expect(screen.queryByText(/Sin confirmar/)).not.toBeInTheDocument();
    // Already fully resolved, but not yet approved.
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Aprobar" }));
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();
  });

  it("toggles Aplicar on and off as a year_mismatch row is approved and un-approved", async () => {
    server.use(
      http.post(`${BASE_URL}/reorganize/analyze`, () =>
        HttpResponse.json({
          root_path: "D:/LOTE 2",
          total_files: 1,
          tipos: [{ tipo: "ACUERDOS", total_files: 1, exception_count: 1 }],
          exceptions: [
            {
              tipo: "ACUERDOS",
              kind: "year_mismatch",
              current_path: "ACUERDOS/MME/2014/A_MME_0031_2015.pdf",
              detected_entity: "MME",
              detected_year: 2015,
              mtime_year_hint: null,
              proposed_path: "ACUERDOS/MME/2015/A_MME_0031_2015.pdf",
            },
          ],
          extra_depth: [],
          extra_depth_total: 0,
          folder_renames: [],
        })
      )
    );
    const user = userEvent.setup();
    render(<ReorganizePanel />);

    await user.type(screen.getByLabelText("Ruta de la carpeta"), "D:\\LOTE 2");
    await user.click(screen.getByRole("button", { name: "Analizar" }));

    expect(await screen.findByText("ACUERDOS/MME/2014/A_MME_0031_2015.pdf")).toBeInTheDocument();
    expect(screen.getByLabelText("Entidad para ACUERDOS/MME/2014/A_MME_0031_2015.pdf")).toHaveValue("MME");
    expect(screen.getByLabelText("Año para ACUERDOS/MME/2014/A_MME_0031_2015.pdf")).toHaveValue("2015");
    expect(screen.getByText("ACUERDOS/MME/2015/A_MME_0031_2015.pdf")).toBeInTheDocument();
    expect(screen.queryByText(/Sin confirmar/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Aprobar" }));
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Deshacer" }));
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeDisabled();
  });

  it("applies only the rows explicitly approved, leaving un-approved ones out of the request", async () => {
    server.use(
      http.post(`${BASE_URL}/reorganize/analyze`, () =>
        HttpResponse.json({
          root_path: "D:/LOTE 2",
          total_files: 2,
          tipos: [
            { tipo: "ACUERDOS", total_files: 1, exception_count: 1 },
            { tipo: "DECRETOS", total_files: 1, exception_count: 1 },
          ],
          exceptions: [
            {
              tipo: "ACUERDOS",
              kind: "entity_mismatch",
              current_path: "ACUERDOS/CMAGUACHICA/2015/A_CAGUACHICA_0003_2015.pdf",
              detected_entity: "CAGUACHICA",
              detected_year: 2015,
              mtime_year_hint: null,
              proposed_path: "ACUERDOS/CAGUACHICA/2015/A_CAGUACHICA_0003_2015.pdf",
            },
            {
              tipo: "DECRETOS",
              kind: "missing_entity_folder",
              current_path: "DECRETOS/2022/D_MSPS_0017AJ_2022.pdf",
              detected_entity: "MSPS",
              detected_year: 2022,
              mtime_year_hint: null,
              proposed_path: "DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf",
            },
          ],
          extra_depth: [],
          extra_depth_total: 0,
          folder_renames: [],
        })
      ),
      http.post(`${BASE_URL}/reorganize/apply`, async ({ request }) => {
        const body = (await request.json()) as { moves: { current_path: string; target_path: string }[] };
        // Only the approved DECRETOS exception should reach the backend.
        expect(body.moves).toEqual([
          {
            current_path: "DECRETOS/2022/D_MSPS_0017AJ_2022.pdf",
            target_path: "DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf",
          },
        ]);
        return HttpResponse.json({
          results: [
            {
              current_path: "DECRETOS/2022/D_MSPS_0017AJ_2022.pdf",
              target_path: "DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf",
              moved: true,
              skip_reason: null,
            },
          ],
          folder_rename_results: [],
        });
      })
    );
    const user = userEvent.setup();
    render(<ReorganizePanel />);

    await user.type(screen.getByLabelText("Ruta de la carpeta"), "D:\\LOTE 2");
    await user.click(screen.getByRole("button", { name: "Analizar" }));
    await screen.findByText("ACUERDOS/CMAGUACHICA/2015/A_CAGUACHICA_0003_2015.pdf");

    // Nothing approved yet — Aplicar stays disabled even though both rows are valid.
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeDisabled();

    const approveButtons = screen.getAllByRole("button", { name: "Aprobar" });
    expect(approveButtons).toHaveLength(2);
    // Approve only the DECRETOS row (second one, per the exceptions order above).
    await user.click(approveButtons[1]);

    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Aplicar" }));

    expect(await screen.findByText(/1 archivo\(s\) movido\(s\)/)).toBeInTheDocument();
  });

  it("shows a folder-rename suggestion, editable, and applies it only after approval", async () => {
    server.use(
      http.post(`${BASE_URL}/reorganize/analyze`, () =>
        HttpResponse.json({
          root_path: "D:/LOTE 2",
          total_files: 2,
          tipos: [{ tipo: "ACUERDOS", total_files: 2, exception_count: 2 }],
          exceptions: [],
          extra_depth: [],
          extra_depth_total: 0,
          folder_renames: [
            {
              tipo: "ACUERDOS",
              current_entity: "CMARAUCA",
              suggested_entity: "CARAUCA",
              current_path: "ACUERDOS/CMARAUCA",
              proposed_path: "ACUERDOS/CARAUCA",
              file_count: 2,
            },
          ],
        })
      ),
      http.post(`${BASE_URL}/reorganize/apply`, async ({ request }) => {
        const body = (await request.json()) as {
          moves: unknown[];
          folder_renames: { current_path: string; target_path: string }[];
        };
        expect(body.moves).toEqual([]);
        expect(body.folder_renames).toEqual([{ current_path: "ACUERDOS/CMARAUCA", target_path: "ACUERDOS/CARAUCA" }]);
        return HttpResponse.json({
          results: [],
          folder_rename_results: [
            { current_path: "ACUERDOS/CMARAUCA", target_path: "ACUERDOS/CARAUCA", renamed: true, skip_reason: null },
          ],
        });
      })
    );
    const user = userEvent.setup();
    render(<ReorganizePanel />);

    await user.type(screen.getByLabelText("Ruta de la carpeta"), "D:\\LOTE 2");
    await user.click(screen.getByRole("button", { name: "Analizar" }));

    expect(await screen.findByText("ACUERDOS/CMARAUCA")).toBeInTheDocument();
    expect(screen.getByLabelText("Nueva entidad para ACUERDOS/CMARAUCA")).toHaveValue("CARAUCA");
    expect(screen.getByText("ACUERDOS/CARAUCA")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Aprobar" }));
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Aplicar" }));

    expect(await screen.findByText(/1 carpeta\(s\) renombrada\(s\)/)).toBeInTheDocument();
  });

  it("toggles Aplicar on and off as a folder-rename suggestion is approved and un-approved", async () => {
    server.use(
      http.post(`${BASE_URL}/reorganize/analyze`, () =>
        HttpResponse.json({
          root_path: "D:/LOTE 2",
          total_files: 2,
          tipos: [{ tipo: "ACUERDOS", total_files: 2, exception_count: 2 }],
          exceptions: [],
          extra_depth: [],
          extra_depth_total: 0,
          folder_renames: [
            {
              tipo: "ACUERDOS",
              current_entity: "CMARAUCA",
              suggested_entity: "CARAUCA",
              current_path: "ACUERDOS/CMARAUCA",
              proposed_path: "ACUERDOS/CARAUCA",
              file_count: 2,
            },
          ],
        })
      )
    );
    const user = userEvent.setup();
    render(<ReorganizePanel />);

    await user.type(screen.getByLabelText("Ruta de la carpeta"), "D:\\LOTE 2");
    await user.click(screen.getByRole("button", { name: "Analizar" }));
    await screen.findByText("ACUERDOS/CMARAUCA");

    expect(screen.getByRole("button", { name: "Aplicar" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Aprobar" }));
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Deshacer" }));
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeDisabled();
  });
});
