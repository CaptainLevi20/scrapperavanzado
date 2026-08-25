# Nueva fuente: Normatividad Ministerio del Deporte (MinDeporte) — Design

## Problema

El Ministerio del Deporte publica su normatividad bajo
`https://www.mindeporte.gov.co/transparencia-y-acceso-a-informacion-publica/2-normativa/2-1-normatividad/normatividad-general-y-reglamentaria`,
sobre una plantilla Laravel del catálogo "GOV.CO" (`generator: Micrositios CMS
http://www.micrositios.net`). No encaja en ninguna de las 16 familias
existentes (`core/scrapers/families/`): no es WordPress
(`adr`/`ane`/`anh`/`mininterior`), ni TYPO3 `data-*` (`madr`/`mincit`), ni
AJAX `admin-ajax.php` (`minambiente`). Usa paginación Laravel estándar
(`?page=N`) sobre bloques `<article>` server-renderizados (confirmado con
`curl` plano — el único bundle JS del sitio es TinyMCE para el panel de
administración, no alimenta el listado público). Necesita una familia
técnica dedicada: `mindeporte`.

## Descubrimiento de páginas

Confirmado con fetch directo (`curl`, sin headers especiales — sitio sin
protección anti-bot):

- La URL dada por el usuario es una página "índice" que enlaza a 3 ramas,
  sin documentos propios:
  - `.../resoluciones` → lista de años (2007, 2008, 2011, 2015–2026), cada
    uno con su propia URL `.../resoluciones/{año}` y paginación `?page=N`
    (50 por página; confirmado 57 resoluciones en 2025 repartidas en 2
    páginas).
  - `.../procesos-judiciales` → mismo patrón de años, pero los títulos no
    tienen forma reconocible (`"Admisorio de la Tutela 2020-155"`, `"Actas"`,
    `"Auto Consejo de Estado"`) — sin número ni fecha extraíble.
  - `.../normograma/{categoría}` → 9 categorías, todas **sin partición por
    año** (un solo listado paginado con `?page=N` que cubre todo el
    histórico): `decretos`, `leyes`, `acuerdos`, `conpes`, `directivas`,
    `circulares`, `manuales`, `normativa-en-estado-de-emergencia-por-covid-19`,
    `politicas-de-privacidad-y-condiciones-de-uso`.
- **Orden confirmado descendente por fecha real del acto** en las categorías
  de `normograma` (verificado con fetch de `decretos` páginas 1 y 2: sin
  excepción, cada item tiene fecha igual o anterior al anterior, de 2025
  hasta 1996 en 2 páginas / ~100 decretos). Igual que `mininterior`, esto
  permite parar la paginación en cuanto aparece el primer item **con fecha
  parseable** anterior a `fini`.
- **Todas las categorías comparten el mismo bloque HTML** (mismo componente
  Blade reusado):

  ```html
  <article class="... rounded-xl ...">
    <div class="flex w-full gap-4 p-4">
      <div class="flex flex-col justify-center flex-1 min-w-0 gap-1">
        <a href="/transparencia-.../normograma/decretos/decreto-0855..." class="block ...">
          <p class="text-base font-semibold ...">Decreto 0855 del 30 de julio de 2025</p>
          <p class="mt-1 text-sm leading-tight text-gray-600"><p>"Por medio del cual..."</p></p>
          <p class="mt-1 text-xs text-gray-400">martes, agosto 12 de 2025</p>
        </a>
        <ul class="mt-2 ml-4 text-sm italic text-gray-600 list-disc">
          <li>
            <a href="https://www.mindeporte.gov.co/files/.../Decreto-0855-del-30-julio-2025.pdf" target="_blank">
              Decreto-0855-del-30-julio-2025.pdf <i class="fas fa-file-pdf"></i>
            </a>
          </li>
        </ul>
      </div>
    </div>
  </article>
  ```

  - **Título**: texto de `p.text-base.font-semibold` dentro del primer `<a>`.
  - **Detalle**: texto de `p.mt-1.text-sm.leading-tight.text-gray-600`
    (doblemente envuelto en `<p>`, comillas externas despojadas) —
    **ausente en `circulares`**, donde la descripción viene concatenada
    dentro del propio título.
  - **Fecha de "publicación en el sitio"**: `p.mt-1.text-xs.text-gray-400`
    — verificado no confiable como fecha del acto: sistemáticamente
    posterior (unos días a semanas) a la fecha real que trae el título
    (ej. Resolución fechada "22 de agosto de 2025" con timestamp de sitio
    "6 de agosto" en un caso y "24 de marzo de 2026" en otro para actos
    similares del mismo lote) — mismo patrón de "Publicado" no confiable
    documentado para `minambiente`. Nunca se usa para filtrar ni para
    `f_providencia`; solo alimenta `f_public` de forma informativa.
  - **Enlace**: primer `<a href>` dentro del `<ul class="... list-disc">`
    (siempre se vio un solo `<li>` por artículo en las muestras reales
    revisadas; si apareciera más de uno, solo se toma el primero — anotado
    como límite conocido de v1, no bloquea nada porque no se observó ningún
    caso real con más de un adjunto).
  - Un mismo template para las 9 categorías de `normograma`, más
    `resoluciones`/`procesos-judiciales` (año) y la portada — confirmado
    visitando cada URL con `curl` real.

- **Título por categoría** (muestras reales):
  - Resoluciones: `"Resolución 000634 del 22 de agosto de 2025"`.
  - Decretos: `"Decreto 0855 del 30 de julio de 2025"` / `"Decreto 1306 de
    2023"` (a veces sin día) / `"Decreto reglamentario ley 1946 de 2019"`
    (caso raro sin número propio — ver "Nomenclatura del título").
  - Leyes: `"Ley 2507 del 30 de julio de 2025"` / `"Ley 599 de 2000"`.
  - Acuerdos: `"Acuerdo No. 002 de 1996"` / `"Acuerdo 6 de 1996"`.
  - Conpes: `"Conpes 3248 de 2003"`.
  - Directivas: `"Directiva Presidencial No 2 del 2 de abril de 2019"` /
    `"Directiva ministerial No. 001 de 2021"` — dos prefijos distintos, un
    solo número igual de reconocible en ambos.
  - Circulares: `"Circular interna No. 031: {tema libre} - 22 de diciembre
    de 2025"` / `"Circular externa 003: {tema libre}"` (sin fecha) /
    `"Circular interna No. 017: {tema libre}"` (sin fecha) — el texto tras
    los dos puntos es libre y puede o no terminar en `"- {fecha}"`.

## Alcance (v1)

Mismo criterio que `minambiente`/`madr`: solo categorías con forma de
metadato homogénea, decidido junto con el usuario:

**Entran en v1**: Resoluciones, Decretos, Leyes, Acuerdos, Conpes,
Directivas, Circulares (con parseo dedicado, ver abajo).

**Quedan fuera de v1** (verificado con fetch):
- **Procesos Judiciales**: títulos sin número ni fecha reconocibles
  (`"Actas"`, `"Auto Consejo de Estado"`).
- **Manuales**: página de texto libre (no usa la plantilla de artículo);
  un único PDF suelto embebido en un párrafo de contenido.
- **Normativa en estado de emergencia por COVID-19**: 0 documentos
  (categoría vacía).
- **Políticas de privacidad y condiciones de uso**: no es normatividad.

Se pueden agregar después con su propio diseño, igual que otras fuentes
dejaron pendientes categorías fuera de forma homogénea.

## Familia técnica: `mindeporte`

Archivo nuevo `core/scrapers/families/mindeporte.py`, clase
`ScrapMinDeporte(BaseScrapper)` registrada con `@register_family
("mindeporte")`. Una sola fuente en el seed: `source = "Ministerio del
Deporte"`. Sin `family_params` (`{}`), igual que `mincit`/`madr`/
`mineducacion`/`mininterior`.

## Parseo

Un solo extractor de bloque (`_extraer_articulos`) reusado por las 7
categorías, parametrizado por `(tipo, letra, requiere_año_en_url)`:

- **Resoluciones** (`requiere_año_en_url=True`): primero se pide la página
  raíz `.../resoluciones` para descubrir los años enlazados; solo se piden
  los años dentro de `[fini.year, ffin.year]` (evita pedir años fuera de
  rango). Por cada año en rango, se pagina `.../resoluciones/{año}?page=N`
  hasta que la página no traiga el enlace `rel="next"`.
- **Decretos/Leyes/Acuerdos/Conpes/Directivas/Circulares**
  (`requiere_año_en_url=False`): un único listado en
  `.../normograma/{categoria}?page=N`. Se pagina secuencialmente; para
  cada item con fecha parseable, si la fecha es anterior a `fini` se corta
  la paginación completa (orden descendente confirmado); se sigue pidiendo
  páginas mientras exista el enlace `rel="next"`.

Extracción por artículo (BeautifulSoup, iterando `soup.find_all("article")`):

- **Título del sitio**: texto de `p.text-base.font-semibold` (primer
  `<a>` del artículo).
- **Detalle**: texto de `p.mt-1.text-sm.leading-tight.text-gray-600` si
  existe (ausente en Circulares), comillas externas despojadas.
- **Enlace**: `href` del primer `<a>` dentro de `ul.list-disc` (ya
  absoluto).
- **Número**: primer run de dígitos en el título (`re.search(r"\d+",
  título)`, mismo criterio que `minambiente` en vez del `^\S+\s+(\d+)`
  anclado de `mincit`) — porque el número siempre es el primer dígito que
  aparece en el título en las 7 categorías, incluidas Directivas
  ("Presidencial No 2") y Circulares ("No. 031"). Único caso real donde
  esto captura el número equivocado: `"Decreto reglamentario ley 1946 de
  2019"` (sin número propio, captura el de la ley referenciada) — límite
  conocido y aceptado, igual que el ruido documentado para `minambiente`.
- **Fecha del acto**: se recorta el texto tras el número
  (`_resto_tras_numero`, idéntica técnica que `madr`) y se corre la misma
  cascada de 4 niveles de `madr._FECHA_PATTERN` (día+mes+año / mes+día+año
  invertido / mes+año / solo año) **más un quinto nivel agregado para este
  sitio**: día+mes+año **sin conector "de/del" entre mes y año**
  (`"15 de noviembre 2024"`, visto en una Circular real) — los 4 niveles de
  `madr` exigen ese conector en los tres primeros niveles y en el de
  solo-año, y esta variante real no lo trae.
- **Fecha "de publicación en el sitio"** (`p.mt-1.text-xs.text-gray-400`):
  no se extrae ni se guarda en ningún campo — un item sin fecha del acto
  parseable ya se descarta antes de necesitar cualquier fallback (ver
  "Manejo de errores"), así que este campo nunca tendría un uso real;
  `f_public` siempre es `f_providencia` (la fecha real, la única
  confiable).

## Fechas — por qué se filtra y identifica por `f_providencia`

Igual que `minambiente`/`mininterior`: la fecha de "publicación en el
sitio" es una marca de indexación del CMS, no la fecha real del acto
(confirmado: siempre igual o posterior a la fecha del título, nunca
anterior). Por eso:

- `fini`/`ffin` se filtran contra `f_providencia` (la fecha real extraída
  del título) — `filters_by_publication_date` se deja en su default
  (`False`).
- `doc_id_uses_publication_date` se deja en su default (`True`): a
  diferencia de `minambiente`, aquí no hay evidencia de reindexado
  retroactivo del CMS (el timestamp del sitio siempre avanza hacia
  adelante desde la fecha del acto, nunca salta años hacia atrás o
  adelante como en `minambiente`), así que no hay el mismo riesgo de
  duplicar `doc_id` por un reindexado.
- `checks_for_republication` se deja en su default `True`: el PDF cuelga
  de una URL GET directa (`mindeporte.gov.co/files/...`).

## Nomenclatura del título

Decisión explícita del usuario: mismo estilo que
`madr`/`mincit`/`minambiente`/`mininterior` (código corto normalizado,
consistente entre fuentes) en vez de conservar el título del sitio.

- `title = f"{LETRA}_MDEPORTE_{numero:04d}_{año}"`:
  - `R` — Resolución
  - `D` — Decreto
  - `L` — Ley
  - `A` — Acuerdo
  - `CONPES` — literal, mismo precedente de `madr`/`minambiente`
  - `DIR` — Directiva (Presidencial o ministerial, mismo código para ambas)
  - `C` — Circular (interna o externa, mismo código para ambas — mismo
    precedente de `minambiente`, que usa un solo literal `C_MADS` para las
    suyas)
- **Sin fecha parseable en el título → se descarta el documento** (no se
  guarda con fecha inventada). Este es el caso real de la mayoría de
  Circulares (3 de 6 muestras reales no traen ninguna fecha en el título) y
  de la Circular con el formato sin conector antes descrito si ese quinto
  nivel no la rescatara.
- **Con fecha pero sin número reconocible** (no se observó ningún caso
  real en Resoluciones/Decretos/Leyes/Acuerdos/Conpes/Directivas/
  Circulares durante el descubrimiento, pero se mantiene el fallback por
  consistencia con todas las demás familias): `title` = título crudo del
  sitio, `title_unverified=True`.

## Manejo de errores

Una categoría o año cuyo `GET` falle (timeout, HTTP error) no descarta lo
ya recolectado de las demás — se registra vía `on_progress` y se continúa
(mismo patrón `adr.py`/`madr.py`/`minambiente.py`). Un artículo sin enlace
de descarga o sin fecha parseable se omite individualmente sin afectar el
resto de la página.

## Seed

En `core/seed.py`:
- Nueva entrada en `_FAMILIES`: `"mindeporte"`.
- `repository.create_source_if_missing(db, family_key="mindeporte",
  name="Ministerio del Deporte", family_params={})`.

## Frontend

Ningún cambio: Sources/Runs/Documents/dashboard leen familias/fuentes desde
la API sin lógica hardcodeada por `family_key` (mismo hallazgo que
`minambiente`).

## Pruebas

`tests/families/test_mindeporte.py`, con fixtures de HTML reales
recortados (bloques `<article>` reales tomados de las páginas fetcheadas),
cubriendo:
- El parseo del bloque común (título, detalle, enlace, fecha del sitio).
- Los 5 niveles de fecha, incluido el nuevo nivel sin conector "de/del".
- La extracción de número para las 7 categorías, incluidas Directivas
  (dos prefijos) y Circulares (con y sin fecha en el título).
- El descarte silencioso de un item sin fecha parseable.
- El corte de paginación por fecha fuera de rango en las categorías de
  `normograma` (orden descendente).
- La navegación por año en Resoluciones, limitada a los años dentro de
  `[fini.year, ffin.year]`.
- La nomenclatura del título por categoría, y el fallback `title_unverified`
  cuando no hay número.
- Que `mindeporte` quede registrada en `FAMILY_REGISTRY`.
