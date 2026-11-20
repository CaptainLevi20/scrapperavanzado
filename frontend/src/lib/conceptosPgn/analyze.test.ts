import { describe, expect, it } from "vitest";
import { analyzeConceptBatch, applyManualFixes, ConceptPgnError, isAlreadyFinal, isRenamable } from "./analyze";
import { fakeMutableDirectory } from "./testFsMutable";

function byPath<T extends { path: string }>(entries: T[], path: string): T {
  const found = entries.find((entry) => entry.path === path);
  if (!found) throw new Error(`No entry for ${path}`);
  return found;
}

describe("analyzeConceptBatch", () => {
  it("reads the year from the top-level folder and keeps per-concept subfolders", async () => {
    const fs = fakeMutableDirectory("20260923", {
      "1991": { "Tomo 1": { "Cto. 1654.pdf": "x" } },
      "2007": { "Tomo 6 2007": { CTO_PGN_0004360_2007: { "4360.pdf": "x" } } },
    });

    const plan = await analyzeConceptBatch(fs.handle);

    const a = byPath(plan.entries, "1991/Tomo 1/Cto. 1654.pdf");
    expect(a.finalName).toBe("CTO_PGN_0001654_1991(C).pdf");
    expect(a.reason).toBeNull();
    expect(a.folderPath).toBe("1991/Tomo 1");
    const b = byPath(plan.entries, "2007/Tomo 6 2007/CTO_PGN_0004360_2007/4360.pdf");
    expect(b.finalName).toBe("CTO_PGN_0004360_2007(C).pdf");
    expect(b.reason).toBeNull();
  });

  it("ignores photos, spreadsheets, text and csv, and reports photo-only folders", async () => {
    const fs = fakeMutableDirectory("20260923", {
      "Léame.txt": "x",
      "Listado.xlsx": "x",
      "registro_renombres_20261120-1010.csv": "x",
      "2006": { "TOMO 10 2006": { "20260708_110124.jpg": "x", "20260708_110130.jpg": "x" } },
      "1998": { "Tomo 3": { "Cto. 1540.pdf": "x", "pagina_233.jpg": "x" } },
    });

    const plan = await analyzeConceptBatch(fs.handle);

    expect(plan.entries.map((entry) => entry.path)).toEqual(["1998/Tomo 3/Cto. 1540.pdf"]);
    expect(plan.photoOnlyFolders).toEqual(["2006/TOMO 10 2006"]);
  });

  it("sends Tomo fragments and a year mismatch to review", async () => {
    const fs = fakeMutableDirectory("lote", {
      "1991": { "Tomo 3": { "Tomo 3 1991-1-14.pdf": "x" } },
      "2009": { "Tomo 3": { "Concepto 4734 de 2008.pdf": "x" } },
    });

    const plan = await analyzeConceptBatch(fs.handle);

    const tomo = byPath(plan.entries, "1991/Tomo 3/Tomo 3 1991-1-14.pdf");
    expect(tomo.reason).toBe("no-number");
    expect(tomo.finalName).toBeNull();
    expect(isRenamable(tomo)).toBe(false);
    const mismatch = byPath(plan.entries, "2009/Tomo 3/Concepto 4734 de 2008.pdf");
    expect(mismatch.reason).toBe("year-mismatch");
    expect(mismatch.finalName).toBe("CTO_PGN_0004734_2008(C).pdf");
    expect(isRenamable(mismatch)).toBe(true);
  });

  it("flags a document outside any year folder", async () => {
    const fs = fakeMutableDirectory("lote", { "Cto. 1.pdf": "x", Varios: { "Cto. 2.pdf": "x" } });

    const plan = await analyzeConceptBatch(fs.handle);

    expect(plan.entries.map((entry) => entry.reason)).toEqual(["no-year", "no-year"]);
    expect(plan.entries.every((entry) => entry.finalName === null)).toBe(true);
  });

  it("blocks a clash inside one folder but only warns about repeats across tomos", async () => {
    const fs = fakeMutableDirectory("lote", {
      "1993": {
        "Tomo 4": { "Cto. 257.pdf": "x", "Concepto 257 de 1993.pdf": "x", "Cto. 258.pdf": "x" },
        "Tomo 5": { "Cto. 258.pdf": "x" },
      },
    });

    const plan = await analyzeConceptBatch(fs.handle);

    for (const path of ["1993/Tomo 4/Cto. 257.pdf", "1993/Tomo 4/Concepto 257 de 1993.pdf"]) {
      const entry = byPath(plan.entries, path);
      expect(entry.reason).toBe("duplicate");
      expect(isRenamable(entry)).toBe(false);
    }
    expect(byPath(plan.entries, "1993/Tomo 4/Cto. 258.pdf").reason).toBeNull();
    expect(byPath(plan.entries, "1993/Tomo 5/Cto. 258.pdf").reason).toBeNull();
    expect(plan.crossFolderRepeats).toEqual([
      { finalName: "CTO_PGN_0000258_1993(C).pdf", paths: ["1993/Tomo 4/Cto. 258.pdf", "1993/Tomo 5/Cto. 258.pdf"] },
    ]);
  });

  it("renames nothing on a second pass over an already-renamed batch", async () => {
    const fs = fakeMutableDirectory("lote", {
      "registro_renombres_20261120-1010.csv": "x",
      "1991": { "Tomo 1": { "CTO_PGN_0001654_1991(C).pdf": "x" } },
    });

    const plan = await analyzeConceptBatch(fs.handle);

    expect(plan.entries).toHaveLength(1);
    expect(isAlreadyFinal(plan.entries[0])).toBe(true);
    expect(isRenamable(plan.entries[0])).toBe(false);
  });

  it("does not send an already-renamed year-mismatch file back to review", async () => {
    const fs = fakeMutableDirectory("lote", { "2009": { "Tomo 3": { "CTO_PGN_0004734_2008(C).pdf": "x" } } });

    const plan = await analyzeConceptBatch(fs.handle);

    expect(isAlreadyFinal(plan.entries[0])).toBe(true);
    expect(plan.entries[0].reason).toBeNull();
  });

  it("throws ConceptPgnError when the folder holds no documents", async () => {
    const fs = fakeMutableDirectory("lote", { "2006": { "TOMO 10": { "a.jpg": "x" } } });

    await expect(analyzeConceptBatch(fs.handle)).rejects.toBeInstanceOf(ConceptPgnError);
  });
});

describe("applyManualFixes", () => {
  it("completes a Tomo fragment and recomputes clashes without mutating the original plan", async () => {
    const fs = fakeMutableDirectory("lote", {
      "1991": { "Tomo 3": { "Tomo 3 1991-1-14.pdf": "x", "Cto. 1660.pdf": "x" } },
    });
    const plan = await analyzeConceptBatch(fs.handle);
    const tomoPath = "1991/Tomo 3/Tomo 3 1991-1-14.pdf";

    const clashing = applyManualFixes(plan, new Map([[tomoPath, { year: "1991", number: "1660" }]]));
    expect(byPath(clashing.entries, tomoPath).reason).toBe("duplicate");
    expect(byPath(clashing.entries, "1991/Tomo 3/Cto. 1660.pdf").reason).toBe("duplicate");

    const fixed = applyManualFixes(plan, new Map([[tomoPath, { year: "1991", number: "1661" }]]));
    const tomo = byPath(fixed.entries, tomoPath);
    expect(tomo.finalName).toBe("CTO_PGN_0001661_1991(C).pdf");
    expect(tomo.reason).toBeNull();
    expect(isRenamable(tomo)).toBe(true);
    expect(byPath(fixed.entries, "1991/Tomo 3/Cto. 1660.pdf").reason).toBeNull();

    expect(byPath(plan.entries, tomoPath).finalName).toBeNull();
    expect(byPath(plan.entries, tomoPath).reason).toBe("no-number");
  });

  it("keeps the year-mismatch row visible after its fields are confirmed", async () => {
    const fs = fakeMutableDirectory("lote", { "2009": { "Tomo 3": { "Concepto 4734 de 2008.pdf": "x" } } });
    const plan = await analyzeConceptBatch(fs.handle);
    const path = "2009/Tomo 3/Concepto 4734 de 2008.pdf";

    const fixed = applyManualFixes(plan, new Map([[path, { year: "2008", number: "4734" }]]));

    expect(byPath(fixed.entries, path).reason).toBe("year-mismatch");
    expect(byPath(fixed.entries, path).finalName).toBe("CTO_PGN_0004734_2008(C).pdf");
  });

  it("an invalid manual number leaves the file with its original name", async () => {
    const fs = fakeMutableDirectory("lote", { "1991": { "Tomo 3": { "Tomo 3 1991-1-14.pdf": "x" } } });
    const plan = await analyzeConceptBatch(fs.handle);
    const path = "1991/Tomo 3/Tomo 3 1991-1-14.pdf";

    const fixed = applyManualFixes(plan, new Map([[path, { year: "1991", number: "abc" }]]));

    expect(byPath(fixed.entries, path).finalName).toBeNull();
    expect(byPath(fixed.entries, path).reason).toBe("no-number");
  });
});
