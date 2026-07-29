import type { SourceCount, TipoCount } from "../api/types";

export interface CountBucket {
  label: string;
  count: number;
}

export function sourceCountsToBuckets(rows: SourceCount[]): CountBucket[] {
  return rows.map((row) => ({ label: row.name, count: row.count }));
}

export function tipoCountsToBuckets(rows: TipoCount[]): CountBucket[] {
  return rows.map((row) => ({ label: row.tipo, count: row.count }));
}
