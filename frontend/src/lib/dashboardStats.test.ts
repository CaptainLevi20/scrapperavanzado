import { describe, expect, it } from "vitest";
import { familyCountsToBuckets, tipoCountsToBuckets } from "./dashboardStats";

describe("tipoCountsToBuckets", () => {
  it("maps tipo/count rows to label/count buckets, preserving server-given order", () => {
    expect(
      tipoCountsToBuckets([
        { tipo: "Resolución", count: 2 },
        { tipo: "Circular", count: 1 },
      ])
    ).toEqual([
      { label: "Resolución", count: 2 },
      { label: "Circular", count: 1 },
    ]);
  });
});

describe("familyCountsToBuckets", () => {
  it("maps key/display_name/count rows to label/count buckets", () => {
    expect(
      familyCountsToBuckets([
        { key: "constitucional", display_name: "Corte Constitucional", count: 2 },
        { key: "samai", display_name: "SAMAI", count: 1 },
      ])
    ).toEqual([
      { label: "Corte Constitucional", count: 2 },
      { label: "SAMAI", count: 1 },
    ]);
  });
});
