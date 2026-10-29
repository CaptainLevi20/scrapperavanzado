# Fuente CCB (laudos arbitrales) — diseño

**Fecha:** 2026-10-26
**Entidad:** Cámara de Comercio de Bogotá — Centro de Arbitraje y Conciliación (`ccb`, sigla `CCB`)
**Estado:** borrador con las decisiones del usuario (2026-10-26, ver "Decisiones") — pendiente de aprobación del administrador antes de implementar

> El cliente pidió "laudos" y la CDMB no los emite (ver
> `2026-10-21-fuente-cdmb-design.md`): vienen de las cámaras de comercio. La
> URL que dio el usuario
> (`bibliotecadigital.ccb.org.co/browse/dateissued?scope=e88a152e-…`) es la
> **Biblioteca Digital** de la CCB, un **DSpace 7.5**. El `scope` es la
> comunidad **"Arbitraje y Conciliación"** (handle `11520/24359`), que mezcla
> 13 subcomunidades: normas, sentencias, eventos, publicaciones, boletines…
> Los laudos están sólo en la subcomunidad **"C. Laudos Arbitrales"**
> (`3beaa692-cecf-44c7-b0e8-d4179d228431`). Esta familia lee sólo esa.
>
> `www.ccb.org.co` responde **403** a peticiones sin navegador (WAF); no se usa
> ni hace falta: la biblioteca es un host aparte y abierto.

## Objetivo

Familia de scraper nueva `ccb` con una sección, desde **2015** (piso propuesto,
ver "Preguntas abiertas"):

| Sección | Colección DSpace | uuid | Ítems hoy | tipo asignado | prefijo |
|---|---|---|---|---|---|
| Laudos — Arbitraje nacional | `a. Arbitraje nacional` | `66633b37-c004-4701-9685-446a1d42c06d` | 2.106 | `Laudo arbitral` | `LA` |
| Laudos — Arbitraje social | `b. Arbitraje social` | `45acc060-7e3f-4263-9243-06e2b0fc9122` | 50 | `Laudo arbitral` | `LA` |

Las dos colecciones se piden juntas con una sola búsqueda sobre la
subcomunidad (2.155 ítems; uno está en las dos colecciones). Cada laudo (PDF)
entra como un `RawDocModel`. Familia **plana**: sin actuaciones, sin
`family_params`.

## Construcción del sitio

- DSpace 7.5 (frontend Angular + **API REST pública** en
  `https://bibliotecadigital.ccb.org.co/server/api`). Todo se lee por la API
  JSON (HAL); no hace falta HTML.
- **TLS válido** (HSTS), sin captcha ni WAF en este host, sin cookies ni login.
  21 páginas seguidas de 100 ítems + ~70 peticiones de bitstreams sin ningún
  bloqueo ni 429.
- El encabezado `dspace-xsrf-token` sólo aplica a escrituras; las lecturas
  `GET` no lo piden.

### Listado

`GET /server/api/discover/search/objects` con:

| Parámetro | Valor |
|---|---|
| `scope` | `3beaa692-cecf-44c7-b0e8-d4179d228431` (subcomunidad Laudos) |
| `dsoType` | `ITEM` |
| `query` | `dc.date.accessioned_dt:[<fini>T00:00:00Z TO <ffin>T23:59:59Z]` |
| `sort` | `dc.date.accessioned,DESC` |
| `size` / `page` | `100` / `0, 1, …` hasta `page.totalPages` (acepta hasta 500) |

- El filtro por rango **funciona sobre el campo Solr `dc.date.accessioned_dt`**
  (verificado: desde 2026-09-01 → 7 ítems). Ojo: con `dc.date.accessioned:[…]`
  (sin `_dt`) Solr ignora el rango y devuelve los 2.155.
- Opciones de orden disponibles: `score`, `dc.title`, `dc.date.issued`,
  `dc.date.accessioned`.
- Tope duro: 50 páginas.

### Metadatos del ítem (vienen en el listado)

| Campo | Ejemplo | Uso |
|---|---|---|
| `uuid`, `handle` | `438bd93c-…`, `11520/30421` | identidad, detalle |
| `dc.description.radicado` | `159970` | **número** del título |
| `dc.title` | `159970: MANUFACTURAS TERPIEL SAS VS. MOLASASA COL SAS` (nuevos) / `TRIBUNAL ARBITRAL DE … VS. …` (antiguos) | `detalle` |
| `dc.date.issued` | `2026-05-29` | fecha del laudo → `f_providencia`, año del título, piso |
| `dc.date.accessioned` | `2026-10-01T15:09:13Z` | fecha de subida → `f_public` y filtro de la corrida |
| `dc.contributor.convocante` / `convocada` | partes | sólo en `detalle` (vía título) |
| `dc.creator.arbitro`, `dc.creator.secretario`, `dc.subject.contrato`, `dc.subject.proposal` | | no se usan en v1 |
| `dc.type` | vacío / `other` / `book` | `book` = cartilla (ver abajo) |

### Archivo

Un `GET /server/api/core/items/{uuid}/bundles?embed=bitstreams` por ítem. El
PDF está en el bundle **`ORIGINAL`** (los otros: `TEXT` = texto extraído,
`THUMBNAIL`, `LICENSE` → se ignoran). Cada bitstream trae `sizeBytes` y
`checkSum` (MD5).

- Enlace de descarga: `/server/api/core/bitstreams/{uuid}/content`. `GET`
  responde `200/206`, `application/pdf`, `ETag` = MD5, `Content-Disposition`
  con el nombre, y acepta `Range`.
- **`HEAD` no sirve:** responde `200` pero con `Content-Type: application/json`
  y `Content-Length: 1`. El chequeo de republicación del worker
  (`check_remote_content_length`) vería "tamaño 1" y volvería a bajar todo en
  cada corrida → **`checks_for_republication = False`**.
- En 59 de 60 ítems recientes hay un solo PDF en `ORIGINAL`; uno
  (`11520/30015`) trae dos con el mismo nombre. El segundo y siguientes entran
  como `_A01`, `_A02` (convención de anexos).
- Un ítem tiene `dc.embargo.terms` (2026-05-26, ya vencido): su PDF se
  descarga normal. Si algún día un bitstream responde 401/403, el worker lo
  marca como fallo de descarga; no se trata aparte.

## Número y nombre canónico

- **Prefijo `LA` (Laudo arbitral)** — no existe ninguno para laudos en
  `core/naming.py` ni en otras familias (sólo `RALA` de SAMAI, que es el
  *recurso de anulación*). Debe ser **el mismo** que use la fuente de la
  Cámara de Comercio de Armenia, que se diseña en paralelo.
- Laudo → `LA_CCB_{radicado}_{año}` con el año de `dc.date.issued`.
  Ej.: `LA_CCB_159970_2026`, `LA_CCB_148862_2026`. El radicado del Centro va
  **sin relleno** (5-6 dígitos, no es un consecutivo anual).
- Origen del radicado, en orden: `dc.description.radicado` (2.100 de 2.106) →
  número inicial de `dc.title` (`"157594: …"`) → número inicial del nombre del
  PDF (`"151064 ESTEFANIA … .pdf"`). Se toman sólo los dígitos iniciales
  (`"137003Encargo fiduciario"` → `137003`, `"137562\n"` → `137562`).
- Radicados raros: `SN 125` (sin número, sólo antes de 2015), `1133 V`,
  `4920/5468` (dos procesos acumulados → se toma el primero, `4920`).
- **Sin radicado legible** → título = `dc.title` limpio (≤120 caracteres) y
  `title_unverified=True`. No se implementa `resolve_unverified_document` en
  v1 (el PDF no trae el radicado en un lugar fijo).
- **Mismo radicado y año en dos ítems** (17 casos desde 2015): pueden ser el
  **mismo PDF subido dos veces** (p. ej. `11520/29990` y `11520/29987`: MD5
  idéntico) o dos piezas distintas del mismo proceso (laudo y auto de
  aclaración/complementación, fechas distintas). Regla: el mismo MD5 se
  descarta (ver "Deduplicación"); un PDF distinto con el mismo título recibe
  sufijo de fecha: `LA_CCB_142529_2025` y `LA_CCB_142529_2025_0813`
  (MMDD del `dc.date.issued`). Ver "Preguntas abiertas".

## Fechas

- `f_providencia` = `dc.date.issued` (fecha del laudo). 2 ítems traen sólo
  `AAAA-MM` → día `01`. 8 no la traen (todos anteriores a 2015 por su
  título/año de subida) → se usa la fecha de subida y se avisa.
- `f_public` = `dc.date.accessioned` (fecha en que se subió a la biblioteca).
- **La corrida filtra por la fecha de subida**
  (`filters_by_publication_date = True`): el Centro sube los laudos con mucho
  retraso — de lo subido desde 2024: mediana **5 días**, p90 **272 días**,
  máximo **6,4 años**. Filtrando por fecha del laudo, la corrida diaria se
  perdería casi todo; filtrando por subida, cada laudo aparece en la ventana
  del día en que se publica, sin importar su antigüedad.
- Hay 3 ítems con fecha del laudo **posterior** a la de subida (p. ej.
  `11520/30421`: laudo 2026-10-02, subido 2026-03-19). Error del sitio; no se
  corrige, la fecha del laudo queda como la trae.
- `scheduled_min_lookback_days = 7`: margen por si el índice de búsqueda
  tarda en reflejar un ítem recién archivado. No cuesta: la consulta por rango
  devuelve sólo lo subido en esa ventana.
- **La CCB sube por tandas** (2025-11: 26, 2025-12: 33; meses enteros sin
  nada; 2026-07 → 2026-10 sin subidas). `alerta_margen_dias = 120` para que el
  aviso de "fuente que puede estar fallando" no salte en esos huecos.

## Piso de año y rango

- `_ANIO_MINIMO = 2015`, aplicado sobre el **año del laudo**
  (`dc.date.issued`), no sobre la fecha de subida: 1.279 laudos se subieron de
  una vez en 2018, incluidos los de 1985-2014; con el piso por subida
  entrarían todos.
- El rango `fini`/`ffin` va contra la fecha de subida (ver "Fechas"). Una
  carga completa desde el piso se lanza con `fini=2015-01-01` (la subida más
  antigua es de 2016).
- La cartilla "Estructura del Laudo Arbitral CAC - CCB" (`dc.type = book`,
  sin radicado) se excluye por `dc.type`.

## Deduplicación dentro de una corrida

- Clave principal: **`checkSum` MD5 del bitstream** (junta el mismo PDF subido
  en dos ítems). Clave secundaria: `uuid` del bitstream.
- Un ítem que está mapeado en las dos colecciones aparece una sola vez en la
  búsqueda por subcomunidad.

## `save_path` / almacenamiento

`storage_path(_SOURCE, fecha_issued_iso, "Laudo arbitral", f"{title}(extension)")`.
`_SOURCE = "Cámara de Comercio de Bogotá"` (mismo texto que el `name` del seed).
Se usa la fecha del laudo para la carpeta (es la que un abogado busca), no la
de subida.

## Volumen esperado

| Año del laudo | ≤2014 | 2015-2019 | 2020-2023 | 2024 | 2025 | 2026 (a 26-oct) |
|---|---|---|---|---|---|---|
| Nacional | 961 (fuera; incl. 8 sin fecha) | 554 | 362 | 137 | 78 | 14 |
| Social | 13 (fuera) | 2 | 14 | 19 | 2 | 0 |

- Carga completa desde 2015: **~1.180 laudos** (~1.145 nacional + 37 social,
  menos duplicados exactos). PDF grandes (7-30 MB): la descarga pesa varios GB.
- Peticiones de la carga completa: ~22 páginas de listado + 1 por ítem
  (bundles) ≈ 2.200 (se piden también los anteriores a 2015 hasta descartarlos
  por año; ver "Riesgos").
- Corrida diaria: 1 petición de listado + 1 por laudo subido en los últimos 7
  días (0-30, por tandas).

## Fuera de alcance (v1)

- **Resto de la comunidad "Arbitraje y Conciliación"**: B. Sentencias sobre
  los MRC (549: tutelas y autos de otras cortes, ya cubiertas por otras
  fuentes), A. Marco normativo, D-M (eventos, publicaciones, boletines,
  investigaciones, convivencia, conciliación en equidad).
- **J. Arbitraje Internacional** (8 ítems): son guías y "practice notes", no
  laudos.
- Laudos anteriores a 2015 (961 + 13).
- Metadatos ricos (árbitros, secretario, tipo de contrato, pretensiones):
  quedan en el sitio; podrían ir al `detalle` si el cliente lo pide.
- `www.ccb.org.co` (bloqueado a clientes sin navegador; no aporta laudos).

## Integración

**Archivos nuevos:**

- `core/scrapers/families/ccb.py` — `@register_family("ccb")`,
  `class ScrapCcb(BaseScrapper)` con `filters_by_publication_date = True`,
  `checks_for_republication = False`, `scheduled_min_lookback_days = 7`,
  `alerta_margen_dias = 120`.
- `tests/families/test_ccb.py`.

**Archivos que se tocan:**

- `core/scrapers/families/__init__.py` — añadir `ccb` al import.
- `core/seed.py` — entrada en `_FAMILIES` (`"Cámara de Comercio de Bogotá"`,
  "Laudos arbitrales del Centro de Arbitraje y Conciliación de la Cámara de
  Comercio de Bogotá") y
  `create_source_if_missing(db, family_key="ccb", name=_SOURCE, family_params={})`.
- `tests/test_seed.py` — +1 familia y +1 fuente de "fuente única", y `"ccb"`
  en el conjunto de claves y en el comentario. **Los conteos se suben sobre
  lo que haya en `master` al implementar:** la rama de CDMB ya los lleva a 32
  familias / `1 + 28 + 29 + 33 + 6`, y Armenia, Corporinoquia y Corantioquia
  se diseñan en paralelo.
- `docs/guia-despliegue-sistemas.md` — ficha de la fuente (paso 7).

Sin migración Alembic. En producción: `python -m core.seed` una vez.

## Pruebas

`tests/families/test_ccb.py`, con JSON real recortado de la API y `responses`,
sin internet:

1. Ítem nuevo (`"159970: …"`, radicado en metadato) → `LA_CCB_159970_2026`,
   tipo `Laudo arbitral`, `f_providencia` = issued, `f_public` = accessioned,
   URL `/core/bitstreams/{uuid}/content`.
2. Radicado de respaldo: sin `dc.description.radicado`, sale del título; sin
   ninguno de los dos, del nombre del PDF.
3. Radicados sucios: `"137003Encargo fiduciario"`, `"137562\n"`,
   `"4920/5468"` → dígitos iniciales.
4. Sin radicado → `dc.title` y `title_unverified=True`.
5. `dc.date.issued` = `AAAA-MM` → día 01; ausente → fecha de subida + aviso.
6. Piso: laudo de 2014 subido en 2025 → fuera.
7. Consulta: `query` con `dc.date.accessioned_dt:[fini TO ffin]`, `scope` de
   la subcomunidad, paginación hasta `totalPages`.
8. `dc.type = book` → excluido.
9. Mismo MD5 en dos ítems → uno solo, con aviso.
10. Mismo radicado y año, PDF distinto → segundo con sufijo `_MMDD`.
11. Dos PDF en `ORIGINAL` → el segundo con `_A01`; bundles `TEXT`/`THUMBNAIL`
    ignorados.
12. Falla de bundles de un ítem → aviso y sigue con los demás.
13. Falla del listado → aviso, devuelve lo acumulado.
14. `stop_event` y `limit` respetados.
15. Atributos de clase (`filters_by_publication_date`,
    `checks_for_republication`, lookback, margen de alerta).

Se corren dirigidas: `pytest tests/families/test_ccb.py tests/test_seed.py`.

## Riesgos y notas

- **Retraso de publicación de años.** Con el filtro por fecha de subida no se
  pierde nada, pero la fecha de la corrida no coincide con la del laudo: una
  corrida manual "de marzo de 2025" trae lo **subido** en marzo de 2025, que
  pueden ser laudos de 2023. Hay que explicarlo en la ficha de la guía.
- **Carga completa pide bundles de ítems anteriores al piso.** Mejora barata:
  descartar por `dc.date.issued` (ya viene en el listado) **antes** de pedir
  los bundles → la carga completa baja a ~1.200 peticiones de bundles.
- **Sin chequeo de republicación.** Si la CCB reemplaza el PDF de un ítem no
  se detecta. Alternativa futura: comparar el `checkSum` del bitstream con el
  guardado (requiere guardar el MD5; fuera de v1).
- **DSpace 7.5 viejo.** Una migración a DSpace 8/9 conserva la API REST casi
  igual, pero el campo `dc.date.accessioned_dt` del índice podría cambiar; se
  vería como "0 documentos" (alerta a los 120 días) o un error de consulta.
- **Datos del sitio con errores:** 3 laudos con fecha posterior a la subida,
  17 radicados repetidos, PDF duplicados en ítems distintos, 6 ítems sin
  radicado en el metadato.

## Decisiones (2026-10-26)

1. **Piso:** 2015 (≈1.180 laudos), no el archivo completo desde 1985.
2. **Prefijo:** `LA` para laudo arbitral (`LA_CCB_159970_2026`), igual en
   Armenia.
3. **Arbitraje social:** entra, con el mismo tipo `Laudo arbitral`.
4. **Mismo radicado con dos PDF distintos:** sufijo con la fecha `_MMDD` del
   `dc.date.issued` (p. ej. `_0813`).
5. **Sentencias sobre los MRC:** no entran; sólo laudos.
