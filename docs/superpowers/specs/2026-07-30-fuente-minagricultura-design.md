# Nueva fuente: Normatividad Ministerio de Agricultura y Desarrollo Rural (MADR)

## Problema

El Ministerio de Agricultura y Desarrollo Rural (MADR) publica su normatividad
en `https://www.minagricultura.gov.co/normatividad`, un sitio construido sobre
TYPO3 CMS. Es una fuente nueva que no encaja en ninguna de las 11 familias
técnicas existentes (`core/scrapers/families/`): no usa tabla `id="Listado"`
como `mincit`, no pagina por año como `mincit`/`anh`, no es WordPress (`adr`) ni
SharePoint (`adres`/`ane`). Necesita una familia técnica dedicada.

## Alcance (v1)

El menú de `/normatividad` tiene 9 secciones. Verificado con fetch directo
(conteo de items y forma del HTML), solo 4 comparten una estructura homogénea
de acto normativo con número + fecha propios:

- Leyes (114 items)
- Decretos (498 items)
- Resoluciones (2378 items)
- Conpes (54 items)

Quedan fuera de v1 (formas de metadato distintas, verificado con fetch): 

- **Jurisprudencia** (40 items): sentencias de otras cortes citadas por el
  ministerio (`"Sentencia Consejo de Estado (0829122001) 25 de agosto de
  2022"`), sin número de acto propio del ministerio.
- **Notificaciones** (694 items): avisos de terminación de contratos y
  notificaciones a personas naturales (`"RICARDO_ELIAS_NOVOA_PARODY"`), sin
  numeración de norma.
- **Agenda regulatoria** (96 items) y **Análisis normativos** (8 items):
  documentos de planeación/política, no normas vigentes.
- **Proyectos normativos**: listado en el menú pero su URL no se verificó en
  esta ronda (no apareció entre los enlaces `/normatividad/*` capturados desde
  las páginas ya scrapeadas).

Se pueden agregar después si se justifica, con su propio diseño de
nomenclatura (mismo criterio que se usó para excluir categorías de `mincit`).

## Familia técnica: `madr`

Archivo nuevo `core/scrapers/families/madr.py`, registrado con
`@register_family("madr")`. No se generaliza junto con `mincit` pese a que
ambas son "normativa de un ministerio .gov.co": la estructura HTML real es
distinta (tabla vs. tarjetas TYPO3), y el proyecto ya mantiene familias
separadas para fuentes conceptualmente parecidas pero técnicamente distintas
(`adr`/`adres`/`ane`/`anh`). Si aparece un segundo sitio con esta misma
plantilla TYPO3, se generaliza entonces.

Una sola fuente en el seed (no hay parametrización por sub-fuente):
`source = "Ministerio de Agricultura y Desarrollo Rural"`.

## Descubrimiento de páginas

A diferencia de `mincit`, **no hay paginación ni archivo por año**: cada
categoría (`/normatividad/{categoria}`) devuelve en una sola respuesta HTML
el listado completo desde 1991 hasta el año en curso (confirmado: la página
de decretos trae 498 artículos con `data-year` desde 1991 hasta 2026 en un
solo `GET`). El scraper hace **un solo `GET` por categoría**, sin construir
mapa de años ni slugs de archivo. Los campos "Número"/"Año"/"Buscar" y
"Exportar a Excel" visibles en la página son filtro/exportación en el
navegador (JS `normas.js`) sobre el DOM ya renderizado — no hace falta
llamarlos ni imitarlos.

## Parseo de artículos

Cada norma es un bloque:

```html
<article class="col-12 pb-5 item_norm"
    data-title="DECRETO 0765 DEL 15 DE JULIO DEL 2026"
    data-info="&quot;Por el cual se adicionan los decretos 1071 del 2015...&quot;"
    data-year="2026"
    data-number="0765"
    data-link="t3://file?uid=14012"
    data-content="">
  <div class="cnt_item_norm">
    <h3>
      <a itemprop="url" href="/fileadmin/normatividad/decretos/DECRETO_No._0765_DEL_15_DE_JULIO_DE_2026.pdf">
        <span itemprop="headline">DECRETO 0765 DEL 15 DE JULIO DEL 2026</span>
      </a>
    </h3>
    <p>...</p>
  </div>
</article>
```

Se parsea con BeautifulSoup, iterando `article.item_norm` por página:

- **Tipo**: ya se conoce por la categoría (mapeo `leyes→Ley`,
  `decretos→Decreto`, `resoluciones→Resolución`, `conpes→Conpes`) — no hace
  falta leerlo del artículo.
- **Número**: atributo `data-number` (ya viene limpio, ej. `"0765"`, `"4076"`)
  — no requiere regex de extracción como en `mincit`.
- **Detalle**: atributo `data-info` (contiene comillas HTML-escapadas y a
  veces está vacío en Conpes/otras — se guarda tal cual, decodificado).
- **Descarga**: `href` del `<a itemprop="url">` dentro del artículo. **Ya es
  la URL final del PDF** (ej. `/fileadmin/normatividad/decretos/DECRETO_No.
  _0765_DEL_15_DE_JULIO_DE_2026.pdf`); no hace falta resolver el
  `data-link="t3://file?uid=..."` (ese es un identificador interno de TYPO3,
  no la URL pública). Se resuelve a absoluta con `urljoin` contra
  `https://www.minagricultura.gov.co`.
- **Artículos sin `<a>` de descarga** (raro, pero posible si el archivo se
  cayó del CMS): se descartan silenciosamente, igual que filas sin enlace en
  `mincit`.

**Dato real de calidad inconsistente observado:** dos artículos de Conpes
distintos pueden compartir el mismo `data-title` (ej. dos entradas "CONPES
4076 DE 2022" con `data-info`/`href` distintos, uno de ellos con un desajuste
título/archivo real del sitio: el PDF se llama `CONPES_4080_DE_2022.pdf`).
Esto no se corrige (el scraper no adivina); cada artículo se procesa de forma
independiente y la deduplicación por doc_id ya existente en el pipeline
(basada en URL/contenido, no en título) se encarga de que sean documentos
distintos si sus archivos lo son.

## Fechas

MADR **no expone una fecha de publicación separada de la fecha de expedición**
(a diferencia de `mincit`, que tiene columnas `Fecha de expedición` y `Fecha
de publicación` distintas). Solo hay una fecha, embebida en `data-title`, con
tres niveles de granularidad confirmados por muestreo real:

1. Día + mes + año: `"Ley 2294 del 19 de mayo de 2023"`,
   `"DECRETO 0765 DEL 15 DE JULIO DEL 2026"`,
   `"RESOLUCION 000179 DE MAYO 4 DE 2026"` (orden mes-día invertido),
   `"RESOLUCION 000223 8 DE JULIO DE 2026"` (sin preposición antes del día).
2. Mes + año (sin día): `"LEY 2337 DE OCTUBRE DE 2023"`.
3. Solo año: `"LEY 2311 DE 2023"`, y **siempre** en Conpes
   (`"CONPES 4076 DE 2022"` — ninguna entrada de Conpes trae día ni mes).

Regex en cascada sobre `data-title` (nivel 1 → nivel 2 → nivel 3), tolerante a
mayúsculas/minúsculas y a los dos órdenes día/mes:

- Nivel 1 encontrado → `f_public = "{año}-{mes:02d}-{día:02d}"`.
- Solo nivel 2 → `f_public = "{año}-{mes:02d}-01"` (mismo criterio que
  `adr.py`).
- Solo nivel 3 (o Conpes) → `f_public = "{año}-01-01"` (mismo criterio que
  `ane.py`/`cndj.py` para fechas sin día).

Como solo hay una fecha real, se sigue el patrón de `adr.py`/`ane.py`: se
llena únicamente `f_public` (no se envía `f_providencia`, queda `None`), se
filtra `fini`/`ffin` directamente contra este `f_public` dentro de
`scrap()`, y `filters_by_publication_date` se deja en su default (`False`) —
no aplica declarar un campo de publicación real que el sitio no distingue.

## Nomenclatura del título

`title = f"{LETRA}_MADR_{numero:04d}_{año}"`, donde:

- `LETRA` = `L` (Ley), `D` (Decreto), `R` (Resolución); para Conpes se usa el
  literal `CONPES` en vez de una sola letra (no hay precedente de letra corta
  para Conpes en las familias existentes): `title =
  f"CONPES_MADR_{numero:04d}_{año}"`.
- `MADR` es literal (sigla fija de la fuente).
- `numero` viene de `data-number`, formateado a 4 dígitos con ceros a la
  izquierda (`"765"` → `0765`, `"4076"` → `4076`).
- `año` es el año de la fecha resuelta arriba (`f_public[:4]`).

Ejemplos: `DECRETO 0765 DEL 15 DE JULIO DEL 2026` → `D_MADR_0765_2026`;
`CONPES 4076 DE 2022` → `CONPES_MADR_4076_2022`.

Mismo estilo que `mincit`/`constitucional` (título como código corto y
filename-safe). La descripción legible vive en `detalle`, no en `title`.

**Caso sin número parseable:** si `data-number` viene vacío (se observó al
menos un artículo vacío en Análisis normativos, categoría fuera de alcance,
pero el caso puede repetirse en las 4 categorías incluidas), se usa
`data-title` tal cual como `title` y se marca `title_unverified=True`.

## Manejo de errores

Una categoría cuyo `GET` falle (timeout, 404, HTML sin artículos) no descarta
lo ya recolectado de las demás categorías — se registra vía `on_progress` y se
continúa, igual que el patrón de `adr.py`/`mincit.py`.

## Seed

En `core/seed.py`:
- Nueva entrada en `_FAMILIES`: `"madr": ("Ministerio de Agricultura y
  Desarrollo Rural", "Normativa publicada por el Ministerio de Agricultura y
  Desarrollo Rural")`.
- `repository.create_source_if_missing(db, family_key="madr", name="Ministerio
  de Agricultura y Desarrollo Rural", family_params={})`.

## Frontend

Ningún cambio: Sources, Runs, Documents y el dashboard ("Documentos por
fuente") leen familias/fuentes desde la API sin lógica hardcodeada por
`family_key` (confirmado — solo aparecen claves de familia en fixtures de
test, no en componentes de producción). En cuanto exista el `Source` en la
base de datos, aparece igual que las demás fuentes.

## Pruebas

`tests/families/test_madr.py`, con fixtures de HTML (una página por categoría
con artículos de ejemplo reales anonimizados/recortados), cubriendo:

- Parseo correcto de las 4 categorías (tipo, número, fecha, detalle,
  descarga).
- Los 3 niveles de granularidad de fecha (día+mes+año, mes+año, solo año),
  incluyendo el orden mes-día invertido de Resoluciones.
- Conpes siempre resuelto a nivel 3 (`{año}-01-01`).
- Formato del número a 4 dígitos.
- Nomenclatura del título para cada tipo, incluyendo el literal `CONPES`.
- Caso `title_unverified=True` cuando `data-number`/`data-title` vienen
  vacíos.
- Filtro por `fini`/`ffin` contra `f_public`.
- Una categoría que falla no descarta los documentos de las demás.
