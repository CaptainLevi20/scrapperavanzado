import { describe, expect, it } from "vitest";
import type { ReorganizeException } from "../../api/types";
import { computeProposedPath } from "./proposePath";

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
});
