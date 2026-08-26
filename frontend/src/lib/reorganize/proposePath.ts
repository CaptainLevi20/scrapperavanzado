import type { ReorganizeException } from "../../api/types";

export interface Correction {
  entity: string;
  year: string;
}

function filenameOf(currentPath: string): string {
  const segments = currentPath.split("/");
  return segments[segments.length - 1];
}

export function computeProposedPath(entry: ReorganizeException, correction: Correction): string | null {
  const year = correction.year.trim();
  if (!/^(?:1[89]\d{2}|20\d{2})$/.test(year)) return null;
  const entity = correction.entity.trim();
  // Entity is required for a missing_entity_folder exception (that's the very
  // thing being fixed), and equally for a missing_year_folder exception whose
  // Tipo the backend already detected as con_entidad (signaled by a non-null
  // detected_entity, populated either from the filename or from the existing
  // entity folder name) — dropping it there would silently produce
  // Tipo/Año/archivo, missing the Entidad segment.
  const entityRequired = entry.kind === "missing_entity_folder" || entry.detected_entity !== null;
  if (entityRequired && !entity) return null;
  if (/[\\/]/.test(entity) || entity.includes("..")) return null;
  const filename = filenameOf(entry.current_path);
  return entity ? `${entry.tipo}/${entity}/${year}/${filename}` : `${entry.tipo}/${year}/${filename}`;
}
