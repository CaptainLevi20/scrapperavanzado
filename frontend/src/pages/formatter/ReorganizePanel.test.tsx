import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { ReorganizePanel } from "./ReorganizePanel";

const BASE_URL = "http://localhost:8000";

describe("ReorganizePanel", () => {
  it("auto-approves a confident missing_entity_folder exception — Aplicar is enabled without any click", async () => {
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
              detected_entity: "MSPS",
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

    expect(await screen.findByText(/1 resuelta\(s\) automáticamente/)).toBeInTheDocument();
    // Fully resolved from the filename, no manual review table shown for it.
    expect(screen.queryByText(/Requieren tu revisión/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();
  });

  it("keeps a missing_year_folder resolved only from the mtime guess in the review section", async () => {
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

    expect(screen.getByText(/Requieren tu revisión/)).toBeInTheDocument();
    expect(screen.getByLabelText("Año para RESOLUCIONES/SGCANDINA/RSG2058.docx")).toHaveValue("2022");
    expect(screen.getByText(/Sin confirmar/)).toBeInTheDocument();
    // Only an mtime guess — not auto-approved, needs a click.
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Aprobar" }));
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Aplicar" }));

    expect(await screen.findByText(/1 archivo\(s\) movido\(s\)/)).toBeInTheDocument();
  });

  it("keeps entity_mismatch in the review section even when fully resolved", async () => {
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
    expect(screen.getByText(/Requieren tu revisión/)).toBeInTheDocument();
    expect(screen.queryByText(/resuelta\(s\) automáticamente/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Aprobar" }));
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();
  });

  it("auto-approves the confirmed CM-prefix entity_mismatch pattern (e.g. CMAGUACHICA -> CAGUACHICA)", async () => {
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
              current_path: "ACUERDOS/CMAGUACHICA/2022/A_CAGUACHICA_0011_2022.pdf",
              detected_entity: "CAGUACHICA",
              detected_year: 2022,
              mtime_year_hint: null,
              proposed_path: "ACUERDOS/CAGUACHICA/2022/A_CAGUACHICA_0011_2022.pdf",
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

    expect(await screen.findByText(/1 resuelta\(s\) automáticamente/)).toBeInTheDocument();
    expect(screen.queryByText(/Requieren tu revisión/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();
  });

  it("does NOT auto-approve an ordinary entity_mismatch that doesn't match the CM-prefix pattern", async () => {
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

    await screen.findByText("ACUERDOS/ARCHIVO/2003/A_AGN_0015_2003.pdf");
    expect(screen.queryByText(/resuelta\(s\) automáticamente/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeDisabled();
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

  it("applies a confident (auto-approved) row together with a manually approved one in the same request", async () => {
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
              current_path: "ACUERDOS/ARCHIVO/2003/A_AGN_0015_2003.pdf",
              detected_entity: "AGN",
              detected_year: 2003,
              mtime_year_hint: null,
              proposed_path: "ACUERDOS/AGN/2003/A_AGN_0015_2003.pdf",
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
        // Moves preserve the original exceptions order (ACUERDOS, then
        // DECRETOS) — DECRETOS is auto-approved (confident); ACUERDOS needs
        // the explicit approval below before it's included too.
        expect(body.moves).toEqual([
          {
            current_path: "ACUERDOS/ARCHIVO/2003/A_AGN_0015_2003.pdf",
            target_path: "ACUERDOS/AGN/2003/A_AGN_0015_2003.pdf",
          },
          {
            current_path: "DECRETOS/2022/D_MSPS_0017AJ_2022.pdf",
            target_path: "DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf",
          },
        ]);
        return HttpResponse.json({
          results: [
            {
              current_path: "ACUERDOS/ARCHIVO/2003/A_AGN_0015_2003.pdf",
              target_path: "ACUERDOS/AGN/2003/A_AGN_0015_2003.pdf",
              moved: true,
              skip_reason: null,
            },
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
    await screen.findByText("ACUERDOS/ARCHIVO/2003/A_AGN_0015_2003.pdf");

    // The DECRETOS row is auto-approved already; Aplicar is enabled with
    // just that, before touching the ACUERDOS row at all.
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Aprobar" }));

    await user.click(screen.getByRole("button", { name: "Aplicar" }));

    expect(await screen.findByText(/2 archivo\(s\) movido\(s\)/)).toBeInTheDocument();
  });

  it("shows a folder-rename suggestion, editable, and applies it only after approval (never auto-approved)", async () => {
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

  it("shows a summary count for each Tipo alongside the exceptions table", async () => {
    server.use(
      http.post(`${BASE_URL}/reorganize/analyze`, () =>
        HttpResponse.json({
          root_path: "D:/LOTE 2",
          total_files: 1,
          tipos: [{ tipo: "DECRETOS", total_files: 1, exception_count: 1 }],
          exceptions: [
            {
              tipo: "DECRETOS",
              kind: "entity_mismatch",
              current_path: "DECRETOS/ARCHIVO/2022/D_MSPS_0017AJ_2022.pdf",
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
      )
    );
    const user = userEvent.setup();
    render(<ReorganizePanel />);

    await user.type(screen.getByLabelText("Ruta de la carpeta"), "D:\\LOTE 2");
    await user.click(screen.getByRole("button", { name: "Analizar" }));

    await screen.findByText("DECRETOS/ARCHIVO/2022/D_MSPS_0017AJ_2022.pdf");
    const tipoSummaryTable = screen.getAllByRole("table")[0];
    expect(within(tipoSummaryTable).getByText("DECRETOS")).toBeInTheDocument();
    expect(within(tipoSummaryTable).getAllByText("1")).toHaveLength(2);
  });
});
