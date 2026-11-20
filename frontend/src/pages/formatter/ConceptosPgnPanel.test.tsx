import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConceptosPgnPanel } from "./ConceptosPgnPanel";
import { fakeMutableDirectory } from "../../lib/conceptosPgn/testFsMutable";

const TOMO = "1991/Tomo 3/Tomo 3 1991-1-14.pdf";

function lote() {
  return fakeMutableDirectory("20260923", {
    "1991": {
      "Tomo 1": { "Cto. 1654.pdf": "a", "Cto. 1655.pdf": "b" },
      "Tomo 3": { "Tomo 3 1991-1-14.pdf": "c" },
    },
  });
}

async function openBatch(fs: ReturnType<typeof lote>) {
  vi.stubGlobal("showDirectoryPicker", vi.fn().mockResolvedValue(fs.handle));
  const user = userEvent.setup();
  render(<ConceptosPgnPanel />);
  await user.click(screen.getByRole("button", { name: "Elegir carpeta del lote" }));
  await screen.findByText(/2 listos para renombrar/);
  return user;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ConceptosPgnPanel", () => {
  it("shows the batch summary", async () => {
    await openBatch(lote());

    expect(screen.getByText(/1 requieren tu revisión/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Renombrar 2 archivos" })).toBeEnabled();
  });

  it("asks for confirmation and then renames the originals", async () => {
    const fs = lote();
    const user = await openBatch(fs);

    await user.click(screen.getByRole("button", { name: "Renombrar 2 archivos" }));
    await user.click(screen.getByRole("button", { name: "Sí, renombrar" }));

    expect(await screen.findByText(/2 renombrados/)).toBeInTheDocument();
    expect(screen.getByText(/Registro guardado en registro_renombres_/)).toBeInTheDocument();
    const files = Object.keys(fs.snapshot());
    expect(files).toContain("1991/Tomo 1/CTO_PGN_0001654_1991(C).pdf");
    expect(files).toContain("1991/Tomo 1/CTO_PGN_0001655_1991(C).pdf");
    expect(files).toContain(TOMO);
  });

  it("cancel touches nothing", async () => {
    const fs = lote();
    const before = fs.snapshot();
    const user = await openBatch(fs);

    await user.click(screen.getByRole("button", { name: "Renombrar 2 archivos" }));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(fs.snapshot()).toEqual(before);
    expect(screen.getByRole("button", { name: "Renombrar 2 archivos" })).toBeInTheDocument();
  });

  it("typing a Tomo's number adds it to the renamable files and keeps its row", async () => {
    const user = await openBatch(lote());

    await user.type(screen.getByLabelText(`Número de ${TOMO}`), "1661");

    expect(screen.getByRole("button", { name: "Renombrar 3 archivos" })).toBeEnabled();
    expect(screen.getByLabelText(`Número de ${TOMO}`)).toHaveValue("1661");
    // Once in the full before → after list and once in its review row.
    expect(screen.getAllByText("CTO_PGN_0001661_1991(C).pdf")).toHaveLength(2);
  });

  it("'Ver' shows the first page of the PDF", async () => {
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() }));
    const user = await openBatch(lote());

    await user.click(screen.getByRole("button", { name: "Ver" }));

    await waitFor(() =>
      expect(screen.getByTitle("Primera página de Tomo 3 1991-1-14.pdf")).toHaveAttribute("src", "blob:x#page=1")
    );
  });

  it("typing while the preview is open does not reload the PDF", async () => {
    const createObjectURL = vi.fn(() => "blob:x");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }));
    const user = await openBatch(lote());

    await user.click(screen.getByRole("button", { name: "Ver" }));
    await waitFor(() => expect(screen.getByTitle("Primera página de Tomo 3 1991-1-14.pdf")).toBeInTheDocument());
    await user.type(screen.getByLabelText(`Número de ${TOMO}`), "1661");

    expect(createObjectURL).toHaveBeenCalledTimes(1);
  });
});
