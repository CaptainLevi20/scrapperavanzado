# Formateador Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Formateador" page where a user uploads a ZIP of inconsistently-named legal documents (grouped into per-year subfolders) and downloads a new ZIP with every file renamed to `{TIPO}_{CIUDAD}_{NUMERO}_{AÑO}.{ext}`, with a review step for the few files whose year/number can't be determined automatically.

**Architecture:** Four new frontend-only modules under `frontend/src/lib/formatter/` (pure rule functions, ZIP analysis, ZIP generation) consumed by one new page component. Everything runs client-side with `JSZip` — no backend endpoint, no persistence, no network calls.

**Tech Stack:** React 19 + TypeScript, `jszip` (new dependency), Vitest + Testing Library (existing conventions).

## Global Constraints

- No backend/API changes — this feature is 100% client-side (spec: "Contexto y objetivo").
- Nothing is persisted (uploaded ZIP, generated ZIP, or history) — spec explicitly out of scope.
- Type code and city code are detected automatically from keywords in the ZIP's root folder name (`acuerdo` → `A`, `cali` → `CONCALI`); no configuration form (spec: "Motor de reglas").
- Output ZIP preserves the `AÑO/archivo.ext` folder structure (spec: "Componente de página" / "Generación del ZIP final").
- New dependency: `jszip@^3.10.1` in `frontend/package.json` — the only new dependency.

---

### Task 1: Rules module — pure name-extraction functions

**Files:**
- Create: `frontend/src/lib/formatter/rules.ts`
- Test: `frontend/src/lib/formatter/rules.test.ts`

**Interfaces:**
- Consumes: nothing (first task).
- Produces (used by Task 2):
  - `export interface FormatterConfig { typeCode: string; cityCode: string; }`
  - `export function detectConfig(rootFolderName: string): FormatterConfig | null`
  - `export function extractYear(folderName: string): number | null`
  - `export function extractNumber(filename: string, year: number | null): number | null`
  - `export function padNumber(value: number): string`
  - `export function fileExtension(filename: string): string`
  - `export function buildFileName(config: FormatterConfig, number: number, year: number, ext: string): string`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/formatter/rules.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { buildFileName, detectConfig, extractNumber, extractYear, fileExtension, padNumber } from "./rules";

describe("detectConfig", () => {
  it("detects type and city from keywords regardless of case and accents", () => {
    expect(detectConfig("Acuerdos Cali")).toEqual({ typeCode: "A", cityCode: "CONCALI" });
    expect(detectConfig("ACUERDOS DE CALÍ")).toEqual({ typeCode: "A", cityCode: "CONCALI" });
  });

  it("returns null when the type keyword is missing", () => {
    expect(detectConfig("Resoluciones Cali")).toBeNull();
  });

  it("returns null when the city keyword is missing", () => {
    expect(detectConfig("Acuerdos Bogota")).toBeNull();
  });
});

describe("extractYear", () => {
  it("extracts a plausible year from the folder name", () => {
    expect(extractYear("ACUERDOS 1962")).toBe(1962);
    expect(extractYear("ACUERDOS 2025")).toBe(2025);
  });

  it("returns null when no plausible year is present", () => {
    expect(extractYear("ACUERDOS VARIOS")).toBeNull();
  });
});

describe("extractNumber", () => {
  it("returns the first number that is not the year", () => {
    expect(extractNumber("Acuerdo 0005 de 1962.pdf", 1962)).toBe(5);
    expect(extractNumber("1962 - acuerdo 12.pdf", 1962)).toBe(12);
  });

  it("returns null when the only number found is the year", () => {
    expect(extractNumber("1962.pdf", 1962)).toBeNull();
  });

  it("returns null when there is no number at all", () => {
    expect(extractNumber("acuerdo sin numero.pdf", 1962)).toBeNull();
  });

  it("returns the first number when year is null", () => {
    expect(extractNumber("acuerdo 7.pdf", null)).toBe(7);
  });
});

describe("padNumber", () => {
  it("pads to at least 4 digits", () => {
    expect(padNumber(5)).toBe("0005");
    expect(padNumber(42)).toBe("0042");
  });

  it("leaves numbers with more than 4 digits untouched", () => {
    expect(padNumber(12345)).toBe("12345");
  });
});

describe("fileExtension", () => {
  it("returns the extension including the dot", () => {
    expect(fileExtension("archivo.pdf")).toBe(".pdf");
  });

  it("returns an empty string when there is no extension", () => {
    expect(fileExtension("archivo")).toBe("");
  });
});

describe("buildFileName", () => {
  it("builds the final name from config, number, year and extension", () => {
    expect(buildFileName({ typeCode: "A", cityCode: "CONCALI" }, 5, 1962, ".pdf")).toBe("A_CONCALI_0005_1962.pdf");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/formatter/rules.test.ts`
Expected: FAIL — `Failed to resolve import "./rules"` (the module doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/lib/formatter/rules.ts`:

```ts
export interface FormatterConfig {
  typeCode: string;
  cityCode: string;
}

const TYPE_KEYWORDS: Record<string, string> = {
  acuerdo: "A",
};

const CITY_KEYWORDS: Record<string, string> = {
  cali: "CONCALI",
};

const YEAR_PATTERN = /\b(1[89]\d{2}|20\d{2})\b/;

function normalize(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

export function detectConfig(rootFolderName: string): FormatterConfig | null {
  const normalized = normalize(rootFolderName);
  const typeEntry = Object.entries(TYPE_KEYWORDS).find(([keyword]) => normalized.includes(keyword));
  const cityEntry = Object.entries(CITY_KEYWORDS).find(([keyword]) => normalized.includes(keyword));
  if (!typeEntry || !cityEntry) return null;
  return { typeCode: typeEntry[1], cityCode: cityEntry[1] };
}

export function extractYear(folderName: string): number | null {
  const match = YEAR_PATTERN.exec(folderName);
  return match ? Number(match[1]) : null;
}

export function extractNumber(filename: string, year: number | null): number | null {
  const matches = filename.match(/\d+/g);
  if (!matches) return null;
  for (const raw of matches) {
    const value = Number(raw);
    if (year === null || value !== year) return value;
  }
  return null;
}

export function padNumber(value: number): string {
  return String(value).padStart(4, "0");
}

export function fileExtension(filename: string): string {
  const match = /\.[^./\\]+$/.exec(filename);
  return match ? match[0] : "";
}

export function buildFileName(config: FormatterConfig, number: number, year: number, ext: string): string {
  return `${config.typeCode}_${config.cityCode}_${padNumber(number)}_${year}${ext}`;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/formatter/rules.test.ts`
Expected: PASS — all `describe` blocks green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/formatter/rules.ts frontend/src/lib/formatter/rules.test.ts
git commit -m "feat: add Formateador rule-extraction functions"
```

---

### Task 2: Analyze module — ZIP parsing and plan building

**Files:**
- Modify: `frontend/package.json` (add `jszip` dependency)
- Create: `frontend/src/lib/formatter/analyze.ts`
- Test: `frontend/src/lib/formatter/analyze.test.ts`

**Interfaces:**
- Consumes from Task 1: `detectConfig`, `extractYear`, `extractNumber`, `fileExtension`, `buildFileName`, `FormatterConfig` from `./rules`.
- Produces (used by Tasks 3 and 4):
  - `export type FormatterReason = "no-year" | "no-number" | "duplicate"`
  - `export interface FormatterEntry { path: string; yearFolder: string; filename: string; detectedYear: number | null; detectedNumber: number | null; reason: FormatterReason | null; }`
  - `export interface FormatterPlan { config: FormatterConfig; rootFolderName: string; entries: FormatterEntry[]; }`
  - `export interface Correction { year: string; number: string; }`
  - `export class FormatterError extends Error {}`
  - `export function analyzeZip(file: File): Promise<FormatterPlan>`
  - `export function computeFinalName(config: FormatterConfig, entry: FormatterEntry): string | null`
  - `export function markDuplicates(entries: FormatterEntry[], config: FormatterConfig): void`
  - `export function applyCorrections(plan: FormatterPlan, corrections: Map<string, Correction>): FormatterPlan`

- [ ] **Step 1: Add the `jszip` dependency**

Run: `cd frontend && npm install jszip@3.10.1`
Expected: `frontend/package.json` gains `"jszip": "^3.10.1"` under `dependencies`, and `frontend/package-lock.json` is updated.

- [ ] **Step 2: Write the failing test**

Create `frontend/src/lib/formatter/analyze.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import JSZip from "jszip";
import { analyzeZip, applyCorrections, computeFinalName, FormatterError } from "./analyze";

async function toFile(zip: JSZip, name: string): Promise<File> {
  const blob = await zip.generateAsync({ type: "blob" });
  return new File([blob], name, { type: "application/zip" });
}

describe("analyzeZip", () => {
  it("detects config, year and number for a zip wrapped in a root folder", async () => {
    const zip = new JSZip();
    zip.file("Acuerdos Cali/ACUERDOS 1962/Acuerdo 0005 de 1962.pdf", "x");
    const file = await toFile(zip, "lote.zip");

    const plan = await analyzeZip(file);

    expect(plan.config).toEqual({ typeCode: "A", cityCode: "CONCALI" });
    expect(plan.rootFolderName).toBe("Acuerdos Cali");
    expect(plan.entries).toHaveLength(1);
    expect(plan.entries[0]).toMatchObject({
      yearFolder: "ACUERDOS 1962",
      detectedYear: 1962,
      detectedNumber: 5,
      reason: null,
    });
  });

  it("falls back to the uploaded file's name when there is no shared root folder", async () => {
    const zip = new JSZip();
    zip.file("ACUERDOS 1962/Acuerdo 0005 de 1962.pdf", "x");
    zip.file("ACUERDOS 1963/Acuerdo 0001 de 1963.pdf", "x");
    const file = await toFile(zip, "Acuerdos Cali.zip");

    const plan = await analyzeZip(file);

    expect(plan.rootFolderName).toBe("Acuerdos Cali");
    expect(plan.entries.find((entry) => entry.yearFolder === "ACUERDOS 1962")).toBeTruthy();
    expect(plan.entries.find((entry) => entry.yearFolder === "ACUERDOS 1963")).toBeTruthy();
  });

  it("throws when the root folder name doesn't match a known type/city", async () => {
    const zip = new JSZip();
    zip.file("Resoluciones Bogota/2020/algo.pdf", "x");
    const file = await toFile(zip, "lote.zip");

    await expect(analyzeZip(file)).rejects.toThrow(FormatterError);
  });

  it("marks files without a detectable year as no-year", async () => {
    const zip = new JSZip();
    zip.file("Acuerdos Cali/VARIOS/Acuerdo 0005.pdf", "x");
    const file = await toFile(zip, "lote.zip");

    const plan = await analyzeZip(file);

    expect(plan.entries[0].reason).toBe("no-year");
    expect(plan.entries[0].detectedYear).toBeNull();
  });

  it("marks files without a detectable number as no-number", async () => {
    const zip = new JSZip();
    zip.file("Acuerdos Cali/ACUERDOS 1962/sin numero.pdf", "x");
    const file = await toFile(zip, "lote.zip");

    const plan = await analyzeZip(file);

    expect(plan.entries[0].reason).toBe("no-number");
  });

  it("marks colliding names as duplicate", async () => {
    const zip = new JSZip();
    zip.file("Acuerdos Cali/ACUERDOS 1962/Acuerdo 0005 primero.pdf", "x");
    zip.file("Acuerdos Cali/ACUERDOS 1962/Acuerdo 0005 segundo.pdf", "x");
    const file = await toFile(zip, "lote.zip");

    const plan = await analyzeZip(file);

    expect(plan.entries.every((entry) => entry.reason === "duplicate")).toBe(true);
  });

  it("throws for a zip with no files", async () => {
    const zip = new JSZip();
    zip.folder("Acuerdos Cali/ACUERDOS 1962");
    const file = await toFile(zip, "lote.zip");

    await expect(analyzeZip(file)).rejects.toThrow(FormatterError);
  });
});

describe("applyCorrections", () => {
  it("resolves an exception and clears its reason once a valid year and number are supplied", async () => {
    const zip = new JSZip();
    zip.file("Acuerdos Cali/ACUERDOS 1962/sin numero.pdf", "x");
    const file = await toFile(zip, "lote.zip");
    const plan = await analyzeZip(file);

    const corrections = new Map([[plan.entries[0].path, { year: "1962", number: "9" }]]);
    const resolved = applyCorrections(plan, corrections);

    expect(resolved.entries[0].reason).toBeNull();
    expect(computeFinalName(resolved.config, resolved.entries[0])).toBe("A_CONCALI_0009_1962.pdf");
  });

  it("re-flags a collision introduced by a correction, and clears one resolved by a later correction", async () => {
    const zip = new JSZip();
    zip.file("Acuerdos Cali/ACUERDOS 1962/Acuerdo 0005 uno.pdf", "x");
    zip.file("Acuerdos Cali/ACUERDOS 1962/sin numero.pdf", "x");
    const file = await toFile(zip, "lote.zip");
    const plan = await analyzeZip(file);
    const noNumberEntry = plan.entries.find((entry) => entry.reason === "no-number")!;

    const collided = applyCorrections(plan, new Map([[noNumberEntry.path, { year: "1962", number: "5" }]]));
    expect(collided.entries.every((entry) => entry.reason === "duplicate")).toBe(true);

    const resolved = applyCorrections(plan, new Map([[noNumberEntry.path, { year: "1962", number: "6" }]]));
    expect(resolved.entries.every((entry) => entry.reason === null)).toBe(true);
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/formatter/analyze.test.ts`
Expected: FAIL — `Failed to resolve import "./analyze"` (the module doesn't exist yet).

- [ ] **Step 4: Write the implementation**

Create `frontend/src/lib/formatter/analyze.ts`:

```ts
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/formatter/analyze.test.ts`
Expected: PASS — all `describe` blocks green.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib/formatter/analyze.ts frontend/src/lib/formatter/analyze.test.ts
git commit -m "feat: add Formateador zip analysis and correction logic"
```

---

### Task 3: Build module — generate the renamed ZIP

**Files:**
- Create: `frontend/src/lib/formatter/build.ts`
- Test: `frontend/src/lib/formatter/build.test.ts`

**Interfaces:**
- Consumes from Task 2: `FormatterPlan`, `analyzeZip`, `computeFinalName` from `./analyze`.
- Produces (used by Task 4):
  - `export interface BuildResult { blob: Blob; skippedCount: number; }`
  - `export function buildFormattedZip(zip: JSZip, plan: FormatterPlan, resolvedNames: Map<string, string>): Promise<BuildResult>`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/formatter/build.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import JSZip from "jszip";
import { analyzeZip, computeFinalName } from "./analyze";
import { buildFormattedZip } from "./build";

describe("buildFormattedZip", () => {
  it("writes each entry under its year folder using the resolved name", async () => {
    const source = new JSZip();
    source.file("Acuerdos Cali/ACUERDOS 1962/Acuerdo 0005 de 1962.pdf", "contenido-a");
    source.file("Acuerdos Cali/ACUERDOS 1963/Acuerdo 0001 de 1963.pdf", "contenido-b");
    const blob = await source.generateAsync({ type: "blob" });
    const file = new File([blob], "lote.zip", { type: "application/zip" });

    const plan = await analyzeZip(file);
    const zip = await JSZip.loadAsync(file);
    const resolvedNames = new Map(plan.entries.map((entry) => [entry.path, computeFinalName(plan.config, entry)!]));

    const { blob: outputBlob, skippedCount } = await buildFormattedZip(zip, plan, resolvedNames);

    expect(skippedCount).toBe(0);
    const output = await JSZip.loadAsync(outputBlob);
    expect(Object.keys(output.files).sort()).toEqual([
      "ACUERDOS 1962/A_CONCALI_0005_1962.pdf",
      "ACUERDOS 1963/A_CONCALI_0001_1963.pdf",
    ]);
    expect(await output.file("ACUERDOS 1962/A_CONCALI_0005_1962.pdf")!.async("string")).toBe("contenido-a");
  });

  it("counts an entry as skipped when it's missing from the source zip", async () => {
    const source = new JSZip();
    source.file("Acuerdos Cali/ACUERDOS 1962/Acuerdo 0005 de 1962.pdf", "contenido-a");
    const blob = await source.generateAsync({ type: "blob" });
    const file = new File([blob], "lote.zip", { type: "application/zip" });

    const plan = await analyzeZip(file);
    const zip = await JSZip.loadAsync(file);
    const resolvedNames = new Map([[plan.entries[0].path, computeFinalName(plan.config, plan.entries[0])!]]);
    zip.remove(plan.entries[0].path);

    const { skippedCount } = await buildFormattedZip(zip, plan, resolvedNames);

    expect(skippedCount).toBe(1);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/formatter/build.test.ts`
Expected: FAIL — `Failed to resolve import "./build"` (the module doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/lib/formatter/build.ts`:

```ts
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/formatter/build.test.ts`
Expected: PASS — both tests green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/formatter/build.ts frontend/src/lib/formatter/build.test.ts
git commit -m "feat: add Formateador zip generation"
```

---

### Task 4: FormatterPage — upload, review, and download flow

**Files:**
- Create: `frontend/src/pages/FormatterPage.tsx`
- Test: `frontend/src/pages/FormatterPage.test.tsx`
- Modify: `frontend/src/App.tsx` (add route)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (add nav link)

**Interfaces:**
- Consumes from Task 2: `analyzeZip`, `applyCorrections`, `computeFinalName`, `FormatterError`, `Correction`, `FormatterPlan` from `../lib/formatter/analyze`.
- Consumes from Task 3: `buildFormattedZip` from `../lib/formatter/build`.
- Consumes existing code: `downloadBlob` from `../api/documents`; `ErrorBanner` from `../components/ErrorBanner`; `Button` from `../components/ui/button`; `Input` from `../components/ui/input`; `TABLE`, `TABLE_SCROLL`, `TABLE_SHELL`, `TBODY_ROW`, `TD`, `TH`, `THEAD_ROW` from `../lib/tableStyles`.
- Produces: `export function FormatterPage()` rendered at route `/formateador`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/FormatterPage.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import JSZip from "jszip";
import { FormatterPage } from "./FormatterPage";

async function buildZipFile(entries: Record<string, string>, name = "Acuerdos Cali.zip"): Promise<File> {
  const zip = new JSZip();
  for (const [path, content] of Object.entries(entries)) {
    zip.file(path, content);
  }
  const blob = await zip.generateAsync({ type: "blob" });
  return new File([blob], name, { type: "application/zip" });
}

describe("FormatterPage", () => {
  it("shows a ready summary and an enabled download button when every file resolves cleanly", async () => {
    const file = await buildZipFile({
      "Acuerdos Cali/ACUERDOS 1962/Acuerdo 0005 de 1962.pdf": "contenido",
      "Acuerdos Cali/ACUERDOS 1962/Acuerdo 0006 de 1962.pdf": "contenido",
    });

    const user = userEvent.setup();
    render(<FormatterPage />);
    const input = screen.getByLabelText(/seleccionar archivo zip/i);
    await user.upload(input, file);

    expect(await screen.findByText(/2 archivos listos/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /descargar zip/i })).toBeEnabled();
  });

  it("keeps the download button disabled until an exception row is filled in, then enables it", async () => {
    const file = await buildZipFile({
      "Acuerdos Cali/ACUERDOS 1962/sin numero.pdf": "contenido",
    });

    const user = userEvent.setup();
    render(<FormatterPage />);
    const input = screen.getByLabelText(/seleccionar archivo zip/i);
    await user.upload(input, file);

    expect(await screen.findByText(/número no detectado/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /descargar zip/i })).toBeDisabled();

    const numberField = screen.getByLabelText(/número para/i);
    await user.type(numberField, "7");

    await waitFor(() => expect(screen.getByRole("button", { name: /descargar zip/i })).toBeEnabled());
  });

  it("shows an error banner for a zip whose root folder isn't recognized", async () => {
    const file = await buildZipFile(
      { "Resoluciones Bogota/2020/algo.pdf": "contenido" },
      "Resoluciones Bogota.zip"
    );

    const user = userEvent.setup();
    render(<FormatterPage />);
    const input = screen.getByLabelText(/seleccionar archivo zip/i);
    await user.upload(input, file);

    expect(await screen.findByText(/no se reconoce el tipo de documento o la ciudad/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/FormatterPage.test.tsx`
Expected: FAIL — `Failed to resolve import "./FormatterPage"` (the component doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/pages/FormatterPage.tsx`:

```tsx
import { useState } from "react";
import JSZip from "jszip";
import { Wand2 } from "lucide-react";
import { downloadBlob } from "../api/documents";
import { ErrorBanner } from "../components/ErrorBanner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  analyzeZip,
  applyCorrections,
  computeFinalName,
  FormatterError,
  type Correction,
  type FormatterPlan,
} from "../lib/formatter/analyze";
import { buildFormattedZip } from "../lib/formatter/build";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TH, THEAD_ROW } from "../lib/tableStyles";

type FormatterState =
  | { step: "idle"; notice?: string }
  | { step: "error"; message: string }
  | { step: "loaded"; plan: FormatterPlan; zip: JSZip; corrections: Map<string, Correction> }
  | { step: "building"; plan: FormatterPlan; zip: JSZip; corrections: Map<string, Correction> };

const REASON_LABEL: Record<string, string> = {
  "no-year": "Año no detectado",
  "no-number": "Número no detectado",
  duplicate: "Número duplicado",
};

export function FormatterPage() {
  const [state, setState] = useState<FormatterState>({ step: "idle" });

  async function handleFileSelected(file: File) {
    try {
      const [plan, zip] = await Promise.all([analyzeZip(file), JSZip.loadAsync(file)]);
      setState({ step: "loaded", plan, zip, corrections: new Map() });
    } catch (error) {
      const message = error instanceof FormatterError ? error.message : "No se pudo leer el archivo ZIP.";
      setState({ step: "error", message });
    }
  }

  function handleCorrectionChange(path: string, field: keyof Correction, value: string) {
    if (state.step !== "loaded") return;
    const entry = state.plan.entries.find((candidate) => candidate.path === path);
    if (!entry) return;
    const corrections = new Map(state.corrections);
    const current =
      corrections.get(path) ?? { year: String(entry.detectedYear ?? ""), number: String(entry.detectedNumber ?? "") };
    corrections.set(path, { ...current, [field]: value });
    setState({ ...state, corrections });
  }

  async function handleDownload() {
    if (state.step !== "loaded") return;
    const resolvedPlan = applyCorrections(state.plan, state.corrections);
    const resolvedNames = new Map<string, string>();
    for (const entry of resolvedPlan.entries) {
      const name = computeFinalName(resolvedPlan.config, entry);
      if (name) resolvedNames.set(entry.path, name);
    }

    setState({ step: "building", plan: state.plan, zip: state.zip, corrections: state.corrections });
    const { blob, skippedCount } = await buildFormattedZip(state.zip, resolvedPlan, resolvedNames);
    downloadBlob(blob, `Formateador_${resolvedPlan.rootFolderName}.zip`);
    setState({
      step: "idle",
      notice:
        skippedCount > 0
          ? `${skippedCount} archivo${skippedCount === 1 ? "" : "s"} se omitieron por error de lectura.`
          : undefined,
    });
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
          <Wand2 className="size-3.5" aria-hidden="true" />
          Renombrado de lotes
        </p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">Formateador</h1>
      </div>

      {state.step === "idle" && (
        <div className={TABLE_SHELL}>
          <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
            {state.notice && <p className="text-xs text-muted-foreground">{state.notice}</p>}
            <p className="text-sm text-muted-foreground">
              Sube un ZIP con la carpeta de acuerdos (subcarpetas por año) para renombrar los archivos.
            </p>
            <Input
              type="file"
              accept=".zip"
              aria-label="Seleccionar archivo ZIP"
              className="max-w-xs"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void handleFileSelected(file);
              }}
            />
          </div>
        </div>
      )}

      {state.step === "error" && <ErrorBanner message={state.message} onRetry={() => setState({ step: "idle" })} />}

      {state.step === "building" && <p className="text-sm text-muted-foreground">Generando el ZIP…</p>}

      {state.step === "loaded" &&
        (() => {
          const resolvedPlan = applyCorrections(state.plan, state.corrections);
          const exceptions = resolvedPlan.entries.filter((entry) => entry.reason !== null);
          const ready = resolvedPlan.entries.length - exceptions.length;
          const canDownload = exceptions.length === 0;

          return (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {ready} archivo{ready === 1 ? "" : "s"} listo{ready === 1 ? "" : "s"}
                {exceptions.length > 0 ? `, ${exceptions.length} por revisar` : ""}.
              </p>

              {exceptions.length > 0 && (
                <div className={TABLE_SHELL}>
                  <div className={TABLE_SCROLL}>
                    <table className={TABLE}>
                      <thead>
                        <tr className={THEAD_ROW}>
                          <th className={TH}>Archivo</th>
                          <th className={TH}>Motivo</th>
                          <th className={TH}>Año</th>
                          <th className={TH}>Número</th>
                        </tr>
                      </thead>
                      <tbody>
                        {exceptions.map((entry) => {
                          const correction = state.corrections.get(entry.path);
                          const yearValue = correction ? correction.year : String(entry.detectedYear ?? "");
                          const numberValue = correction ? correction.number : String(entry.detectedNumber ?? "");
                          return (
                            <tr key={entry.path} className={TBODY_ROW}>
                              <td className={TD}>{entry.path}</td>
                              <td className={TD}>{REASON_LABEL[entry.reason ?? ""]}</td>
                              <td className={TD}>
                                <Input
                                  aria-label={`Año para ${entry.path}`}
                                  value={yearValue}
                                  onChange={(event) => handleCorrectionChange(entry.path, "year", event.target.value)}
                                  className="w-24"
                                />
                              </td>
                              <td className={TD}>
                                <Input
                                  aria-label={`Número para ${entry.path}`}
                                  value={numberValue}
                                  onChange={(event) => handleCorrectionChange(entry.path, "number", event.target.value)}
                                  className="w-24"
                                />
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <Button onClick={() => void handleDownload()} disabled={!canDownload}>
                Descargar ZIP
              </Button>
            </div>
          );
        })()}
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/FormatterPage.test.tsx`
Expected: PASS — all three tests green.

- [ ] **Step 5: Wire up the route**

Modify `frontend/src/App.tsx`: add the import next to the other page imports (after `BulkDownloadsPage`):

```ts
import { FormatterPage } from "./pages/FormatterPage";
```

And add the route inside the protected `AppLayout` routes (after the `/bulk-downloads` route):

```tsx
<Route path="/formateador" element={<FormatterPage />} />
```

- [ ] **Step 6: Add the sidebar link**

Modify `frontend/src/components/layout/Sidebar.tsx`: add `Wand2` to the existing `lucide-react` import (line 3):

```ts
import { Archive, FileStack, Gauge, LogOut, PanelLeftClose, PanelLeftOpen, PlayCircle, Radar, Wand2 } from "lucide-react";
```

And add an entry to `LINKS` (after the `/bulk-downloads` entry):

```ts
{ to: "/formateador", label: "Formateador", end: false, icon: Wand2 },
```

- [ ] **Step 7: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: PASS — no regressions in existing pages (`App.test.tsx` and `Sidebar`-adjacent tests still pass with the new route/link present).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/FormatterPage.tsx frontend/src/pages/FormatterPage.test.tsx frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat: add Formateador page, route and nav link"
```

---

## Self-Review Notes

- **Spec coverage:** root-folder keyword detection (Task 2), year/number extraction (Task 1), review screen for `no-year`/`no-number`/`duplicate` (Task 4), ZIP output preserving `AÑO/archivo` structure (Task 3), no backend/persistence (no task touches `api/`, `core/`, or `worker/`), skipped-entry counting on read failure (Task 3's `skippedCount`, surfaced in Task 4's post-download notice) — all covered.
- **Type consistency:** `FormatterConfig` (Task 1) → `FormatterPlan`/`FormatterEntry`/`Correction` (Task 2) → `BuildResult`/`buildFormattedZip` (Task 3) → `FormatterPage` (Task 4) all reference the same field names (`detectedYear`, `detectedNumber`, `reason`, `yearFolder`, `path`) verified consistent across every task's code blocks.
- **No placeholders:** every step has complete, runnable code — no TODOs or "similar to Task N" shortcuts.
