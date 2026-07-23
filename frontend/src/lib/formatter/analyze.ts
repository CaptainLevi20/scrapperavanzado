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
  let hasYearFolders = false;

  for await (const handle of root.values()) {
    if (handle.kind === "file") {
      rawEntries.push({ path: handle.name, yearFolder: "", filename: handle.name, fileHandle: handle });
      continue;
    }
    hasYearFolders = true;
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
  // (in addition to rootFolderName) covers that real-world naming pattern. A
  // fully flat batch (no year subfolders at all) has nowhere else to carry
  // those keywords, so filenames themselves join the search instead.
  const yearFolderNames = Array.from(
    new Set(rawEntries.filter((entry) => entry.yearFolder !== "").map((entry) => entry.yearFolder))
  );
  const detectionText = hasYearFolders
    ? [rootFolderName, ...yearFolderNames].join(" ")
    : [rootFolderName, ...rawEntries.map((entry) => entry.filename)].join(" ");

  const config = detectConfig(detectionText);
  if (!config) {
    throw new FormatterError(`No se reconoce el tipo de documento o la ciudad en «${rootFolderName}».`);
  }

  const entries: FormatterEntry[] = rawEntries.map(({ path, yearFolder, filename, fileHandle }) => {
    if (yearFolder === "") {
      // A file directly in the root: if the batch has no year subfolders at
      // all, this is the normal shape for this batch and the year has to come
      // from the filename itself. If the batch DOES use year subfolders
      // elsewhere, a file sitting outside all of them is more likely a
      // mistake, so it's left for manual review instead of guessing.
      if (!hasYearFolders) {
        const detectedYear = extractYear(filename);
        const detectedNumber = detectedYear === null ? null : extractNumber(filename, detectedYear);
        return {
          path,
          yearFolder: detectedYear === null ? "" : String(detectedYear),
          filename,
          fileHandle,
          detectedYear,
          detectedNumber,
          reason: null,
          suffix: "",
        };
      }
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

function tryAnexoResolution(group: FormatterEntry[]): boolean {
  const hasAnexo = group.some((entry) => normalizeForMatch(entry.filename).includes("anexo"));
  if (!hasAnexo) return false;
  const sorted = [...group].sort((a, b) => a.filename.localeCompare(b.filename));
  sorted.forEach((entry, index) => {
    entry.suffix = `_anexo${index + 1}`;
  });
  return true;
}

// A file whose name flags it as a special designation about another one in the
// same collision (e.g. a "nulidad" ruling that cites the acuerdo it concerns)
// gets that keyword appended as a suffix, while the plain file it refers to
// keeps its name as-is. Only resolves the group if the keyword actually
// distinguishes every member — if two colliding files both carry it (or
// neither does), there's nothing to disambiguate them and it's left for review.
function tryKeywordSuffixResolution(
  group: FormatterEntry[],
  config: FormatterConfig,
  keyword: string,
  suffix: string
): boolean {
  const hasKeyword = group.some((entry) => normalizeForMatch(entry.filename).includes(keyword));
  if (!hasKeyword) return false;

  for (const entry of group) {
    entry.suffix = normalizeForMatch(entry.filename).includes(keyword) ? suffix : "";
  }

  const resolvedNames = new Set(group.map((entry) => computeFinalName(config, entry)));
  if (resolvedNames.size !== group.length) {
    for (const entry of group) entry.suffix = "";
    return false;
  }
  return true;
}

function tryParenMarkerResolution(group: FormatterEntry[], config: FormatterConfig): boolean {
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

// Some collisions have an unambiguous resolution baked into the original
// filenames themselves, so they don't need a human to look at them. Tried in
// order; the first strategy that fully disambiguates the group wins. Returns
// true if the whole group was resolved (each entry's `suffix` is set and all
// entries now have distinct final names); false if it still needs manual
// review, in which case no entry's `suffix` is touched.
function tryAutoResolveCollision(group: FormatterEntry[], config: FormatterConfig): boolean {
  if (tryAnexoResolution(group)) return true;
  if (tryKeywordSuffixResolution(group, config, "nulidad", "_nulidad")) return true;
  if (tryParenMarkerResolution(group, config)) return true;
  return false;
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
