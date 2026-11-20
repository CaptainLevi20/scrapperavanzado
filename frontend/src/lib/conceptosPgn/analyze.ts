import { fileExtension } from "../formatter/rules";
import {
  buildConceptName,
  isDocument,
  isImage,
  parseConceptInput,
  parseConceptName,
  yearFromFolderName,
  type ConceptNumber,
} from "./rules";

export type ReviewReason = "no-number" | "no-year" | "year-mismatch" | "duplicate";

export interface ConceptEntry {
  path: string;
  folderPath: string;
  filename: string;
  dirHandle: FileSystemDirectoryHandle;
  fileHandle: FileSystemFileHandle;
  folderYear: number | null;
  year: number | null;
  number: ConceptNumber | null;
  finalName: string | null;
  reason: ReviewReason | null;
}

export interface CrossFolderRepeat {
  finalName: string;
  paths: string[];
}

export interface ConceptPlan {
  rootName: string;
  rootHandle: FileSystemDirectoryHandle;
  entries: ConceptEntry[];
  crossFolderRepeats: CrossFolderRepeat[];
  photoOnlyFolders: string[];
}

export interface ManualFix {
  year: string;
  number: string;
}

export class ConceptPgnError extends Error {}

export function isRenamable(entry: ConceptEntry): boolean {
  return entry.finalName !== null && entry.finalName !== entry.filename && entry.reason !== "duplicate";
}

export function isAlreadyFinal(entry: ConceptEntry): boolean {
  return entry.finalName === entry.filename;
}

// Base reason before clash detection: what a single file says about itself.
function baseReason(entry: Pick<ConceptEntry, "folderYear" | "year" | "number">): ReviewReason | null {
  if (entry.year === null) return "no-year";
  if (entry.number === null) return "no-number";
  if (entry.folderYear !== null && entry.year !== entry.folderYear) return "year-mismatch";
  return null;
}

function withNaming(entry: ConceptEntry, year: number | null, number: ConceptNumber | null): ConceptEntry {
  const finalName =
    year !== null && number !== null ? buildConceptName(number, year, fileExtension(entry.filename)) : null;
  return { ...entry, year, number, finalName, reason: baseReason({ folderYear: entry.folderYear, year, number }) };
}

// Two files of the SAME folder ending with the same name (compared like
// Windows does, ignoring case) would overwrite each other: both are blocked.
// The same name in DIFFERENT folders doesn't clash on disk nor in Azure (the
// folder path is part of the blob name), so it's only reported.
function markClashes(entries: ConceptEntry[]): CrossFolderRepeat[] {
  const byFolderAndName = new Map<string, ConceptEntry[]>();
  const byName = new Map<string, ConceptEntry[]>();
  for (const entry of entries) {
    if (entry.finalName === null) continue;
    const key = entry.finalName.toLowerCase();
    const folderKey = `${entry.folderPath}\u0000${key}`;
    byFolderAndName.set(folderKey, [...(byFolderAndName.get(folderKey) ?? []), entry]);
    byName.set(key, [...(byName.get(key) ?? []), entry]);
  }
  for (const group of byFolderAndName.values()) {
    if (group.length > 1) for (const entry of group) entry.reason = "duplicate";
  }

  const repeats: CrossFolderRepeat[] = [];
  for (const group of byName.values()) {
    const folders = new Set(group.map((entry) => entry.folderPath));
    if (folders.size > 1) repeats.push({ finalName: group[0].finalName!, paths: group.map((entry) => entry.path) });
  }
  return repeats;
}

interface WalkResult {
  entries: ConceptEntry[];
  photoOnlyFolders: string[];
}

async function walk(dir: FileSystemDirectoryHandle, folderPath: string, out: WalkResult): Promise<void> {
  let documents = 0;
  let images = 0;
  const subdirs: FileSystemDirectoryHandle[] = [];
  for await (const handle of dir.values()) {
    if (handle.kind === "directory") {
      subdirs.push(handle as FileSystemDirectoryHandle);
      continue;
    }
    if (isImage(handle.name)) images += 1;
    if (!isDocument(handle.name)) continue;
    documents += 1;

    const topFolder = folderPath.split("/")[0];
    const folderYear = folderPath === "" ? null : yearFromFolderName(topFolder);
    const { number, nameYear } = parseConceptName(handle.name, folderYear);
    const entry: ConceptEntry = {
      path: folderPath ? `${folderPath}/${handle.name}` : handle.name,
      folderPath,
      filename: handle.name,
      dirHandle: dir,
      fileHandle: handle as FileSystemFileHandle,
      folderYear,
      year: null,
      number: null,
      finalName: null,
      reason: null,
    };
    // Without a year folder there's nothing trustworthy to name it with.
    out.entries.push(folderYear === null ? withNaming(entry, null, null) : withNaming(entry, nameYear ?? folderYear, number));
  }
  if (images > 0 && documents === 0 && folderPath !== "") out.photoOnlyFolders.push(folderPath);

  for (const subdir of subdirs) {
    await walk(subdir, folderPath ? `${folderPath}/${subdir.name}` : subdir.name, out);
  }
}

export async function analyzeConceptBatch(root: FileSystemDirectoryHandle): Promise<ConceptPlan> {
  const result: WalkResult = { entries: [], photoOnlyFolders: [] };
  await walk(root, "", result);
  if (result.entries.length === 0) {
    throw new ConceptPgnError("La carpeta no contiene ningún documento.");
  }
  const entries = result.entries.sort((a, b) => a.path.localeCompare(b.path));
  const crossFolderRepeats = markClashes(entries);
  return {
    rootName: root.name,
    rootHandle: root,
    entries,
    crossFolderRepeats,
    photoOnlyFolders: result.photoOnlyFolders.sort((a, b) => a.localeCompare(b)),
  };
}

function parseYearInput(text: string): number | null {
  return yearFromFolderName(text.trim());
}

// Re-derives every entry from the ORIGINAL analysis plus the manual fixes, so
// undoing a fix (or fixing a clash) always recomputes from a clean state.
// Returns a new plan; the given one is never mutated.
export function applyManualFixes(plan: ConceptPlan, fixes: Map<string, ManualFix>): ConceptPlan {
  const entries = plan.entries.map((entry) => {
    const fix = fixes.get(entry.path);
    const base = { ...entry, reason: entry.reason === "duplicate" ? baseReason(entry) : entry.reason };
    if (!fix) return base;
    const year = parseYearInput(fix.year);
    const number = parseConceptInput(fix.number);
    if (year === null || number === null) {
      // An incomplete fix never invents a name: the file keeps its own.
      return { ...base, finalName: null, reason: base.reason ?? "no-number" };
    }
    return withNaming(entry, year, number);
  });
  const crossFolderRepeats = markClashes(entries);
  return { ...plan, entries, crossFolderRepeats };
}
