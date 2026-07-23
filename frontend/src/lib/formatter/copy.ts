import type { FormatterPlan } from "./analyze";

export interface CopyResult {
  copiedCount: number;
  skippedCount: number;
}

export async function copyFormattedFiles(
  outputRoot: FileSystemDirectoryHandle,
  plan: FormatterPlan,
  resolvedNames: Map<string, string>,
  onProgress?: (done: number, total: number) => void
): Promise<CopyResult> {
  const targets = plan.entries.filter((entry) => resolvedNames.has(entry.path));
  let copiedCount = 0;
  let skippedCount = 0;
  let done = 0;

  for (const entry of targets) {
    const finalName = resolvedNames.get(entry.path)!;
    try {
      // Read the source fully before touching the destination — getFileHandle(create: true)
      // creates the destination file immediately, even before anything is written to it, so
      // reading first avoids leaving an empty stray file behind when the source read fails.
      const buffer = await (await entry.fileHandle.getFile()).arrayBuffer();
      const dirHandle = entry.yearFolder
        ? await outputRoot.getDirectoryHandle(entry.yearFolder, { create: true })
        : outputRoot;
      const fileHandle = await dirHandle.getFileHandle(finalName, { create: true });
      const writable = await fileHandle.createWritable();
      await writable.write(buffer);
      await writable.close();
      copiedCount += 1;
    } catch {
      skippedCount += 1;
    }
    done += 1;
    onProgress?.(done, targets.length);
  }

  return { copiedCount, skippedCount };
}
