# Fuente Auditoría General de la República (AGR) — diseño

**Fecha:** 2026-11-23 (revisado 2026-11-26 con las decisiones del
administrador y una revisión contra el sitio en vivo)
**Entidad:** Auditoría General de la República (`auditoria`, sigla propuesta `AGR`)
**Estado:** aprobado por el administrador el 2026-11-26. Implementado en
`core/scrapers/families/auditoria.py` (plan:
`docs/superpowers/plans/2026-11-26-fuente-auditoria.md`).

> El enlace que dio el usuario
> (`https://www.auditoria.gov.co/web/guest/auditoria/normatividad`) es un
> **menú**: el Decreto Ley 272 de 2000 (enlace a Función Pública), el
> normograma interno (intranet, pide sesión) y tres enlaces a los listados
> reales: **Resoluciones internas**, **Circulares** y **Conceptos
> jurídicos**. Cada uno es una biblioteca de documentos de **Liferay**
> (Documents and Media) organizada en carpetas por año.

## Objetivo

Familia de scraper nueva `auditoria`, desde **2025** (año del documento;
piso decidido por el administrador, pregunta 3).
Propuesta (a confirmar, preguntas 1 y 2):

| Sección | Página / carpeta | tipo | título | Archivos desde 2025 |
|---|---|---|---|---|
| Conceptos jurídicos | `/auditoria/normatividad/conceptos-juridicos` → `Conceptos AAAA/` | `Concepto` | `CTO_AGR_{número}_{año}` | 152 |
| Resoluciones orgánicas | `/auditoria/normatividad/resoluciones` → `Resoluciones Orgánicas/…AAAA/` | `Resolución orgánica` | `R_AGR_ORG-{número}_{año}` | 21 |
| Resoluciones reglamentarias | `… → Resoluciones Reglamentarias/…AAAA/` | `Resolución reglamentaria` | `R_AGR_REG-{número}_{año}` | 17 |
| Circulares externas | `/auditoria/normatividad/circulares` → `AAAA/Circulares Externas AAAA/` | `Circular externa` | `CE_AGR_{número}_{año}` | 6 |
| Circulares conjuntas | ídem (`Circulares Conjuntas AAAA/`) | `Circular conjunta` | `CJ_AGR_{número}_{año}` | 0 (hoy) |
| Circulares dispositivas | ídem (`Circulares Dispositivas 2026/`) | `Circular dispositiva` | `CD_AGR_{número}_{año}` | 3 |
| Resoluciones ordinarias (opcional) | `… → Resoluciones Ordinarias/` | `Resolución ordinaria` | `R_AGR_ORD-{número}_{año}` | 3 |

**La clase de resolución va en el número** (decisión del administrador,
2026-11-26): la AGR numera orgánicas, reglamentarias y ordinarias con
consecutivos independientes (hay una Orgánica 003 de 2026 y una
Reglamentaria 003 de 2026), así que el título lleva la clase delante del
número y conserva el prefijo `R`: `R_AGR_ORG-003_2026`,
`R_AGR_REG-003_2026`. Es el mismo estilo que la Contraloría
(`R_CGR_OGZ-0897_2026`): clase, guion y número, todo en el segmento del
número. `CE` y `CJ` ya existen en la convención; `CD` es nuevo
(pregunta 4).

Familia **con anexos** (`_A01`) para los pocos casos en que un mismo número
trae un segundo PDF marcado como anexo (ver casos raros); sin actuaciones,
sin `family_params`.

Las **resoluciones ordinarias** publicadas son casi todas ofertas de bienes
dados de baja ("Por la cual se ofrecen unos bienes de propiedad de la AGR
para su enajenación a título gratuito…"): 27 de mayo de 2024, 3 de 2025.
No son normativa; se proponen **fuera** salvo que el usuario las quiera
(pregunta 2). Con el piso 2025 sólo serían 3.

## Construcción del sitio

- **Liferay DXP 7.x** (portlet `DLPortlet`, documentos en
  `/documents/<groupId>/<folderId>/<nombre>/<uuid>`). Familia modelo de
  Liferay: `supersociedades`. Sin WAF, sin captcha, sin JavaScript
  obligatorio. Pone cookies `JSESSIONID`, `GUEST_LANGUAGE_ID`,
  `COOKIE_SUPPORT` y `cookiesession1` (balanceador); ninguna hace falta.
- **TLS roto** (comprobado de nuevo el 2026-11-26): el servidor envía su
  certificado (`*.auditoria.gov.co`, emitido por *GeoTrust TLS RSA CA G1*,
  vence 19-01-2027) seguido de un intermedio **equivocado** (*Comodo AAA
  Certificate Services*) en vez del G1. `requests` falla con
  `CERTIFICATE_VERIFY_FAILED` / `unable to get local issuer certificate`.
  Completando la cadena con el intermedio real (AIA:
  `http://cacerts.geotrust.com/GeoTrustTLSRSACAG1.crt`) valida bien. Mismo
  caso que Función Pública → **`verify=False` solo para este host**, en la
  sesión y en `link["verify"] = False`, documentado en el código y en la
  guía. (La revisión por tamaño con `HEAD` ya respeta `verify`, PR #77.)
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
  - Paginación: texto `Mostrando el intervalo a - b de N resultados.`
    (aparece también cuando todo cabe en una página: `1 - 79 de 79`); si no
    aparece, todo cabe en una página. Se sigue `curEntry` mientras `b < N`
    (con tope de seguridad). Probado con `deltaEntry=20`: `1 - 20 de 79` y,
    con `curEntry=2`, `21 - 40 de 79`.
  - Subcarpetas: enlaces `…/document_library/<instancia>/view/<folderId>`
    con texto; se recorren en profundidad (hay dos niveles: `2025/Circulares
    Externas 2025/`).
  - **Enlaces que no son subcarpetas:** cada página repite varios enlaces
    `…/view/<folderId de la misma carpeta>` (el selector de tamaño de
    página: textos `5`, `10`, `20`, `30`, `50`, `75`). Se descartan los
    enlaces a la carpeta que se está leyendo; si no, el recorrido se repite.
  - **Carpetas por debajo del piso:** el nombre de cada subcarpeta trae el
    año (`Conceptos 2024`, `Res. Orgánicas 2019`, `Res. Orgánica 2026`,
    `Organica 2014`, `2018`, `Circulares Externas 2025`,
    `RESOLUCIONES ORDINARIAS 2025`). Si el nombre trae un año menor que el
    piso, **la carpeta no se abre**. Las carpetas sin año en el nombre
    (`Resoluciones Orgánicas`, `Circulares Externas`…) se abren siempre.
    Así una carpeta nueva (`Conceptos 2027`) entra sola.
- **Cada archivo** trae, en la fila del listado:
  - enlace `view_file/<fileEntryId>` (ficha) y
  - enlace de descarga
    `https://www.auditoria.gov.co/documents/20123/<folderId>/<nombre+codificado>.pdf/<uuid>?t=<ms>&download=true`
    con el tamaño en el texto (`Descargar (1,9 MB)`).
  - El mismo archivo aparece **tres veces** en el HTML: miniatura
    (`?version=1.0&t=…&documentThumbnail=1`), vista (`?version=…`) y
    descarga (`?t=…&download=true`). Se toma sólo el de descarga y se
    **deduplica por `uuid`** dentro de la carpeta.
- **El menú lateral** de cada página repite un enlace al "Normograma"
  (`/documents/20123/119334/…`): se ignora la carpeta 119334.
- Recorrido con el piso 2025: unas **15 peticiones de listado** (raíces,
  carpetas 2025/2026 y sus subcarpetas), unos 5 s. (Recorrer las tres
  bibliotecas completas eran 90 peticiones, ~28 s.)

### Descarga

- `link = {"url": "https://www.auditoria.gov.co/documents/20123/<folderId>/<nombre>/<uuid>", "method": "GET", "verify": False}`
  — **sin `?t=`** (cambia con cada versión del archivo; ver errores
  frecuentes de la guía) y sin `download=true`. Probado (2026-11-26): con y
  sin `?t=` responde lo mismo (`200`, `application/pdf`, `Content-Length`,
  `Last-Modified`, `Content-Disposition` con el nombre). Liferay resuelve
  por `uuid`; el segmento del nombre no importa (con un nombre inventado y
  el mismo `uuid` entrega el mismo archivo).
- `HEAD` funciona (mismos encabezados): la revisión de republicación por
  tamaño sirve (`checks_for_republication = True`). HEAD a 40 PDF al azar:
  **0 rotos**, mediana 0,02 s.
- Tamaño: mediana 0,7 MB, el mayor 20 MB (medido sobre todo el sitio).
  Desde 2025 son ~200 archivos, del orden de **0,2 GB** (estimado con la
  mediana). Todos `.pdf`: el descargador toma la extensión del
  `Content-Type` (el `Content-Disposition` viene como `filename*=UTF-8''…`,
  que `extract_filename` no lee, y no hace falta).

## Fechas y filtro

El listado de Liferay **no trae la fecha de expedición**: sólo "modificado
hace N años". Lo que sí hay:

| Dato | De dónde | Qué es |
|---|---|---|
| año del documento | nombre de la carpeta (`Conceptos 2025`, `Res. Orgánica 2026`, `2025`) y casi siempre también el nombre del archivo | año de expedición |
| fecha de carga | parámetro `?t=<ms epoch>` del enlace de descarga (= `Last-Modified`, = "Creado" de la ficha) | cuándo se subió la versión vigente |

- Para lo de 2025 en adelante la fecha de carga es fiel: días o semanas
  después de expedirse (p. ej. la Orgánica 010 de 2025 se subió el
  05-01-2026). Lo anterior a 2020 se migró en bloque (cargas de 2019 y
  2023), pero queda por debajo del piso.
- La ficha (`view_file`) sólo repite esas mismas fechas: no aporta la
  expedición y costaría una petición por documento. La fecha real sólo está
  dentro del PDF.

**Propuesta (pregunta 5):**

- `f_public` = fecha de carga (`?t=`, convertida a hora de Bogotá).
  `filters_by_publication_date = True`: el filtro `fini <= f_public <= ffin`
  es exacto y la corrida diaria encuentra lo nuevo sin margen extra (cada
  corrida recorre todas las carpetas desde el piso, ~5 s).
  `scheduled_min_lookback_days` queda en `None`.
- `f_providencia` = `<año>-01-01` (año de la carpeta), como ICBF: el año es
  seguro, el día no se conoce.
- **Piso: año del documento ≥ 2025** (el de la carpeta; no la fecha de
  carga). Se aplica dos veces: no se abren carpetas con año < 2025 y, en
  las carpetas sin año (la raíz de Conceptos), se descarta el archivo cuyo
  año (del nombre) es < 2025.
- **Corrida manual por rango:** como el filtro es por fecha de carga, un
  rango manual encuentra los documentos por cuándo se subieron, no por
  cuándo se expidieron (un documento de diciembre de 2025 subido en enero de
  2026 sale en el rango de 2026). Se anota en la ficha de despliegue.
- `doc_id_uses_publication_date = False`: si la AGR sube una **versión
  nueva** del mismo archivo, Liferay conserva el `uuid` pero cambia `?t=`;
  así el documento no se duplica y la revisión por tamaño detecta la
  republicación.
- `save_path = storage_path(_SOURCE, f_public, tipo, f"{title}(extension)")`.

## Número y nombre canónico

Se lee del **nombre del archivo** (el título que muestra el listado es el
mismo nombre). Se quitan tildes y se normaliza `N°`/`No.`/`NO_` antes de
buscar.

**El número se copia tal como lo escribe la AGR** (decisión del
administrador, 2026-11-26): sin rellenar con ceros ni quitarlos. Si la AGR
escribe `015`, el título lleva `015`; si escribe `08`, lleva `08`.

| Sección | Formatos vistos (desde 2025) | Número |
|---|---|---|
| Conceptos | `AGR-Concepto 110.015.2025.De la…`, `AGR -Concepto 110.014.2025. De la…`, `AGR- Concepto 110.019.2026 Del…`, `Concepto 110.060.2026 Del…`, **con ordinal delante:** `13. AGR- Concepto 110.022.2026 …`, `6. Concepto 110.072.2026 …`, `4.  Concepto 110.070.2026 …`; errata del código: `AGR -Concepto 1100.023.2025.` | lo que sigue al código de oficina `110` (se tolera `1100`) |
| Res. orgánicas | `Resolución Orgánica No. 003 …`, `Resolución Orgánica 001 Por la cual…`, `Resolución Orgánica No. 008_2025 …` (antes de 2025 también `Res_Orgánica_015_2022`, `Res. Organica 04 de 2019`, `AGR. Res. Org. 003 - …`) | primer número tras "Orgánica"/"Org." |
| Res. reglamentarias | `Res_Reglamentaria No. 001_2025 …`, `Resolución Reglamentaria N° 005 …`, `Resolución Reglamentaria No 007 …`, `Resolución Reglamentaria No. 001 de 2026 …` (antes de 2025 también `NO_007_2019` y erratas `Reglamenteria`, `Regalmentaria`, `Reglamentarias`) | primer número tras la palabra |
| Circulares | `Circular Externa 006 de 2025.pdf`, `Circular Externa 004 DE 2025.pdf`, `Circular Dispositiva No. 003 de 2026 …` (antes de 2025 también `AGR_Circular_Externa_005_2021 (…)`, `AGR-CGR_Circular_Conjunta_001_de_2021-…`) | primer número tras Externa/Conjunta/Dispositiva |

- **Ordinal delante (conceptos de 2026):** muchos nombres empiezan con un
  número de orden de la carga (`13. `, `6. `, `4.  `) que **no** es el
  número del concepto. La regla "lo que sigue al código `110`" lo salta;
  el ordinal no entra al título ni al `detalle`.
- Título: `{PREFIJO}_AGR_{número}_{año}` con el número tal cual:
  `CTO_AGR_015_2025`, `CTO_AGR_022_2026` (del `13. AGR- Concepto
  110.022.2026`), `CTO_AGR_023_2025` (del `1100.023.2025`),
  `R_AGR_ORG-003_2026`, `R_AGR_REG-001_2025`, `R_AGR_ORD-{n}_2025`,
  `CE_AGR_006_2025`, `CD_AGR_003_2026`.
- **Año = el de la carpeta.** Si el nombre trae otro año, manda la carpeta y
  se avisa. Cuidado con los falsos positivos: "Reglamentaria N° 005
  Modifica … la Reglamentaria 010_2024" (carpeta 2026) o "Orgánica No. 003
  Por la cual se incluye un parágrafo transitorio Res_011_2024" (carpeta
  2025): por eso se toma el **primer** número y el año sólo si va pegado a
  él.
- Sufijo de letra o guion del número se conserva tal cual (antes del piso
  había `110.042A.2011`, `110.061-1.2011`; hoy no hay casos desde 2025).
- **Número ilegible** → título con el nombre del archivo saneado,
  `title_unverified=True` y aviso. Desde 2025 sólo queda
  `39-02-2025_010-IGIP.pdf`, que se trata como anexo (ver casos raros).
  Con el año de la carpeta, las erratas del año no afectan.
- `detalle` = el nombre del archivo sin el ordinal, sin el número ni la
  extensión (el asunto: "Del proceso de cobro coactivo").
- **Comparación para dedup:** el título lleva el número tal cual, pero para
  decidir si dos archivos son el mismo número se compara el valor
  (`008` = `08` = `8`, conservando la letra del sufijo).

### Clase de circular

En las carpetas de año de Circulares (`2025/`, `2026/`) **no hay archivos
sueltos**: todos están en subcarpetas `Circulares Externas AAAA/`,
`Circulares Dispositivas AAAA/` (y antes `Circulares Conjuntas AAAA/`). La
clase (`CE`/`CJ`/`CD`) sale del **nombre de la subcarpeta**; si un archivo
aparece suelto en la carpeta del año (pasó en 2017 y 2021), sale de la
palabra del nombre del archivo (Externa/Conjunta/Dispositiva). Si ninguna
de las dos la da → `CE` con `title_unverified=True` y aviso.

## Casos raros del sitio

| Caso | Qué se hace |
|---|---|
| Mismo archivo en la raíz de Conceptos y en su carpeta del año (desde 2025: `110.015.2025`; `uuid` distintos) | Dedup por (sección, número, año): se queda el de la carpeta del año, en silencio. Los archivos de la raíz toman el año del nombre; si el nombre no trae año (hoy `AGR-Concepto-110-009-SIA-ATC.080…` y `AGR-Concepto-110-010-SIA ATC 083…`) no se puede saber si pasan el piso: se omiten con aviso. |
| Archivo en la carpeta de resoluciones del año **sin clase en el nombre** pero con el número de una resolución de la misma carpeta: `39-02-2025_010-IGIP.pdf` en `Res. Orgánicas 2025` (subido 01-06-2026; escaneo de 3 páginas con el sello "010 30 DIC 2025"; la Orgánica 010 de 2025 es la que adopta los instrumentos IGIP) | Se toma como `_A01` de esa resolución (`R_AGR_ORG-010_2025_A01`), con aviso. Puede ser un anexo o la copia firmada; no se abre el PDF para decidirlo. Regla: nombre sin clase reconocible + `_<n>-` o `_<n>_` que coincide con un número ya visto en la carpeta. Si no coincide con ninguno → `title_unverified=True` y aviso. |
| Segundo PDF del mismo número marcado como anexo (antes del piso: `Res. Orgánica 02 de 2019 (… ANEXO)`, `Circular Externa 002_2021 (ANEXO_FICHAS…)`, `Circular Externa No 004 Manual de Usuario` de 2024) | Si el nombre contiene "anexo" o "manual" → `_A01` del documento principal. Hoy no hay casos desde 2025, pero la regla se deja. |
| Mismo número dos veces con asuntos distintos (todos antes del piso: Orgánica 012 de 2020, Orgánica 007 de 2024, Reglamentaria 009 de 2024, conceptos 2014-2018) | Hoy no hay casos desde 2025. Si aparece: se guarda el primero y el segundo como `_A01`, con aviso que nombra los dos archivos. No se "arregla" (pregunta 6). |
| Carpeta `Repositorio Ofi Jurídica` (subcarpetas `Ordinaria` y `Resoluciones Minsalud`: resoluciones del Minsalud 844 y 1462 de 2020 + 2 ordinarias) | Se ignora: no son actos de la AGR / quedan con las ordinarias. |
| Carpeta 119334 (normograma del menú lateral) | Se ignora. |
| Antes de 2025 (conceptos desde 2001, orgánicas desde 2011, circulares desde 2011) | Fuera por el piso; esas carpetas ni se abren. |
| La `Circular Conjunta 001 de 2021` AGR-CGR es el mismo acto que la `Circular Conjunta 0001-2021` de la Contraloría | Antes del piso de la AGR; no aplica hoy. Si una conjunta futura sale en las dos fuentes, quedará dos veces (una por entidad), como cualquier acto conjunto. |

## Volumen esperado (desde 2025, por año del documento)

Contado en el sitio el 2026-11-26.

| Sección | 2025 | 2026 | Total |
|---|---|---|---|
| Conceptos | 80 (79 + 1 repetido en la raíz) | 72 | 152 |
| Res. orgánicas | 11 (incluye el `39-02-2025_010-IGIP`) | 10 | 21 |
| Res. reglamentarias | 10 | 7 | 17 |
| Circulares externas | 6 | 0 | 6 |
| Circulares dispositivas | | 3 | 3 |
| Res. ordinarias (opcional) | 3 | | 3 |

(Archivos, no documentos: incluye el anexo y el repetido de la raíz.)
Corrida completa sin ordinarias: **~199 archivos (~198 documentos),
del orden de 0,2 GB, pocos minutos**. Corrida diaria: ~15 peticiones de
listado (~5 s) y 0-3 PDF nuevos; la AGR sube ~1-2 conceptos por semana.

## Fuera de alcance (v1)

- Resoluciones ordinarias (salvo que el usuario las pida, pregunta 2).
- Normograma por procesos (intranet, pide sesión) y el PDF del normograma
  general (lista de leyes y decretos, no actos de la AGR).
- Decreto Ley 272 de 2000 (enlace a Función Pública, que ya tiene su propio
  diseño).
- Resoluciones del Minsalud en "Repositorio Ofi Jurídica".
- Antes de 2025.
- Leer la fecha de expedición dentro del PDF (`resolve_unverified_document`):
  posible v2 si el usuario necesita el día exacto.

## Integración

**Archivos nuevos:** `core/scrapers/families/auditoria.py`
(`@register_family("auditoria")`), `tests/families/test_auditoria.py`.

**Archivos que se tocan:** `core/scrapers/families/__init__.py`,
`core/seed.py` (`_SOURCE = "Auditoría General de la República"`,
`family_params={}`), `tests/test_seed.py` (conteos), ficha en
`docs/guia-despliegue-sistemas.md` (incluye el detalle del certificado y
que el rango manual va por fecha de carga).

Sin migración Alembic. En producción: `python -m core.seed` una vez.

## Pruebas

`tests/families/test_auditoria.py`, con `responses` y fragmentos reales del
HTML del portlet (una carpeta con subcarpetas, una con archivos, una con
paginación):

1. Lectura de una carpeta: subcarpetas, archivos (`folderId`, nombre,
   `uuid`, `t`), se ignora la carpeta 119334; se descartan los enlaces del
   selector de tamaño (`view/<misma carpeta>`); el archivo que aparece
   tres veces (miniatura, vista, descarga) sale una sola vez (dedup por
   `uuid`); texto "Mostrando el intervalo" presente y ausente.
2. Enlace: quita `?t=` y `download=true`; `verify` es `False`.
3. `t` → `f_public` en hora de Bogotá (`1716467244362` → `2024-05-23`).
4. Número → título, un caso por formato de la tabla de números, con el
   número **tal cual**: `110.015.2025` → `CTO_AGR_015_2025`; ordinal
   delante (`13. AGR- Concepto 110.022.2026` → `CTO_AGR_022_2026`, `4.
   Concepto 110.070.2026` → `CTO_AGR_070_2026`); `1100.023.2025` →
   `CTO_AGR_023_2025`; `Resolución Orgánica No. 003` → `R_AGR_ORG-003_2026`;
   `Res_Reglamentaria No. 001_2025` → `R_AGR_REG-001_2025`;
   `Resolución Reglamentaria N° 005` → `R_AGR_REG-005_2026`;
   `Circular Externa 004 DE 2025` → `CE_AGR_004_2025`; variantes `N°`,
   `No`, `No.`, `NO_`, erratas `Reglamenteria`/`Regalmentaria`.
5. Año: el de la carpeta; año distinto en el nombre → aviso; "Modifica la
   Reglamentaria 010_2024" y "parágrafo transitorio Res_011_2024" no
   confunden número ni año.
6. Número ilegible → `title_unverified=True` + aviso.
7. Dedup raíz/carpeta (comparando el valor: `015` = `15`); concepto de la
   raíz sin año → omitido con aviso; anexo por palabra (`_A01`);
   `39-02-2025_010-IGIP.pdf` → `R_AGR_ORG-010_2025_A01` con aviso; número
   repetido con aviso.
8. Clase de resolución (`ORG`, `REG`, `ORD`) según la carpeta; clase de
   circular (`CE`, `CJ`, `CD`) según la **subcarpeta** y, para un archivo
   suelto en la carpeta del año, según el nombre; "Repositorio Ofi
   Jurídica" ignorado.
9. Piso: una carpeta `Conceptos 2024` / `Res. Orgánicas 2024` / `2024` **no
   se pide** (el simulador falla si se pide); una carpeta sin año sí;
   filtro por `f_public`; `filters_by_publication_date is True`,
   `doc_id_uses_publication_date is False`.
10. `stop_event`, `limit`, una sección que falla (aviso y sigue), sección
    vacía → aviso, tope de paginación.

## Preguntas para el usuario / administrador

1. **Secciones:** ¿conceptos + resoluciones orgánicas y reglamentarias +
   circulares (propuesto)?
   **Se toma la propuesta (aprobación del 2026-11-26).**
2. **Resoluciones ordinarias** (casi todas ofertas de bienes dados de baja;
   3 desde 2025): ¿se dejan fuera (propuesto)?
   **Se toma la propuesta (aprobación del 2026-11-26).**
3. **Piso:** **Respondida por el administrador el 2026-11-25:** primero
   respondió "desde 2015" y luego "documentos del 2025 en adelante". Se
   toma la última, **2025**. **Respondida por el administrador el
   2026-11-26:** el piso de la AGR es 2025; el diseño queda escrito para
   2025 en todas las secciones (y las carpetas de años anteriores no se
   abren).
4. **Prefijos y sigla:** **Respondida por el administrador el 2026-11-26
   (resoluciones):** la clase va en el número y se conserva `R`:
   `R_AGR_ORG-…`, `R_AGR_REG-…`, `R_AGR_ORD-…` (se descartan `RORG`,
   `RREG`, `RORD`), con el mismo estilo que la Contraloría. Siguen abiertos:
   ¿`CD` para las circulares dispositivas? ¿Sigla `AGR`? (Revisado en el
   código: `AGR` sólo existe como código de especialidad "Asuntos agrarios"
   de SAMAI, que no va en títulos; `CD` no existe en ningún título. No hay
   choque.)
   **Se toma la propuesta (aprobación del 2026-11-26): `CD` y `AGR`.**
5. **Fecha:** ¿`f_public` = fecha de carga al sitio y `f_providencia` =
   1 de enero del año del documento (propuesto)? Con el piso 2025 ya no
   aplica el problema de las cargas masivas de 2019/2023.
   **Se toma la propuesta (aprobación del 2026-11-26).**
6. **Números repetidos con asunto distinto:** ¿el segundo como `_A01` con
   aviso (propuesto) o como documento aparte con sufijo? (Revisado en el
   sitio el 2026-11-26: todos los casos conocidos son de 2017-2024; desde
   2025 no hay ninguno, así que hoy no afecta.)
   **Se toma la propuesta (aprobación del 2026-11-26).**
7. **Formato del número:** **Respondida por el administrador el
   2026-11-26:** el número se copia tal como lo escribe la entidad, sin
   rellenar con ceros ni quitarlos (`CTO_AGR_015_2025`,
   `R_AGR_ORG-003_2026`, `CE_AGR_006_2025`).

## Plan de implementación (cuando se apruebe)

1. Prueba + lector de carpeta del portlet (subcarpetas, enlaces propios,
   dedup por `uuid`, carpetas bajo el piso) y enlace limpio (casos 1-3).
2. Prueba + número/año/clase → título, dedup y anexos (casos 4-8).
3. Prueba + `scrap()` con el sitio simulado (casos 9-10).
4. Import en `families/__init__.py`, seed y `tests/test_seed.py`.
5. Corrida real local desde 2025-01-01 (abrir varios PDF y comparar con el
   listado) y segunda corrida sin descargas nuevas.
6. Ficha en `docs/guia-despliegue-sistemas.md`.
