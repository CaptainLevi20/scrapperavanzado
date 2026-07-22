# Formateador v2: carpeta a carpeta — Diseño

Fecha: 2026-07-22

## Contexto y objetivo

La primera versión del Formateador (ver `2026-07-22-formateador-design.md`) subía un `.zip` completo a memoria del navegador vía `JSZip` y descargaba un `.zip` de salida. Al probarlo con un lote real ("Acuerdos de Cali", 2131 archivos, 2.3 GiB) se confirmaron dos límites reales de ese enfoque:

1. Un archivo de más de ~2 GiB dispara `NotReadableError` al leerlo con la File API del navegador — un límite conocido de Chrome, no un bug de la lógica de renombrado.
2. Aunque se evite el límite de lectura (dividiendo el `.zip` de entrada), producir un `.zip` de salida de tamaño similar tiene el mismo riesgo del lado de la escritura — dividir no resuelve el problema, solo lo mueve.

El usuario necesita procesar lotes sin techo de tamaño (potencialmente 10 GiB o más) sin tener que subdividir manualmente. Este diseño reemplaza por completo el mecanismo de entrada/salida: en vez de comprimir todo en un `.zip` y cargarlo entero en memoria, se usa la **File System Access API** para leer una carpeta de entrada y escribir directamente en una carpeta de salida, archivo por archivo, en streaming — sin que el lote completo pase nunca por la memoria del navegador de una sola vez. El límite pasa a ser el disco, no la RAM de la pestaña.

Decisión explícita del usuario: esto **reemplaza** el flujo de `.zip` (no convive con él) y se acepta que solo funcione en navegadores basados en Chromium (Chrome, Edge) — Firefox y Safari no implementan `showDirectoryPicker`.

Explícitamente en alcance:
- Botón "Elegir carpeta de entrada" → `window.showDirectoryPicker()`. Se recorre la carpeta (subcarpetas por año + sus archivos) leyendo solo **nombres**, nunca contenido, para construir el mismo plan de renombrado que ya existe (detección de tipo/ciudad, año, número, excepciones, colisiones).
- Misma pantalla de revisión que ya existe: excepciones editables, botón deshabilitado hasta resolverlas.
- Botón "Elegir carpeta de salida" → segundo `showDirectoryPicker({ mode: "readwrite" })`, carpeta separada de la de entrada (nunca se modifica el origen).
- Copia en streaming, archivo por archivo, a la carpeta de salida, recreando `AÑO/archivo_renombrado.ext`, con indicador de progreso ("Copiando N / M").
- Guard de compatibilidad: si el navegador no soporta `showDirectoryPicker`, se muestra un mensaje claro en vez de romper.
- Un archivo que falle al copiarse se cuenta como omitido y no aborta el resto del lote (mismo espíritu que la v1).

Explícitamente fuera de alcance:
- Mantener el flujo de subir/descargar `.zip` como alternativa — se elimina por completo, junto con la dependencia `jszip`.
- Soporte para Firefox/Safari (aceptado explícitamente por el usuario).
- Reanudar una copia interrumpida a mitad de camino, o saltar archivos ya copiados en una corrida anterior.
- Permisos persistentes entre sesiones (cada corrida vuelve a pedir las carpetas; no hay nada que persistir, igual que en v1).

## Motor de reglas — sin cambios

`frontend/src/lib/formatter/rules.ts` y `rules.test.ts` quedan **intactos**: son funciones puras sobre texto (`detectConfig`, `extractYear`, `extractNumber`, `padNumber`, `fileExtension`, `buildFileName`) — no les importa si el nombre vino de una entrada de zip o de un `FileSystemHandle`.

## Lectura de la carpeta de entrada

Se reemplaza `analyzeZip(file: File)` por `analyzeDirectory(root: FileSystemDirectoryHandle)` dentro de `frontend/src/lib/formatter/analyze.ts`. El resto del archivo (`computeFinalName`, `markDuplicates`, `applyCorrections`, `recomputeReasons`, `parsePositiveInt`, `FormatterError`, `Correction`) se conserva sin cambios de comportamiento.

`FormatterEntry` gana un campo nuevo:

```ts
export interface FormatterEntry {
  path: string;                  // ruta relativa para mostrar/identificar, ej. "ACUERDOS 1962/Acuerdo 0005.pdf"
  yearFolder: string;
  filename: string;
  fileHandle: FileSystemFileHandle; // para leer el contenido real solo al momento de copiar
  detectedYear: number | null;
  detectedNumber: number | null;
  reason: FormatterReason | null;
}
```

`analyzeDirectory`:

1. `rootFolderName = root.name` — directo, sin ambigüedad (ya no existe el problema de "carpeta compartida vs. nombre del .zip" de la v1, porque la carpeta elegida por el usuario **es** la raíz).
2. Recorre `root.values()` (iterador async de `FileSystemHandle`; el orden de iteración no está garantizado por la especificación y no importa para el resultado, ya que el plan se construye completo antes de mostrarse):
   - Si la entrada es un archivo directamente en `root` (sin carpeta de año): se agrega como excepción `"no-year"` con `yearFolder: ""`, igual que el caso equivalente en v1.
   - Si la entrada es una subcarpeta (carpeta de año): recorre `entry.values()` una vez más; cada archivo dentro se agrega como `FormatterEntry` con `yearFolder = entry.name`.
   - No se recorre más de dos niveles de profundidad (mismo alcance que v1: carpeta ráiz → carpeta de año → archivos).
3. Si no se encontró ningún archivo en todo el recorrido: `FormatterError("La carpeta no contiene ningún archivo.")`.
4. Igual que el fix ya aplicado en v1: la detección de tipo/ciudad busca en `rootFolderName` **y** en cada nombre de carpeta de año distinto (`detectConfig([rootFolderName, ...yearFolderNames].join(" "))`), no solo en `rootFolderName` — sigue siendo necesario porque una carpeta de entrada puede llamarse igual que en el caso real ya visto ("CALI 2026", sin la palabra "Acuerdo"), mientras que las subcarpetas sí la traen ("ACUERDOS 1962").
5. Año/número por archivo: exactamente la misma lógica que v1 (`extractYear(yearFolder)`, `extractNumber(filename, year)`), y la misma detección de colisiones vía `markDuplicates`.

## Copiado a la carpeta de salida

Nuevo archivo `frontend/src/lib/formatter/copy.ts`, reemplaza `build.ts` (que se elimina junto con `build.test.ts`):

```ts
export interface CopyResult {
  copiedCount: number;
  skippedCount: number;
}

export async function copyFormattedFiles(
  outputRoot: FileSystemDirectoryHandle,
  plan: FormatterPlan,
  resolvedNames: Map<string, string>,
  onProgress?: (done: number, total: number) => void
): Promise<CopyResult>;
```

Por cada `FormatterEntry` con nombre final resuelto (mismo criterio que v1: `resolvedNames.get(entry.path)`):

1. `yearDirHandle = entry.yearFolder ? await outputRoot.getDirectoryHandle(entry.yearFolder, { create: true }) : outputRoot` — recrea la carpeta de año en el destino (o escribe directo en la raíz si el archivo no tenía carpeta de año, igual que el guard `entry.yearFolder ? ... : finalName` que ya existe en `build.ts`).
2. `outFileHandle = await yearDirHandle.getFileHandle(finalName, { create: true })`.
3. `writable = await outFileHandle.createWritable()`; se lee el archivo de origen completo a memoria (`await (await entry.fileHandle.getFile()).arrayBuffer()`) y se escribe con `await writable.write(buffer)` seguido de `await writable.close()`. (`File.stream()` no está soportado por el entorno de test — jsdom — así que se usa `arrayBuffer()`, que sí lo está; esto ya resuelve el problema real, porque el límite de memoria pasa a ser **un archivo a la vez**, no el lote completo — para documentos individuales de tamaño normal, mucho más chico que el lote entero, esto es holgado.)
4. Cualquier error en esos pasos para un archivo puntual: se cuenta en `skippedCount`, se continúa con el siguiente (no aborta el lote — mismo comportamiento que v1's manejo de errores por archivo).
5. `onProgress?.(done, total)` después de cada archivo (copiado u omitido), para que la página pueda mostrar progreso sin tener que esperar a que termine todo el lote.

## Componente de página

`frontend/src/pages/FormatterPage.tsx` cambia su máquina de estados: ya no guarda un `JSZip` en memoria, sino que las referencias a los archivos viven dentro de cada `FormatterEntry.fileHandle`.

```ts
type FormatterState =
  | { step: "idle"; notice?: string }
  | { step: "unsupported" }
  | { step: "error"; message: string }
  | { step: "loaded"; plan: FormatterPlan; corrections: Map<string, Correction> }
  | { step: "copying"; done: number; total: number };
```

- Al montar: si `!("showDirectoryPicker" in window)`, el estado inicial es `"unsupported"` en vez de `"idle"` — se muestra un `ErrorBanner` fijo ("Esta función necesita Chrome o Edge; tu navegador actual no es compatible.") sin botón de reintentar, y no se renderiza ningún control de carpeta.
- **idle**: botón "Elegir carpeta de entrada" → `window.showDirectoryPicker()` → `analyzeDirectory(handle)`. Igual que v1, un `FormatterError` capturado muestra su mensaje; cualquier otro error (incluido que el usuario cierre el diálogo sin elegir nada — `showDirectoryPicker` rechaza con `AbortError` en ese caso) vuelve a `"idle"` sin mostrar error, ya que cancelar el diálogo no es un fallo.
- **loaded**: **misma tabla de revisión que v1**, sin cambios — `visibleRows`/`pending`/`canDownload` derivados de `applyCorrections` igual que hoy, con el fix ya aplicado (filas estables durante ediciones de varios dígitos). Solo cambia el botón final: "Elegir carpeta de salida y copiar" en vez de "Descargar ZIP".
- Al confirmar: `window.showDirectoryPicker({ mode: "readwrite" })` para la carpeta de salida → `step: "copying"` → `copyFormattedFiles(outputHandle, resolvedPlan, resolvedNames, onProgress)`. El callback de progreso actualiza el estado solo cada 20 archivos (o al llegar al total), para no forzar miles de renders en lotes grandes.
- Al terminar: vuelve a `"idle"` con un `notice` resumen ("2131 archivos copiados." o "2129 copiados, 2 omitidos por error de lectura." si `skippedCount > 0`), igual que el resumen que ya existía en v1 para `skippedCount`.
- Cancelar cualquiera de los dos diálogos de carpeta (`AbortError`) no debe mostrarse como error — vuelve al estado anterior sin cambios.

## Manejo de errores

- **Navegador sin soporte**: guard fijo al montar, descrito arriba.
- **Carpeta de entrada vacía**: `FormatterError("La carpeta no contiene ningún archivo.")`.
- **Tipo/ciudad no reconocidos**: mismo mensaje que v1, bloqueante.
- **Cancelar el picker de entrada o salida**: no es un error, vuelve al estado anterior.
- **Archivo individual no legible o no escribible durante la copia**: se cuenta en `skippedCount`, no aborta el resto — mismo espíritu que v1.

## Testing

`showDirectoryPicker`, `FileSystemDirectoryHandle` y `FileSystemFileHandle` no existen en jsdom (el entorno de los tests). Se agregan fakes mínimos de solo lectura/escritura en memoria en un helper de test compartido (`frontend/src/lib/formatter/testFsFakes.ts`, usado por `analyze.test.ts`, `copy.test.ts` y `FormatterPage.test.tsx`):

- `fakeFileHandle(name, content)`: implementa `.getFile()` devolviendo un `File` real de jsdom.
- `fakeDirectoryHandle(name, entries)`: implementa `.values()` (iterador async), `.getDirectoryHandle(name, opts)`, `.getFileHandle(name, opts)` — con creación real de sub-handles en memoria para que `copyFormattedFiles` pueda verificarse escribiendo a un `fakeDirectoryHandle` de salida y luego inspeccionando su estructura interna.

Casos a cubrir (equivalentes a los que ya existían para la versión zip, adaptados):
- `analyze.test.ts`: carpeta con años válidos, año sin detectar, número sin detectar, colisión, detección de tipo/ciudad vía nombres de carpeta de año cuando el nombre de la carpeta raíz no alcanza (mismo caso real ya cubierto en v1), carpeta vacía.
- `copy.test.ts`: copia exitosa preservando `AÑO/archivo` en el handle de salida, conteo de omitidos cuando un archivo falla al leerse, progreso reportado correctamente.
- `FormatterPage.test.tsx`: flujo sin excepciones, flujo con corrección de varios dígitos (mismo caso que el fix ya verificado en v1), mensaje de navegador no soportado cuando `showDirectoryPicker` no existe en `window`, cancelar el picker de entrada no muestra error.

## Dependencias

- Se **elimina** `jszip` de `frontend/package.json` (deja de usarse en todo el módulo).
- No se agrega ninguna dependencia nueva — la File System Access API es nativa del navegador.
