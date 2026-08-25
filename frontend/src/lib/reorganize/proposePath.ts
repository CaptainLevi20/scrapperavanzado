import type { ReorganizeException } from "../../api/types";

export interface Correction {
  entity: string;
  year: string;
}

function filenameOf(currentPath: string): string {
  const segments = currentPath.split("/");
  return segments[segments.length - 1];
}

function tipoOf(currentPath: string): string {
  const segments = currentPath.split("/");
  return segments[0];
}

export function computeProposedPath(entry: ReorganizeException, correction: Correction): string | null {
  const year = correction.year.trim();
  if (!/^\d{4}$/.test(year)) return null;
  const entity = correction.entity.trim();
  if (entry.kind === "missing_entity_folder" && !entity) return null;
  const tipo = tipoOf(entry.current_path);
  const filename = filenameOf(entry.current_path);
  return entity ? `${tipo}/${entity}/${year}/${filename}` : `${tipo}/${year}/${filename}`;
}
