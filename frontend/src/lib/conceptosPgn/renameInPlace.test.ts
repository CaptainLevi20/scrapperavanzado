import { describe, expect, it } from "vitest";
import { analyzeConceptBatch } from "./analyze";
import { buildLogCsv, logFileName, renameConcepts } from "./renameInPlace";
import { fakeMutableDirectory, type MutableFsOptions } from "./testFsMutable";

const NOW = new Date(2026, 10, 20, 9, 5);
const LOG = "registro_renombres_20261120-0905.csv";

function withoutLog(snapshot: Record<string, string>): Record<string, string> {
  const copy = { ...snapshot };
  delete copy[LOG];
  return copy;
}

async function setup(options?: MutableFsOptions) {
  const fs = fakeMutableDirectory("lote", { "1991": { "Tomo 1": { "Cto. 1654.pdf": "contenido-1654" } } }, options);
  const plan = await analyzeConceptBatch(fs.handle);
  return { fs, plan };
}

describe("renameConcepts", () => {
  it("renames with move() when the browser supports it", async () => {
    const { fs, plan } = await setup();

    const summary = await renameConcepts(plan, { now: NOW });

    expect(withoutLog(fs.snapshot())).toEqual({ "1991/Tomo 1/CTO_PGN_0001654_1991(C).pdf": "contenido-1654" });
    expect(summary.renamedCount).toBe(1);
    expect(summary.skippedCount).toBe(0);
  });

  it("falls back to copy-verify-delete when move() doesn't exist", async () => {
    const { fs, plan } = await setup({ supportsMove: false });

    const summary = await renameConcepts(plan, { now: NOW });

    expect(withoutLog(fs.snapshot())).toEqual({ "1991/Tomo 1/CTO_PGN_0001654_1991(C).pdf": "contenido-1654" });
    expect(summary.renamedCount).toBe(1);
  });

  it("falls back for that file when move() throws", async () => {
    const { fs, plan } = await setup({ failMoveFor: ["Cto. 1654.pdf"] });

    const summary = await renameConcepts(plan, { now: NOW });

    expect(withoutLog(fs.snapshot())).toEqual({ "1991/Tomo 1/CTO_PGN_0001654_1991(C).pdf": "contenido-1654" });
    expect(summary.renamedCount).toBe(1);
  });

  it("never overwrites an existing destination, whatever its case", async () => {
    const { fs, plan } = await setup();
    fs.put("1991/Tomo 1/cto_pgn_0001654_1991(c).pdf", "viejo");

    const summary = await renameConcepts(plan, { now: NOW });

    expect(withoutLog(fs.snapshot())).toEqual({
      "1991/Tomo 1/Cto. 1654.pdf": "contenido-1654",
      "1991/Tomo 1/cto_pgn_0001654_1991(c).pdf": "viejo",
    });
    expect(summary.outcomes[0].skipReason).toBe("Ya existe un archivo con ese nombre en la carpeta");
  });

  it("skips a case-only rename when move() is unavailable", async () => {
    const fs = fakeMutableDirectory(
      "lote",
      { "1991": { "Tomo 1": { "cto_pgn_0001654_1991(C).pdf": "x" } } },
      { supportsMove: false }
    );
    const plan = await analyzeConceptBatch(fs.handle);

    const summary = await renameConcepts(plan, { now: NOW });

    expect(withoutLog(fs.snapshot())).toEqual({ "1991/Tomo 1/cto_pgn_0001654_1991(C).pdf": "x" });
    expect(summary.outcomes[0].skipReason).toBe("Solo cambian mayúsculas; renómbralo a mano");
  });

  it("does a case-only rename when move() is available", async () => {
    const fs = fakeMutableDirectory("lote", { "1991": { "Tomo 1": { "cto_pgn_0001654_1991(C).pdf": "x" } } });
    const plan = await analyzeConceptBatch(fs.handle);

    await renameConcepts(plan, { now: NOW });

    expect(withoutLog(fs.snapshot())).toEqual({ "1991/Tomo 1/CTO_PGN_0001654_1991(C).pdf": "x" });
  });

  it.each([
    ["a failed write", { supportsMove: false, failWriteFor: ["CTO_PGN_0001654_1991(C).pdf"] }],
    ["an incomplete write", { supportsMove: false, truncateWriteFor: ["CTO_PGN_0001654_1991(C).pdf"] }],
  ])("%s leaves the original intact and no leftovers", async (_label, options) => {
    const { fs, plan } = await setup(options);
    const before = fs.snapshot();

    const summary = await renameConcepts(plan, { now: NOW });

    expect(withoutLog(fs.snapshot())).toEqual(before);
    expect(summary.skippedCount).toBe(1);
    expect(summary.renamedCount).toBe(0);
  });

  it("keeps going after one file fails", async () => {
    const fs = fakeMutableDirectory(
      "lote",
      { "1991": { "Tomo 1": { "Cto. 1654.pdf": "a", "Cto. 1655.pdf": "b" } } },
      { supportsMove: false, failWriteFor: ["CTO_PGN_0001654_1991(C).pdf"] }
    );
    const plan = await analyzeConceptBatch(fs.handle);

    const summary = await renameConcepts(plan, { now: NOW });

    expect(withoutLog(fs.snapshot())).toEqual({
      "1991/Tomo 1/Cto. 1654.pdf": "a",
      "1991/Tomo 1/CTO_PGN_0001655_1991(C).pdf": "b",
    });
    expect(summary.renamedCount).toBe(1);
    expect(summary.skippedCount).toBe(1);
  });

  it("writes the log in the batch root", async () => {
    const { fs, plan } = await setup();

    const summary = await renameConcepts(plan, { now: NOW });

    expect(summary.logName).toBe(LOG);
    const log = fs.snapshot()[LOG];
    expect(log.startsWith("﻿ruta;nombre_anterior;nombre_nuevo;resultado\r\n")).toBe(true);
    expect(log).toContain("1991/Tomo 1/Cto. 1654.pdf;Cto. 1654.pdf;CTO_PGN_0001654_1991(C).pdf;renombrado");
  });

  it("writes the log as pending before touching any file", async () => {
    const { fs, plan } = await setup();
    let logDuringFirstRename: string | undefined;

    await renameConcepts(plan, {
      now: NOW,
      onProgress: (done) => {
        if (done === 0) logDuringFirstRename = fs.snapshot()[LOG];
      },
    });

    expect(logDuringFirstRename).toContain(";pendiente");
  });
});

describe("logFileName / buildLogCsv", () => {
  it("names the log by local date and time", () => {
    expect(logFileName(NOW)).toBe(LOG);
  });

  it("quotes fields with separators or quotes", () => {
    const csv = buildLogCsv([{ path: 'a;b/"c".pdf', from: "x", to: "y", result: "saltado: uno; dos" }]);
    expect(csv).toBe('﻿ruta;nombre_anterior;nombre_nuevo;resultado\r\n"a;b/""c"".pdf";x;y;"saltado: uno; dos"\r\n');
  });
});
