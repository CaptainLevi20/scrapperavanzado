# Nueva fuente: Normatividad MinCIT

## Problema

El Ministerio de Comercio, Industria y Turismo (MinCIT) publica su normatividad
en `https://www.mincit.gov.co/normatividad`, un sitio construido sobre Kentico
CMS. Es una fuente nueva que no encaja en ninguna de las 10 familias técnicas
existentes (`core/scrapers/families/`): no es WordPress (`adr`), no es
SharePoint (`adres`, `ane`), no pagina por parámetro (`anh`), y no es ninguna
de las familias judiciales. Necesita una familia técnica dedicada.

## Alcance (v1)

De las 10 categorías listadas en `/normatividad` (Resoluciones, Decretos,
Circulares, Leyes, Decreto Único Reglamentario, Agenda Regulatoria, Proyectos
de normatividad, Emplazamientos, Jurisprudencia, Normograma), solo se scrapean
las 4 que comparten la misma estructura verificada (archivo por año/rango de
años + tabla con fecha real y enlace de descarga) y que son normativa vigente
propia del ministerio:

- Resoluciones
- Decretos
- Circulares
- Leyes

Quedan fuera: Jurisprudencia (fallos judiciales, no normativa del ministerio),
Proyectos de normatividad y Agenda Regulatoria (borradores/planeación, no
normas vigentes), Decreto Único Reglamentario, Emplazamientos y Normograma
(estructura no verificada / redirige a sistema externo). Se pueden agregar
después si se justifica, siguiendo el mismo patrón.

## Familia técnica: `mincit`

Archivo nuevo `core/scrapers/families/mincit.py`, registrado con
`@register_family("mincit")`. Sigue el patrón ya establecido por `anh.py`
(`requests` + `BeautifulSoup`, tabla real con columnas de fecha) en vez de
generalizar un "family genérico para sitios Kentico" — no hay evidencia de que
otra fuente futura use esta misma plataforma, y el proyecto ya mantiene
`adr`/`adres`/`ane`/`anh` como archivos separados aunque las cuatro sean
conceptualmente "normativa de una agencia". Si aparece un segundo sitio con
este mismo patrón, se generaliza entonces.

Una sola fuente en el seed (no hay parametrización por sub-fuente como en
`samai`/`rama_judicial`): `source = "Ministerio de Comercio, Industria y
Turismo"`.

## Descubrimiento de páginas por año

Cada categoría tiene un índice (`/normatividad/{categoria}`) que enlaza a
páginas de archivo por año o por rango de años (confirmado: años sueltos como
`/leyes/2021` y rangos como `/leyes/1990-1994` para años viejos). El scraper:

1. Pide el índice de la categoría una sola vez.
2. Extrae los enlaces `/normatividad/{categoria}/{slug}` con regex sobre el
   HTML.
3. Para cada slug, determina qué años cubre (un año suelto cubre ese año; un
   rango `AAAA-AAAA` cubre todos los años del rango inclusive).
4. Construye un mapa año → slug, y pide solo los slugs únicos cuyos años
   caen dentro de `[fini, ffin]`.

Esto evita asumir `/{categoria}/{año}` para años viejos donde en realidad la
URL real es un rango, y evita pedir años fuera de rango.

**Margen de un año por el desfase expedición/publicación:** las páginas de
archivo del sitio agrupan por año de **expedición**, pero el rango `[fini,
ffin]` que se usa para decidir qué páginas pedir es de **publicación** (ver
`filters_by_publication_date` más abajo). Una norma expedida en diciembre
suele publicarse semanas después, ya en el año siguiente (ejemplo real:
Resolución 365, expedición 30/12/2025, publicación 12/02/2026). Por eso el
límite inferior del rango de años usado para elegir páginas de archivo se
amplía en un año (`_ANIOS_DE_MARGEN = 1` en `scrap()`), confiando en que el
filtro por `f_public` de `_extraer_filas` descarte después lo que quede
genuinamente fuera del rango pedido. No simplificar este margen sin entender
esta razón: quitarlo hace que documentos publicados en el año N pero expedidos
en diciembre del año N-1 desaparezcan silenciosamente de los resultados.

## Parseo de filas

Cada página de archivo tiene `<table id="Listado">`, con columnas idénticas
verificadas en las 4 categorías: `No`, `Archivo`, `Tamaño`, `Fecha de
expedición`, `Fecha de publicación`, `Descargar` (enlace). Se parsea con
BeautifulSoup:

- **Tipo**: ya se conoce por la categoría (no hace falta leerlo de la fila) —
  mapeo `resoluciones→Resolución`, `decretos→Decreto`, `circulares→Circular`,
  `leyes→Ley`.
- **Número**: se extrae con regex del inicio de la celda `Archivo` (ej.
  `"Resolución 365 del 30 de diciembre de 2025, ..."` → `365`). Patrón:
  `^\S+\s+(\d+)` sobre el texto de la celda (el primer token es el tipo, el
  segundo el número).
- **Descripción** (`detalle`): el resto del texto de la celda `Archivo`
  después de la fecha — la parte entre comillas o después de `:` (algunas
  categorías usan coma+comillas, Circulares usa dos puntos sin comillas; ver
  ejemplos abajo). Se guarda tal cual, sin normalizar comillas.
- **Descarga**: el `href` de la celda `Descargar`
  (`/getattachment/{guid}/{slug}.aspx`), resuelto a URL absoluta contra
  `https://www.mincit.gov.co`.

Ejemplos reales observados:
- `Resolución 365 del 30 de diciembre de 2025, "por la cual se adopta la determinación final..."`
- `Decreto 1438 del 27 de diciembre de 2025, "por medio del cual se realiza un nombramiento ordinario".`
- `Circular 018 del 27 de diciembre de 2024: distribución y administración del contingente...`
- `Ley 2094 del 29 de junio del 2021,"por medio de la cual se reforma la Ley 1952 de 2019..."`

## Fechas

- **`f_public`** = columna `Fecha de publicación` (dd/mm/yyyy → yyyy-mm-dd).
  Es la fecha contra la que se filtra `fini`/`ffin`.
- **`f_providencia`** = columna `Fecha de expedición` (dd/mm/yyyy →
  yyyy-mm-dd). Fecha oficial/intrínseca de la norma; se guarda pero no se usa
  para filtrar.
- La clase fija `filters_by_publication_date = True` en `BaseScrapper` (el
  default es `False` porque la mayoría de fuentes solo permiten filtrar por
  fecha de providencia/expedición; MinCIT sí expone fecha de publicación real
  y es la que se debe usar para el rango).
- `doc_id_uses_publication_date` se deja en su default (`True`). No se sabe
  todavía si el sitio republica un mismo documento con una fecha de
  publicación distinta (ej. corrección de un archivo) — si los resultados
  reales muestran que sí pasa, se revisita este flag entonces; no se
  sobre-diseña ahora sin evidencia.

## Nomenclatura del título

`title = f"{LETRA}_MCIT_{numero:04d}_{año}"`, donde:

- `LETRA` = `R` (Resolución), `L` (Ley), `D` (Decreto), `C` (Circular).
- `MCIT` es literal (abreviatura fija de la fuente).
- `numero` es el número extraído de la celda `Archivo`, formateado a 4
  dígitos con ceros a la izquierda (`365` → `0365`, `18` → `0018`).
- `año` es el año de `f_providencia` (fecha de expedición) en 4 dígitos.

Ejemplo: `Resolución 365 del 30 de diciembre de 2025` → `R_MCIT_0365_2025`.

Mismo estilo que ya usa `constitucional.py` (título como código corto y
filename-safe, no como texto descriptivo) en vez del estilo de `anh.py`
(título = texto legible). La descripción legible ("por la cual se...") vive en
`detalle`, no en `title`.

**Caso sin número parseable:** si el regex no encuentra un número al inicio de
la celda `Archivo` (formato inesperado), se usa el texto crudo de la celda
como `title` y se marca `title_unverified=True` — el mecanismo que ya existe
en `RawDocModel`/`BaseScrapper.resolve_unverified_document` para estos casos.

## Manejo de errores

Un año/slug que falle (404, timeout, tabla ausente) no descarta lo ya
recolectado de otras páginas/categorías — se registra vía `on_progress` y se
continúa, igual que el patrón ya usado en `adr.py` (`except Exception` por
año, con log y `continue`).

## Seed

En `core/seed.py`:
- Nueva entrada en `_FAMILIES`: `"mincit": ("Ministerio de Comercio, Industria y Turismo", "Normativa publicada por el Ministerio de Comercio, Industria y Turismo")`.
- `repository.create_source_if_missing(db, family_key="mincit", name="Ministerio de Comercio, Industria y Turismo", family_params={})`.

## Pruebas

`tests/families/test_mincit.py`, con fixtures de HTML (índice de categoría con
años sueltos y con rangos; página de archivo con filas de ejemplo de las 4
categorías), cubriendo:

- Parseo correcto de las 4 categorías (tipo, número, fecha, detalle,
  descarga).
- Formato del número a 4 dígitos, incluyendo el caso de número ya escrito con
  cero a la izquierda en el HTML (`018`).
- Mapeo de rango de años (`1990-1994`) a cada año individual.
- Filtro por `fini`/`ffin` usando `f_public` (fecha de publicación), no
  `f_providencia`.
- Caso `title_unverified=True` cuando el regex no encuentra número al inicio
  de la celda.
- Un año/slug que falla no descarta los documentos de los demás.
