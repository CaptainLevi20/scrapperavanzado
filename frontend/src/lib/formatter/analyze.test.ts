import { describe, expect, it } from "vitest";
import JSZip from "jszip";
import { analyzeZip, applyCorrections, computeFinalName, FormatterError } from "./analyze";

async function toFile(zip: JSZip, name: string): Promise<File> {
  const blob = await zip.generateAsync({ type: "blob" });
  return new File([blob], name, { type: "application/zip" });
}

describe("analyzeZip", () => {
  it("detects config, year and number for a zip wrapped in a root folder", async () => {
    const zip = new JSZip();
    zip.file("Acuerdos Cali/ACUERDOS 1962/Acuerdo 0005 de 1962.pdf", "x");
    const file = await toFile(zip, "lote.zip");

    const plan = await analyzeZip(file);

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

  it("falls back to the uploaded file's name when there is no shared root folder", async () => {
    const zip = new JSZip();
    zip.file("ACUERDOS 1962/Acuerdo 0005 de 1962.pdf", "x");
    zip.file("ACUERDOS 1963/Acuerdo 0001 de 1963.pdf", "x");
    const file = await toFile(zip, "Acuerdos Cali.zip");

    const plan = await analyzeZip(file);

    expect(plan.rootFolderName).toBe("Acuerdos Cali");
    expect(plan.entries.find((entry) => entry.yearFolder === "ACUERDOS 1962")).toBeTruthy();
    expect(plan.entries.find((entry) => entry.yearFolder === "ACUERDOS 1963")).toBeTruthy();
  });

  it("throws when the root folder name doesn't match a known type/city", async () => {
    const zip = new JSZip();
    zip.file("Resoluciones Bogota/2020/algo.pdf", "x");
    const file = await toFile(zip, "lote.zip");

    await expect(analyzeZip(file)).rejects.toThrow(FormatterError);
  });

  it("marks files without a detectable year as no-year", async () => {
    const zip = new JSZip();
    zip.file("Acuerdos Cali/VARIOS/Acuerdo 0005.pdf", "x");
    const file = await toFile(zip, "lote.zip");

    const plan = await analyzeZip(file);

    expect(plan.entries[0].reason).toBe("no-year");
    expect(plan.entries[0].detectedYear).toBeNull();
  });

  it("marks files without a detectable number as no-number", async () => {
    const zip = new JSZip();
    zip.file("Acuerdos Cali/ACUERDOS 1962/sin numero.pdf", "x");
    const file = await toFile(zip, "lote.zip");

    const plan = await analyzeZip(file);

    expect(plan.entries[0].reason).toBe("no-number");
  });

  it("marks colliding names as duplicate", async () => {
    const zip = new JSZip();
    zip.file("Acuerdos Cali/ACUERDOS 1962/Acuerdo 0005 primero.pdf", "x");
    zip.file("Acuerdos Cali/ACUERDOS 1962/Acuerdo 0005 segundo.pdf", "x");
    const file = await toFile(zip, "lote.zip");

    const plan = await analyzeZip(file);

    expect(plan.entries.every((entry) => entry.reason === "duplicate")).toBe(true);
  });

  it("throws for a zip with no files", async () => {
    const zip = new JSZip();
    zip.folder("Acuerdos Cali/ACUERDOS 1962");
    const file = await toFile(zip, "lote.zip");

    await expect(analyzeZip(file)).rejects.toThrow(FormatterError);
  });
});

describe("applyCorrections", () => {
  it("resolves an exception and clears its reason once a valid year and number are supplied", async () => {
    const zip = new JSZip();
    zip.file("Acuerdos Cali/ACUERDOS 1962/sin numero.pdf", "x");
    const file = await toFile(zip, "lote.zip");
    const plan = await analyzeZip(file);

    const corrections = new Map([[plan.entries[0].path, { year: "1962", number: "9" }]]);
    const resolved = applyCorrections(plan, corrections);

    expect(resolved.entries[0].reason).toBeNull();
    expect(computeFinalName(resolved.config, resolved.entries[0])).toBe("A_CONCALI_0009_1962.pdf");
  });

  it("re-flags a collision introduced by a correction, and clears one resolved by a later correction", async () => {
    const zip = new JSZip();
    zip.file("Acuerdos Cali/ACUERDOS 1962/Acuerdo 0005 uno.pdf", "x");
    zip.file("Acuerdos Cali/ACUERDOS 1962/sin numero.pdf", "x");
    const file = await toFile(zip, "lote.zip");
    const plan = await analyzeZip(file);
    const noNumberEntry = plan.entries.find((entry) => entry.reason === "no-number")!;

    const collided = applyCorrections(plan, new Map([[noNumberEntry.path, { year: "1962", number: "5" }]]));
    expect(collided.entries.every((entry) => entry.reason === "duplicate")).toBe(true);

    const resolved = applyCorrections(plan, new Map([[noNumberEntry.path, { year: "1962", number: "6" }]]));
    expect(resolved.entries.every((entry) => entry.reason === null)).toBe(true);
  });
});
