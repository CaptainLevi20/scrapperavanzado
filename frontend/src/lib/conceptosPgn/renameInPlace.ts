import { isRenamable, type ConceptEntry, type ConceptPlan } from "./analyze";

export interface RenameOutcome {
  path: string;
  from: string;
  to: string;
  renamed: boolean;
  skipReason?: string;
}

export interface RenameSummary {
  outcomes: RenameOutcome[];
  logName: string;
  renamedCount: number;
  skippedCount: number;
}

interface LogRow {
  path: string;
  from: string;
  to: string;
  result: string;
}

const SKIP_EXISTS = "Ya existe un archivo con ese nombre en la carpeta";
const SKIP_CASE_ONLY = "Solo cambian mayúsculas; renómbralo a mano";
const SKIP_INCOMPLETE = "La copia no quedó completa; el original no se tocó";

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

export function logFileName(now: Date): string {
  const date = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
  return `registro_renombres_${date}-${pad(now.getHours())}${pad(now.getMinutes())}.csv`;
}

function csvField(value: string): string {
  return /[;"\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

// BOM so Excel opens the accents correctly; ";" is Excel's list separator in
// Spanish locales.
export function buildLogCsv(rows: LogRow[]): string {
  const lines = ["ruta;nombre_anterior;nombre_nuevo;resultado"];
  for (const row of rows) lines.push([row.path, row.from, row.to, row.result].map(csvField).join(";"));
  return `﻿${lines.join("\r\n")}\r\n`;
}

async function writeLog(root: FileSystemDirectoryHandle, name: string, rows: LogRow[]): Promise<void> {
  const handle = await root.getFileHandle(name, { create: true });
  const writable = await handle.createWritable();
  await writable.write(new TextEncoder().encode(buildLogCsv(rows)));
  await writable.close();
}

async function destinationTaken(entry: ConceptEntry, finalName: string): Promise<boolean> {
  const target = finalName.toLowerCase();
  for await (const handle of entry.dirHandle.values()) {
    if (handle.name !== entry.filename && handle.name.toLowerCase() === target) return true;
  }
  return false;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

// Same-folder copy, verified by size, and only then the original is removed.
// Any failure after the destination exists removes the partial copy, so the
// original is always left as it was.
async function copyVerifyDelete(entry: ConceptEntry, finalName: string): Promise<string | null> {
  const original = await entry.fileHandle.getFile();
  const buffer = await original.arrayBuffer();
  let created = false;
  try {
    const target = await entry.dirHandle.getFileHandle(finalName, { create: true });
    created = true;
    const writable = await target.createWritable();
    await writable.write(buffer);
    await writable.close();
    const written = await target.getFile();
    if (written.size !== original.size) {
      await entry.dirHandle.removeEntry(finalName).catch(() => {});
      return SKIP_INCOMPLETE;
    }
  } catch (error) {
    if (created) await entry.dirHandle.removeEntry(finalName).catch(() => {});
    return `No se pudo renombrar: ${errorMessage(error)}`;
  }
  await entry.dirHandle.removeEntry(entry.filename);
  return null;
}

async function renameOne(entry: ConceptEntry, finalName: string): Promise<string | null> {
  if (await destinationTaken(entry, finalName)) return SKIP_EXISTS;

  if (typeof entry.fileHandle.move === "function") {
    try {
      await entry.fileHandle.move(finalName);
      return null;
    } catch {
      // e.g. move() exists but the (network) drive refuses it: fall through.
    }
  }

  // On a case-insensitive disk (Windows) "creating" the target would open the
  // very same file, and deleting the original afterwards would destroy it.
  if (finalName.toLowerCase() === entry.filename.toLowerCase()) return SKIP_CASE_ONLY;

  try {
    return await copyVerifyDelete(entry, finalName);
  } catch (error) {
    return `No se pudo renombrar: ${errorMessage(error)}`;
  }
}

export async function renameConcepts(
  plan: ConceptPlan,
  options: { now?: Date; onProgress?: (done: number, total: number) => void } = {}
): Promise<RenameSummary> {
  const targets = plan.entries.filter(isRenamable);
  const logName = logFileName(options.now ?? new Date());
  const rows: LogRow[] = targets.map((entry) => ({
    path: entry.path,
    from: entry.filename,
    to: entry.finalName!,
    result: "pendiente",
  }));

  // Written before anything is touched, so there is a record even if the
  // browser closes halfway through.
  await writeLog(plan.rootHandle, logName, rows);
  options.onProgress?.(0, targets.length);

  const outcomes: RenameOutcome[] = [];
  for (const [index, entry] of targets.entries()) {
    const finalName = entry.finalName!;
    const skipReason = await renameOne(entry, finalName);
    outcomes.push({
      path: entry.path,
      from: entry.filename,
      to: finalName,
      renamed: skipReason === null,
      ...(skipReason === null ? {} : { skipReason }),
    });
    rows[index].result = skipReason === null ? "renombrado" : `saltado: ${skipReason}`;
    options.onProgress?.(index + 1, targets.length);
  }

  await writeLog(plan.rootHandle, logName, rows);

  const renamedCount = outcomes.filter((outcome) => outcome.renamed).length;
  return { outcomes, logName, renamedCount, skippedCount: outcomes.length - renamedCount };
}
