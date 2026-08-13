# Nueva fuente: Normatividad Ministerio de Ambiente y Desarrollo Sostenible (MinAmbiente)

## Problema

El Ministerio de Ambiente y Desarrollo Sostenible publica su normatividad en
`https://www.minambiente.gov.co/normativa/`, sobre un tema WordPress a medida
("wp-mads"). No encaja en ninguna de las 12 familias técnicas existentes
(`core/scrapers/families/`): no usa la REST API estándar de WordPress
(`wp-json/wp/v2/...`) como `adr.py`, ni tabla `id="Listado"` como `mincit`, ni
artículos TYPO3 `data-*` como `madr`. El listado real no está en el HTML de
`/normativa/`: se sirve vía un endpoint AJAX propio
(`POST /wp-admin/admin-ajax.php`, `action=normativa_paginacion-load-posts-2`).
Necesita una familia técnica dedicada: `minambiente`.

## Descubrimiento de páginas

Confirmado con fetch directo contra el sitio real (no solo lectura de la
página renderizada):

- `POST https://www.minambiente.gov.co/wp-admin/admin-ajax.php` con
  `action=normativa_paginacion-load-posts-2`, `area1={termID}`, `page=1`.
- El parámetro `page` **no pagina nada** — se probó `page=1` y `page=2` para
  la misma categoría y devolvieron bytes idénticos. Cada categoría trae TODO
  su historial (desde 1959 hasta hoy) en una sola respuesta, agrupado en
  acordeón por año. Un solo `POST` por categoría, sin recorrer años.
- 10 categorías (botones con `termID` en la página), cada una verificada con
  fetch real:

  | Categoría | termID | En v1 |
  |---|---|---|
  | Resoluciones | 46 | Sí |
  | Leyes | 47 | Sí |
  | Decretos | 48 | Sí |
  | Autos | 58 | Sí |
  | Conpes | 61 | Sí |
  | Conceptos | 962 | Sí (estructura especial) |
  | Agenda Regulatoria | 59 | No |
  | Circulares | 60 | No |
  | Boletín Legal | 956 | No |
  | Boletín Legal Decretos | 961 | No |

## Alcance (v1)

Mismo criterio que `madr.py` (ver
`2026-07-30-fuente-minagricultura-design.md`): solo categorías con forma de
metadato homogénea entran en v1.

Quedan fuera de v1 (verificado con fetch):

- **Agenda Regulatoria**: títulos versionados sin número de acto
  (`"Agenda Regulatoria V4 2026"`, `"Agenda Regulatoria 2025 Versión 7"`).
- **Circulares**: el "número" es un código de radicado largo
  (`"Circular 10002026E4000041 del 23 de julio de 2026"`), no un consecutivo
  corto; al menos una entrada real no tiene número en absoluto. No hay
  nomenclatura limpia que aplicar.
- **Boletín Legal** y **Boletín Legal Decretos**: sus enlaces no son PDFs de
  MinAmbiente, son páginas externas de `suin-juriscol.gov.co`
  (`viewDocument.asp?ruta=...`). No hay archivo descargable, y el contenido
  ya está cubierto por Leyes/Decretos (v1) desde la fuente original.

Se pueden agregar después con su propio diseño, igual que MADR dejó
pendientes Jurisprudencia/Notificaciones/Agenda regulatoria/Análisis
normativos.

## Familia técnica: `minambiente`

Archivo nuevo `core/scrapers/families/minambiente.py`, registrado con
`@register_family("minambiente")`. Una sola fuente en el seed:
`source = "Ministerio de Ambiente y Desarrollo Sostenible"`.

## Parseo — dos formas de bloque

### 1) Resoluciones/Leyes/Decretos/Autos/Conpes

Bloque `div.row.box-docgd` (BeautifulSoup, iterando por categoría):

```html
<div class="row box-docgd">
  <div class="col-md-10">
    <div><a class="documento-normativa" href="...pdf" title="Auto No. 127 de 2026">Auto No. 127 de 2026</a></div>
    <div><p class="descripcion-archivo">"Por medio del cual..."</p></div>
    <div><span class="txt-peque-archivo">Publicado: agosto 11, 2026</span></div>
  </div>
</div>
```

- **Enlace**: `href` de `a.documento-normativa` (ya absoluto).
- **Detalle**: texto de `p.descripcion-archivo`, comillas externas
  despojadas.
- **Fecha del acto y número**: extraídos del texto del título con la MISMA
  técnica de cascada de `madr.py` (`_resto_tras_numero` + `_FECHA_PATTERN`,
  4 niveles: día+mes+año / mes+día+año invertido / mes+año / solo año),
  reutilizada tal cual porque los formatos reales vistos aquí son idénticos
  en forma (`"Decreto 0766 del 15 julio de 2026"`,
  `"Decreto 1248 de 26 de julio del 2023"`, `"Ley 2294 de 2023"`). El número
  se extrae con `re.search(r"\d+", título)` (primer run de dígitos) en vez
  del `^\S+\s+(\d+)` de `mincit`, porque hay ruido real antes del tipo
  (`"Actualizada – Res 0953 del 03 de Septiembre de 2021"`).
- **Fecha "Publicado:"**: un solo formato fijo, `"Publicado: {mes} {día},
  {año}"` en español sin cero a la izquierda — confirmado en 133+111+104+
  109+33 muestras reales.

### 2) Conceptos (estructura distinta — no usa el parseo genérico)

El enlace de nivel superior de cada año (`a.documento-normativa`) apunta a
un CSV índice (`Conceptos-CSV.csv`), **no** a un documento real. Los
documentos reales están en una tabla HTML embebida dentro de
`p.descripcion-archivo`, columnas `N° | Fecha | Rad. Salida | Tema |
Descarga`:

```html
<td>178</td><td>12/08/2025</td><td>concep_028506</td>
<td>Cesion Permisos De Emisio</td>
<td><a href="....pdf">concep_250812_028506</a></td>
```

Se itera `table tr` dentro de cada `box-docgd` de la categoría Conceptos
(saltando encabezado). Confirmado con fetch: de 42 años listados, solo 4
tienen contenido real (los demás son placeholders vacíos marcados
`display:none`, se ignoran naturalmente al no tener tabla).

## Fechas — por qué se filtra por `f_providencia`, no por "Publicado"

**Verificado con fetch real: "Publicado:" no es confiable como fecha del
acto.** Un mismo Decreto de 2022 aparece con `Publicado: julio 10, 2024` —
dos años después, un artefacto de reindexado/migración del CMS del sitio, no
la fecha real del acto. Por eso:

- `fini`/`ffin` se filtran contra `f_providencia` (la fecha real, extraída
  del título) — `filters_by_publication_date` se deja en su default
  (`False`).
- `doc_id_uses_publication_date = False`: si el doc_id dependiera de
  `f_public` (que alimenta "Publicado"), un simple reindexado del sitio
  generaría un doc_id nuevo para el mismo archivo y lo duplicaría en la base
  de datos — mismo riesgo documentado para `rama_judicial`/`samai` con sus
  propios campos de fecha inestables.
- `f_public` es obligatorio en `RawDocModel`, así que sigue llenándose con
  el valor de "Publicado" (informativo, se muestra en la UI) cuando existe;
  si faltara (raro), se usa `f_providencia` como respaldo.
- Conceptos solo tiene una fecha real (columna `Fecha` de la tabla): se
  guarda en `f_providencia` y se duplica en `f_public` (por el mismo
  requisito de campo obligatorio), sin el riesgo de reindexado de las demás
  categorías.

## Nomenclatura del título

Mismo estilo que `madr`/`mincit` (código corto, filename-safe; la
descripción legible vive en `detalle`):

- `title = f"{LETRA}_MADS_{numero:04d}_{año}"` — `R` (Resolución), `D`
  (Decreto), `L` (Ley), `A` (Auto). `MADS` es la sigla oficial del
  Ministerio de Ambiente y Desarrollo Sostenible.
- `title = f"CONPES_MADS_{numero:04d}_{año}"` (literal `CONPES`, mismo
  precedente de `madr`).
- `title = f"CONCEPTO_MADS_{rad_salida}"` para Conceptos, usando el código
  de `Rad. Salida` (ej. `concep_250812_028506`) — ya único y filename-safe.
- **Sin número o sin fecha parseable**: `title` = texto crudo del sitio,
  `title_unverified=True` (mismo fallback que `madr`/`mincit`).

## Manejo de errores

Una categoría cuyo `POST` falle (timeout, HTTP error) no descarta lo ya
recolectado de las demás — se registra vía `on_progress` y se continúa
(patrón `adr.py`/`madr.py`).

## Seed

En `core/seed.py`:
- Nueva entrada en `_FAMILIES`: `"minambiente"`.
- `repository.create_source_if_missing(db, family_key="minambiente",
  name="Ministerio de Ambiente y Desarrollo Sostenible", family_params={})`.

## Frontend

Ningún cambio: confirmado que Sources/Runs/Documents/dashboard leen
familias/fuentes desde la API sin lógica hardcodeada por `family_key`.

## Pruebas

`tests/families/test_minambiente.py`, con fixtures de HTML reales
recortados y `responses` (con `matchers.urlencoded_params_matcher` para
distinguir categorías por `area1`, ya que todas comparten la misma URL de
`admin-ajax.php`), cubriendo el parseo de ambos tipos de bloque, los 4
niveles de fecha, el fallback de `f_public` a `f_providencia`, la
nomenclatura por tipo, `title_unverified`, el filtro por `f_providencia`, y
que `doc_id_uses_publication_date` quede en `False`.
