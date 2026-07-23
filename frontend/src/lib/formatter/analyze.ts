import { buildFileName, detectConfig, extractNumber, extractYear, fileExtension, type FormatterConfig } from "./rules";

export type FormatterReason = "no-year" | "no-number" | "duplicate";

export interface FormatterEntry {
  path: string;
  yearFolder: string;
  filename: string;
  fileHandle: FileSystemFileHandle;
  detectedYear: number | null;
  detectedNumber: number | null;
  reason: FormatterReason | null;
  suffix: string;
}

export interface FormatterPlan {
  config: FormatterConfig;
  rootFolderName: string;
  entries: FormatterEntry[];
}

export interface Correction {
  year: string;
  number: string;
}

export class FormatterError extends Error {}

interface RawEntry {
  path: string;
  yearFolder: string;
  filename: string;
  fileHandle: FileSystemFileHandle;
}

export async function analyzeDirectory(root: FileSystemDirectoryHandle): Promise<FormatterPlan> {
  const rootFolderName = root.name;
  const rawEntries: RawEntry[] = [];

  for await (const handle of root.values()) {
    if (handle.kind === "file") {
      rawEntries.push({ path: handle.name, yearFolder: "", filename: handle.name, fileHandle: handle });
      continue;
    }
    for await (const child of handle.values()) {
      if (child.kind !== "file") continue;
      rawEntries.push({
        path: `${handle.name}/${child.name}`,
        yearFolder: handle.name,
        filename: child.name,
        fileHandle: child,
      });
    }
  }

  if (rawEntries.length === 0) {
    throw new FormatterError("La carpeta no contiene ningún archivo.");
  }

  // The root folder's own name doesn't always carry both the type and city
  // keywords — e.g. a folder named "CALI 2026" only has the city, while the
  // type ("Acuerdo") only shows up in each year subfolder's own name
  // ("ACUERDOS 1962"). Searching across every distinct year-folder name too
  // (in addition to rootFolderName) covers that real-world naming pattern.
  const yearFolderNames = Array.from(
    new Set(rawEntries.filter((entry) => entry.yearFolder !== "").map((entry) => entry.yearFolder))
  );

  const config = detectConfig([rootFolderName, ...yearFolderNames].join(" "));
  if (!config) {
    throw new FormatterError(`No se reconoce el tipo de documento o la ciudad en «${rootFolderName}».`);
  }

  const entries: FormatterEntry[] = rawEntries.map(({ path, yearFolder, filename, fileHandle }) => {
    if (yearFolder === "") {
      return {
        path,
        yearFolder,
        filename,
        fileHandle,
        detectedYear: null,
        detectedNumber: null,
        reason: null,
        suffix: "",
      };
    }
    const detectedYear = extractYear(yearFolder);
    const detectedNumber = detectedYear === null ? null : extractNumber(filename, detectedYear);
    return { path, yearFolder, filename, fileHandle, detectedYear, detectedNumber, reason: null, suffix: "" };
  });

  markDuplicates(entries, config);

  return { config, rootFolderName, entries };
}

export function computeFinalName(config: FormatterConfig, entry: FormatterEntry): string | null {
  if (entry.detectedYear === null || entry.detectedNumber === null) return null;
  return buildFileName(config, entry.detectedNumber, entry.detectedYear, fileExtension(entry.filename), entry.suffix);
}

function recomputeReasons(entries: FormatterEntry[]): void {
  for (const entry of entries) {
    if (entry.detectedYear === null) entry.reason = "no-year";
    else if (entry.detectedNumber === null) entry.reason = "no-number";
    else entry.reason = null;
  }
}

function normalizeForMatch(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

function parenMarker(filename: string): string | null {
  const match = /\((\d+)\)/.exec(filename);
  return match ? match[1] : null;
}

// Some collisions have an unambiguous resolution baked into the original
// filenames themselves, so they don't need a human to look at them:
//   - Every colliding file mentions "anexo" (an attachment) → number them
//     _anexo1, _anexo2, ... in a stable order.
//   - Exactly one colliding file has a plain name and the rest carry a
//     Windows-style "(N)" copy marker → the plain one keeps its name, the
//     copies get "_N" appended.
// Returns true if the whole group was resolved (each entry's `suffix` is set
// and all entries now have distinct final names); false if it still needs
// manual review, in which case no entry's `suffix` is touched.
function tryAutoResolveCollision(group: FormatterEntry[], config: FormatterConfig): boolean {
  const hasAnexo = group.some((entry) => normalizeForMatch(entry.filename).includes("anexo"));
  if (hasAnexo) {
    const sorted = [...group].sort((a, b) => a.filename.localeCompare(b.filename));
    sorted.forEach((entry, index) => {
      entry.suffix = `_anexo${index + 1}`;
    });
    return true;
  }

  const canonicalCount = group.filter((entry) => parenMarker(entry.filename) === null).length;
  if (canonicalCount !== 1) return false;

  for (const entry of group) {
    const marker = parenMarker(entry.filename);
    entry.suffix = marker === null ? "" : `_${marker}`;
  }

  const resolvedNames = new Set(group.map((entry) => computeFinalName(config, entry)));
  if (resolvedNames.size !== group.length) {
    for (const entry of group) entry.suffix = "";
    return false;
  }
  return true;
}

export function markDuplicates(entries: FormatterEntry[], config: FormatterConfig): void {
  recomputeReasons(entries);
  for (const entry of entries) entry.suffix = "";

  const byName = new Map<string, FormatterEntry[]>();
  for (const entry of entries) {
    if (entry.reason !== null) continue;
    const name = computeFinalName(config, entry);
    if (name === null) continue;
    const group = byName.get(name) ?? [];
    group.push(entry);
    byName.set(name, group);
  }
  for (const group of byName.values()) {
    if (group.length <= 1) continue;
    if (!tryAutoResolveCollision(group, config)) {
      for (const entry of group) entry.reason = "duplicate";
    }
  }
}

function parsePositiveInt(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const parsed = Number(trimmed);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

export function applyCorrections(plan: FormatterPlan, corrections: Map<string, Correction>): FormatterPlan {
  const entries = plan.entries.map((entry) => {
    const correction = corrections.get(entry.path);
    if (!correction) return { ...entry };
    return {
      ...entry,
      detectedYear: parsePositiveInt(correction.year),
      detectedNumber: parsePositiveInt(correction.number),
    };
  });
  markDuplicates(entries, plan.config);
  return { ...plan, entries };
}
