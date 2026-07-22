import JSZip from "jszip";
import type { FormatterPlan } from "./analyze";

export interface BuildResult {
  blob: Blob;
  skippedCount: number;
}

export async function buildFormattedZip(
  zip: JSZip,
  plan: FormatterPlan,
  resolvedNames: Map<string, string>
): Promise<BuildResult> {
  const output = new JSZip();
  let skippedCount = 0;

  for (const entry of plan.entries) {
    const finalName = resolvedNames.get(entry.path);
    if (!finalName) continue;

    const source = zip.file(entry.path);
    if (!source) {
      skippedCount += 1;
      continue;
    }

    try {
      const content = await source.async("blob");
      output.file(`${entry.yearFolder}/${finalName}`, content);
    } catch {
      skippedCount += 1;
    }
  }

  const blob = await output.generateAsync({ type: "blob" });
  return { blob, skippedCount };
}
