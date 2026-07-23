# Formateador: Soporte para Lotes Planos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a Formateador input folder has no year subfolders at all (a "flat" batch), extract each file's year from its own filename instead of blocking every file for manual review.

**Architecture:** A single change inside `analyzeDirectory` (`frontend/src/lib/formatter/analyze.ts`): track whether any subfolder was seen while walking the input, and when none were, derive each root-level file's year (and its final output folder name) from its own filename via the existing `extractYear`/`extractNumber` functions instead of leaving it unresolved. Nothing outside `analyzeDirectory` changes — `copy.ts` already places each entry under `entry.yearFolder` generically, and `markDuplicates`/`computeFinalName` already operate on whatever `detectedYear`/`detectedNumber` they're given.

**Tech Stack:** TypeScript, Vitest — same as the rest of the Formateador feature.

## Global Constraints

- A file sitting directly in the input root is only treated as "flat-batch, extract year from filename" when the root has **zero** subfolders. If the root has at least one subfolder anywhere, a stray root-level file keeps the existing behavior exactly (`yearFolder: ""`, `detectedYear: null`, reason `"no-year"`, no filename-based year extraction attempted) — it's more likely a misplaced file than a genuinely flat batch.
- `TYPE_KEYWORDS`/`CITY_KEYWORDS` in `rules.ts` are explicitly out of scope for this plan — they stay exactly as they are.
- A flat-batch file whose name has no extractable year still gets `reason: "no-year"` — nothing is guessed.
- Output structure for a flat batch still groups by year (e.g. `1962/archivo_renombrado.ext`), derived from the year found in the filename, not flattened.

---

### Task 1: Detect flat batches and extract year from filename in `analyzeDirectory`

**Files:**
- Modify: `frontend/src/lib/formatter/analyze.ts` (replace the body of `analyzeDirectory`, lines 36-95)
- Modify: `frontend/src/lib/formatter/analyze.test.ts` (add new tests)
- Modify: `frontend/src/lib/formatter/copy.test.ts` (add one new test)

**Interfaces:**
- Consumes: `extractYear`, `extractNumber`, `detectConfig` from `./rules` (unchanged imports, already present in `analyze.ts`); `fakeInputDirectory`, `fakeOutputDirectory` from `./testFsFakes` (test-only, already used by both test files).
- Produces: no new exports — `analyzeDirectory`'s signature (`(root: FileSystemDirectoryHandle) => Promise<FormatterPlan>`) and `FormatterEntry`'s shape are unchanged; only the values `analyzeDirectory` computes for root-level files change.

- [ ] **Step 1: Write the failing tests**

Add these tests to `frontend/src/lib/formatter/analyze.test.ts`, inside the existing `describe("analyzeDirectory", ...)` block (after the existing `"marks a file sitting directly in the root (no year folder) as no-year"` test, which stays unchanged):

```ts
  it("extracts the year from the filename itself when the batch has no year subfolders at all", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "Acuerdo 0005 de 1962.pdf": "x",
    });

    const plan = await analyzeDirectory(root);

    expect(plan.entries).toHaveLength(1);
    expect(plan.entries[0]).toMatchObject({
      yearFolder: "1962",
      detectedYear: 1962,
      detectedNumber: 5,
      reason: null,
    });
    expect(computeFinalName(plan.config, plan.entries[0])).toBe("A_CONCALI_0005_1962.pdf");
  });

  it("detects config from filenames when the batch is flat and the root folder name alone lacks the keywords", async () => {
    const root = fakeInputDirectory("Lote 2026", {
      "Acuerdo 0005 de Cali 1962.pdf": "x",
    });

    const plan = await analyzeDirectory(root);

    expect(plan.config).toEqual({ typeCode: "A", cityCode: "CONCALI" });
  });

  it("does not extract a year from a stray root file's name when the batch also uses year subfolders elsewhere", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "ACUERDOS 1962": { "Acuerdo 0005 de 1962.pdf": "x" },
      "suelto de 1998.pdf": "x",
    });

    const plan = await analyzeDirectory(root);

    const strayEntry = plan.entries.find((entry) => entry.filename === "suelto de 1998.pdf")!;
    expect(strayEntry).toMatchObject({ yearFolder: "", detectedYear: null, reason: "no-year" });
  });
```

Add this test to `frontend/src/lib/formatter/copy.test.ts`, inside the existing `describe("copyFormattedFiles", ...)` block:

```ts
  it("groups a flat batch's entries under the year folder derived from each filename", async () => {
    const root = fakeInputDirectory("Acuerdos Cali", {
      "Acuerdo 0005 de 1962.pdf": "contenido-a",
    });
    const plan = await analyzeDirectory(root);
    const resolvedNames = new Map(plan.entries.map((entry) => [entry.path, computeFinalName(plan.config, entry)!]));
    const output = fakeOutputDirectory("salida");

    const { copiedCount } = await copyFormattedFiles(output.handle, plan, resolvedNames);

    expect(copiedCount).toBe(1);
    expect(output.readAll()).toEqual({ "1962/A_CONCALI_0005_1962.pdf": "contenido-a" });
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/formatter/analyze.test.ts src/lib/formatter/copy.test.ts`
Expected: FAIL — the two new `analyze.test.ts` "flat batch" tests fail because every root-level file currently gets `detectedYear: null`/`yearFolder: ""` regardless of its own name; the `copy.test.ts` test fails for the same reason (nothing to copy under a `"1962"` folder since the entry never resolves). The third new `analyze.test.ts` test (stray file alongside a real subfolder) currently PASSES already, since it describes the unchanged behavior — that's expected, not a problem.

- [ ] **Step 3: Replace `analyzeDirectory`'s body**

In `frontend/src/lib/formatter/analyze.ts`, replace the full function (currently lines 36-95, from `export async function analyzeDirectory` through its closing `}`) with:

```ts
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/formatter/analyze.test.ts src/lib/formatter/copy.test.ts`
Expected: PASS — all tests in both files green, including the pre-existing ones (the `"marks a file sitting directly in the root..."` test with fixture `{ "suelto.pdf": "x" }` still passes: with no subfolders, `hasYearFolders` is `false`, `extractYear("suelto.pdf")` finds no year, so it still ends up `{ yearFolder: "", reason: "no-year" }` — same outcome as before, now reached via the flat-batch branch).

- [ ] **Step 5: Run the full suite and the type checker**

Run: `cd frontend && npx vitest run`
Expected: PASS — no regressions anywhere else in the project.

Run: `cd frontend && npx tsc -b`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/formatter/analyze.ts frontend/src/lib/formatter/analyze.test.ts frontend/src/lib/formatter/copy.test.ts
git commit -m "feat: extract year from filename for Formateador batches with no year subfolders"
```

---

## Self-Review Notes

- **Spec coverage:** flat-batch detection (`hasYearFolders`), year-from-filename extraction, filename-inclusive type/city detection for flat batches, output still grouped by derived year (verified via the `copy.test.ts` addition, no `copy.ts` change needed), mixed-batch stray file left unchanged (explicit regression test) — all covered by Task 1. The spec's explicit out-of-scope items (expanding `TYPE_KEYWORDS`/`CITY_KEYWORDS`, filename-year fallback for a named-but-unparseable subfolder) are correctly not addressed by any step.
- **Type consistency:** `FormatterEntry`'s shape (`path`, `yearFolder`, `filename`, `fileHandle`, `detectedYear`, `detectedNumber`, `reason`, `suffix`) is unchanged — Task 1 only changes what values are computed for it, not the interface. `computeFinalName`, `markDuplicates`, `copyFormattedFiles` are all consumed exactly as they already exist, with no signature changes required anywhere.
- **No placeholders:** the one step with code changes contains the complete replacement function; every test has full, runnable assertions.
