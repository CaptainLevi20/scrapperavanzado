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

  it("extracts the year from the filename itself when the batch has no year subfolders at all", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "Acuerdo 0005 de 1962.pdf": "x",
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries).toHaveLength(1);
    expect(plan.entries[0]).toMatchObject({
      yearFolder: "1962",
      detectedYear: 1962,
      detectedNumber: 5,
      reason: null,
    });
    expect(computeFinalName(plan.config, plan.entries[0])).toBe("A_CONCALI_0005_1962.pdf");
  });

  it("detects config from filenames when the batch is flat and the root folder name alone lacks the keywords", async () => {
    const root = fakeInputDirectory("Lote 2026", {
      "Acuerdo 0005 de Cali 1962.pdf": "x",
    });

    const plan = await analyzeDirectory(root);

    expect(plan.config).toEqual({ typeCode: "A", cityCode: "CONCALI" });
  });

  it("does not extract a year from a stray root file's name when the batch also uses year subfolders elsewhere", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": { "Acuerdo 0005 de 1962.pdf": "x" },
      "suelto de 1998.pdf": "x",
    });

    const plan = await analyzeDirectory(root);

    const strayEntry = plan.entries.find((entry) => entry.filename === "suelto de 1998.pdf")!;
    expect(strayEntry).toMatchObject({ yearFolder: "", detectedYear: null, reason: "no-year" });
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

  it("updates yearFolder to match a genuinely corrected year, not just the filename", async () => {
    // Regression test: applyCorrections used to spread the entry as-is and only
    // override detectedYear/detectedNumber — yearFolder was carried over
    // unchanged, so a file whose year was auto-detected wrong (e.g. from the
    // "ACUERDOS 1962" folder) would get a corrected NAME but still be copied
    // into the OLD year's folder by copyFormattedFiles (copy.ts), which uses
    // yearFolder as the destination directory.
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": { "Acuerdo 0005 de 1963.pdf": "x" }, // misfiled: really a 1963 document
    });
    const plan = await analyzeDirectory(root);
    expect(plan.entries[0].yearFolder).toBe("ACUERDOS 1962");

    const resolved = applyCorrections(plan, new Map([[plan.entries[0].path, { year: "1963", number: "5" }]]));

    expect(resolved.entries[0].detectedYear).toBe(1963);
    expect(resolved.entries[0].yearFolder).toBe("1963");
    expect(computeFinalName(resolved.config, resolved.entries[0])).toBe("A_CONCALI_0005_1963.pdf");
  });

  it("keeps the original yearFolder when a correction only fixes the number, not the year", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": { "sin numero.pdf": "x" },
    });
    const plan = await analyzeDirectory(root);

    // Mirrors FormatterPage.tsx: the year field is pre-filled with the
    // already-correct detected year, only the number is actually edited.
    const resolved = applyCorrections(
      plan,
      new Map([[plan.entries[0].path, { year: String(plan.entries[0].detectedYear), number: "9" }]])
    );

    expect(resolved.entries[0].yearFolder).toBe("ACUERDOS 1962");
  });

  it("clears yearFolder when a correction removes the year entirely", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": { "Acuerdo 0005 de 1962.pdf": "x" },
    });
    const plan = await analyzeDirectory(root);

    const resolved = applyCorrections(plan, new Map([[plan.entries[0].path, { year: "", number: "5" }]]));

    expect(resolved.entries[0].detectedYear).toBeNull();
    expect(resolved.entries[0].yearFolder).toBe("");
    expect(resolved.entries[0].reason).toBe("no-year");
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

describe("markDuplicates auto-resolution", () => {
  it("auto-resolves a duplicate pair via a '(1)' filename marker, appending _1 to the copy", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1973": {
        "055NOVIEMBRE1973ACUERDO.pdf": "x",
        "055NOVIEMBRE1973ACUERDO (1).pdf": "x",
      },
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries.every((entry) => entry.reason === null)).toBe(true);
    const names = plan.entries.map((entry) => computeFinalName(plan.config, entry)).sort();
    expect(names).toEqual(["A_CONCALI_0055_1973.pdf", "A_CONCALI_0055_1973_1.pdf"]);
  });

  it("auto-resolves an 'anexo' collision by numbering each attachment", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 2016": {
        "Acuerdo No.402 anexos.rar": "x",
        "Acuerdo No.402 anexos abril 2017.rar": "x",
      },
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries.every((entry) => entry.reason === null)).toBe(true);
    const names = plan.entries.map((entry) => computeFinalName(plan.config, entry)).sort();
    expect(names).toEqual(["A_CONCALI_0402_2016_anexo1.rar", "A_CONCALI_0402_2016_anexo2.rar"]);
  });

  it("auto-resolves a collision where one file is a 'nulidad' ruling about the other, appending _nulidad", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1998": {
        "acdo32-98.pdf": "x",
        "NULIDAD ARTICULO 16 DEL ACUERDO 032 DE 1998 PDF1.PDF": "x",
      },
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries.every((entry) => entry.reason === null)).toBe(true);
    const names = plan.entries.map((entry) => computeFinalName(plan.config, entry)).sort();
    expect(names).toEqual(["A_CONCALI_0032_1998.pdf", "A_CONCALI_0032_1998_nulidad.pdf"]);
  });

  it("still requires manual review when every colliding file mentions 'nulidad' (nothing to distinguish them)", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1998": {
        "NULIDAD PARCIAL ACUERDO 032 DE 1998.pdf": "x",
        "NULIDAD TOTAL ACUERDO 032 DE 1998.pdf": "x",
      },
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries.every((entry) => entry.reason === "duplicate")).toBe(true);
  });

  it("still requires manual review when neither the '(N)' nor the 'anexo' pattern disambiguates a collision", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": {
        "Acuerdo 0005 primero.pdf": "x",
        "Acuerdo 0005 segundo.pdf": "x",
      },
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries.every((entry) => entry.reason === "duplicate")).toBe(true);
  });

  it("falls back to manual review when two colliding copies share the same '(N)' marker", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": {
        "Acuerdo 0005 (1) copia a.pdf": "x",
        "Acuerdo 0005 (1) copia b.pdf": "x",
      },
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries.every((entry) => entry.reason === "duplicate")).toBe(true);
  });
});
