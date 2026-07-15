import type { Document, Source, SourceFamily } from "../api/types";

export interface CountBucket {
  label: string;
  count: number;
}

function countBy(items: Document[], keyFn: (doc: Document) => string): CountBucket[] {
  const counts = new Map<string, number>();
  for (const item of items) {
    const key = keyFn(item);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count);
}

export function countByTipo(items: Document[], limit = 8): CountBucket[] {
  return countBy(items, (doc) => doc.tipo ?? "Sin tipo").slice(0, limit);
}

export function countByFamily(items: Document[], sources: Source[], families: SourceFamily[]): CountBucket[] {
  const familyKeyBySourceId = new Map(sources.map((source) => [source.id, source.family_key]));
  const displayNameByFamilyKey = new Map(families.map((family) => [family.key, family.display_name]));

  return countBy(items, (doc) => {
    const familyKey = familyKeyBySourceId.get(doc.source_id);
    if (!familyKey) return "Desconocida";
    return displayNameByFamilyKey.get(familyKey) ?? familyKey;
  });
}

// Manual "YYYY-MM-..." parsing (rather than `new Date(value).getFullYear()`)
// sidesteps the UTC-midnight-to-local-timezone day shift that would otherwise
// bucket a document dated the 1st of the month into the previous month for
// any browser west of UTC.
function yearMonthOf(dateValue: string): { year: number; month: number } {
  const [year, month] = dateValue.split("-");
  return { year: Number(year), month: Number(month) - 1 };
}

function bestDateFor(doc: Document): string | null {
  return doc.f_public ?? doc.downloaded_at ?? null;
}

export function availableYears(items: Document[]): number[] {
  const years = new Set<number>();
  for (const item of items) {
    const dateValue = bestDateFor(item);
    if (dateValue) years.add(yearMonthOf(dateValue).year);
  }
  return Array.from(years).sort((a, b) => b - a);
}

export function countByMonth(items: Document[], year: number): number[] {
  const counts = new Array(12).fill(0);
  for (const item of items) {
    const dateValue = bestDateFor(item);
    if (!dateValue) continue;
    const { year: itemYear, month } = yearMonthOf(dateValue);
    if (itemYear === year) counts[month] += 1;
  }
  return counts;
}
