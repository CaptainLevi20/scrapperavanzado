# Diseño: Nueva fuente — Ministerio de Educación Nacional (MinEducación)

**Fecha:** 2026-08-13
**Estado:** Implementado (rediseñado durante el mismo día, ver "Pivote" abajo).

## Problema

Continuación del proyecto "una fuente a la vez" para IURISYNC (la fuente
anterior, MinVivienda, quedó en el PR #47). Esta vez: `Ministerio de
Educación Nacional: https://www.mineducacion.gov.co/portal/Normatividad/`.

## Fuente descartada antes de llegar a esta: Ministerio de Defensa

Antes de MinEducación se evaluó `Ministerio de Defensa Nacional:
https://www.mindefensa.gov.co/transparencia/normatividad`. Se descartó
porque su único enlace real de normatividad ("Normatividad expedida por la
Entidad") apunta a `normograma.info/mindef`, un portal de compilación
normativa **construido por Avance Jurídico** (confirmado por el propio
`<meta name="Author">` de esa página) — la empresa del usuario. A pedido
explícito del usuario ("no tengo muy claro el panorama") se saltó esta
fuente sin decidir su forma final.

## Primera versión: "Últimas publicaciones" (descartada, ver Pivote)

La primera versión de esta fuente usó
`/portal/Normatividad/Ultimas-publicaciones;anos-normatividad/{año}/`, un
listado nativo del sitio del ministerio (fuera de la marca Normograma), con
Resolución/Decreto/Ley/Circular/Directiva/Acuerdo clasificados por la
primera palabra del título de cada fila, año por página sin paginación
interna. Funcionaba y tenía 48 pruebas en verde, pero **solo cubría desde
2016** y tenía muy poca cobertura de Leyes (1 sola en 10 años) porque no es
un archivo histórico, es un feed de "lo más reciente".

## Pivote: el usuario pidió Leyes y Conceptos, que no existen fuera del Normograma

Al mostrarle ejemplos de resultados, el usuario notó: "Faltaron Leyes y
Conceptos". Investigando por qué, se confirmó que **ninguna** categoría del
sitio (ni Leyes, ni Conceptos, ni Circulares, ni Decretos, ni Resoluciones)
tiene un archivo histórico completo fuera del Normograma — el propio botón
de "Leyes"/"Conceptos"/etc. de la página de Normatividad apunta siempre a
`normograma.info/men`. "Últimas publicaciones" es la única alternativa
nativa, y es parcial para **todas** las categorías, no solo para Leyes y
Conceptos.

Se le explicó esto al usuario junto con el riesgo (es scrapear el producto
de su propia empresa) y respondió explícitamente: **"Scrapear el
Normograma para mineducación de todos modos"**. Sobre el alcance dentro
del Normograma (que además compila normativa de decenas de otras entidades
del sector educativo — SENA, ICETEX, universidades públicas, JEP, DNP...),
se le preguntó y confirmó: **"Solo Leyes (Congreso) y Conceptos (MEN)"**,
es decir, mantener el mismo alcance acotado (documentos relacionados
específicamente con el Ministerio) que ya tenían las demás categorías, no
expandir a todo el sector.

Dado que el Normograma es estrictamente más completo que "Últimas
publicaciones" para las categorías que ya existían (más años, mismos
documentos, PDF real en vez de solo la página HTML transcrita), se
**reemplazó por completo** el scraper — no se dejaron los dos mecanismos
mezclados. Como esto no se había subido ni fusionado a producción, no hubo
ningún dato ya guardado que migrar.

## Estructura del Normograma

El Normograma (`normograma.info/men/compilacion/compilacion/`) organiza la
normativa por **tipo de documento y entidad de origen**: cada tipo tiene
una página por cada una de las decenas de entidades del sector educativo
que lo expiden. Para el alcance acotado a MEN, se usa siempre la página de
la entidad que realmente expide cada tipo (no siempre es el propio
Ministerio):

| Tipo | Nombre base de archivo | Entidad |
|---|---|---|
| Resolución | `cndser_ministerio_educacion_nacional` | Ministerio de Educación |
| Decreto | `cndsed_presidencia_republica` | Presidencia de la República |
| Circular | `cndsec_ministerio_educacion_nacional` | Ministerio de Educación |
| Directiva | `cndsed_ministerio_educacion_nacional` | Ministerio de Educación |
| Acuerdo | `cndsea_ministerio_educacion_nacional` | Ministerio de Educación |
| Ley | `cndsel_congreso_republica` | Congreso de la República |
| Concepto | `c-dc_occ_ministerio_educacion_nacional` | Ministerio de Educación |

Confirmado con fetch real: Decreto y Ley llegan hasta 1936 y 1905
respectivamente (Ley tiene entradas hasta 1886 en el selector de años);
Circular/Directiva/Concepto llegan hasta ~2002-2015; Acuerdo es la más
chica, solo 6 años (2017-2023).

### Paginación: página base + fragmentos por año, con un detalle real

Cada página de categoría trae embebido **el año más reciente** directamente
en el HTML, más un `<select>` con todos los años disponibles en su
historial. Los demás años se piden por separado:
`GET {base}_{año}.html` (confirmado inspeccionando el JS del sitio,
`docFunction.js`/`loadYear.js`: el selector de año dispara exactamente esa
URL vía XHR).

**Hallazgo real durante la verificación**: esto no es uniforme. Una
categoría con poco volumen histórico (ej. Acuerdo, solo 6 años) trae **todos**
sus años ya embebidos en la página base y **no tiene archivos
`_{año}.html` separados en absoluto** — pedir uno devuelve 404 real. El
código no asume "solo el año por defecto viene incluido": primero extrae
todas las filas que ya trajo la página base, agrupadas por el año que cada
fila reporta en su propio texto (`id-documento`), y **solo pide como
fragmento aparte los años que el rango solicitado necesita y que todavía no
aparecieron** en esa primera pasada. Esto evita tanto el 404 real
(categorías chicas) como peticiones de más (categorías grandes, donde no
hace falta re-pedir el año que ya vino embebido).

### El PDF real no requiere visitar la página del documento

Cada fila enlaza a una página HTML transcrita del documento (ej.
`docs/resolucion_mineducacion_19230_2026.htm`), no al PDF directamente. El
PDF real vive en una ruta paralela: `docs/pdf/{mismo nombre}.pdf`
(confirmado inspeccionando `docFunction.js` del visor:
`pathDocumentosPDF = "pdf/"`, concatenado al nombre de archivo sin
extensión). Es una transformación de texto sobre el propio `href` del
listado — no hace falta un fetch adicional por documento para descubrir el
enlace de descarga.

### Formato del identificador — uniforme en las 7 categorías

Cada fila trae su identificador en un formato consistente:
`"{Tipo} {numero} de {año}"`, con un sufijo opcional `" ME"` cuando lo
expide el propio Ministerio (ausente en Decreto/Ley, que son de
Presidencia/Congreso). Verificado con **1269 filas reales muestreadas**,
desde 2026 hasta 1905 (incluye años intercalados de cada categoría, no solo
los más recientes): **cero excepciones** al patrón. No hace falta una
cascada de formatos como en `madr.py`/la primera versión de esta fuente —
es el listado más limpio y uniforme de todas las fuentes de este proyecto
hasta ahora.

## Por qué `f_public` solo tiene año (limitación aceptada a propósito)

El listado del Normograma **no da día ni mes**, solo año (a diferencia de
la primera versión de esta fuente, que sí tenía fecha completa vía
"Últimas publicaciones"). Se evaluaron dos opciones con el usuario:
visitar cada documento para intentar extraer una fecha más precisa del
propio texto de la norma (una petición extra por documento — con miles de
documentos históricos, mucho más lento y más agresivo contra el sitio de
un tercero), o aceptar solo año. El usuario pidió una recomendación; se
recomendó **solo año** por dos motivos: el volumen (Decreto y Ley con casi
100 años de historial cada uno) y que es el mismo criterio ya aceptado en
`madr.py` para casos sin fecha completa (`"DE 2022"` → `"2022-01-01"`), no
una excepción nueva. `f_public` se llena como `f"{año}-01-01"`; el filtro
`fini`/`ffin` compara contra ese valor con el mismo criterio que
`madr.py` (comparación de cadena exacta, no "el año se solapa con el
rango" — un documento de un año límite puede quedar fuera si `fini` cae
después del 1 de enero de ese año, limitación conocida y ya aceptada en
otras fuentes).

`doc_id_uses_publication_date` se deja en el default `True`: a diferencia
de `minvivienda`/`minambiente` (donde `f_public` es un timestamp de
reindexado del sitio que puede cambiar para el mismo archivo), aquí
`f_public` viene del propio identificador del documento — intrínseco,
nunca cambia. `filters_by_publication_date` se queda en el default
`False`, mismo criterio que `madr.py`.

## Nomenclatura del título

`_normalize_title(letra, numero, año)`: `f"{letra}_MEN_{int(numero):04d}_{año}"`
(Directiva usa el literal `DIRECTIVA`, Concepto usa el literal `CONCEPTO`,
en vez de una letra — mismo patrón que `CONPES` en `madr.py`). `MEN` es la
sigla oficial y universalmente usada del Ministerio de Educación Nacional.

## Manejo de errores

Una categoría cuya página base falle no descarta lo ya recolectado — se
registra vía `on_progress` y se continúa con la siguiente categoría. Un
año-fragmento que falle dentro de una categoría (ya en curso) tampoco
descarta lo que esa categoría ya trajo de otros años — mismo criterio. Una
fila con formato de identificador no reconocido (nunca visto en el
muestreo real de 1269 filas, pero posible) se descarta con aviso vía
`on_progress`, no rompe la corrida.

## Seed

`core/seed.py`: entrada `"mineducacion"` en `_FAMILIES` (descripción
actualizada para reflejar el Normograma), `create_source_if_missing(...,
family_key="mineducacion", family_params={})` sin cambios de key/nombre
— el pivote fue puramente interno al scraper, no afecta el seed ni rompe
compatibilidad con nada externo.

## Frontend

Ningún cambio de código — Sources/Runs/Documents/dashboard leen familias
desde la API, sin lógica hardcodeada por `family_key`.

## Pruebas

`tests/families/test_mineducacion.py`, 23 pruebas (reescrito por completo,
reemplaza las 48 pruebas de la primera versión): `_normalize_title`
(incluye el caso alfanumérico defensivo), `_pdf_href_from_doc_href`
(con/sin carpeta), `_extraer_fila` (fila limpia con sufijo " ME", fila sin
sufijo, formato no reconocido con aviso, sin enlace, sin descripción),
`_scrap_categoria` (solo pide los años-fragmento que hacen falta y que no
vinieron ya embebidos, NO vuelve a pedir un año que la categoría chica ya
trajo embebido — regresión directa del hallazgo real de Acuerdo/404, filtra
fuera de rango, continúa cuando un año-fragmento o la página base fallan),
`scrap()` (agrega las 7 categorías, continúa si una falla, límite
respetado, `stop_event` respetado entre categorías), registro en
`FAMILY_REGISTRY`, y flags de la familia (`filters_by_publication_date` en
`False`, `doc_id_uses_publication_date` en `True`).

## Verificación contra el sitio real

- 2026 completo (6 categorías con datos ese año, Acuerdo en 0 porque su
  año más reciente es 2023): 112 documentos, 0 filas descartadas, todos los
  PDF verificados como `application/pdf` real.
- Histórico 1990-1995: 107 documentos (Resolución, Decreto, Ley — las
  únicas 3 categorías con cobertura tan antigua), confirma que la lógica de
  fragmentos por año funciona también muy atrás en el tiempo, no solo para
  los años recientes.
