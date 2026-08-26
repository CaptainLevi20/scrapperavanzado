import { describe, expect, it } from "vitest";
import type { ReorganizeException } from "../../api/types";
import { computeFolderRenameTarget, computeProposedPath, isConfidentException } from "./proposePath";

function makeException(overrides: Partial<ReorganizeException> = {}): ReorganizeException {
  return {
    tipo: "DECRETOS",
    kind: "missing_entity_folder",
    current_path: "DECRETOS/2022/D_MSPS_0017AJ_2022.pdf",
    detected_entity: "MSPS",
    detected_year: 2022,
    mtime_year_hint: null,
    proposed_path: null,
    ...overrides,
  };
}

describe("computeProposedPath", () => {
  it("builds Tipo/Entidad/Año/archivo when entity and year are resolved", () => {
    const entry = makeException();
    expect(computeProposedPath(entry, { entity: "MSPS", year: "2022" })).toBe(
      "DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf"
    );
  });

  it("returns null for missing_entity_folder when entity is blank", () => {
    const entry = makeException({ detected_entity: null });
    expect(computeProposedPath(entry, { entity: "", year: "2022" })).toBeNull();
  });

  it("returns null when year isn't four digits", () => {
    const entry = makeException();
    expect(computeProposedPath(entry, { entity: "MSPS", year: "22" })).toBeNull();
  });

  it("builds Tipo/Año/archivo (no entity segment) for a missing_year_folder entry with no entity", () => {
    const entry = makeException({
      kind: "missing_year_folder",
      tipo: "Leyes",
      current_path: "Leyes/LEY_0042_2019.pdf",
      detected_entity: null,
      detected_year: null,
    });
    expect(computeProposedPath(entry, { entity: "", year: "2019" })).toBe("Leyes/2019/LEY_0042_2019.pdf");
  });

  it("returns null for a missing_year_folder entry under a con_entidad Tipo when entity is blank", () => {
    const entry = makeException({
      kind: "missing_year_folder",
      tipo: "RESOLUCIONES",
      current_path: "RESOLUCIONES/PGN/R_PGN_0158.docx",
      detected_entity: "PGN",
      detected_year: null,
    });
    expect(computeProposedPath(entry, { entity: "", year: "2019" })).toBeNull();
  });

  it("rejects an entity containing a path separator or a parent-directory reference", () => {
    const entry = makeException();
    expect(computeProposedPath(entry, { entity: "../..", year: "2022" })).toBeNull();
    expect(computeProposedPath(entry, { entity: "MSPS/../etc", year: "2022" })).toBeNull();
    expect(computeProposedPath(entry, { entity: "MSPS\\etc", year: "2022" })).toBeNull();
  });

  it("rejects a year outside the plausible 1800-2099 range", () => {
    const entry = makeException();
    expect(computeProposedPath(entry, { entity: "MSPS", year: "0000" })).toBeNull();
    expect(computeProposedPath(entry, { entity: "MSPS", year: "3450" })).toBeNull();
  });

  it("accepts a boundary year matching the backend's YEAR_RE", () => {
    const entry = makeException();
    expect(computeProposedPath(entry, { entity: "MSPS", year: "1899" })).toBe("DECRETOS/MSPS/1899/D_MSPS_0017AJ_2022.pdf");
  });
});

describe("computeFolderRenameTarget", () => {
  it("builds Tipo/NuevaEntidad", () => {
    expect(computeFolderRenameTarget("ACUERDOS", "CARAUCA")).toBe("ACUERDOS/CARAUCA");
  });

  it("returns null when the entity is blank", () => {
    expect(computeFolderRenameTarget("ACUERDOS", "")).toBeNull();
    expect(computeFolderRenameTarget("ACUERDOS", "   ")).toBeNull();
  });

  it("rejects an entity containing a path separator or a parent-directory reference", () => {
    expect(computeFolderRenameTarget("ACUERDOS", "../..")).toBeNull();
    expect(computeFolderRenameTarget("ACUERDOS", "CARAUCA/../etc")).toBeNull();
    expect(computeFolderRenameTarget("ACUERDOS", "CARAUCA\\etc")).toBeNull();
  });
});

describe("isConfidentException", () => {
  it("is confident for missing_entity_folder once resolved from the filename", () => {
    expect(isConfidentException(makeException())).toBe(true);
  });

  it("is confident for year_mismatch (year is always read from the filename, never a guess)", () => {
    const entry = makeException({
      kind: "year_mismatch",
      detected_entity: "MME",
      detected_year: 2015,
    });
    expect(isConfidentException(entry)).toBe(true);
  });

  it("is confident for missing_year_folder once the year is resolved from the filename", () => {
    const entry = makeException({
      kind: "missing_year_folder",
      detected_entity: "PGN",
      detected_year: 2019,
    });
    expect(isConfidentException(entry)).toBe(true);
  });

  it("is NOT confident when the year is only an mtime guess", () => {
    const entry = makeException({
      kind: "missing_year_folder",
      detected_year: null,
      mtime_year_hint: 2022,
    });
    expect(isConfidentException(entry)).toBe(false);
  });

  it("is never confident for entity_mismatch, even with a resolved year", () => {
    const entry = makeException({ kind: "entity_mismatch", detected_entity: "AGN", detected_year: 2003 });
    expect(isConfidentException(entry)).toBe(false);
  });

  it("is NOT confident for missing_entity_folder when the entity couldn't be parsed, even though the year is always known", () => {
    // detected_year for missing_entity_folder is the year of the folder the
    // file already sits in — always known, never a guess — but a blank
    // entity still means a human has to type one in.
    const entry = makeException({ detected_entity: null, detected_year: 2022 });
    expect(isConfidentException(entry)).toBe(false);
  });
});
