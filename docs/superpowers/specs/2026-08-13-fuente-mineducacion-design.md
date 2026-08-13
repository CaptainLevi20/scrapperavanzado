# Diseño: Nueva fuente — Ministerio de Educación Nacional (MinEducación)

**Fecha:** 2026-08-13
**Estado:** Implementado.

## Problema

Continuación del proyecto "una fuente a la vez" para IURISYNC (la fuente
anterior, MinVivienda, quedó en el PR #47). Esta vez: `Ministerio de
Educación Nacional: https://www.mineducacion.gov.co/portal/Normatividad/`.

## Fuentes descartadas antes de llegar a esta

Antes de MinEducación se evaluó `Ministerio de Defensa Nacional:
https://www.mindefensa.gov.co/transparencia/normatividad`. Se descartó
porque su único enlace real de normatividad ("Normatividad expedida por la
Entidad") apunta a `normograma.info/mindef`, un portal de compilación
normativa **construido por Avance Jurídico** (confirmado por el propio
`<meta name="Author">` de esa página) — la empresa del usuario. A pedido
explícito del usuario ("no tengo muy claro el panorama") se saltó esta
fuente sin decidir su forma final; queda pendiente para cuando haya
claridad sobre cómo tratar una fuente que es, en el fondo, un producto
propio.

MinEducación tiene el mismo patrón (su página de Normatividad también
promociona un "Normograma" en `normograma.info/men`, mismo producto), pero
a diferencia de MinDefensa **sí tiene un listado nativo propio del
ministerio** — "Últimas publicaciones" — completamente independiente del
Normograma, así que no aplica el mismo dilema: se usa esa fuente nativa.

## Descubrimiento de la página

- `https://www.mineducacion.gov.co/portal/Normatividad/` es una portadilla
  Newtenberg CMS que enlaza tanto al Normograma (descartado, ver arriba)
  como a "Últimas publicaciones de norma"
  (`/1759/w3-propertyvalue-67454.html`, que redirige a
  `/portal/Normatividad/Ultimas-publicaciones;anos-normatividad/{año actual}/`)
  — un listado **propio del sitio del ministerio**, sin pasar por el
  Normograma.
- El listado es **por año completo en una sola página**, sin paginación
  dentro del año: `GET
  https://www.mineducacion.gov.co/portal/Normatividad/Ultimas-publicaciones;anos-normatividad/{año}/`.
  Confirmado con fetch real contra varios años (2016, 2017, 2018, 2019,
  2020, 2021, 2022, 2023, 2024, 2025, 2026): el número de bloques `h3.h4.titulo`
  en cada página coincide exactamente con el contador que el propio sitio
  muestra en su filtro de años (ej. 58 para 2023, 47 para 2020, 27 para
  2026) — no hay truncamiento ni una segunda página oculta.
  El listado solo tiene datos reales desde **2016** en adelante (años
  anteriores existen como opción de filtro pero devuelven 0 resultados);
  como cada año es una petición barata e independiente, no hace falta
  ninguna lógica especial de corte — un backfill histórico completo simplemente
  hace ~10 peticiones baratas en vez de necesitar paginación con corte
  temprano como en `minvivienda`.
- Cada fila (`h3.h4.titulo`, dentro de un `div.recuadro`) es **texto libre
  del sitio**: título completo tipo "Resolución N° 020664 del 4 de agosto de
  2026", "Circular No.37 del 8 de octubre de 2020", "Decreto NO.0617 del 17
  de junio de 2026" — **no hay un campo de fecha estructurado separado como
  en `minvivienda`** (con su `<time datetime>` ISO 8601). El único campo de
  fecha del sitio (`p.fecha`, texto "Actualizado: DD de MES de AAAA") es la
  fecha de última edición del artículo en el CMS, no la fecha real de la
  norma — se decidió no usarlo en absoluto (ver más abajo), igual que
  `madr.py` no usa ningún campo así porque tampoco existe uno confiable.
- El sitio no separa por categoría en la URL: **todos los tipos de norma
  (Resolución, Decreto, Ley, Circular, Directiva, Acuerdo) se listan juntos
  por año**, mezclados con "Proyecto de Decreto"/"Proyecto de Resolución"
  (borradores en consulta pública, no normas vigentes) y, ocasionalmente,
  documentos sueltos que no son normas (`"Guía..."`, `"Manual..."`,
  `"Reglamento Operativo..."`, cada uno visto una sola vez en 306 filas
  muestreadas de 2016 a 2026).

## Alcance — clasificación por la primera palabra del título

Como el sitio no separa por categoría, cada fila se clasifica por la
primera palabra de su propio título:

| Primera palabra | Tipo | Letra |
|---|---|---|
| Resolución / Resolucion | Resolución | `R` |
| Decreto | Decreto | `D` |
| Ley | Ley | `L` |
| Circular | Circular | `C` |
| Directiva | Directiva | literal `DIRECTIVA` |
| Acuerdo | Acuerdo | `A` |
| **Proyecto** (de Decreto/Resolución) | — | excluido a propósito: borrador en consulta pública, no es norma vigente |
| cualquier otra (Guía, Manual, Reglamento Operativo...) | — | excluido: no es un tipo de norma reconocible |

Confirmado con muestreo real (306 títulos, 2016-2026): 131 Resolución, 84
Circular, 32 Proyecto (excluidos), 27 Directiva, 25 Decreto, 3 Acuerdo, 1
Ley, y 3 documentos sueltos (Reglamento/Manual/Guía, excluidos).

## Extracción de número y fecha — texto libre, sin campo estructurado

Sin un campo de fecha separado (a diferencia de `minvivienda`), tanto el
número como la fecha se extraen del propio título con regex, siguiendo el
mismo criterio de `madr.py` (cascada de formatos en una sola alternancia,
`.search()` para que gane la coincidencia más a la izquierda).

**Número**: el primer grupo de dígitos del título completo (después de la
palabra de tipo, ignorando marcas como "N°"/"No."/"NO."/"nro." que no
tienen dígitos propios) es siempre el número real de la norma, nunca parte
de la fecha — la fecha viene después en el título en todos los casos
reales revisados.

**Fecha** (buscada en el resto del título, después de recortar el número):
cascada de 5 niveles, de más a menos específico:
1. `"4 de agosto de 2026"` / `"27 de mayo del 2016"` — nombre de mes, con
   "de" antes del día y antes del año, cada uno opcional por separado
   (varias filas reales omiten el segundo: `"7 de julio 2026"`).
2. `"de agosto de 2026"` — sin día, solo nombre de mes.
3. `"15-3-2022"` — fecha numérica `DD-M-AAAA` o `DD/M/AAAA` (visto en
   `"Circular CONJUNTA 001 del 15-3-2022"`).
4. `"26 NOV 2019"` / `"04 FEB 2026"` — mes abreviado en mayúsculas, sin
   "de" (visto en varias Resoluciones de 2019, 2025 y 2026).
5. `"de 2026"` — solo año, sin día ni mes.

Verificado contra las 306 filas reales con tipo reconocido: 268/271 (98.9%)
producen fecha; las 3 restantes se descartan a propósito (sin fecha
reconocible en el título en absoluto, ej. `"Directiva Ministerial No 37"`
donde la fecha solo aparece en el resumen, no en el título) y quedan
registradas vía `on_progress`, igual que `madr.py`.

## Selección del adjunto — preferir PDF, no la primera posición

Cada fila puede traer varios adjuntos dentro del mismo `div.recuadro` (la
norma misma + anexos: actas, formatos, guías, hojas de cálculo). La
posición NO es un indicador confiable de cuál es la norma: se encontró un
caso real (`"Circular No. 21 del 4 de marzo del 2016"`) donde el **primer**
adjunto listado es un `.docx` con un formulario anexo ("Formato Préstamo
Bicicletas") y el **segundo** es el PDF real de la circular — tomar el
primero a secas habría descargado el anexo, no la norma. Se eligió en su
lugar: el primer adjunto cuyo `href` termina en `.pdf`, en el orden en que
aparece en el HTML (si ninguno es PDF, se usa el primero de todos modos).
Confirmado contra los únicos 2 casos reales del muestreo con más de un PDF
adjunto (`"Circular No. 21 del 17 de marzo de 2020"` y `"Resolución N°
020664 del 4 de agosto de 2026"`): en ambos, el primer PDF en orden de
documento es efectivamente la norma, y los PDF siguientes son anexos con
título claramente distinto (`"Documento Técnico de Soporte"`, `"Guía
orientadora..."`).

## `<base href>`: los enlaces son relativos a una URL distinta de la pedida

La plantilla Newtenberg CMS declara su propio `<base href>` (ej.
`https://www.mineducacion.gov.co/1780/w3-multipropertyvalues-67454-69916.html`),
**distinto de la URL amigable pedida**
(`/portal/Normatividad/Ultimas-publicaciones;anos-normatividad/2026/`). Los
`href` de los adjuntos son relativos (ej. `articles-430180_recurso_1.pdf`)
y deben resolverse contra ese `<base>`, no contra la URL de la petición —
resolverlos contra la URL pedida produciría una ruta con el segmento
`;anos-normatividad/2026/` insertado, que no existe. Confirmado con el
sanity check contra el sitio real: los enlaces resueltos vía `<base>`
descargan correctamente.

## Fechas — por qué `f_public` es la fecha real, no la del CMS

A diferencia de `minvivienda`/`minambiente` (donde el sitio ofrece un campo
de fecha propio pero no confiable, que se guarda igual como informativo en
`f_public`), aquí el único campo de fecha del sitio (`p.fecha`,
"Actualizado: ...") **no se captura en absoluto** — no hay un campo
estructurado separado para la fecha real de la norma como en `minvivienda`
(su `<time datetime>` ISO 8601), así que, igual que `madr.py`, `f_public`
se llena directamente con la fecha real ya parseada del título. No hay
`f_providencia`. `doc_id_uses_publication_date` se queda en el default
`True` (a diferencia de `minvivienda`/`minambiente`): esta fecha es
intrínseca al documento (viene de su propio título, nunca cambia para el
mismo archivo), no un timestamp de reindexado del CMS.
`filters_by_publication_date` se queda en el default `False`, igual que
`madr.py` (criterio ya probado: `test_filters_by_publication_date_stays_at_default_false`).

## Hallazgo del sanity check contra el sitio real: duplicados genuinos del sitio

El chequeo manual (rango 2020-2026, 250 documentos) encontró 14 títulos
normalizados que corresponden a **dos artículos distintos del CMS** (`aid`
distinto, `href` de PDF distinto) con el mismo tipo, número y fecha — ej.
`C_MEN_0037_2020` aparece dos veces, con
`articles-401422_recurso_1.pdf` y `articles-422599_recurso_1.pdf`. Es una
duplicación real del propio sitio (la misma circular subida dos veces bajo
artículos separados), no un error de parseo: cada ocurrencia tiene su
propia URL de descarga, así que cada una recibe su propio `doc_id` — el
pipeline las trata como dos documentos distintos con el mismo título de
archivo (mismo comportamiento que tendría cualquier otra fuente ante una
duplicación real del sitio). No se intentó deduplicar por título: hacerlo
arriesgaría fusionar dos normas genuinamente distintas que coincidan de
número y año por casualidad.

## Nomenclatura del título

`_normalize_title(letra, numero, anio)`: `f"{letra}_MEN_{int(numero):04d}_{anio}"`
(Directiva usa el literal `DIRECTIVA` en vez de una letra, mismo patrón que
`CONPES` en `madr.py`). `MEN` es la sigla oficial y universalmente usada del
Ministerio de Educación Nacional (confirmada en el propio meta-keywords del
sitio: "MEN, ministerio de educacion").

## Manejo de errores

Un año cuyo `GET` falle no descarta lo ya recolectado — se registra vía
`on_progress` y se continúa con el siguiente año. Una fila con tipo
reconocido pero sin número, sin fecha parseable, o sin ningún adjunto se
descarta con aviso vía `on_progress`. Una fila con tipo no reconocido
(Proyecto, Guía, Manual...) se descarta en silencio — es el comportamiento
esperado y frecuente (32 de 306 filas muestreadas), no una anomalía que
justifique un aviso.

## Seed

`core/seed.py`: nueva entrada `"mineducacion"` en `_FAMILIES` y
`create_source_if_missing(..., family_key="mineducacion", family_params={})`,
mismo patrón que `madr`/`mincit`/`minvivienda`. Conteos hardcodeados en
`tests/test_seed.py` actualizados (13 familias).

## Frontend

Ningún cambio de código — Sources/Runs/Documents/dashboard leen familias
desde la API, sin lógica hardcodeada por `family_key`.

## Pruebas

`tests/families/test_mineducacion.py`, 48 pruebas: clasificación por
primera palabra (los 6 tipos reconocidos, exclusión de "Proyecto de..." y
de documentos sueltos, case-insensitive), extracción de número, cascada
completa de fecha (los 5 niveles + casos límite: fecha calendario
imposible, case-insensitive), normalización de título, selección de
adjunto (prefiere PDF, ignora un `.docx` que aparece primero, cae al
primero si no hay ningún PDF), resolución de enlaces contra `<base href>`
en vez de la URL pedida, fila sin adjunto descartada, fila con tipo
reconocido pero sin fecha descartada (con aviso), filtro por rango de
fechas, un año que falla no descarta los demás, límite respetado,
`stop_event` respetado entre años, y flags de la familia
(`filters_by_publication_date` en `False`, `doc_id_uses_publication_date`
en `True`, a diferencia de `minvivienda`/`minambiente`).
