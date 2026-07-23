import { describe, expect, it } from "vitest";
import { analyzeDirectory, computeFinalName } from "./analyze";
import { copyFormattedFiles } from "./copy";
import { fakeInputDirectory, fakeOutputDirectory } from "./testFsFakes";

describe("copyFormattedFiles", () => {
  it("writes each entry under its year folder using the resolved name", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": { "Acuerdo 0005 de 1962.pdf": "contenido-a" },
      "ACUERDOS 1963": { "Acuerdo 0001 de 1963.pdf": "contenido-b" },
    });
    const plan = await analyzeDirectory(root);
    const resolvedNames = new Map(plan.entries.map((entry) => [entry.path, computeFinalName(plan.config, entry)!]));
    const output = fakeOutputDirectory("salida");

    const progressCalls: Array<[number, number]> = [];
    const { copiedCount, skippedCount } = await copyFormattedFiles(output.handle, plan, resolvedNames, (done, total) =>
      progressCalls.push([done, total])
    );

    expect(copiedCount).toBe(2);
    expect(skippedCount).toBe(0);
    expect(output.readAll()).toEqual({
      "ACUERDOS 1962/A_CONCALI_0005_1962.pdf": "contenido-a",
      "ACUERDOS 1963/A_CONCALI_0001_1963.pdf": "contenido-b",
    });
    expect(progressCalls).toEqual([
      [1, 2],
      [2, 2],
    ]);
  });

  it("counts an entry as skipped when reading it fails, without aborting the rest of the batch", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": {
        "Acuerdo 0005 de 1962.pdf": "contenido-a",
        "Acuerdo 0006 de 1962.pdf": "contenido-b",
      },
    });
    const plan = await analyzeDirectory(root);
    const resolvedNames = new Map(plan.entries.map((entry) => [entry.path, computeFinalName(plan.config, entry)!]));
    const output = fakeOutputDirectory("salida");

    const brokenEntry = plan.entries.find((entry) => entry.filename === "Acuerdo 0005 de 1962.pdf")!;
    brokenEntry.fileHandle = {
      ...brokenEntry.fileHandle,
      getFile: async () => {
        throw new Error("simulated read failure");
      },
    } as typeof brokenEntry.fileHandle;

    const { copiedCount, skippedCount } = await copyFormattedFiles(output.handle, plan, resolvedNames);

    expect(copiedCount).toBe(1);
    expect(skippedCount).toBe(1);
    expect(output.readAll()).toEqual({
      "ACUERDOS 1962/A_CONCALI_0006_1962.pdf": "contenido-b",
    });
  });

  it("groups a flat batch's entries under the year folder derived from each filename", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "Acuerdo 0005 de 1962.pdf": "contenido-a",
    });
    const plan = await analyzeDirectory(root);
    const resolvedNames = new Map(plan.entries.map((entry) => [entry.path, computeFinalName(plan.config, entry)!]));
    const output = fakeOutputDirectory("salida");

    const { copiedCount } = await copyFormattedFiles(output.handle, plan, resolvedNames);

    expect(copiedCount).toBe(1);
    expect(output.readAll()).toEqual({ "1962/A_CONCALI_0005_1962.pdf": "contenido-a" });
  });
});
