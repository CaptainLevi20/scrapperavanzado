import JSZip from "jszip";
import { buildFileName, detectConfig, extractNumber, extractYear, fileExtension, type FormatterConfig } from "./rules";

export type FormatterReason = "no-year" | "no-number" | "duplicate";

export interface FormatterEntry {
  path: string;
  yearFolder: string;
  filename: string;
  detectedYear: number | null;
  detectedNumber: number | null;
  reason: FormatterReason | null;
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

function stripZipExtension(name: string): string {
  return name.replace(/\.zip$/i, "");
}

function commonRootSegment(paths: string[]): string | null {
  const [first, ...rest] = paths.map((path) => path.split("/")[0]);
  return first !== undefined && rest.every((segment) => segment === first) ? first : null;
}

export async function analyzeZip(file: File): Promise<FormatterPlan> {
  let zip: JSZip;
  try {
    zip = await JSZip.loadAsync(file);
  } catch {
    throw new FormatterError("El archivo seleccionado no es un ZIP válido.");
  }

  const fileEntries = Object.values(zip.files).filter((entry) => !entry.dir);
  if (fileEntries.length === 0) {
    throw new FormatterError("El ZIP no contiene ningún archivo.");
  }

  const sharedRoot = commonRootSegment(fileEntries.map((entry) => entry.name));
  const rootFolderName = sharedRoot ?? stripZipExtension(file.name);

  const config = detectConfig(rootFolderName);
  if (!config) {
    throw new FormatterError(`No se reconoce el tipo de documento o la ciudad en «${rootFolderName}».`);
  }

  const entries: FormatterEntry[] = fileEntries.map((entry) => {
    const segments = sharedRoot ? entry.name.split("/").slice(1) : entry.name.split("/");
    const filename = segments[segments.length - 1];

    if (segments.length < 2) {
      return { path: entry.name, yearFolder: "", filename, detectedYear: null, detectedNumber: null, reason: null };
    }

    const yearFolder = segments[0];
    const detectedYear = extractYear(yearFolder);
    const detectedNumber = detectedYear === null ? null : extractNumber(filename, detectedYear);
    return { path: entry.name, yearFolder, filename, detectedYear, detectedNumber, reason: null };
  });

  markDuplicates(entries, config);

  return { config, rootFolderName, entries };
}

export function computeFinalName(config: FormatterConfig, entry: FormatterEntry): string | null {
  if (entry.detectedYear === null || entry.detectedNumber === null) return null;
  return buildFileName(config, entry.detectedNumber, entry.detectedYear, fileExtension(entry.filename));
}

function recomputeReasons(entries: FormatterEntry[]): void {
  for (const entry of entries) {
    if (entry.detectedYear === null) entry.reason = "no-year";
    else if (entry.detectedNumber === null) entry.reason = "no-number";
    else entry.reason = null;
  }
}

export function markDuplicates(entries: FormatterEntry[], config: FormatterConfig): void {
  recomputeReasons(entries);
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
    if (group.length > 1) {
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
