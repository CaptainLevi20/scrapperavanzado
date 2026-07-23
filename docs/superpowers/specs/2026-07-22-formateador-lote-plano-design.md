# Formateador: soporte para lotes planos (sin subcarpetas por año) — Diseño

Fecha: 2026-07-22

## Contexto y objetivo

El Formateador (v2, carpeta a carpeta) fue construido y probado contra un único lote real: "Acuerdos de Cali", organizado en subcarpetas por año (`ACUERDOS 1962/`, `ACUERDOS 1963/`, ...). Al revisar el texto de la pantalla inicial, se detectaron dos supuestos implícitos que no se cumplirán necesariamente en lotes futuros:

1. **Tipo/ciudad están limitados a un diccionario de palabras clave** (`acuerdo`→`A`, `cali`→`CONCALI` en `rules.ts`). Confirmado con el usuario: esto se queda como está por ahora — es una lista escalable (agregar un tipo o ciudad nuevo es una línea en el diccionario, sin tocar la lógica de detección), y ampliarla no es parte de este diseño.
2. **Un archivo directamente en la carpeta raíz (sin subcarpeta de año) siempre se marca `"no-year"`** y bloquea la copia hasta corregirlo a mano. Esto tiene sentido cuando es la excepción dentro de un lote organizado por año (probablemente un archivo mal ubicado por error), pero es un mal comportamiento por defecto para un lote que **nunca** tuvo subcarpetas — cada archivo del lote terminaría bloqueando la copia.

Este diseño resuelve el punto 2: cuando una carpeta de entrada no tiene **ninguna** subcarpeta, el Formateador debe funcionar igual de bien que con el caso ya soportado, extrayendo el año de cada archivo desde su propio nombre en vez de desde una carpeta de año que nunca existió.

Explícitamente en alcance:
- Detectar si el lote es "organizado por año" (tiene al menos una subcarpeta) o "plano" (ninguna subcarpeta) al recorrer la carpeta raíz.
- En un lote plano, extraer el año de cada archivo desde su propio nombre (reutilizando `extractYear`, ya genérico sobre cualquier string).
- En un lote plano, la detección de tipo/ciudad también busca en los nombres de archivo (además del nombre de la carpeta raíz), ya que no hay subcarpetas de las que tomar prestada esa información.
- En la salida, los archivos de un lote plano se siguen organizando en carpetas por año (ej. `1962/archivo_renombrado.ext`), derivadas del año detectado en el nombre — no se aplanan en la salida solo porque la entrada era plana.
- Un archivo de un lote plano sin año detectable en su nombre sigue yendo a revisión manual (no se inventa nada).

Explícitamente fuera de alcance:
- Ampliar `TYPE_KEYWORDS`/`CITY_KEYWORDS` — confirmado que se queda igual por ahora.
- Aplicar la extracción de año "desde el nombre del archivo" como respaldo cuando SÍ hay subcarpeta pero su nombre no trae un año parseable — ese caso sigue sin cambios (`"no-year"`, revisión manual), para no ampliar el alcance más allá de lo pedido.
- Un lote **mixto** (con subcarpetas de año Y además un archivo suelto en la raíz) — el archivo suelto sigue marcado `"no-year"` para revisión manual, porque ahí es más probable que sea un archivo mal ubicado por error que un lote genuinamente plano. La detección de "lote plano" es binaria: si existe *cualquier* subcarpeta en la raíz, el lote entero se trata como organizado por año, y solo los archivos sueltos (fuera de esas subcarpetas) siguen el comportamiento actual sin cambios.

## Cambios en `analyzeDirectory` (`frontend/src/lib/formatter/analyze.ts`)

Durante el recorrido de `root.values()`, se registra si apareció alguna entrada de tipo `"directory"`:

```ts
let hasYearFolders = false;
// ...dentro del for await:
if (handle.kind === "file") { /* como ya existe */ continue; }
hasYearFolders = true;
// ...resto del recorrido de subcarpeta como ya existe
```

**Detección de tipo/ciudad**: el texto de búsqueda cambia según la estructura detectada:

```ts
const detectionText = hasYearFolders
  ? [rootFolderName, ...yearFolderNames].join(" ")   // comportamiento actual, sin cambios
  : [rootFolderName, ...rawEntries.map((e) => e.filename)].join(" ");  // lote plano: suma los nombres de archivo
```

**Construcción de cada `FormatterEntry`** para una entrada con `yearFolder === ""` (archivo directo en la raíz):

- Si `hasYearFolders` es `false` (lote genuinamente plano): `detectedYear = extractYear(filename)`; si se encontró, `detectedNumber = extractNumber(filename, detectedYear)`; y el campo `yearFolder` de la entrada pasa a ser el año detectado como string (ej. `"1962"`), para que la carpeta de salida se derive de ahí. Si no se encontró año en el nombre, `detectedYear`/`detectedNumber` quedan en `null` y la entrada sigue el camino normal hacia `"no-year"` vía `recomputeReasons` (sin cambios en esa función).
- Si `hasYearFolders` es `true` (lote mixto, este archivo es la excepción): comportamiento actual sin cambios — `detectedYear`/`detectedNumber` en `null`, `yearFolder` se queda en `""`, termina en `"no-year"`.

El resto de `analyzeDirectory` (extracción para archivos dentro de una subcarpeta de año, validación de carpeta vacía, `markDuplicates`) no cambia.

## Manejo de errores

Sin cambios respecto al comportamiento ya existente — un lote plano donde ni el nombre de la carpeta raíz ni ningún nombre de archivo traen las palabras clave de tipo/ciudad sigue terminando en el mismo `FormatterError` ya definido ("No se reconoce el tipo de documento o la ciudad..."). Un archivo sin año detectable en un lote plano sigue yendo a revisión manual igual que cualquier otro `"no-year"`.

## Testing

Nuevos casos en `frontend/src/lib/formatter/analyze.test.ts` (usando `fakeInputDirectory` de Task 1, ya existente):

- Lote plano donde cada archivo trae su año en el propio nombre: confirma `detectedYear`/`detectedNumber` correctos y que la entrada resultante no necesita revisión (`reason === null`).
- Lote plano donde el nombre de la carpeta raíz por sí solo no trae las palabras clave, pero los nombres de archivo sí: confirma que `detectConfig` igual resuelve el tipo/ciudad.
- Lote plano donde un archivo no trae ningún año en su nombre: confirma que sigue quedando `"no-year"` (no se inventa un año).
- Lote mixto (una subcarpeta de año normal + un archivo suelto en la raíz): confirma que el archivo suelto sigue marcado `"no-year"` sin cambios — no se le intenta extraer año de su nombre solo porque el lote también use subcarpetas en otra parte.
- La salida agrupa correctamente por año derivado del nombre de archivo: un test en `frontend/src/lib/formatter/copy.test.ts` (o extendiendo uno ya existente) verificando que `copyFormattedFiles` escribe la entrada bajo `«año»/archivo_renombrado.ext` cuando el `yearFolder` viene de un lote plano.
