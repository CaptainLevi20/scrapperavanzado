import { describe, expect, it } from "vitest";
import { sourceCountsToBuckets, tipoCountsToBuckets } from "./dashboardStats";

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

describe("sourceCountsToBuckets", () => {
  it("maps id/name/count rows to label/count buckets", () => {
    expect(
      sourceCountsToBuckets([
        { id: 1, name: "Corte Constitucional", count: 2 },
        { id: 2, name: "Consejo de Estado", count: 1 },
      ])
    ).toEqual([
      { label: "Corte Constitucional", count: 2 },
      { label: "Consejo de Estado", count: 1 },
    ]);
  });
});
