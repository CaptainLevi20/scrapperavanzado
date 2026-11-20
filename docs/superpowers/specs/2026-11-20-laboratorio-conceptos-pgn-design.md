# Renombrado de Conceptos PGN (Laboratorio)

## Intención

Se pidió renombrar un lote de conceptos de la Procuraduría General de la
Nación (PGN) digitalizados por tomos, para cargarlos después a Azure. El
lote vive en `O:\FBU\PGN\20260923` en una máquina a la que ni el servidor
de IURISYNC ni el desarrollador tienen acceso. Solo la persona que corre la
herramienta, en su propio navegador, llega al disco. La subida a Azure la
hace el usuario por su cuenta, fuera de esta herramienta. Se sube la
carpeta raíz completa, así que la estructura de carpetas se conserva como
parte del nombre del blob.

Formato pedido para cada documento:

```
CTO_PGN_{número a 7 dígitos}_{año a 4 dígitos}(C).{ext}
```

`(C)` significa "constitucional" y va en todos los archivos del lote.
Ejemplo: `Concepto 5588 de 2013.pdf` → `CTO_PGN_0005588_2013(C).pdf`.

## Metas, no-metas, anti-metas

**Metas**
- Renombrar **en el lugar** (sobre los originales, decisión del usuario)
  todos los documentos del lote cuyo número y año se puedan determinar.
- Respetar la estructura de carpetas tal como está (`AÑO\Tomo N\…`). Solo
  cambia el nombre del archivo; ninguna carpeta se mueve ni se renombra.
- Permitir completar a mano el número de los archivos que no lo traen,
  viendo la primera página del PDF dentro de la misma pantalla.
- Mostrar el "antes → después" completo antes de tocar nada.
- Dejar un registro (CSV) de cada renombre, para poder revertir a mano.

**No-metas**
- Subir a Azure.
- Convertir fotos (`.jpg`) a PDF ni tocarlas de ninguna forma.
- Leer el número desde dentro del PDF. Los "Tomo 3 1991-…" son escaneos
  sin texto (validado por el usuario con `Tomo 3 1991-1-14.pdf`), así que
  no hay texto que leer y se descarta OCR.
- Resolver los números repetidos entre tomos (ver abajo): solo se informan.
- Reorganizar carpetas (eso es la pestaña "Reorganización").

**Anti-metas** (fallaría aunque "funcione")
- Perder o pisar un archivo: un nombre destino que ya existe **nunca** se
  sobrescribe.
- Inventar un número de concepto que no está en el nombre ni lo escribió
  una persona.
- Romper el "Renombrado" actual de Acuerdos de Cali.

## El lote real (de `lista_lote.txt`, 2,424 rutas)

Estructura: `AÑO\Tomo N\archivo` (2,332 archivos). Hay además ~65 conceptos
que viven en su propia subcarpeta (`2007\Tomo 6 2007\CTO_PGN_0004360_2007\4360.pdf`)
y 3 archivos de control en la raíz (`.xlsx`, `Léame.txt`). Los nombres de
carpeta de tomo varían (`Tomo 1`, `TOMO 9 2007`, `Tomo 2 del 2003`,
`TOMO 1-1996`, `tomo 7 2013`, `TOMO 1 2006-TOMO 2 2006`); no importan
porque el año se toma del **primer nivel** (`AÑO`).

Formas de nombre encontradas (`#` = dígitos):

| Forma | Cantidad | Ejemplo | Número |
|---|---|---|---|
| `Cto. #` | 1,357 | `Cto. 1653.pdf` | 1653 |
| `Concepto # de #` | 556 | `Concepto 2258 de 2000.pdf` | 2258 |
| `#` | 198 | `4004.pdf` | 4004 |
| `Concepto #` | 131 | `Concepto 4838.pdf` | 4838 |
| `CTO_PGN_#_#` | 48 | `CTO_PGN_0003788_2005.pdf` | 3788 (solo falta `(C)`) |
| `Cto. NN #` / `Cto. NN#` | 27 | `Cto. NN 1.pdf` | 1 ("NN" no significa nada, decisión del usuario) |
| `Concepto #A de #` / `Concepto #-A` | 10 | `Concepto 4036A de 2006.pdf` | 4036A |
| Errores de tipeo | ~12 | `Concpeto 5018 de 2010`, `Conceptto`, `Concepro`, `Cncepto`, `Concepto de 5094 de 2011`, `Cto. 3168pdf`, `Concepto 5651 de 2013..pdf`, `Cto. 114 .pdf` | el primer número |
| `Tomo # AAAA-p-p` | 11 | `Tomo 3 1991-1-14.pdf` | **ninguno**: pedazos de un tomo por rango de páginas |
| `.jpg` | 69 | `20260708_110124.jpg`, `pagina_233.jpg` | se ignoran |

Las 69 fotos están en `2006\TOMO 10 2006\` (41, el tomo entero, sin
ningún PDF), `2007\TOMO 9 2007\CTO_PGN_0004425_2007\` (21, el concepto
4425 solo existe como fotos) y `1998\Tomo 3\` (7 páginas sueltas junto a
21 PDFs).

## Reglas de renombre

1. **Qué archivos entran.** Solo documentos: `.pdf`, `.doc`, `.docx`,
   `.rtf` (sin distinguir mayúsculas). Todo lo demás (fotos, Excel, `.txt`)
   se ignora: no se lista como pendiente ni se toca. Las carpetas que
   tienen fotos pero ningún documento sí se mencionan en el aviso final
   ("solo fotos, sin documento"), para que el usuario sepa qué no tiene
   versión subible.
2. **Año.** Del primer nivel de carpeta bajo la raíz (`1991`, `2013`…). Un
   archivo en la raíz (sin carpeta de año) queda como "falta el año".
3. **Número.** Se buscan solo los dígitos del nombre (sin extensión): el
   primer grupo de dígitos que **no** sea el año, opcionalmente seguido de
   una letra `A` (con o sin guion: `4036A`, `4883-A` → `4036A`). Se
   descartan "NN" y cualquier palabra alrededor, así que los errores de
   tipeo de "Concepto" no importan. Un nombre `CTO_PGN_0003788_2005` se
   lee igual (`3788`). Con 7 dígitos de relleno: `0003788`; la letra va
   después: `0004036A`. La extensión se pasa a minúsculas en el nombre
   nuevo.
   - Un nombre que empieza por `Tomo` (`Tomo 3 1991-1-14.pdf`) **no** tiene
     número de concepto: el "3" es el tomo. Va directo a revisión como "sin
     número" (regla 5).
   - Si el único número candidato es igual al año de la carpeta (p. ej.
     `Cto. 2005.pdf` dentro de `2005\`), va a revisión. No ocurre en este
     lote; es una protección. *Decisión de Claude.*
4. **Año en el nombre distinto al de la carpeta.** Caso real único:
   `2009\Tomo 3\Concepto 4734 de 2008.pdf`. Va a revisión, con el año del
   nombre propuesto en la casilla (es el dato más específico). Con la
   casilla ya llena, la fila cuenta como lista para renombrar; la revisión
   es para que el usuario la vea, no la bloquea. *Decisión de Claude.*
5. **Sin número** (`Tomo 3 1991-1-14.pdf` y cualquier otro): va a revisión
   con la casilla de número vacía y la vista previa de la primera página. Si
   se deja vacía, el archivo conserva su nombre original.
6. **Ya está en el formato final** (`…(C).pdf` idéntico al calculado): se
   cuenta como "ya listo" y no se toca. Así, correr la herramienta dos
   veces sobre el mismo lote no hace nada la segunda vez.
7. **Choques dentro de una misma carpeta.** Si dos archivos de la misma
   carpeta dan el mismo nombre final, los dos van a revisión como
   "duplicado" y ninguno se renombra hasta que se corrija uno. Si el nombre
   final ya existe como **otro** archivo en esa carpeta, ese archivo se
   salta (nunca se sobrescribe). Verificado contra `lista_lote.txt`: en
   este lote **no hay** ningún choque dentro de una misma carpeta, y cada
   subcarpeta de concepto (`CTO_PGN_0004360_2007\`) tiene un solo
   documento. Por eso no hace falta un sufijo de partes o anexos; la regla
   queda solo como protección para lotes futuros.
8. **Repetidos entre tomos** (48 pares reales, ej. `1993\Tomo 4\Cto. 257` y
   `1993\Tomo 5\Cto. 257`): **no bloquean**. Como la estructura se
   conserva, no chocan en disco ni en Azure. Se listan en el aviso final
   como información.

## Cómo se ve

Nueva pestaña **"Conceptos PGN"** en el Laboratorio, junto a Renombrado,
Reorganización y Decretos Cali.

```
[Elegir carpeta del lote]

Lote: 20260923 · 2,352 documentos
  ✔ 2,340 listos para renombrar     ▸ ver todos (antes → después)
       (incluye los 48 CTO_PGN_… a los que solo les falta "(C)")
  ✔ 0 ya tienen el nombre final (en una segunda pasada serían todos)
  ⚠ 12 requieren tu revisión (11 "Tomo 3 1991-…" + 1 año distinto)

Requieren tu revisión
┌───────────────────────────────┬──────────────┬──────┬──────────┬──────────────────────────┐
│ Archivo                       │ Motivo       │ Año  │ Número   │ Nombre nuevo             │
├───────────────────────────────┼──────────────┼──────┼──────────┼──────────────────────────┤
│ 1991/Tomo 3/Tomo 3 1991-1-14  │ Sin número   │ 1991 │ [_____]  │ (queda igual)  [👁 ver]  │
│ 2009/Tomo 3/Concepto 4734 de… │ Año distinto │[2008]│ [4734 ]  │ CTO_PGN_0004734_2008(C)  │
└───────────────────────────────┴──────────────┴──────┴──────────┴──────────────────────────┘
  [👁 ver] abre al lado la primera página del PDF.

Avisos (no bloquean)
  ▸ 48 números aparecen en dos tomos del mismo año
  ▸ 2 carpetas tienen solo fotos, sin documento

[Renombrar 2,299 archivos]   → confirma: "Esto cambia los nombres de los
                                originales y no se puede deshacer desde aquí.
                                Se guardará un registro en la carpeta raíz."
Progreso: 1,240 / 2,299
Resultado: 2,297 renombrados · 2 saltados (motivo por archivo)
```

## Enfoques considerados

- **A. Ampliar el "Renombrado" actual.** Está hecho a la medida de Acuerdos
  de Cali (dos niveles, `A`/`CONCALI` fijos). Generalizarlo arriesga
  romperlo y lo llena de casos especiales. Descartado.
- **B. Pestaña nueva con reglas propias, reutilizando piezas (elegido por
  el usuario).** Mismo modelo que el Renombrado (navegador, selector de
  carpeta, revisión antes de aplicar), pero con sus propias reglas y
  renombrando en el lugar.
- **C. Script de PowerShell de una sola vez.** Sin vista previa ni revisión
  cómoda. Descartado: el usuario pidió trabajarlo en el Laboratorio.
- **D. Recorrido desde el servidor (como Reorganización).** Imposible: el
  servidor no llega a `O:`.

## Diseño técnico

Todo en el frontend; **sin cambios de backend ni de base de datos.**

- `frontend/src/lib/conceptosPgn/rules.ts`: funciones puras
  (`extractConceptNumber`, `extractYearFromName`, `buildConceptName`,
  `isDocument`). Sin relación con `lib/formatter/rules.ts` (esas reglas
  son de Cali).
- `frontend/src/lib/conceptosPgn/analyze.ts`: recorre el árbol con
  `FileSystemDirectoryHandle` (recursivo, cualquier profundidad), arma una
  entrada por documento (`path`, `dirHandle`, `fileHandle`, año, número,
  nombre final, motivo de revisión) y los avisos. Aplica correcciones
  manuales y vuelve a calcular choques, igual que
  `formatter/analyze.ts` (`applyCorrections` / `markDuplicates`).
- `frontend/src/lib/conceptosPgn/renameInPlace.ts`: por cada archivo
  aprobado:
  1. Si el destino ya existe en la carpeta → se salta con motivo.
  2. Si el navegador permite `fileHandle.move(nuevoNombre)` → se usa.
  3. Si no → se lee el original completo, se crea el destino en la misma
     carpeta, se escribe, se compara el tamaño y **solo si coincide** se
     borra el original (`dirHandle.removeEntry`). Si algo falla a mitad de
     camino, se borra el destino a medias y el original queda intacto.
  4. Un fallo de un archivo nunca detiene el resto.
- **Registro:** antes de renombrar se escribe
  `registro_renombres_AAAAMMDD-HHMM.csv` en la raíz del lote (columnas:
  ruta, nombre anterior, nombre nuevo, resultado). Al terminar se reescribe
  con el resultado real de cada archivo. UTF-8 con BOM, para que Excel
  muestre bien las tildes. El `.csv` no es un documento, así que nunca
  entra en un análisis posterior. Ubicación confirmada por el usuario: en
  la raíz, sabiendo que se sube a Azure junto con el lote si no se retira
  antes (igual que el `.xlsx` y el `Léame.txt` que ya están ahí). La
  pantalla final lo recuerda en una línea ("Registro guardado en … — retíralo
  antes de subir a Azure si no quieres que se suba").
- **Vista previa:** la primera página se muestra con el visor de PDF propio
  del navegador (`URL.createObjectURL(file)` en un `<iframe>` con
  `#page=1`), sin agregar librerías. *Decisión de Claude*; si el visor no
  carga en el iframe, se puede pasar a `pdfjs-dist`.
- `frontend/src/pages/formatter/ConceptosPgnPanel.tsx`: la pantalla. Se
  agrega como cuarta pestaña en `FormatterPage.tsx`. Pide permiso de
  lectura y escritura (`showDirectoryPicker({ mode: "readwrite" })`).
- Se reutiliza lo que sirva de `lib/formatter` (tipos de File System
  Access, `testFsFakes.ts` para pruebas) sin modificar su comportamiento.

**`move()` en la unidad `O:`.** Nadie salvo el usuario llega a `O:`, así
que no hay prueba previa allá ni despliegue de prueba. Se entrega todo de
una vez y la decisión se toma **por archivo, al momento**: se intenta
`move()`; si no existe o falla (incluido el caso "existe pero falla en la
unidad de red"), ese archivo pasa al camino alternativo (copiar en la
misma carpeta, verificar tamaño, borrar el original). El desarrollador
valida los dos caminos en su Chrome local sobre una carpeta de prueba en
`C:`, y las pruebas automáticas cubren ambos. *Decisión de Claude.*

## Pruebas

- `rules.test.ts`: una prueba por cada forma de nombre de la tabla del lote
  real, incluidos todos los errores de tipeo, `NN`, la letra `A`, el
  `CTO_PGN_` ya formateado y los "Tomo 3 1991-…" (sin número).
- `analyze.test.ts` (con `testFsFakes`): año desde la carpeta de primer
  nivel, subcarpetas de concepto, archivos ignorados, año distinto a la
  carpeta, choque dentro de una carpeta, repetidos entre tomos como aviso,
  carpetas con solo fotos, "ya listo".
- `renameInPlace.test.ts`: con `move()` y sin él (copiar, verificar,
  borrar), destino existente se salta, fallo a mitad deja el original
  intacto, registro CSV escrito.
- `ConceptosPgnPanel.test.tsx`: flujo de revisión, casilla de número,
  confirmación antes de renombrar, resultado.
- Las pruebas existentes del Renombrado de Cali no cambian.

## Queda a criterio de quien implemente

Textos exactos de la pantalla, diseño de la tabla "antes → después"
completa (paginada o con desplazamiento), y cómo se muestra el progreso.
