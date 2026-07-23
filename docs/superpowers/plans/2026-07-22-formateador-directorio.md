# Formateador v2 (carpeta a carpeta) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Formateador's ZIP upload/download flow with a directory-to-directory flow using the File System Access API, so batch size is bounded by disk, not by the browser's ~2GiB in-memory file-read limit.

**Architecture:** `rules.ts` (pure string functions) stays untouched. `analyze.ts` swaps its ZIP-parsing entry point for a directory-walking one but keeps all of its plan/correction/duplicate-detection logic. `build.ts` is deleted and replaced by `copy.ts`, which streams each resolved file from an input `FileSystemFileHandle` to an output one via `arrayBuffer()`/`write()` — memory bounded to one file at a time, never the whole batch. `FormatterPage.tsx` swaps its `<input type="file">` + zip-download flow for two `showDirectoryPicker()` calls (input, then output) with a copy-progress state. `jszip` is removed as a dependency.

**Tech Stack:** React 19 + TypeScript, the browser-native File System Access API (`FileSystemDirectoryHandle`, `FileSystemFileHandle`, `showDirectoryPicker`), Vitest + Testing Library.

## Global Constraints

- Chromium-only (Chrome/Edge) by explicit user decision — no Firefox/Safari fallback. If `"showDirectoryPicker" in window` is false, show a fixed message instead of the picker UI.
- The output folder is always a separate folder from the input folder — the input is never written to. The user picks the output folder explicitly via a second `showDirectoryPicker({ mode: "readwrite" })` call, after confirming the review table.
- No backend/API changes, nothing persisted — same as v1.
- Type/city are still auto-detected (no configuration form): search across the root folder's own name **and** every distinct year-subfolder name (this fix from v1 carries over verbatim).
- A file that fails to read or write during the copy is counted as skipped and does not abort the rest of the batch.
- `jszip` is removed from `frontend/package.json` — no dependency replaces it (the File System Access API is native).
- The already-verified review-table behavior (stable rows during multi-digit edits, live duplicate re-detection) must be preserved exactly: rows render from `entry.reason !== null || state.corrections.has(entry.path)`, not from a filtered exceptions-only list.

---

### Task 1: Test infrastructure — in-memory File System Access API fakes

**Files:**
- Create: `frontend/src/lib/formatter/testFsFakes.ts`
- Test: `frontend/src/lib/formatter/testFsFakes.test.ts`

**Interfaces:**
- Consumes: nothing (first task; only uses `FileSystemDirectoryHandle`/`FileSystemFileHandle`/`FileSystemWritableFileStream` types, which already ship in this project's TypeScript's `lib.dom.d.ts` — no ambient declaration needed for these three).
- Produces (used by Tasks 2, 3, 4):
  - `export function fakeInputDirectory(name: string, entries: DirectoryEntries): FileSystemDirectoryHandle` — read-only fake built from a nested object literal (`{ "ACUERDOS 1962": { "archivo.pdf": "contenido" } }`).
  - `export interface RecordingDirectory { handle: FileSystemDirectoryHandle; readAll(): Record<string, string>; }`
  - `export function fakeOutputDirectory(name: string): RecordingDirectory` — writable in-memory fake that grows via `getDirectoryHandle`/`getFileHandle` with `{ create: true }`, plus a `readAll()` helper that flattens the written tree to `{ "AÑO/archivo.ext": "contenido", ... }` for assertions.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/formatter/testFsFakes.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { fakeInputDirectory, fakeOutputDirectory } from "./testFsFakes";

describe("fakeInputDirectory", () => {
  it("iterates files and subdirectories via values()", async () => {
    const root = fakeInputDirectory("root", {
      sub: { "a.txt": "hola" },
      "b.txt": "chau",
    });

    const names: string[] = [];
    for await (const handle of root.values()) {
      names.push(`${handle.kind}:${handle.name}`);
    }
    expect(names.sort()).toEqual(["directory:sub", "file:b.txt"]);
  });

  it("getFile() on a nested file handle returns its content", async () => {
    const root = fakeInputDirectory("root", { sub: { "a.txt": "hola" } });

    let fileContent = "";
    for await (const handle of root.values()) {
      if (handle.kind === "directory") {
        for await (const child of handle.values()) {
          if (child.kind === "file") {
            fileContent = await (await child.getFile()).text();
          }
        }
      }
    }
    expect(fileContent).toBe("hola");
  });
});

describe("fakeOutputDirectory", () => {
  it("creates nested directories and files on demand, and readAll() flattens them", async () => {
    const output = fakeOutputDirectory("salida");

    const subDir = await output.handle.getDirectoryHandle("AÑO 2000", { create: true });
    const fileHandle = await subDir.getFileHandle("archivo.txt", { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(new TextEncoder().encode("contenido").buffer);
    await writable.close();

    expect(output.readAll()).toEqual({ "AÑO 2000/archivo.txt": "contenido" });
  });

  it("getDirectoryHandle/getFileHandle without create throws for a missing entry", async () => {
    const output = fakeOutputDirectory("salida");
    await expect(output.handle.getDirectoryHandle("no-existe")).rejects.toThrow();
    await expect(output.handle.getFileHandle("no-existe.txt")).rejects.toThrow();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/formatter/testFsFakes.test.ts`
Expected: FAIL — `Failed to resolve import "./testFsFakes"` (the module doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/lib/formatter/testFsFakes.ts`:

```ts
// In-memory fakes for the File System Access API, used only in tests — jsdom implements
// neither FileSystemDirectoryHandle/FileSystemFileHandle nor showDirectoryPicker natively.

export type DirectoryEntries = { [key: string]: string | DirectoryEntries };

function buildFileHandle(name: string, content: string): FileSystemFileHandle {
  return {
    kind: "file",
    name,
    isSameEntry: async () => false,
    getFile: async () => new File([content], name),
    createWritable: async () => {
      throw new Error("Read-only fake file handle: createWritable is not supported.");
    },
  } as unknown as FileSystemFileHandle;
}

function buildDirectoryHandle(name: string, entries: DirectoryEntries): FileSystemDirectoryHandle {
  const children = new Map<string, FileSystemFileHandle | FileSystemDirectoryHandle>();
  for (const [childName, value] of Object.entries(entries)) {
    children.set(
      childName,
      typeof value === "string" ? buildFileHandle(childName, value) : buildDirectoryHandle(childName, value)
    );
  }

  return {
    kind: "directory",
    name,
    isSameEntry: async () => false,
    values: () => {
      const iterator = children.values();
      return {
        [Symbol.asyncIterator]() {
          return this;
        },
        next: async () => iterator.next(),
      } as unknown as ReturnType<FileSystemDirectoryHandle["values"]>;
    },
    getDirectoryHandle: async () => {
      throw new Error("Read-only fake directory handle: getDirectoryHandle is not supported.");
    },
    getFileHandle: async () => {
      throw new Error("Read-only fake directory handle: getFileHandle is not supported.");
    },
  } as unknown as FileSystemDirectoryHandle;
}

export function fakeInputDirectory(name: string, entries: DirectoryEntries): FileSystemDirectoryHandle {
  return buildDirectoryHandle(name, entries);
}

interface RecordingNode {
  kind: "file" | "directory";
  content?: ArrayBuffer;
  children?: Map<string, RecordingNode>;
}

export interface RecordingDirectory {
  handle: FileSystemDirectoryHandle;
  readAll(): Record<string, string>;
}

export function fakeOutputDirectory(name: string): RecordingDirectory {
  const root: RecordingNode = { kind: "directory", children: new Map() };

  function wrapFile(node: RecordingNode, fileName: string): FileSystemFileHandle {
    return {
      kind: "file",
      name: fileName,
      isSameEntry: async () => false,
      getFile: async () => new File([node.content ?? new ArrayBuffer(0)], fileName),
      createWritable: async () => {
        return {
          write: async (data: ArrayBuffer) => {
            node.content = data;
          },
          close: async () => {},
        } as unknown as FileSystemWritableFileStream;
      },
    } as unknown as FileSystemFileHandle;
  }

  function wrapDir(node: RecordingNode, dirName: string): FileSystemDirectoryHandle {
    return {
      kind: "directory",
      name: dirName,
      isSameEntry: async () => false,
      values: () => {
        throw new Error("fakeOutputDirectory does not support iteration — it's write-only for copy.ts.");
      },
      getDirectoryHandle: async (childName: string, options?: { create?: boolean }) => {
        let child = node.children!.get(childName);
        if (!child) {
          if (!options?.create) throw new DOMException("Not found", "NotFoundError");
          child = { kind: "directory", children: new Map() };
          node.children!.set(childName, child);
        }
        return wrapDir(child, childName);
      },
      getFileHandle: async (childName: string, options?: { create?: boolean }) => {
        let child = node.children!.get(childName);
        if (!child) {
          if (!options?.create) throw new DOMException("Not found", "NotFoundError");
          child = { kind: "file" };
          node.children!.set(childName, child);
        }
        return wrapFile(child, childName);
      },
    } as unknown as FileSystemDirectoryHandle;
  }

  function flatten(node: RecordingNode, prefix: string, out: Record<string, string>): void {
    for (const [childName, child] of node.children ?? []) {
      const path = prefix ? `${prefix}/${childName}` : childName;
      if (child.kind === "file") {
        out[path] = new TextDecoder().decode(child.content ?? new ArrayBuffer(0));
      } else {
        flatten(child, path, out);
      }
    }
  }

  return {
    handle: wrapDir(root, name),
    readAll: () => {
      const out: Record<string, string> = {};
      flatten(root, "", out);
      return out;
    },
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/formatter/testFsFakes.test.ts`
Expected: PASS — all 4 tests green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/formatter/testFsFakes.ts frontend/src/lib/formatter/testFsFakes.test.ts
git commit -m "test: add in-memory File System Access API fakes for Formateador tests"
```

---

### Task 2: Directory analysis — replace ZIP parsing with directory walking

**Files:**
- Modify: `frontend/src/lib/formatter/analyze.ts` (full rewrite of the ZIP-specific parts; `computeFinalName`, `markDuplicates`, `applyCorrections`, `recomputeReasons`, `parsePositiveInt`, `FormatterError`, `Correction` are unchanged)
- Modify: `frontend/src/lib/formatter/analyze.test.ts` (full rewrite — replaces every ZIP-fixture test with an equivalent directory-fixture test)

**Interfaces:**
- Consumes from Task 1: `fakeInputDirectory` from `./testFsFakes` (test-only).
- Consumes unchanged from `./rules`: `detectConfig`, `extractYear`, `extractNumber`, `buildFileName`, `fileExtension`, `FormatterConfig`.
- Produces (used by Tasks 3 and 4 — same names as v1 except `analyzeZip` → `analyzeDirectory`, and `FormatterEntry` gains `fileHandle`):
  - `export type FormatterReason = "no-year" | "no-number" | "duplicate"`
  - `export interface FormatterEntry { path: string; yearFolder: string; filename: string; fileHandle: FileSystemFileHandle; detectedYear: number | null; detectedNumber: number | null; reason: FormatterReason | null; }`
  - `export interface FormatterPlan { config: FormatterConfig; rootFolderName: string; entries: FormatterEntry[]; }`
  - `export interface Correction { year: string; number: string; }`
  - `export class FormatterError extends Error {}`
  - `export function analyzeDirectory(root: FileSystemDirectoryHandle): Promise<FormatterPlan>`
  - `export function computeFinalName(config: FormatterConfig, entry: FormatterEntry): string | null`
  - `export function markDuplicates(entries: FormatterEntry[], config: FormatterConfig): void`
  - `export function applyCorrections(plan: FormatterPlan, corrections: Map<string, Correction>): FormatterPlan`

- [ ] **Step 1: Write the failing test**

Replace the full contents of `frontend/src/lib/formatter/analyze.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { analyzeDirectory, applyCorrections, computeFinalName, FormatterError } from "./analyze";
import { fakeInputDirectory } from "./testFsFakes";

describe("analyzeDirectory", () => {
  it("detects config, year and number for files under year subfolders", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": { "Acuerdo 0005 de 1962.pdf": "x" },
    });

    const plan = await analyzeDirectory(root);

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

  it("detects config from year-folder names when the root folder name lacks the type keyword", async () => {
    const root = fakeInputDirectory("CALI 2026", {
      "ACUERDOS 1962": { "Acuerdo 0005 de 1962.pdf": "x" },
      "ACUERDOS 1963": { "Acuerdo 0001 de 1963.pdf": "x" },
    });

    const plan = await analyzeDirectory(root);

    expect(plan.config).toEqual({ typeCode: "A", cityCode: "CONCALI" });
  });

  it("throws when the root and year-folder names don't match a known type/city", async () => {
    const root = fakeInputDirectory("Resoluciones Bogota", {
      "2020": { "algo.pdf": "x" },
    });

    await expect(analyzeDirectory(root)).rejects.toThrow(FormatterError);
  });

  it("marks files without a detectable year as no-year", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      VARIOS: { "Acuerdo 0005.pdf": "x" },
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries[0].reason).toBe("no-year");
    expect(plan.entries[0].detectedYear).toBeNull();
  });

  it("marks a file sitting directly in the root (no year folder) as no-year", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "suelto.pdf": "x",
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries[0]).toMatchObject({ yearFolder: "", reason: "no-year" });
  });

  it("marks files without a detectable number as no-number", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": { "sin numero.pdf": "x" },
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries[0].reason).toBe("no-number");
  });

  it("marks colliding names as duplicate", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": {
        "Acuerdo 0005 primero.pdf": "x",
        "Acuerdo 0005 segundo.pdf": "x",
      },
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries.every((entry) => entry.reason === "duplicate")).toBe(true);
  });

  it("throws for a folder with no files", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": {},
    });

    await expect(analyzeDirectory(root)).rejects.toThrow(FormatterError);
  });
});

describe("applyCorrections", () => {
  it("resolves an exception and clears its reason once a valid year and number are supplied", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": { "sin numero.pdf": "x" },
    });
    const plan = await analyzeDirectory(root);

    const corrections = new Map([[plan.entries[0].path, { year: "1962", number: "9" }]]);
    const resolved = applyCorrections(plan, corrections);

    expect(resolved.entries[0].reason).toBeNull();
    expect(computeFinalName(resolved.config, resolved.entries[0])).toBe("A_CONCALI_0009_1962.pdf");
  });

  it("re-flags a collision introduced by a correction, and clears one resolved by a later correction", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": {
        "Acuerdo 0005 uno.pdf": "x",
        "sin numero.pdf": "x",
      },
    });
    const plan = await analyzeDirectory(root);
    const noNumberEntry = plan.entries.find((entry) => entry.reason === "no-number")!;

    const collided = applyCorrections(plan, new Map([[noNumberEntry.path, { year: "1962", number: "5" }]]));
    expect(collided.entries.every((entry) => entry.reason === "duplicate")).toBe(true);

    const resolved = applyCorrections(plan, new Map([[noNumberEntry.path, { year: "1962", number: "6" }]]));
    expect(resolved.entries.every((entry) => entry.reason === null)).toBe(true);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/formatter/analyze.test.ts`
Expected: FAIL — `analyzeDirectory` is not exported from `./analyze` (the old file only exports `analyzeZip`).

- [ ] **Step 3: Write the implementation**

Replace the full contents of `frontend/src/lib/formatter/analyze.ts`:

```ts
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
      return { path, yearFolder, filename, fileHandle, detectedYear: null, detectedNumber: null, reason: null };
    }
    const detectedYear = extractYear(yearFolder);
    const detectedNumber = detectedYear === null ? null : extractNumber(filename, detectedYear);
    return { path, yearFolder, filename, fileHandle, detectedYear, detectedNumber, reason: null };
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

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/formatter/analyze.test.ts`
Expected: PASS — all 10 tests green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/formatter/analyze.ts frontend/src/lib/formatter/analyze.test.ts
git commit -m "feat: replace Formateador ZIP analysis with directory walking"
```

---

### Task 3: Copy module — stream files to the output directory, delete the ZIP builder

**Files:**
- Delete: `frontend/src/lib/formatter/build.ts`
- Delete: `frontend/src/lib/formatter/build.test.ts`
- Create: `frontend/src/lib/formatter/copy.ts`
- Test: `frontend/src/lib/formatter/copy.test.ts`

**Interfaces:**
- Consumes from Task 1: `fakeInputDirectory`, `fakeOutputDirectory` from `./testFsFakes` (test-only).
- Consumes from Task 2: `analyzeDirectory`, `computeFinalName`, `FormatterPlan` from `./analyze`.
- Produces (used by Task 4):
  - `export interface CopyResult { copiedCount: number; skippedCount: number; }`
  - `export function copyFormattedFiles(outputRoot: FileSystemDirectoryHandle, plan: FormatterPlan, resolvedNames: Map<string, string>, onProgress?: (done: number, total: number) => void): Promise<CopyResult>`

- [ ] **Step 1: Delete the old ZIP builder**

```bash
git rm frontend/src/lib/formatter/build.ts frontend/src/lib/formatter/build.test.ts
```

- [ ] **Step 2: Write the failing test**

Create `frontend/src/lib/formatter/copy.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { analyzeDirectory, computeFinalName } from "./analyze";
import { copyFormattedFiles } from "./copy";
import { fakeInputDirectory, fakeOutputDirectory } from "./testFsFakes";

describe("copyFormattedFiles", () => {
  it("writes each entry under its year folder using the resolved name", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": { "Acuerdo 0005 de 1962.pdf": "contenido-a" },
      "ACUERDOS 1963": { "Acuerdo 0001 de 1963.pdf": "contenido-b" },
    });
    const plan = await analyzeDirectory(root);
    const resolvedNames = new Map(plan.entries.map((entry) => [entry.path, computeFinalName(plan.config, entry)!]));
    const output = fakeOutputDirectory("salida");

    const progressCalls: Array<[number, number]> = [];
    const { copiedCount, skippedCount } = await copyFormattedFiles(output.handle, plan, resolvedNames, (done, total) =>
      progressCalls.push([done, total])
    );

    expect(copiedCount).toBe(2);
    expect(skippedCount).toBe(0);
    expect(output.readAll()).toEqual({
      "ACUERDOS 1962/A_CONCALI_0005_1962.pdf": "contenido-a",
      "ACUERDOS 1963/A_CONCALI_0001_1963.pdf": "contenido-b",
    });
    expect(progressCalls).toEqual([
      [1, 2],
      [2, 2],
    ]);
  });

  it("counts an entry as skipped when reading it fails, without aborting the rest of the batch", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": {
        "Acuerdo 0005 de 1962.pdf": "contenido-a",
        "Acuerdo 0006 de 1962.pdf": "contenido-b",
      },
    });
    const plan = await analyzeDirectory(root);
    const resolvedNames = new Map(plan.entries.map((entry) => [entry.path, computeFinalName(plan.config, entry)!]));
    const output = fakeOutputDirectory("salida");

    const brokenEntry = plan.entries.find((entry) => entry.filename === "Acuerdo 0005 de 1962.pdf")!;
    brokenEntry.fileHandle = {
      ...brokenEntry.fileHandle,
      getFile: async () => {
        throw new Error("simulated read failure");
      },
    } as typeof brokenEntry.fileHandle;

    const { copiedCount, skippedCount } = await copyFormattedFiles(output.handle, plan, resolvedNames);

    expect(copiedCount).toBe(1);
    expect(skippedCount).toBe(1);
    expect(output.readAll()).toEqual({
      "ACUERDOS 1962/A_CONCALI_0006_1962.pdf": "contenido-b",
    });
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/formatter/copy.test.ts`
Expected: FAIL — `Failed to resolve import "./copy"` (the module doesn't exist yet).

- [ ] **Step 4: Write the implementation**

Create `frontend/src/lib/formatter/copy.ts`:

```ts
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/formatter/copy.test.ts`
Expected: PASS — both tests green.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/formatter/copy.ts frontend/src/lib/formatter/copy.test.ts
git commit -m "feat: add Formateador directory-to-directory copy, remove ZIP builder"
```

(The `git rm` from Step 1 is included in this commit automatically since it was already staged.)

---

### Task 4: FormatterPage — directory pickers, copy progress, unsupported-browser guard

**Files:**
- Create: `frontend/src/lib/formatter/fileSystemAccess.d.ts`
- Modify: `frontend/src/pages/FormatterPage.tsx` (full rewrite)
- Modify: `frontend/src/pages/FormatterPage.test.tsx` (full rewrite)
- Modify: `frontend/package.json` and `frontend/package-lock.json` (remove `jszip`)

**Interfaces:**
- Consumes from Task 1: `fakeInputDirectory`, `fakeOutputDirectory` from `../lib/formatter/testFsFakes` (test-only).
- Consumes from Task 2: `analyzeDirectory`, `applyCorrections`, `computeFinalName`, `FormatterError`, `Correction`, `FormatterPlan` from `../lib/formatter/analyze`.
- Consumes from Task 3: `copyFormattedFiles` from `../lib/formatter/copy`.
- Consumes existing code: `ErrorBanner` from `../components/ErrorBanner`; `Button` from `../components/ui/button`; `Input` from `../components/ui/input`; `TABLE`, `TABLE_SCROLL`, `TABLE_SHELL`, `TBODY_ROW`, `TD`, `TH`, `THEAD_ROW` from `../lib/tableStyles`.
- Produces: `export function FormatterPage()`, still rendered at route `/formateador` (no change to `App.tsx`/`Sidebar.tsx` — the route and nav link from v1 stay as-is).

- [ ] **Step 1: Add the ambient type declaration**

TypeScript's bundled `lib.dom.d.ts` in this project already declares `FileSystemDirectoryHandle`, `FileSystemFileHandle`, and `FileSystemWritableFileStream`, but not the global `showDirectoryPicker()` function or its options type. Create `frontend/src/lib/formatter/fileSystemAccess.d.ts`:

```ts
export {};

declare global {
  interface DirectoryPickerOptions {
    id?: string;
    mode?: "read" | "readwrite";
    startIn?: FileSystemHandle | string;
  }

  interface Window {
    showDirectoryPicker(options?: DirectoryPickerOptions): Promise<FileSystemDirectoryHandle>;
  }
}
```

- [ ] **Step 2: Write the failing test**

Replace the full contents of `frontend/src/pages/FormatterPage.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FormatterPage } from "./FormatterPage";
import { fakeInputDirectory, fakeOutputDirectory } from "../lib/formatter/testFsFakes";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("FormatterPage", () => {
  it("shows a ready summary and an enabled copy button when every file resolves cleanly", async () => {
    const inputRoot = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": {
        "Acuerdo 0005 de 1962.pdf": "contenido",
        "Acuerdo 0006 de 1962.pdf": "contenido",
      },
    });
    vi.stubGlobal("showDirectoryPicker", vi.fn().mockResolvedValue(inputRoot));

    render(<FormatterPage />);
    await userEvent.click(screen.getByRole("button", { name: /elegir carpeta de entrada/i }));

    expect(await screen.findByText(/2 archivos listos/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /elegir carpeta de salida y copiar/i })).toBeEnabled();
  });

  it("keeps the copy button disabled until a multi-digit correction is fully typed, then copies", async () => {
    const inputRoot = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": { "sin numero.pdf": "contenido" },
    });
    const output = fakeOutputDirectory("salida");
    const picker = vi.fn().mockResolvedValueOnce(inputRoot).mockResolvedValueOnce(output.handle);
    vi.stubGlobal("showDirectoryPicker", picker);

    const user = userEvent.setup();
    render(<FormatterPage />);
    await user.click(screen.getByRole("button", { name: /elegir carpeta de entrada/i }));

    await screen.findByText(/número no detectado/i);
    const numberField = screen.getByLabelText(/número para/i);
    await user.type(numberField, "12");
    expect(numberField).toHaveValue("12");

    const copyButton = screen.getByRole("button", { name: /elegir carpeta de salida y copiar/i });
    await waitFor(() => expect(copyButton).toBeEnabled());
    await user.click(copyButton);

    await waitFor(() => expect(screen.getByText(/1 archivo copiado/i)).toBeInTheDocument());
    expect(output.readAll()).toEqual({ "ACUERDOS 1962/A_CONCALI_0012_1962.pdf": "contenido" });
  });

  it("shows an error banner for a folder whose name isn't recognized", async () => {
    const inputRoot = fakeInputDirectory("Resoluciones Bogota", { "2020": { "algo.pdf": "x" } });
    vi.stubGlobal("showDirectoryPicker", vi.fn().mockResolvedValue(inputRoot));

    render(<FormatterPage />);
    await userEvent.click(screen.getByRole("button", { name: /elegir carpeta de entrada/i }));

    expect(await screen.findByText(/no se reconoce el tipo de documento o la ciudad/i)).toBeInTheDocument();
  });

  it("does not show an error when the user cancels the directory picker", async () => {
    const abortError = new DOMException("The user aborted a request.", "AbortError");
    vi.stubGlobal("showDirectoryPicker", vi.fn().mockRejectedValue(abortError));

    render(<FormatterPage />);
    await userEvent.click(screen.getByRole("button", { name: /elegir carpeta de entrada/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: /elegir carpeta de entrada/i })).toBeInTheDocument());
    expect(screen.queryByText(/no se pudo/i)).not.toBeInTheDocument();
  });

  it("shows the unsupported-browser message when showDirectoryPicker doesn't exist", () => {
    render(<FormatterPage />);

    expect(screen.getByText(/necesita chrome o edge/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /elegir carpeta de entrada/i })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/FormatterPage.test.tsx`
Expected: FAIL — the current `FormatterPage` renders a file `<input>`, not an "Elegir carpeta de entrada" button, so every test's `getByRole("button", { name: /elegir carpeta de entrada/i })` throws.

- [ ] **Step 4: Write the implementation**

Replace the full contents of `frontend/src/pages/FormatterPage.tsx`:

```tsx
import { useState } from "react";
import { Wand2 } from "lucide-react";
import { ErrorBanner } from "../components/ErrorBanner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  analyzeDirectory,
  applyCorrections,
  computeFinalName,
  FormatterError,
  type Correction,
  type FormatterPlan,
} from "../lib/formatter/analyze";
import { copyFormattedFiles } from "../lib/formatter/copy";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TH, THEAD_ROW } from "../lib/tableStyles";

type FormatterState =
  | { step: "idle"; notice?: string }
  | { step: "unsupported" }
  | { step: "error"; message: string }
  | { step: "loaded"; plan: FormatterPlan; corrections: Map<string, Correction> }
  | { step: "copying"; done: number; total: number };

const REASON_LABEL: Record<string, string> = {
  "no-year": "Año no detectado",
  "no-number": "Número no detectado",
  duplicate: "Número duplicado",
};

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function FormatterPage() {
  const [state, setState] = useState<FormatterState>(() =>
    "showDirectoryPicker" in window ? { step: "idle" } : { step: "unsupported" }
  );

  async function handlePickInput() {
    try {
      const root = await window.showDirectoryPicker();
      const plan = await analyzeDirectory(root);
      setState({ step: "loaded", plan, corrections: new Map() });
    } catch (error) {
      if (isAbortError(error)) return;
      const message = error instanceof FormatterError ? error.message : "No se pudo leer la carpeta.";
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

  async function handleCopy() {
    if (state.step !== "loaded") return;
    const resolvedPlan = applyCorrections(state.plan, state.corrections);
    const resolvedNames = new Map<string, string>();
    for (const entry of resolvedPlan.entries) {
      const name = computeFinalName(resolvedPlan.config, entry);
      if (name) resolvedNames.set(entry.path, name);
    }

    let outputRoot: FileSystemDirectoryHandle;
    try {
      outputRoot = await window.showDirectoryPicker({ mode: "readwrite" });
    } catch (error) {
      if (isAbortError(error)) return;
      setState({ step: "error", message: "No se pudo abrir la carpeta de salida." });
      return;
    }

    setState({ step: "copying", done: 0, total: resolvedNames.size });
    try {
      const { copiedCount, skippedCount } = await copyFormattedFiles(
        outputRoot,
        resolvedPlan,
        resolvedNames,
        (done, total) => {
          if (done % 20 === 0 || done === total) setState({ step: "copying", done, total });
        }
      );
      const copiedLabel = `${copiedCount} archivo${copiedCount === 1 ? "" : "s"} copiado${copiedCount === 1 ? "" : "s"}`;
      setState({
        step: "idle",
        notice:
          skippedCount > 0
            ? `${copiedLabel}, ${skippedCount} omitido${skippedCount === 1 ? "" : "s"} por error de lectura.`
            : `${copiedLabel}.`,
      });
    } catch {
      setState({ step: "error", message: "No se pudo completar la copia." });
    }
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

      {state.step === "unsupported" && (
        <ErrorBanner message="Esta función necesita Chrome o Edge; tu navegador actual no es compatible." />
      )}

      {state.step === "idle" && (
        <div className={TABLE_SHELL}>
          <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
            {state.notice && <p className="text-xs text-muted-foreground">{state.notice}</p>}
            <p className="text-sm text-muted-foreground">
              Elige la carpeta con los acuerdos (subcarpetas por año) para renombrar los archivos.
            </p>
            <Button onClick={() => void handlePickInput()}>Elegir carpeta de entrada</Button>
          </div>
        </div>
      )}

      {state.step === "error" && <ErrorBanner message={state.message} onRetry={() => setState({ step: "idle" })} />}

      {state.step === "copying" && (
        <p className="text-sm text-muted-foreground">
          Copiando {state.done} / {state.total}…
        </p>
      )}

      {state.step === "loaded" &&
        (() => {
          const resolvedPlan = applyCorrections(state.plan, state.corrections);
          const pending = resolvedPlan.entries.filter((entry) => entry.reason !== null);
          const visibleRows = resolvedPlan.entries.filter(
            (entry) => entry.reason !== null || state.corrections.has(entry.path)
          );
          const ready = resolvedPlan.entries.length - pending.length;
          const canCopy = pending.length === 0;

          return (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {ready} archivo{ready === 1 ? "" : "s"} listo{ready === 1 ? "" : "s"}
                {pending.length > 0 ? `, ${pending.length} por revisar` : ""}.
              </p>

              {visibleRows.length > 0 && (
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
                        {visibleRows.map((entry) => {
                          const correction = state.corrections.get(entry.path);
                          const yearValue = correction ? correction.year : String(entry.detectedYear ?? "");
                          const numberValue = correction ? correction.number : String(entry.detectedNumber ?? "");
                          return (
                            <tr key={entry.path} className={TBODY_ROW}>
                              <td className={TD}>{entry.path}</td>
                              <td className={TD}>{entry.reason ? REASON_LABEL[entry.reason] : "Resuelto"}</td>
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

              <Button onClick={() => void handleCopy()} disabled={!canCopy}>
                Elegir carpeta de salida y copiar
              </Button>
            </div>
          );
        })()}
    </div>
  );
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/FormatterPage.test.tsx`
Expected: PASS — all 5 tests green.

- [ ] **Step 6: Remove the `jszip` dependency**

Run: `cd frontend && npm uninstall jszip`
Expected: `frontend/package.json` loses the `"jszip"` line under `dependencies`; `frontend/package-lock.json` updates accordingly.

- [ ] **Step 7: Run the full frontend test suite and the TypeScript compiler**

Run: `cd frontend && npx vitest run`
Expected: PASS — no regressions (`rules.test.ts` and `App.test.tsx`/route/nav tests untouched by this plan still pass).

Run: `cd frontend && npx tsc -b`
Expected: no errors — confirms `showDirectoryPicker`/`FileSystemDirectoryHandle` types resolve correctly via `fileSystemAccess.d.ts` plus the bundled `lib.dom.d.ts`.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/formatter/fileSystemAccess.d.ts frontend/src/pages/FormatterPage.tsx frontend/src/pages/FormatterPage.test.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat: switch Formateador to directory pickers, drop jszip"
```

---

## Self-Review Notes

- **Spec coverage:** directory-to-directory flow (Tasks 2-4), rules.ts untouched (verified — no task modifies it), type/city detection via root name + year-folder names (Task 2, ported verbatim from the already-shipped v1 fix), separate output folder never touching input (Task 4's two independent `showDirectoryPicker` calls, `mode: "readwrite"` only on the output one), per-file skip-without-abort (Task 3), unsupported-browser guard (Task 4), `jszip` removal (Task 4 Step 6), stable review-table rows preserved exactly (Task 4's `visibleRows`/`pending` split, unchanged from the already-verified v1 logic) — all covered.
- **Type consistency:** `FormatterEntry.fileHandle` (Task 2) is produced by `analyzeDirectory` and consumed by `copyFormattedFiles` (Task 3) via `entry.fileHandle.getFile()`, and by nothing else — consistent. `CopyResult { copiedCount, skippedCount }` (Task 3) matches exactly how Task 4 destructures it. `resolvedNames: Map<string, string>` keyed by `entry.path` is built identically in both `copy.test.ts` and `FormatterPage.tsx`.
- **No placeholders:** every step has complete, runnable code; deletions are explicit `git rm`/file-delete steps, not silently implied.
