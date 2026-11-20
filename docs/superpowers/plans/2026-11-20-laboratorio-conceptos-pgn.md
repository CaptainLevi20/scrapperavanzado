# Renombrado de Conceptos PGN — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nueva pestaña "Conceptos PGN" en el Laboratorio que renombra en el lugar un lote de conceptos de la PGN a `CTO_PGN_{7 dígitos}_{año}(C).{ext}`, con revisión previa, vista previa de la primera página y un registro CSV.

**Architecture:** Todo en el frontend, sobre la File System Access API, igual que el Renombrado de Cali. Hay tres módulos puros/testeables en `frontend/src/lib/conceptosPgn/`: reglas de nombre, análisis del árbol y renombre en el lugar con registro. Encima va un panel React nuevo, agregado como cuarta pestaña de `FormatterPage`. Sin backend ni base de datos.

**Tech Stack:** React 19 + TypeScript, Vitest + Testing Library, oxlint, File System Access API (Chrome/Edge).

**Spec:** `docs/superpowers/specs/2026-11-20-laboratorio-conceptos-pgn-design.md`

## Global Constraints

- Nombre final: `CTO_PGN_{número rellenado a 7 dígitos}{letra A opcional}_{año 4 dígitos}(C){ext en minúsculas}` (ej. `CTO_PGN_0004036A_2006(C).pdf`).
- Documentos = `.pdf`, `.doc`, `.docx`, `.rtf` (sin distinguir mayúsculas). Todo lo demás se ignora y nunca se toca.
- El año sale de la carpeta de **primer nivel** bajo la raíz (nombre exacto `19xx`/`20xx`).
- Ninguna carpeta se mueve ni se renombra; solo cambia el nombre del archivo, dentro de su misma carpeta.
- Un nombre destino que ya existe (comparando sin mayúsculas, como Windows) **nunca** se sobrescribe: ese archivo se salta.
- Nunca se inventa un número: si no se detecta y nadie lo escribe, el archivo conserva su nombre.
- El Renombrado de Cali (`lib/formatter/*`, `pages/formatter/RenamePanel.tsx`) no cambia de comportamiento.
- Nada de `window.alert`/`confirm`/`prompt`: la confirmación es un paso dentro de la página.
- Registro: `registro_renombres_AAAAMMDD-HHMM.csv` en la raíz del lote, UTF-8 con BOM, separador `;`, columnas `ruta;nombre_anterior;nombre_nuevo;resultado`. Se escribe antes de renombrar (resultado `pendiente`) y se reescribe al terminar.
- Texto de la pantalla en español.

## Review Focus

1. **Números de concepto entre 1900 y 2099 sin año en el nombre** (`2011.pdf`, `Cto. 2011.pdf` dentro de `2000\`): el lote real tiene conceptos 2011–2365 en el año 2000. Hay que leerlos como número, no como año. Prueba en Task 1.
2. **Archivo destino que ya existe con otras mayúsculas** (`cto_pgn_0001654_1991(c).pdf` ya presente): se salta, no se pisa. Prueba en Task 3.
3. **Fallo a mitad del camino alternativo** (la escritura queda incompleta o falla): el original sigue intacto y no queda ningún archivo a medias. Prueba en Task 3.
4. **Segunda pasada sobre un lote ya renombrado**: todo sale como "ya tiene el nombre final" y no se renombra nada. Además, el CSV de la primera pasada no aparece como documento. Prueba en Task 2.
5. **Corrección manual con letra o ceros** (`4036a`, `0004036`, `4883-A`): produce el mismo nombre que la detección automática. Prueba en Task 1.

---

### Task 1: Reglas de nombre

**Files:**
- Create: `frontend/src/lib/conceptosPgn/rules.ts`
- Test: `frontend/src/lib/conceptosPgn/rules.test.ts`

**Interfaces:**
- Consumes: `fileExtension(filename: string): string` de `frontend/src/lib/formatter/rules.ts` (ya devuelve en minúsculas, con el punto).
- Produces:
  - `interface ConceptNumber { value: number; letter: "" | "A" }`
  - `isDocument(filename: string): boolean`
  - `isImage(filename: string): boolean` (`.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`)
  - `yearFromFolderName(name: string): number | null`: solo si el nombre completo es `19xx`/`20xx`.
  - `parseConceptName(filename: string, folderYear: number | null): { number: ConceptNumber | null; nameYear: number | null }`
  - `parseConceptInput(text: string): ConceptNumber | null`
  - `buildConceptName(number: ConceptNumber, year: number, ext: string): string`

Algoritmo de `parseConceptName` (validado contra `lista_lote.txt`: 2,340 listos, 11 sin número, 1 año distinto):
1. `stem` = nombre sin extensión. Si `stem` empieza (ignorando espacios y mayúsculas) por la palabra `tomo` → `{ number: null, nameYear: null }`.
2. Grupos = coincidencias de `/(\d+)(?:-?([Aa])(?![A-Za-z]))?/g` sobre `stem`. Así, `4883-A` → 4883 + A, y `3168pdf` → 3168 sin letra.
3. `nameYear`: si hay **2 o más** grupos y el último es `19xx`/`20xx` sin letra, ese es el año del nombre y se quita de la lista. Con un solo grupo nunca hay año en el nombre (cubre `2011.pdf`).
4. Se descartan los grupos sin letra cuyo valor sea igual a `folderYear`.
5. El primero que quede es el número (`value` = entero, por lo que los ceros a la izquierda desaparecen; la letra va en mayúscula). Si no queda ninguno, `number: null`.

- [ ] **Step 1: Write the failing tests** en `rules.test.ts`, con `it.each` sobre las formas reales (`folderYear` entre paréntesis → nombre esperado con `buildConceptName(number, nameYear ?? folderYear, ext)`):

```ts
const CASES: [string, number, string][] = [
  ["Cto. 1653.pdf", 1991, "CTO_PGN_0001653_1991(C).pdf"],
  ["Cto. NN 1.pdf", 1991, "CTO_PGN_0000001_1991(C).pdf"],
  ["Cto. NN1.pdf", 2000, "CTO_PGN_0000001_2000(C).pdf"],
  ["Cto. 114 .pdf", 1992, "CTO_PGN_0000114_1992(C).pdf"],
  ["Cto. 3168pdf.pdf", 2003, "CTO_PGN_0003168_2003(C).pdf"],
  ["Concepto 2258 de 2000.pdf", 2000, "CTO_PGN_0002258_2000(C).pdf"],
  ["Concepto de 5094 de 2011.pdf", 2011, "CTO_PGN_0005094_2011(C).pdf"],
  ["Concpeto 5018 de 2010.pdf", 2010, "CTO_PGN_0005018_2010(C).pdf"],
  ["Conceptto 4106 de 2006.pdf", 2006, "CTO_PGN_0004106_2006(C).pdf"],
  ["Concepro 4747 de 2009.pdf", 2009, "CTO_PGN_0004747_2009(C).pdf"],
  ["Cncepto 5649.pdf", 2013, "CTO_PGN_0005649_2013(C).pdf"],
  ["Concepto 5651 de 2013..pdf", 2013, "CTO_PGN_0005651_2013(C).pdf"],
  ["Concepto 4450 de 2008 .pdf", 2008, "CTO_PGN_0004450_2008(C).pdf"],
  ["Concepto 4838.pdf", 2009, "CTO_PGN_0004838_2009(C).pdf"],
  ["4004.pdf", 2006, "CTO_PGN_0004004_2006(C).pdf"],
  ["2011.pdf", 2000, "CTO_PGN_0002011_2000(C).pdf"],          // Review Focus 1
  ["Cto. 2011.pdf", 2000, "CTO_PGN_0002011_2000(C).pdf"],     // Review Focus 1
  ["Concepto 4036A de 2006.pdf", 2006, "CTO_PGN_0004036A_2006(C).pdf"],
  ["Concepto 4883-A.pdf", 2010, "CTO_PGN_0004883A_2010(C).pdf"],
  ["CTO_PGN_0003788_2005.pdf", 2005, "CTO_PGN_0003788_2005(C).pdf"],
  ["Cto. 1654.PDF", 1991, "CTO_PGN_0001654_1991(C).pdf"],
];
```
Más pruebas sueltas:
- `parseConceptName("Tomo 3 1991-1-14.pdf", 1991)` → `{ number: null, nameYear: null }`.
- `parseConceptName("Concepto 4734 de 2008.pdf", 2009)` → number 4734, `nameYear: 2008`.
- `parseConceptName("Cto. 2005.pdf", 2005).number` → `null`.
- `parseConceptInput` con `"4036A"`, `"4036a"`, `" 0004036A "`, `"4036-A"` → `{ value: 4036, letter: "A" }`; `"4036"` → letra `""`; `""`, `"abc"`, `"12B"`, `"-3"` → `null` (Review Focus 5).
- `isDocument`: `true` para `a.PDF`, `a.docx`, `a.rtf`, `a.doc`; `false` para `a.jpg`, `a.xlsx`, `Léame.txt`, `registro_renombres_20261120-1010.csv`.
- `yearFromFolderName`: `"1991"` → 1991; `"Tomo 1"`, `"1991 bis"`, `"1800"` → `null`.

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/lib/conceptosPgn/rules.test.ts`
Expected: FAIL (no se puede resolver `./rules`).

- [ ] **Step 3: Implement `rules.ts`** con las firmas de arriba. `buildConceptName` = `` `CTO_PGN_${String(value).padStart(7, "0")}${letter}_${year}(C)${ext}` ``. `parseConceptInput` acepta `^\s*(\d+)\s*-?\s*([Aa])?\s*$`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/lib/conceptosPgn/rules.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/conceptosPgn/rules.ts frontend/src/lib/conceptosPgn/rules.test.ts
git commit -m "feat(laboratorio): reglas de nombre para Conceptos PGN"
```

---

### Task 2: Falso sistema de archivos modificable + análisis del lote

**Files:**
- Create: `frontend/src/lib/conceptosPgn/testFsMutable.ts` (solo pruebas)
- Create: `frontend/src/lib/conceptosPgn/analyze.ts`
- Test: `frontend/src/lib/conceptosPgn/analyze.test.ts`

**Interfaces:**
- Consumes: todo lo de Task 1.
- Produces:
  - `fakeMutableDirectory(name: string, entries: DirectoryEntries, options?: { supportsMove?: boolean; failMoveFor?: string[]; failWriteFor?: string[]; truncateWriteFor?: string[] }): { handle: FileSystemDirectoryHandle; snapshot(): Record<string, string> }`. `DirectoryEntries` se importa de `../formatter/testFsFakes`. Implementa `values`, `getDirectoryHandle`, `getFileHandle({create})`, `removeEntry`, `createWritable` (`write`/`close`/`abort`), `getFile`, `isSameEntry` y, si `supportsMove` (por defecto `true`), `move(newName)` en los archivos. Las opciones `fail*`/`truncate*` reciben nombres de archivo: `failMoveFor` hace que `move` lance error, `failWriteFor` hace que `write` del archivo **nuevo** con ese nombre lance error, y `truncateWriteFor` hace que escriba solo la mitad de los bytes. `snapshot()` devuelve `{ "1991/Tomo 1/x.pdf": "contenido" }`. `put(path: string, content: string): void` crea o reemplaza un archivo después de armado el fake (simula un cambio en disco entre el análisis y el renombre).
  - En `analyze.ts`:

```ts
export type ReviewReason = "no-number" | "no-year" | "year-mismatch" | "duplicate";
export interface ConceptEntry {
  path: string;                 // "1991/Tomo 1/Cto. 1654.pdf"
  folderPath: string;           // "1991/Tomo 1"
  filename: string;
  dirHandle: FileSystemDirectoryHandle;
  fileHandle: FileSystemFileHandle;
  year: number | null;          // año efectivo (nombre si existe, si no carpeta)
  number: ConceptNumber | null;
  finalName: string | null;     // null = conserva su nombre
  reason: ReviewReason | null;  // no-null = aparece en "Requieren tu revisión"
}
export interface CrossFolderRepeat { finalName: string; paths: string[] }
export interface ConceptPlan {
  rootName: string;
  rootHandle: FileSystemDirectoryHandle;
  entries: ConceptEntry[];
  crossFolderRepeats: CrossFolderRepeat[];
  photoOnlyFolders: string[];
}
export interface ManualFix { year: string; number: string }
export class ConceptPgnError extends Error {}
export async function analyzeConceptBatch(root: FileSystemDirectoryHandle): Promise<ConceptPlan>;
export function applyManualFixes(plan: ConceptPlan, fixes: Map<string, ManualFix>): ConceptPlan;
export function isRenamable(entry: ConceptEntry): boolean;      // finalName !== null && finalName !== filename && reason !== "duplicate"
export function isAlreadyFinal(entry: ConceptEntry): boolean;   // finalName === filename
```

Reglas (del spec):
- Recorrido recursivo a cualquier profundidad. Solo los documentos (`isDocument`) generan `ConceptEntry`. `folderYear` = `yearFromFolderName` del primer segmento de `folderPath`. Un documento en la raíz o bajo una carpeta que no es año → `reason: "no-year"`, `finalName: null`.
- Sin número → `"no-number"`. `nameYear` distinto de `folderYear` → `"year-mismatch"`, con `year = nameYear` y `finalName` calculado (cuenta como renombrable).
- Duplicados: dentro del mismo `folderPath`, dos entradas con el mismo `finalName` (comparado en minúsculas) → todas `"duplicate"`. La misma `finalName` en **carpetas distintas** → no bloquea, va a `crossFolderRepeats`.
- `photoOnlyFolders`: carpetas con al menos un `isImage` y ningún documento **directamente** en ellas.
- Sin ningún documento → `throw new ConceptPgnError("La carpeta no contiene ningún documento.")`.
- `applyManualFixes`: para cada `path` con fix, `parseConceptInput(fix.number)` y año = entero de `fix.year` si es `19xx`/`20xx`. Con ambos válidos se recalcula `finalName` y el motivo pasa a `null`, salvo que siga siendo `year-mismatch` respecto a la carpeta, que se conserva para que la fila no desaparezca de la tabla. Si no, `finalName: null` con el motivo original. Después se recalculan los duplicados como en el análisis. Igual que `formatter/analyze.ts` (`applyCorrections` → `markDuplicates`): devuelve un plan nuevo y no muta el anterior.

- [ ] **Step 1: Write the failing tests** en `analyze.test.ts`, con `fakeMutableDirectory`:
  - `"lee el año de la carpeta de primer nivel y conserva subcarpetas de concepto"`: `{ "1991": { "Tomo 1": { "Cto. 1654.pdf": "x" } }, "2007": { "Tomo 6 2007": { "CTO_PGN_0004360_2007": { "4360.pdf": "x" } } } }` → `finalName` `CTO_PGN_0001654_1991(C).pdf` y `CTO_PGN_0004360_2007(C).pdf`, ambos `reason: null`.
  - `"ignora fotos, excel, txt y csv, y reporta carpetas con solo fotos"`: raíz con `Léame.txt`, `Listado.xlsx`, `registro_renombres_20261120-1010.csv`; `2006/TOMO 10 2006/` con dos `.jpg`; `1998/Tomo 3/` con `Cto. 1540.pdf` y `pagina_233.jpg` → 1 entrada; `photoOnlyFolders` = `["2006/TOMO 10 2006"]`.
  - `"manda a revisión los Tomo sin número y el año distinto"`: `Tomo 3 1991-1-14.pdf` → `no-number`, `finalName: null`; `2009/Tomo 3/Concepto 4734 de 2008.pdf` → `year-mismatch`, `finalName` `CTO_PGN_0004734_2008(C).pdf`, `isRenamable` true.
  - `"documento fuera de una carpeta de año"` → `no-year`.
  - `"choque en la misma carpeta bloquea; entre tomos solo avisa"`: `1993/Tomo 4/{Cto. 257.pdf, Concepto 257 de 1993.pdf}` → ambos `duplicate`, `isRenamable` false; `1993/Tomo 4/Cto. 258.pdf` + `1993/Tomo 5/Cto. 258.pdf` → `reason: null` y un `crossFolderRepeats` con las dos rutas.
  - `"una segunda pasada no renombra nada"` (Review Focus 4): `1991/Tomo 1/CTO_PGN_0001654_1991(C).pdf` + el CSV en la raíz → 1 entrada, `isAlreadyFinal` true, `isRenamable` false.
  - `"corrección manual completa un Tomo y recalcula duplicados"`: `applyManualFixes` con `{ year: "1991", number: "1660" }` sobre `Tomo 3 1991-1-14.pdf`, en una carpeta donde ya existe `Cto. 1660.pdf` → los dos quedan `duplicate`. Con `"1661"` → `finalName` `CTO_PGN_0001661_1991(C).pdf`, `reason: null`, y el plan original sin cambios.
  - `"sin documentos lanza ConceptPgnError"`.

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/lib/conceptosPgn/analyze.test.ts`
Expected: FAIL (no se puede resolver `./analyze`).

- [ ] **Step 3: Implement `testFsMutable.ts` y `analyze.ts`** con las firmas de arriba.

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/lib/conceptosPgn/`
Expected: PASS (Task 1 + Task 2).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/conceptosPgn/
git commit -m "feat(laboratorio): análisis del lote de Conceptos PGN"
```

---

### Task 3: Renombre en el lugar + registro CSV

**Files:**
- Create: `frontend/src/lib/conceptosPgn/fileSystemMove.d.ts`: `interface FileSystemHandle { move?(newName: string): Promise<void> }` en `declare global`, con `export {}` como `formatter/fileSystemAccess.d.ts`.
- Create: `frontend/src/lib/conceptosPgn/renameInPlace.ts`
- Test: `frontend/src/lib/conceptosPgn/renameInPlace.test.ts`

**Interfaces:**
- Consumes: `ConceptPlan`, `ConceptEntry`, `isRenamable` (Task 2); `fakeMutableDirectory` (Task 2).
- Produces:

```ts
export interface RenameOutcome { path: string; from: string; to: string; renamed: boolean; skipReason?: string }
export interface RenameSummary { outcomes: RenameOutcome[]; logName: string; renamedCount: number; skippedCount: number }
export function logFileName(now: Date): string;   // "registro_renombres_20261120-0905.csv" (hora local)
export function buildLogCsv(rows: { path: string; from: string; to: string; result: string }[]): string;
export async function renameConcepts(
  plan: ConceptPlan,
  options?: { now?: Date; onProgress?: (done: number, total: number) => void }
): Promise<RenameSummary>;
```

Comportamiento, por cada entrada `isRenamable` y en orden:
1. Antes de empezar se escribe el CSV en `plan.rootHandle` con todas las filas y resultado `pendiente`.
2. Si el directorio ya tiene otra entrada cuyo nombre en minúsculas sea igual a `finalName` en minúsculas (y no es el archivo mismo) → `skipReason: "Ya existe un archivo con ese nombre en la carpeta"`.
3. Si `typeof fileHandle.move === "function"`: `await fileHandle.move(finalName)`. Si lanza error, pasa al paso 4 con ese mismo archivo.
4. Si `finalName` y `filename` difieren **solo en mayúsculas**, el camino alternativo no es seguro: en Windows, "crear" el destino abriría el mismo archivo y luego se borraría. Se salta con `skipReason: "Solo cambian mayúsculas; renómbralo a mano"`.
5. Camino alternativo: leer el original completo, `getFileHandle(finalName, { create: true })`, escribir, cerrar, volver a leer y comparar `size`. Solo si coincide se ejecuta `removeEntry(filename)`. Si algo falla después de crear el destino: `removeEntry(finalName)` (con el error ignorado), el original queda intacto y `skipReason: "No se pudo renombrar: <mensaje>"`. Si los tamaños no coinciden: `"La copia no quedó completa; el original no se tocó"`.
6. Un fallo nunca detiene el resto. Al final se reescribe el CSV con `renombrado` o `saltado: <motivo>`.

CSV: `"﻿"` + encabezado `ruta;nombre_anterior;nombre_nuevo;resultado`, líneas con `\r\n`. Los campos con `;`, `"` o salto de línea van entre comillas, con `"` duplicadas.

- [ ] **Step 1: Write the failing tests** en `renameInPlace.test.ts`, con un plan de `analyzeConceptBatch` sobre `fakeMutableDirectory` y `now = new Date(2026, 10, 20, 9, 5)`:
  - `"renombra con move cuando existe"`: `snapshot()` contiene `1991/Tomo 1/CTO_PGN_0001654_1991(C).pdf` con el contenido original y ya no contiene `Cto. 1654.pdf`; `renamedCount` 1.
  - `"usa copiar-verificar-borrar cuando no hay move"` (`supportsMove: false`): mismo resultado final.
  - `"si move falla, ese archivo cae al camino alternativo"` (`failMoveFor: ["Cto. 1654.pdf"]`): renombrado.
  - `"nunca sobrescribe un destino existente, sin importar mayúsculas"` (Review Focus 2): se analiza una carpeta con `Cto. 1654.pdf` (contenido "nuevo"). **Después** del análisis, `put("1991/Tomo 1/cto_pgn_0001654_1991(c).pdf", "viejo")`. Al renombrar: el archivo puesto sigue con "viejo", `Cto. 1654.pdf` sigue ahí y el motivo es `"Ya existe un archivo con ese nombre en la carpeta"`.
  - `"un cambio solo de mayúsculas sin move se salta"`: `supportsMove: false`, archivo `cto_pgn_0001654_1991(C).pdf` en `1991/Tomo 1` → `skipReason` `"Solo cambian mayúsculas; renómbralo a mano"` y el archivo intacto. Con `move` disponible, sí se renombra.
  - `"escritura fallida o incompleta deja el original intacto y sin restos"` (Review Focus 3): con `supportsMove: false` y `failWriteFor: ["CTO_PGN_0001654_1991(C).pdf"]`, y luego con `truncateWriteFor` → `snapshot()` idéntico al inicial salvo el CSV; `skippedCount` 1.
  - `"un fallo no detiene el resto"`: dos archivos y uno falla → el otro queda renombrado.
  - `"escribe el registro en la raíz"`: `snapshot()["registro_renombres_20261120-0905.csv"]` empieza con BOM, tiene encabezado y una fila `1991/Tomo 1/Cto. 1654.pdf;Cto. 1654.pdf;CTO_PGN_0001654_1991(C).pdf;renombrado`.
  - `"buildLogCsv cita campos con ; y comillas"`.

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/lib/conceptosPgn/renameInPlace.test.ts`
Expected: FAIL (no se puede resolver `./renameInPlace`).

- [ ] **Step 3: Implement `fileSystemMove.d.ts` y `renameInPlace.ts`** con las firmas de arriba.

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/lib/conceptosPgn/`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/conceptosPgn/
git commit -m "feat(laboratorio): renombre en el lugar con registro para Conceptos PGN"
```

---

### Task 4: Pantalla "Conceptos PGN" y pestaña del Laboratorio

**Files:**
- Create: `frontend/src/pages/formatter/ConceptosPgnPanel.tsx`
- Test: `frontend/src/pages/formatter/ConceptosPgnPanel.test.tsx`
- Modify: `frontend/src/pages/FormatterPage.tsx` (agregar `"conceptos-pgn"` a `Tab`, `TABS` con la etiqueta `"Conceptos PGN"` y `PanelActivo`)
- Modify: `frontend/src/pages/FormatterPage.test.tsx` (la prueba recorre también la cuarta pestaña)

**Interfaces:**
- Consumes: `analyzeConceptBatch`, `applyManualFixes`, `isRenamable`, `isAlreadyFinal`, `ConceptPgnError`, `ManualFix` (Task 2); `renameConcepts`, `RenameSummary` (Task 3). Estilos de tabla de `../../lib/tableStyles`, `Button`/`Input`/`ErrorBanner` como en `RenamePanel.tsx`.
- Produces: `export function ConceptosPgnPanel(): JSX.Element`.

Estados: `idle` | `unsupported` (sin `showDirectoryPicker`, mismo texto "necesita Chrome o Edge" que el RenamePanel) | `error` | `loaded` (plan + fixes) | `confirming` | `renaming` (done/total) | `done` (`RenameSummary`).

Contenido (los textos exactos quedan a criterio, salvo los citados, que usan las pruebas):
- Botón **"Elegir carpeta del lote"** → `showDirectoryPicker({ mode: "readwrite" })`.
- Resumen: `"{n} listos para renombrar"`, `"{n} ya tienen el nombre final"`, `"{n} requieren tu revisión"`, más un `<details>` "Ver todos (antes → después)" con la tabla de los renombrables.
- Tabla **"Requieren tu revisión"**: archivo, motivo (`no-number` "Sin número", `no-year` "Sin año", `year-mismatch` "Año distinto a la carpeta", `duplicate` "Nombre repetido en la carpeta"), casillas Año y Número (rellenas con lo detectado, `aria-label` `"Año de {ruta}"` / `"Número de {ruta}"`), nombre nuevo o "(queda igual)", y botón **"Ver"** solo en PDFs. "Ver" muestra al lado un `<iframe title="Primera página de {archivo}">` con `URL.createObjectURL(await fileHandle.getFile()) + "#page=1"`. La URL se revoca al cerrar o cambiar de archivo.
- Avisos en `<details>`: `"{n} números aparecen en más de un tomo"` (lista de rutas) y `"{n} carpetas tienen solo fotos, sin documento"`.
- Botón **"Renombrar {n} archivos"** (deshabilitado si n = 0) → estado `confirming`, que muestra: "Esto cambia los nombres de los archivos originales y no se puede deshacer desde aquí. Se guardará un registro en la carpeta raíz del lote." con botones **"Sí, renombrar"** y **"Cancelar"**.
- Progreso `"{done} / {total}"`. Resultado: `"{n} renombrados"`, `"{n} saltados"` con la lista de motivos, y la línea `"Registro guardado en {logName}. Retíralo antes de subir a Azure si no quieres que se suba."`

- [ ] **Step 1: Write the failing tests** en `ConceptosPgnPanel.test.tsx` (patrón de `RenamePanel.test.tsx`: `vi.stubGlobal("showDirectoryPicker", …)`, con `fakeMutableDirectory`):
  - `"muestra el resumen del lote"`: 2 listos + 1 Tomo → textos `2 listos para renombrar` y `1 requieren tu revisión`; el botón `Renombrar 2 archivos` está habilitado.
  - `"pide confirmación y renombra"`: clic en `Renombrar 2 archivos`, luego `Sí, renombrar` → `2 renombrados`, `snapshot()` con los nombres nuevos y `Registro guardado en registro_renombres_`.
  - `"cancelar no toca nada"`: después de `Cancelar`, `snapshot()` sigue igual al inicial.
  - `"escribir el número de un Tomo lo suma a los renombrables"`: escribir `1661` en `Número de 1991/Tomo 3/Tomo 3 1991-1-14.pdf` → `Renombrar 3 archivos`.
  - `"Ver muestra la primera página"`: con `URL.createObjectURL` simulado (`vi.fn(() => "blob:x")`), clic en `Ver` → existe un iframe con título `Primera página de Tomo 3 1991-1-14.pdf` y `src` `blob:x#page=1`.
  - `FormatterPage.test.tsx`: clic en la pestaña `Conceptos PGN` → aparece `Elegir carpeta del lote`.

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/pages/formatter/ConceptosPgnPanel.test.tsx src/pages/FormatterPage.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement `ConceptosPgnPanel.tsx` y el cambio en `FormatterPage.tsx`.**

- [ ] **Step 4: Run all frontend checks**

Run: `cd frontend && npm test && npm run lint && npm run build`
Expected: todo PASS, sin errores de lint ni de tipos. Las pruebas existentes del Renombrado, la Reorganización y Decretos Cali siguen pasando sin cambios.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/formatter/ConceptosPgnPanel.tsx frontend/src/pages/formatter/ConceptosPgnPanel.test.tsx frontend/src/pages/FormatterPage.tsx frontend/src/pages/FormatterPage.test.tsx
git commit -m "feat(laboratorio): pestaña Conceptos PGN"
```

---

### Task 5: Verificación en Chrome real

Sin código nuevo. Se valida lo que las pruebas automáticas no pueden: el `move()` real de Chrome, el visor de PDF dentro del iframe y el registro en disco.

- [ ] **Step 1: Armar una carpeta de prueba** en el scratchpad con la estructura real: `1991/Tomo 1/{Cto. 1654.pdf, Cto. NN 1.pdf}`, `1991/Tomo 3/Tomo 3 1991-1-14.pdf`, `2009/Tomo 3/Concepto 4734 de 2008.pdf`, `2007/Tomo 6 2007/CTO_PGN_0004360_2007/4360.pdf`, `2006/TOMO 10 2006/foto.jpg` y `Léame.txt`. Los PDFs deben ser reales de una página (se pueden generar con `reportlab`, que ya es dependencia del backend).
- [ ] **Step 2: Levantar la app** con la skill `run-iurisync`, entrar como admin, abrir Laboratorio → Conceptos PGN y elegir la carpeta. Verificar: 4 listos, 1 Tomo en revisión, 1 año distinto, el aviso de la carpeta con solo fotos, y que "Ver" muestra la primera página del Tomo.
- [ ] **Step 3: Escribir un número para el Tomo y renombrar.** En disco: nombres nuevos, la foto y `Léame.txt` intactos, la subcarpeta `CTO_PGN_0004360_2007` sin renombrar y el CSV en la raíz (abrirlo y comprobar las tildes). Anotar en el PR si Chrome usó `move()` o el camino alternativo (un `console.debug` temporal o el panel de rendimiento; no dejar logs en el código).
- [ ] **Step 4: Correr la herramienta otra vez** sobre la misma carpeta: todo aparece como "ya tienen el nombre final" y el botón de renombrar queda deshabilitado.
