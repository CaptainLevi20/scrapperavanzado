import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { ReorganizePanel } from "./ReorganizePanel";

const BASE_URL = "http://localhost:8000";

describe("ReorganizePanel", () => {
  it("analyzes a path and disables Aplicar until the missing entity is filled in", async () => {
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

    await user.type(screen.getByLabelText("Entidad para DECRETOS/2022/D_MSPS_0017AJ_2022.pdf"), "MSPS");

    expect(screen.getByText("DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();
  });

  it("shows extra-depth entries as informational only, without an Entidad/Año row", async () => {
    server.use(
      http.post(`${BASE_URL}/reorganize/analyze`, () =>
        HttpResponse.json({
          root_path: "D:/LOTE 2",
          total_files: 1,
          tipos: [],
          exceptions: [],
          extra_depth: [{ tipo: "Gacetas", current_path: "Gacetas/GC/1992/AC/AC_0001_1992.pdf" }],
          extra_depth_total: 1,
        })
      )
    );
    const user = userEvent.setup();
    render(<ReorganizePanel />);

    await user.type(screen.getByLabelText("Ruta de la carpeta"), "D:\\LOTE 2");
    await user.click(screen.getByRole("button", { name: "Analizar" }));

    expect(await screen.findByText("Gacetas/GC/1992/AC/AC_0001_1992.pdf")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Entidad para Gacetas/)).not.toBeInTheDocument();
  });

  it("pre-fills the year from the mtime hint and applies the resolved move", async () => {
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
        });
      })
    );
    const user = userEvent.setup();
    render(<ReorganizePanel />);

    await user.type(screen.getByLabelText("Ruta de la carpeta"), "D:\\LOTE 2");
    await user.click(screen.getByRole("button", { name: "Analizar" }));
    await screen.findByText("RESOLUCIONES/SGCANDINA/RSG2058.docx");

    expect(screen.getByLabelText("Año para RESOLUCIONES/SGCANDINA/RSG2058.docx")).toHaveValue("2022");
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();
    // detected_year is null here — 2022 is only the file's mtime, not a
    // year read from its name — so the "unconfirmed" warning must show.
    expect(screen.getByText(/Sin confirmar/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Aplicar" }));

    expect(await screen.findByText(/1 archivo\(s\) movido\(s\)/)).toBeInTheDocument();
  });
});
