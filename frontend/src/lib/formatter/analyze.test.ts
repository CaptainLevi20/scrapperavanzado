import { describe, expect, it } from "vitest";
import { analyzeDirectory, applyCorrections, computeFinalName, FormatterError } from "./analyze";
import { fakeInputDirectory } from "./testFsFakes";

describe("analyzeDirectory", () => {
  it("detects config, year and number for files under year subfolders", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": { "Acuerdo 0005 de 1962.pdf": "x" },
    });

    const plan = await analyzeDirectory(root);

    expect(plan.config).toEqual({ typeCode: "A", cityCode: "CONCALI" });
    expect(plan.rootFolderName).toBe("Acuerdos Cali");
    expect(plan.entries).toHaveLength(1);
    expect(plan.entries[0]).toMatchObject({
      yearFolder: "ACUERDOS 1962",
      detectedYear: 1962,
      detectedNumber: 5,
      reason: null,
    });
  });

  it("detects config from year-folder names when the root folder name lacks the type keyword", async () => {
    const root = fakeInputDirectory("CALI 2026", {
      "ACUERDOS 1962": { "Acuerdo 0005 de 1962.pdf": "x" },
      "ACUERDOS 1963": { "Acuerdo 0001 de 1963.pdf": "x" },
    });

    const plan = await analyzeDirectory(root);

    expect(plan.config).toEqual({ typeCode: "A", cityCode: "CONCALI" });
  });

  it("throws when the root and year-folder names don't match a known type/city", async () => {
    const root = fakeInputDirectory("Resoluciones Bogota", {
      "2020": { "algo.pdf": "x" },
    });

    await expect(analyzeDirectory(root)).rejects.toThrow(FormatterError);
  });

  it("marks files without a detectable year as no-year", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      VARIOS: { "Acuerdo 0005.pdf": "x" },
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries[0].reason).toBe("no-year");
    expect(plan.entries[0].detectedYear).toBeNull();
  });

  it("marks a file sitting directly in the root (no year folder) as no-year", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "suelto.pdf": "x",
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries[0]).toMatchObject({ yearFolder: "", reason: "no-year" });
  });

  it("marks files without a detectable number as no-number", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": { "sin numero.pdf": "x" },
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries[0].reason).toBe("no-number");
  });

  it("marks colliding names as duplicate", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": {
        "Acuerdo 0005 primero.pdf": "x",
        "Acuerdo 0005 segundo.pdf": "x",
      },
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries.every((entry) => entry.reason === "duplicate")).toBe(true);
  });

  it("throws for a folder with no files", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": {},
    });

    await expect(analyzeDirectory(root)).rejects.toThrow(FormatterError);
  });
});

describe("applyCorrections", () => {
  it("resolves an exception and clears its reason once a valid year and number are supplied", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": { "sin numero.pdf": "x" },
    });
    const plan = await analyzeDirectory(root);

    const corrections = new Map([[plan.entries[0].path, { year: "1962", number: "9" }]]);
    const resolved = applyCorrections(plan, corrections);

    expect(resolved.entries[0].reason).toBeNull();
    expect(computeFinalName(resolved.config, resolved.entries[0])).toBe("A_CONCALI_0009_1962.pdf");
  });

  it("re-flags a collision introduced by a correction, and clears one resolved by a later correction", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": {
        "Acuerdo 0005 uno.pdf": "x",
        "sin numero.pdf": "x",
      },
    });
    const plan = await analyzeDirectory(root);
    const noNumberEntry = plan.entries.find((entry) => entry.reason === "no-number")!;

    const collided = applyCorrections(plan, new Map([[noNumberEntry.path, { year: "1962", number: "5" }]]));
    expect(collided.entries.every((entry) => entry.reason === "duplicate")).toBe(true);

    const resolved = applyCorrections(plan, new Map([[noNumberEntry.path, { year: "1962", number: "6" }]]));
    expect(resolved.entries.every((entry) => entry.reason === null)).toBe(true);
  });
});
