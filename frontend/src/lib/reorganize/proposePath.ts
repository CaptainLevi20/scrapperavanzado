import type { ReorganizeException } from "../../api/types";

export interface Correction {
  entity: string;
  year: string;
}

export function initialCorrection(entry: ReorganizeException): Correction {
  const year = entry.detected_year ?? entry.mtime_year_hint;
  return { entity: entry.detected_entity ?? "", year: year !== null ? String(year) : "" };
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

export function computeFolderRenameTarget(tipo: string, entityName: string): string | null {
  const entity = entityName.trim();
  if (!entity) return null;
  if (/[\\/]/.test(entity) || entity.includes("..")) return null;
  return `${tipo}/${entity}`;
}

// A confirmed, narrow pattern: a folder literally named "CM" + a city (e.g.
// "CMAGUACHICA") where the file names just "C" + that same city (e.g.
// "CAGUACHICA" — the "M" dropped). Verified against the real batch across
// 13 different city folders under ACUERDOS, all consistent — a systematic
// naming convention gap, not coincidental typos. Doesn't fire for a city
// whose own name starts with "M" (Medellín, Mocoa, Montería all correctly
// keep "CM" in both the folder and the filename, so they never mismatch in
// the first place — this pattern only ever sees the cases where they do).
function isConfirmedCmToCPattern(entry: ReorganizeException): boolean {
  if (entry.detected_entity === null) return false;
  const currentEntity = entry.current_path.split("/")[1];
  if (!currentEntity || currentEntity.slice(0, 2).toUpperCase() !== "CM") return false;
  const expected = currentEntity.slice(0, 1) + currentEntity.slice(2);
  return expected.toUpperCase() === entry.detected_entity.toUpperCase();
}

// Another confirmed, narrow case: the handful of files left behind in
// CONCEPTO/SDH always belong under CONCEPTO/SDHBOG (900+ files) — the same
// "todo debe ser SDHBOG" correction already applied everywhere else this
// entity shows up in the batch. These can't go through the whole-folder
// rename (that requires the target to NOT already exist — merging into an
// existing folder isn't a rename), so they'd otherwise sit as individual
// entity_mismatch rows needing a click every single analysis even though
// the destination is already an established, confirmed folder.
function isConfirmedSdhToSdhbogMerge(entry: ReorganizeException): boolean {
  const currentEntity = entry.current_path.split("/")[1];
  return entry.tipo === "CONCEPTO" && currentEntity === "SDH" && entry.detected_entity === "SDHBOG";
}

// Whether a file's own exception can be resolved without a human decision.
// entity_mismatch only ever qualifies via one of the confirmed patterns
// above — otherwise the folder and the filename actively disagree, which is a
// judgment call about which one is right, not just a gap to fill in. For
// the other kinds: the year must come from the filename itself, never the
// mtime fallback (that's explicitly not authoritative), AND the
// exception's own detected values must resolve to a complete, valid path
// on their own — reusing computeProposedPath against initialCorrection is
// what actually proves nothing is left blank (e.g. a missing_entity_folder
// whose entity couldn't be read from the filename still needs a human to
// type one in, even though its year is known from the folder it's already
// sitting in).
export function isConfidentException(entry: ReorganizeException): boolean {
  if (entry.kind === "entity_mismatch") {
    return isConfirmedCmToCPattern(entry) || isConfirmedSdhToSdhbogMerge(entry);
  }
  if (entry.detected_year === null) return false;
  return computeProposedPath(entry, initialCorrection(entry)) !== null;
}
