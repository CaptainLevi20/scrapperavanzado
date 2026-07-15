import { describe, expect, it } from "vitest";
import { availableYears, countByFamily, countByMonth, countByTipo } from "./dashboardStats";
import type { Document, Source, SourceFamily } from "../api/types";

function makeDoc(overrides: Partial<Document> = {}): Document {
  return {
    id: 1,
    doc_id: "doc-1",
    source_id: 1,
    title: "Doc",
    tipo: "Resolución",
    seccion: null,
    especialidad: null,
    magistrado: null,
    detalle: null,
    f_public: "2026-01-15",
    f_providencia: null,
    source_url: null,
    storage_bucket: "bucket",
    storage_key: "key.pdf",
    content_type: "application/pdf",
    file_size_bytes: 100,
    review_status: "pending",
    reviewed_at: null,
    downloaded_at: "2026-01-16T00:00:00Z",
    ...overrides,
  };
}

describe("countByTipo", () => {
  it("groups and sorts by count descending", () => {
    const docs = [
      makeDoc({ tipo: "Resolución" }),
      makeDoc({ tipo: "Resolución" }),
      makeDoc({ tipo: "Circular" }),
    ];

    expect(countByTipo(docs)).toEqual([
      { label: "Resolución", count: 2 },
      { label: "Circular", count: 1 },
    ]);
  });

  it("buckets a null tipo under 'Sin tipo'", () => {
    const docs = [makeDoc({ tipo: null })];
    expect(countByTipo(docs)).toEqual([{ label: "Sin tipo", count: 1 }]);
  });

  it("truncates to the given limit", () => {
    const docs = ["A", "B", "C"].map((tipo) => makeDoc({ tipo }));
    expect(countByTipo(docs, 2)).toHaveLength(2);
  });
});

describe("countByFamily", () => {
  const sources: Source[] = [
    { id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: true },
    { id: 2, family_key: "samai", name: "Consejo de Estado", family_params: {}, active: true },
  ];
  const families: SourceFamily[] = [
    { key: "constitucional", display_name: "Corte Constitucional", description: null },
    { key: "samai", display_name: "SAMAI", description: null },
  ];

  it("resolves source_id to the family's display name", () => {
    const docs = [makeDoc({ source_id: 1 }), makeDoc({ source_id: 1 }), makeDoc({ source_id: 2 })];

    expect(countByFamily(docs, sources, families)).toEqual([
      { label: "Corte Constitucional", count: 2 },
      { label: "SAMAI", count: 1 },
    ]);
  });

  it("falls back to 'Desconocida' when the source_id isn't in the active sources list", () => {
    const docs = [makeDoc({ source_id: 999 })];
    expect(countByFamily(docs, sources, families)).toEqual([{ label: "Desconocida", count: 1 }]);
  });
});

describe("availableYears", () => {
  it("returns distinct years sorted descending, preferring f_public over downloaded_at", () => {
    const docs = [
      makeDoc({ f_public: "2024-05-01", downloaded_at: "2026-01-01T00:00:00Z" }),
      makeDoc({ f_public: "2025-05-01", downloaded_at: "2026-01-01T00:00:00Z" }),
      makeDoc({ f_public: null, downloaded_at: "2023-01-01T00:00:00Z" }),
    ];

    expect(availableYears(docs)).toEqual([2025, 2024, 2023]);
  });
});

describe("countByMonth", () => {
  it("counts documents per month for the given year only", () => {
    const docs = [
      makeDoc({ f_public: "2026-01-05" }),
      makeDoc({ f_public: "2026-01-20" }),
      makeDoc({ f_public: "2026-03-01" }),
      makeDoc({ f_public: "2025-01-01" }), // different year, excluded
    ];

    const counts = countByMonth(docs, 2026);

    expect(counts[0]).toBe(2); // January
    expect(counts[2]).toBe(1); // March
    expect(counts.reduce((a, b) => a + b, 0)).toBe(3);
  });

  it("does not shift a first-of-month date into the previous month", () => {
    // Regression: new Date("2026-01-01").getMonth() renders as December in
    // any browser west of UTC, because the string parses as UTC midnight.
    const docs = [makeDoc({ f_public: "2026-01-01" })];
    const counts = countByMonth(docs, 2026);
    expect(counts[0]).toBe(1);
    expect(counts[11]).toBe(0);
  });
});
