# Fuente Auditoría General de la República (AGR) — diseño

**Fecha:** 2026-11-23
**Entidad:** Auditoría General de la República (`auditoria`, sigla propuesta `AGR`)
**Estado:** pendiente de aprobación del administrador. No se programa nada
hasta que se apruebe.

> El enlace que dio el usuario
> (`https://www.auditoria.gov.co/web/guest/auditoria/normatividad`) es un
> **menú**: el Decreto Ley 272 de 2000 (enlace a Función Pública), el
> normograma interno (intranet, pide sesión) y tres enlaces a los listados
> reales: **Resoluciones internas**, **Circulares** y **Conceptos
> jurídicos**. Cada uno es una biblioteca de documentos de **Liferay**
> (Documents and Media) organizada en carpetas por año.

## Objetivo

Familia de scraper nueva `auditoria`, desde **2015** (año del documento).
Propuesta (a confirmar, preguntas 1-3):

| Sección | Página / carpeta | tipo | título | Docs desde 2015 |
|---|---|---|---|---|
| Conceptos jurídicos | `/auditoria/normatividad/conceptos-juridicos` → `Conceptos AAAA/` | `Concepto` | `CTO_AGR_{número}_{año}` | 845 |
| Resoluciones orgánicas | `/auditoria/normatividad/resoluciones` → `Resoluciones Orgánicas/…AAAA/` | `Resolución orgánica` | `RORG_AGR_{número}_{año}` | 130 |
| Resoluciones reglamentarias | `… → Resoluciones Reglamentarias/…AAAA/` | `Resolución reglamentaria` | `RREG_AGR_{número}_{año}` | 101 |
| Circulares externas | `/auditoria/normatividad/circulares` → `AAAA/[Circulares Externas AAAA/]` | `Circular externa` | `CE_AGR_{número}_{año}` | 65 |
| Circulares conjuntas | ídem (`Circulares Conjuntas 2022/`, sueltas en 2017 y 2021) | `Circular conjunta` | `CJ_AGR_{número}_{año}` | 4 |
| Circulares dispositivas | ídem (`Circulares Dispositivas 2026/`) | `Circular dispositiva` | `CD_AGR_{número}_{año}` | 3 |
| Resoluciones ordinarias (opcional) | `… → Resoluciones Ordinarias/` | `Resolución ordinaria` | `RORD_AGR_{número}_{año}` | 31 |

**Prefijos distintos por clase de resolución:** la AGR numera orgánicas,
reglamentarias y ordinarias con consecutivos independientes (hay una
Orgánica 003 de 2026 y una Reglamentaria 003 de 2026), así que `R_AGR_…`
para todas chocaría. `CE` y `CJ` ya existen en la convención; `RORG`,
`RREG`, `RORD` y `CD` son nuevos (pregunta 4).

Familia **con anexos** (`_A01`) para los pocos casos en que un mismo número
trae un segundo PDF marcado como anexo (ver casos raros); sin actuaciones,
sin `family_params`.

Las **resoluciones ordinarias** publicadas son casi todas ofertas de bienes
dados de baja ("Por la cual se ofrecen unos bienes de propiedad de la AGR
para su enajenación a título gratuito…"): 27 de mayo de 2024, 3 de 2025.
No son normativa; se proponen **fuera** salvo que el usuario las quiera
(pregunta 2).

## Construcción del sitio

- **Liferay DXP 7.x** (portlet `DLPortlet`, documentos en
  `/documents/<groupId>/<folderId>/<nombre>/<uuid>`). Familia modelo de
  Liferay: `supersociedades`. Sin WAF, sin captcha, sin JavaScript
  obligatorio. Pone cookies `JSESSIONID`, `GUEST_LANGUAGE_ID`,
  `COOKIE_SUPPORT` y `cookiesession1` (balanceador); ninguna hace falta.
- **TLS roto:** el servidor envía su certificado (`*.auditoria.gov.co`,
  emitido por *GeoTrust TLS RSA CA G1*, vence 19-01-2027) seguido de un
  intermedio **equivocado** (*Comodo AAA Certificate Services*) en vez del
  G1. `requests` falla con `unable to get local issuer certificate`.
  Completando la cadena con el intermedio real (AIA:
  `http://cacerts.geotrust.com/GeoTrustTLSRSACAG1.crt`) valida bien. Mismo
  caso que Función Pública → **`verify=False` solo para este host**, en la
  sesión y en `link["verify"] = False`, documentado en el código y en la
  guía.
- **API cerrada:** `/o/headless-delivery/v1.0/document-folders/…` y
  `/api/jsonws/dlapp/…` responden `403 Access denied` al invitado. Se lee el
  **HTML** del portlet.
- **Listado de una carpeta:**
  `GET /web/guest/auditoria/normatividad/<página>/-/document_library/<instancia>/view/<folderId>`
  con los parámetros del portlet
  (`_com_liferay_document_library_web_portlet_DLPortlet_INSTANCE_<instancia>_`
  + `deltaEntry`, `curEntry`):

  | Página | Instancia del portlet | Carpeta raíz |
  |---|---|---|
  | `resoluciones` | `Jjx7nXQXAbGp` | (la raíz no pagina; sus 4 subcarpetas: Ordinarias 2799316, Orgánicas 2437712, Reglamentarias 2437715, Repositorio Ofi Jurídica 2437724) |
  | `circulares` | `pgO78BwckEE6` | 108260 |
  | `conceptos-juridicos` | `h6j3F7UA67se` | 108816 |

  - `deltaEntry=500` **se respeta** en las carpetas (`/view/<id>`); en la URL
    de la página sin `/view/<id>` se ignora (siempre 10). Con 500 cada
    carpeta sale en una sola página (la más grande tiene 109).
  - Paginación: texto `Mostrando el intervalo a - b de N resultados.`; si no
    aparece, todo cabe en una página. Se sigue `curEntry` mientras `b < N`
    (con tope de seguridad).
  - Subcarpetas: enlaces `…/document_library/<instancia>/view/<folderId>`
    con texto; se recorren en profundidad (hay dos niveles: `2025/Circulares
    Externas 2025/`).
- **Cada archivo** trae, en la fila del listado:
  - enlace `view_file/<fileEntryId>` (ficha) y
  - enlace de descarga
    `https://www.auditoria.gov.co/documents/20123/<folderId>/<nombre+codificado>.pdf/<uuid>?t=<ms>&download=true`
    con el tamaño en el texto (`Descargar (1,9 MB)`).
- **El menú lateral** de cada página repite un enlace al "Normograma"
  (`/documents/20123/119334/…`): se ignora la carpeta 119334.
- Recorrido completo de las tres bibliotecas: **90 peticiones, ~28 s**
  (≈ 0,3 s cada una, 200-280 KB de HTML).

### Descarga

- `link = {"url": "https://www.auditoria.gov.co/documents/20123/<folderId>/<nombre>/<uuid>", "method": "GET", "verify": False}`
  — **sin `?t=`** (cambia con cada versión del archivo; ver errores
  frecuentes de la guía) y sin `download=true`. Probado: con y sin `?t=`
  responde lo mismo (`200`, `application/pdf`, `Content-Length`,
  `Last-Modified`, `Content-Disposition` con el nombre). Liferay resuelve
  por `uuid`; el segmento del nombre no importa.
- `HEAD` funciona (mismos encabezados): la revisión de republicación por
  tamaño sirve (`checks_for_republication = True`). HEAD a 40 PDF al azar:
  **0 rotos**, mediana 0,02 s.
- Tamaño (según el listado), desde 2015: **1.179 PDF, ≈ 1,6 GB**, mediana
  0,7 MB, el mayor 20 MB. Todos `.pdf` salvo uno sin extensión (concepto
  110.035 de 2019): el descargador ya toma el tipo del `Content-Type`.

## Fechas y filtro

El listado de Liferay **no trae la fecha de expedición**: sólo "modificado
hace N años". Lo que sí hay:

| Dato | De dónde | Qué es |
|---|---|---|
| año del documento | nombre de la carpeta (`Conceptos 2024`, `Res. Orgánicas 2019`, `2018`) y casi siempre también el nombre del archivo | año de expedición |
| fecha de carga | parámetro `?t=<ms epoch>` del enlace de descarga (= `Last-Modified`, = "Creado" de la ficha) | cuándo se subió la versión vigente |

- Para lo cargado desde 2020 la fecha de carga es fiel (días después de
  expedirse: 886 de 1.179 se subieron el mismo año). Lo anterior se migró en
  bloque: casi todo 2011-2018 tiene fecha de carga **17/26/27-09-2019** o
  **08-11-2023**.
- La ficha (`view_file`) sólo repite esas mismas fechas: no aporta la
  expedición y costaría una petición por documento. La fecha real sólo está
  dentro del PDF.

**Propuesta (pregunta 5):**

- `f_public` = fecha de carga (`?t=`, convertida a hora de Bogotá).
  `filters_by_publication_date = True`: el filtro `fini <= f_public <= ffin`
  es exacto y la corrida diaria encuentra lo nuevo sin margen extra (cada
  corrida recorre todo igualmente, ~28 s). `scheduled_min_lookback_days`
  queda en `None`.
- `f_providencia` = `<año>-01-01` (año de la carpeta), como ICBF: el año es
  seguro, el día no se conoce.
- **Piso:** año del documento ≥ 2015 (no la fecha de carga, porque lo viejo
  se cargó en 2019/2023).
- `doc_id_uses_publication_date = False`: si la AGR sube una **versión
  nueva** del mismo archivo, Liferay conserva el `uuid` pero cambia `?t=`;
  así el documento no se duplica y la revisión por tamaño detecta la
  republicación.
- `save_path = storage_path(_SOURCE, f_public, tipo, f"{title}(extension)")`.

## Número y nombre canónico

Se lee del **nombre del archivo** (el título que muestra el listado es el
mismo nombre). Se quitan tildes y se normaliza `N°`/`No.`/`NO_` antes de
buscar.

| Sección | Formatos vistos | Número |
|---|---|---|
| Conceptos | `AGR-Concepto 110.015.2025.De la…`, `AGR_Concepto_110_36_(…)`, `AGR-Concepto-110-010-SIA ATC 083 …`, `Concepto 110.060.2026 Del…`, `AGR-Concepto110. 07.2019` | lo que sigue al código de oficina `110` |
| Res. orgánicas | `Resolución Orgánica No. 003 …`, `Res_Orgánica_015_2022 …`, `Res. Organica 04 de 2019 (…)`, `AGR. Res. Org. 003 - Modifica…` | primer número tras "Orgánica"/"Org." |
| Res. reglamentarias | `Resolución Reglamentaria N° 005 …`, `Res_Reglamentaria_008_2020 (…)`, `Resolución_Reglamentaria_NO_007_2019`, erratas `Reglamenteria`, `Regalmentaria`, `Reglamentarias` | primer número tras la palabra |
| Circulares | `Circular Externa 006 de 2025.pdf`, `AGR_Circular_Externa_005_2021 (…)`, `Circular Dispositiva No. 003 de 2026 …`, `AGR-CGR_Circular_Conjunta_001_de_2021-…` | primer número tras Externa/Conjunta/Dispositiva |

- Título: `{PREFIJO}_AGR_{número:04}_{año}` (relleno a 4 como ICA/ICBF/SSF):
  `CTO_AGR_0015_2025`, `RORG_AGR_0003_2026`, `CE_AGR_0006_2025`.
- **Año = el de la carpeta.** Si el nombre trae otro año, manda la carpeta y
  se avisa (2 casos desde 2015; uno es falso positivo: "Reglamentaria N° 005
  Modifica … la Reglamentaria 010_2024", por eso se toma el **primer**
  número y el año sólo si va pegado a él).
- Sufijo de letra o guion del número se conserva (`110.042A.2011` →
  `CTO_AGR_0042A_2011`, `110.061-1.2011` → `…_0061-1_…`; ambos antes del
  piso).
- **Número ilegible** (hoy ~30 de 2.045, casi todos arreglables con la
  regla de arriba; quedan p. ej. `39-02-2025_010-IGIP.pdf`, `Manual de
  contratación para AGR 2022.pdf`, `AGR CGN. Circular Conjunta (Saneamiento
  contable 2017).pdf`, el año con erratas `110.004.20015`, `110.006.214`,
  `1100.023.2025`) → título con el nombre del archivo saneado,
  `title_unverified=True` y aviso. Con el año de la carpeta, las erratas del
  año no afectan.
- `detalle` = el nombre del archivo sin el número ni la extensión (el
  asunto: "Del proceso de cobro coactivo").

## Casos raros del sitio

| Caso | Qué se hace |
|---|---|
| Mismo archivo en la raíz de Conceptos y en su carpeta del año (4 casos: 110.015.2025, 110.109.2022, 110_08 y 110_09 de 2020; `uuid` distintos) | Dedup por (sección, número, año): se queda el de la carpeta del año, en silencio. |
| Segundo PDF del mismo número marcado como anexo (`Res. Orgánica 02 de 2019 (… ANEXO)`, `Circular Externa 002_2021 (ANEXO_FICHAS…)`, `Circular Externa 12 de 2018_2(ANEXO…)`, `Circular Externa No 004 Manual de Usuario` de 2024) | Si el nombre contiene "anexo" o "manual" → `_A01` del documento principal. |
| Mismo número dos veces con asuntos distintos (`Res. Orgánica 012 de 2020` × 2, `Orgánica 007 de 2024` × 2, `Reglamentaria 009 de 2024` × 2, conceptos 110.055.2018, 110.016.2017, 110.031.2014) | Error de carga o numeración del sitio: se guarda el primero y el segundo como `_A01`, con aviso que nombra los dos archivos. No se "arregla" (pregunta 6). |
| Carpeta `Repositorio Ofi Jurídica` (resoluciones del Minsalud 844 y 1462 de 2020 + 2 ordinarias) | Se ignora: no son actos de la AGR / quedan con las ordinarias. |
| Carpeta 119334 (normograma del menú lateral) | Se ignora. |
| Antes de 2015 (conceptos desde 2001, orgánicas desde 2011, circulares desde 2011) | Fuera por el piso. |

## Volumen esperado (desde 2015, por año del documento)

| Sección | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Conceptos | 28 | 20 | 35 | 67 | 64 | 68 | 91 | 112 | 107 | 101 | 80 | 72 | 845 |
| Res. orgánicas | 4 | 6 | 9 | 10 | 8 | 21 | 11 | 16 | 11 | 13 | 11 | 10 | 130 |
| Res. reglamentarias | 6 | 9 | 9 | 14 | 6 | 11 | 7 | 6 | 4 | 12 | 10 | 7 | 101 |
| Circulares externas | 5 | 5 | 3 | 16 | 2 | 4 | 7 | 6 | 4 | 7 | 6 | 0 | 65 |
| Circulares conjuntas / dispositivas | | | 1 | | | | 2 | 1 | | | | 3 | 7 |
| Res. ordinarias (opcional) | | | | | | | | | | 28 | 3 | | 31 |

(Archivos, no documentos: incluye los anexos y duplicados de la tabla
anterior.) Corrida completa sin ordinarias: **~1.150 PDF, ≈ 1,6 GB,
10-20 min** (el recorrido del listado es ~30 s). Corrida diaria: ~90
peticiones de listado (~30 s) y 0-3 PDF nuevos; la AGR sube ~1-2 conceptos
por semana.

## Fuera de alcance (v1)

- Resoluciones ordinarias (salvo que el usuario las pida, pregunta 2).
- Normograma por procesos (intranet, pide sesión) y el PDF del normograma
  general (lista de leyes y decretos, no actos de la AGR).
- Decreto Ley 272 de 2000 (enlace a Función Pública, que ya tiene su propio
  diseño).
- Resoluciones del Minsalud en "Repositorio Ofi Jurídica".
- Antes de 2015.
- Leer la fecha de expedición dentro del PDF (`resolve_unverified_document`):
  posible v2 si el usuario necesita el día exacto.

## Integración

**Archivos nuevos:** `core/scrapers/families/auditoria.py`
(`@register_family("auditoria")`), `tests/families/test_auditoria.py`.

**Archivos que se tocan:** `core/scrapers/families/__init__.py`,
`core/seed.py` (`_SOURCE = "Auditoría General de la República"`,
`family_params={}`), `tests/test_seed.py` (conteos), ficha en
`docs/guia-despliegue-sistemas.md` (incluye el detalle del certificado).

Sin migración Alembic. En producción: `python -m core.seed` una vez.

## Pruebas

`tests/families/test_auditoria.py`, con `responses` y fragmentos reales del
HTML del portlet (una carpeta con subcarpetas, una con archivos, una con
paginación):

1. Lectura de una carpeta: subcarpetas, archivos (`folderId`, nombre,
   `uuid`, `t`), se ignora la carpeta 119334; texto "Mostrando el intervalo"
   presente y ausente.
2. Enlace: quita `?t=` y `download=true`; `verify` es `False`.
3. `t` → `f_public` en hora de Bogotá (`1716467244362` → `2024-05-23`).
4. Número → título, un caso por formato de la tabla de números (incluidas
   las erratas `Reglamenteria`, `Regalmentaria`, `NO_007`, `N°`, `Res.
   Org.`), relleno a 4, sufijo `A`.
5. Año: el de la carpeta; año distinto en el nombre → aviso; "Modifica la
   Reglamentaria 010_2024" no confunde número ni año.
6. Número ilegible → `title_unverified=True` + aviso.
7. Dedup raíz/carpeta, anexo (`_A01`), número repetido con aviso.
8. Clase de resolución y de circular según carpeta y nombre (`RORG`, `RREG`,
   `CE`, `CJ`, `CD`); "Repositorio Ofi Jurídica" ignorado.
9. Filtro por `f_public` y piso por año del documento;
   `filters_by_publication_date is True`,
   `doc_id_uses_publication_date is False`.
10. `stop_event`, `limit`, una sección que falla (aviso y sigue), sección
    vacía → aviso, tope de paginación.

## Preguntas para el usuario / administrador

1. **Secciones:** ¿conceptos + resoluciones orgánicas y reglamentarias +
   circulares (propuesto)?
2. **Resoluciones ordinarias** (31, casi todas ofertas de bienes dados de
   baja): ¿se dejan fuera (propuesto)?
3. **Piso:** **Respondida (administrador, 2026-11-25):** primero respondió "desde 2015" y luego
   "documentos del 2025 en adelante". Se toma la última, **2025**; falta que
   confirme si aplica a todas las secciones o sólo a los conceptos. Mandó el
   enlace de conceptos (`/auditoria/normatividad/conceptos-juridicos`), que ya
   es el de la tabla de secciones.
4. **Prefijos:** ¿`RORG`/`RREG` (y `RORD`) para las resoluciones y `CD` para
   las circulares dispositivas? ¿Sigla `AGR`? (Hoy sólo existe `AGR` como
   código de especialidad "Asuntos agrarios" de SAMAI, que no va en títulos.)
5. **Fecha:** ¿`f_public` = fecha de carga al sitio y `f_providencia` =
   1 de enero del año del documento (propuesto), aceptando que lo anterior a
   2019 aparece con fecha de carga de 2019 o 2023?
6. **Números repetidos con asunto distinto** (6 casos desde 2015): ¿el
   segundo como `_A01` con aviso (propuesto) o como documento aparte con
   sufijo?

## Plan de implementación (cuando se apruebe)

1. Prueba + lector de carpeta del portlet y enlace limpio (casos 1-3).
2. Prueba + número/año/clase → título, dedup y anexos (casos 4-8).
3. Prueba + `scrap()` con el sitio simulado (casos 9-10).
4. Import en `families/__init__.py`, seed y `tests/test_seed.py`.
5. Corrida real local desde 2015 y segunda corrida sin descargas nuevas.
6. Ficha en `docs/guia-despliegue-sistemas.md`.
