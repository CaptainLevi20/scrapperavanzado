# Formateador — Diseño

Fecha: 2026-07-22

## Contexto y objetivo

Existen lotes de documentos (por ahora, "Acuerdos de Cali") guardados en carpetas cuyos nombres de archivo no siguen ninguna convención fija. Se necesita una sección nueva, "Formateador", donde el usuario suba un ZIP con esa estructura y reciba de vuelta un ZIP con los mismos archivos renombrados según una convención fija: `{TIPO}_{CIUDAD}_{NUMERO}_{AÑO}.{ext}` (ej. `A_CONCALI_0001_1962.pdf`).

Esta funcionalidad es independiente del dominio de scraping/documentos del resto de la app: no persiste nada, no toca la base de datos ni el almacenamiento (MinIO), y no requiere que el usuario llene ningún formulario de configuración — el tipo de documento y el código de ciudad se detectan automáticamente a partir de los nombres de carpeta dentro del propio ZIP.

Explícitamente en alcance:
- Subir un archivo `.zip` con una carpeta raíz que contiene subcarpetas por año, cada una con los documentos de ese año.
- Detección automática de tipo de documento y código de ciudad a partir del nombre de la carpeta raíz (por ahora: `acuerdo` → `A`, `cali` → `CONCALI`).
- Extracción automática de año (desde el nombre de cada subcarpeta) y número de acuerdo (desde el nombre de cada archivo).
- Pantalla de revisión para los pocos archivos donde el año o el número no se pudieron determinar automáticamente, o donde dos archivos calcularon el mismo nombre final (colisión).
- Descarga de un ZIP nuevo con la misma estructura de carpetas por año, con los archivos renombrados.
- Todo el procesamiento ocurre en el navegador (sin backend); nada se sube ni se guarda en el servidor.

Explícitamente fuera de alcance:
- Configurar manualmente el tipo de documento o el código de ciudad — si no se detectan por palabras clave, el proceso se detiene con un error explicativo en vez de adivinar.
- Persistir el ZIP subido, el resultado, o un historial de formateos (a diferencia de "Descargas masivas", aquí no hay nada que listar después).
- Soportar más de un nivel de subcarpetas, o carpetas de año anidadas de forma irregular.
- Tipos de documento o ciudades más allá de `acuerdo`/`cali` en esta iteración (se agregan extendiendo los mapas de palabras clave cuando aparezca un caso real).

## Motor de reglas (funciones puras)

Nuevo módulo `frontend/src/lib/formatter/rules.ts`, sin dependencias de IO — todas sus funciones son puras y se prueban directamente con vitest.

```ts
export interface FormatterConfig {
  typeCode: string; // "A"
  cityCode: string; // "CONCALI"
}

const TYPE_KEYWORDS: Record<string, string> = { acuerdo: "A" };
const CITY_KEYWORDS: Record<string, string> = { cali: "CONCALI" };

export function detectConfig(rootFolderName: string): FormatterConfig | null;
export function extractYear(folderName: string): number | null;
export function extractNumber(filename: string, year: number | null): number | null;
export function padNumber(n: number): string; // rellena a mínimo 4 dígitos
export function fileExtension(filename: string): string; // incluye el punto, o "" si no hay
export function buildFileName(config: FormatterConfig, number: number, year: number, ext: string): string;
```

- `detectConfig`: normaliza a minúsculas sin acentos, busca la primera palabra clave de `TYPE_KEYWORDS` y la primera de `CITY_KEYWORDS` presentes en el nombre. Si falta cualquiera de las dos, retorna `null`.
- `extractYear`: busca el primer número de 4 dígitos plausible como año (`/\b(1[89]\d{2}|20\d{2})\b/`) en el nombre de la carpeta.
- `extractNumber`: recorre todos los números (`/\d+/g`) del nombre de archivo en orden de aparición y retorna el primero que **no** sea igual a `year` (si `year` es `null`, retorna el primero que aparezca). Si no hay ninguno, `null`.
- `padNumber`: `String(n).padStart(4, "0")` — si `n` ya tiene más de 4 dígitos, se deja tal cual.
- `buildFileName`: `` `${config.typeCode}_${config.cityCode}_${padNumber(number)}_${year}${ext}` ``.

## Lectura del ZIP y agrupación por carpeta de año

Nuevo módulo `frontend/src/lib/formatter/analyze.ts`, que usa `JSZip` para leer el archivo subido y arma el plan de renombrado.

1. Cargar el `.zip` con `JSZip.loadAsync(file)`. Si falla (no es un zip válido), se propaga como error para que la página muestre un banner.
2. Tomar todas las entradas que no son directorio (`!entry.dir`). Si no hay ninguna, es un "zip vacío" (se maneja como error de estado, ver más abajo).
3. Determinar la carpeta raíz:
   - Si **todas** las entradas comparten el mismo primer segmento de ruta (ej. `Acuerdos Cali/...`), ese segmento es la carpeta raíz y el segundo segmento de cada ruta es su carpeta de año.
   - Si no comparten un único primer segmento (el zip se generó desde dentro de la carpeta, sin envoltorio), se usa el nombre del archivo `.zip` subido (sin extensión) como carpeta raíz "virtual", y el primer segmento de cada ruta pasa a ser la carpeta de año.
   - Cualquier archivo que no tenga al menos un segmento de carpeta de año antes de su nombre (es decir, que quede directamente en la raíz) se marca como excepción `"no-year"` con `detectedYear: null`.
4. `detectConfig(rootFolderName)`. Si retorna `null`, el análisis se corta ahí: la página muestra un error bloqueante ("No se reconoce el tipo de documento o la ciudad en «{rootFolderName}»") y no se genera ningún plan ni pantalla de revisión.
5. Para cada archivo, con su carpeta de año:
   - `year = extractYear(yearFolderName)`. Si es `null` → excepción `"no-year"`.
   - `number = extractNumber(filename, year)`. Si es `null` → excepción `"no-number"` (con el `year` ya detectado, si lo hay).
   - Si ambos se determinaron, el nombre final es `buildFileName(config, number, year, fileExtension(filename))`.
6. Colisiones: agrupar todos los archivos que sí obtuvieron nombre final por ese nombre; cualquier grupo con más de un archivo pasa **todos sus miembros** a excepción `"duplicate"` (se les preserva su `detectedYear`/`detectedNumber` como valor inicial editable, ya que el problema es la coincidencia, no la extracción en sí).

Resultado del análisis:

```ts
export interface FormatterEntry {
  path: string;              // ruta original completa dentro del zip
  yearFolder: string;
  filename: string;
  detectedYear: number | null;
  detectedNumber: number | null;
  reason: "no-year" | "no-number" | "duplicate" | null; // null = sin problema
}

export interface FormatterPlan {
  config: FormatterConfig;
  rootFolderName: string;
  entries: FormatterEntry[];
}

export function analyzeZip(file: File): Promise<FormatterPlan>; // o lanza si el zip es inválido o detectConfig da null
```

## Pantalla de revisión y generación del resultado

`FormatterEntry[]` con `reason !== null` son las **excepciones**; el resto están listos tal cual.

- Cada excepción se muestra en una fila editable con dos campos numéricos: Año y Número, prellenados con `detectedYear`/`detectedNumber` cuando existan (vacíos si no). El botón "Descargar ZIP" permanece deshabilitado mientras cualquier fila tenga un campo vacío o inválido.
- Tras cada edición se recalculan los nombres finales de **todas** las entradas (excepciones corregidas + entradas ya listas) y se vuelve a correr la detección de colisiones sobre el conjunto completo; si una corrección genera una colisión nueva, esa fila (y la que choca con ella) se marcan visualmente sin bloquear la edición de las demás.
- Si `entries.filter(e => e.reason !== null).length === 0` tras el análisis inicial, la pantalla de revisión se omite: se muestra directamente un resumen ("N archivos listos") y el botón de descarga ya habilitado.

Generación del ZIP final (`frontend/src/lib/formatter/build.ts`):

```ts
export function buildFormattedZip(zip: JSZip, plan: FormatterPlan, resolvedNames: Map<string, string>): Promise<Blob>;
```

Recorre cada `FormatterEntry`, lee su contenido del `JSZip` original (`zip.file(entry.path).async("blob")`) y lo agrega al nuevo `JSZip` bajo `${entry.yearFolder}/${resolvedNames.get(entry.path)}`, preservando la agrupación por año. Al final, `newZip.generateAsync({ type: "blob" })` y se descarga con el `downloadBlob` que ya existe en `frontend/src/api/documents.ts`, con el nombre `Formateador_${rootFolderName}.zip`.

## Componente de página

Nueva página `frontend/src/pages/FormatterPage.tsx`, ruta `/formateador`, agregada a `AppLayout`/`App.tsx` y a `LINKS` en `Sidebar.tsx` (ícono `Wand2` de lucide-react, o similar).

Estado local con una máquina de estados simple:

```ts
type FormatterState =
  | { step: "idle" }
  | { step: "error"; message: string }
  | { step: "review"; plan: FormatterPlan; zip: JSZip; corrections: Map<string, { year: string; number: string }> }
  | { step: "ready"; plan: FormatterPlan; zip: JSZip }
  | { step: "building" }
```

- **idle**: input de archivo (`<input type="file" accept=".zip">`, también con drag-and-drop) con instrucciones breves. Al seleccionar, se llama `analyzeZip`.
- Si `analyzeZip` lanza (zip inválido, zip vacío, o `detectConfig` retornó `null`): `step: "error"` con el mensaje correspondiente y un botón para intentar de nuevo.
- Si hay excepciones: `step: "review"` — tabla de excepciones editable como se describió arriba.
- Si no hay excepciones: `step: "ready"` — resumen y botón de descarga directo.
- Al confirmar (desde `review` con todas las filas válidas, o directo desde `ready`): `step: "building"` mientras se llama `buildFormattedZip` y se dispara la descarga; luego vuelve a `step: "idle"` para permitir formatear otro lote.

No requiere ningún cambio en `api/client.ts` ni nuevas llamadas de red — toda la lógica vive en `lib/formatter/*` y el componente.

## Manejo de errores

- **ZIP inválido** (no es un archivo zip real): mensaje "El archivo seleccionado no es un ZIP válido."
- **ZIP vacío** (sin archivos): mensaje "El ZIP no contiene ningún archivo."
- **Tipo/ciudad no reconocidos**: mensaje bloqueante indicando el nombre de carpeta que no se pudo interpretar, sin generar plan.
- **Archivo individual no legible dentro del zip** (raro, pero `JSZip` puede fallar por entrada corrupta): se excluye del plan y se cuenta aparte, mostrado en el resumen ("1 archivo omitido por error de lectura"), sin abortar el resto — mismo espíritu que el manejo de fallos individuales en "Descargas masivas".

## Testing

- `lib/formatter/rules.test.ts`: casos de `detectConfig` (con/sin palabras clave, mayúsculas/acentos), `extractYear` (año presente, ausente, folder sin números), `extractNumber` (número presente distinto del año, número igual al año se ignora y sigue buscando, sin números), `padNumber`, `buildFileName`.
- `lib/formatter/analyze.test.ts`: construye ZIPs de prueba en memoria con `JSZip` (carpeta envuelta vs. sin envolver, subcarpetas de año con y sin año detectable, archivos con y sin número, dos archivos que colisionan) y verifica el `FormatterPlan` resultante.
- `lib/formatter/build.test.ts`: dado un plan ya resuelto (sin excepciones pendientes), verifica que el ZIP generado contiene las entradas esperadas bajo `AÑO/nombre_final.ext`.
- `pages/FormatterPage.test.tsx`: dos flujos con un ZIP de prueba construido con `JSZip` en el propio test — (1) sin excepciones: sube el archivo, aparece el resumen, el botón de descarga está habilitado; (2) con excepciones: sube el archivo, aparece la tabla de revisión, el botón permanece deshabilitado hasta llenar los campos, y se habilita al completarlos.

## Dependencias nuevas

- `jszip` (`^3.10.1`) en `frontend/package.json` — única dependencia nueva, sin contraparte de tipos separada (trae sus propios tipos TS).
