import type { FamilyCount, TipoCount } from "../api/types";

export interface CountBucket {
  label: string;
  count: number;
}

export function familyCountsToBuckets(rows: FamilyCount[]): CountBucket[] {
  return rows.map((row) => ({ label: row.display_name, count: row.count }));
}

export function tipoCountsToBuckets(rows: TipoCount[]): CountBucket[] {
  return rows.map((row) => ({ label: row.tipo, count: row.count }));
}
