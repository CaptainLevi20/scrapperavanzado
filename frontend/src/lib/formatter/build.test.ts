import { describe, expect, it } from "vitest";
import JSZip from "jszip";
import { analyzeZip, computeFinalName } from "./analyze";
import { buildFormattedZip } from "./build";

describe("buildFormattedZip", () => {
  it("writes each entry under its year folder using the resolved name", async () => {
    const source = new JSZip();
    source.file("Acuerdos Cali/ACUERDOS 1962/Acuerdo 0005 de 1962.pdf", "contenido-a");
    source.file("Acuerdos Cali/ACUERDOS 1963/Acuerdo 0001 de 1963.pdf", "contenido-b");
    const blob = await source.generateAsync({ type: "blob" });
    const file = new File([blob], "lote.zip", { type: "application/zip" });

    const plan = await analyzeZip(file);
    const zip = await JSZip.loadAsync(file);
    const resolvedNames = new Map(plan.entries.map((entry) => [entry.path, computeFinalName(plan.config, entry)!]));

    const { blob: outputBlob, skippedCount } = await buildFormattedZip(zip, plan, resolvedNames);

    expect(skippedCount).toBe(0);
    const output = await JSZip.loadAsync(outputBlob);
    const outputFileNames = Object.values(output.files)
      .filter((entry) => !entry.dir)
      .map((entry) => entry.name)
      .sort();
    expect(outputFileNames).toEqual([
      "ACUERDOS 1962/A_CONCALI_0005_1962.pdf",
      "ACUERDOS 1963/A_CONCALI_0001_1963.pdf",
    ]);
    expect(await output.file("ACUERDOS 1962/A_CONCALI_0005_1962.pdf")!.async("string")).toBe("contenido-a");
  });

  it("counts an entry as skipped when it's missing from the source zip", async () => {
    const source = new JSZip();
    source.file("Acuerdos Cali/ACUERDOS 1962/Acuerdo 0005 de 1962.pdf", "contenido-a");
    const blob = await source.generateAsync({ type: "blob" });
    const file = new File([blob], "lote.zip", { type: "application/zip" });

    const plan = await analyzeZip(file);
    const zip = await JSZip.loadAsync(file);
    const resolvedNames = new Map([[plan.entries[0].path, computeFinalName(plan.config, plan.entries[0])!]]);
    zip.remove(plan.entries[0].path);

    const { skippedCount } = await buildFormattedZip(zip, plan, resolvedNames);

    expect(skippedCount).toBe(1);
  });
});
