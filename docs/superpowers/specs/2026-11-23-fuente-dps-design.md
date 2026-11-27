# Fuente Prosperidad Social (DPS) — diseño

**Fecha:** 2026-11-23
**Entidad:** Departamento Administrativo para la Prosperidad Social (`dps`, sigla propuesta `DPS`)
**Estado:** aprobado por el administrador el 2026-11-26. Alcance decidido por
el usuario el mismo día: sólo lo propio del DPS (resoluciones, circulares y
acuerdos), sin decretos ni leyes. Implementado en
`core/scrapers/families/dps.py` (plan:
`docs/superpowers/plans/2026-11-26-fuente-dps.md`).

> El enlace que dio el usuario
> (`https://prosperidadsocial.gov.co/transparencia/normativa/`) es un
> **menú**, no un listado. Los listados reales son sus páginas hijas de
> WordPress: `resoluciones/`, `decretos/`, `leyes/`, `circulares/` y
> `acuerdos-interinstitucionales/`. Los PDF no están en WordPress: cada
> número enlaza a un **enlace compartido anónimo de SharePoint Online**
> (`dpsco.sharepoint.com/:b:/s/CentroDocumentacionPSF/...`).
>
> La entidad tiene además un **Normograma** aparte
> (`normograma.prosperidadsocial.gov.co`) con otras ~78 resoluciones y 127
> conceptos jurídicos. Se deja para una v2 (pregunta 2).

## Objetivo

Familia de scraper nueva `dps`, desde **2015** (año de expedición).
Alcance aprobado (pregunta 1: sólo lo propio del DPS):

| Sección | Página WP (id) | tipo | título | Filas desde 2015 |
|---|---|---|---|---|
| Resoluciones | `/transparencia/normativa/resoluciones/` (33139) | `Resolución` | `R_DPS_{número}_{año}` | 479 |
| Circulares | `/transparencia/normativa/circulares/` (1221) | `Circular` | `C_DPS_{número}_{año}` | 16 (la última es de 2021) |
| Acuerdos interinstitucionales | `/transparencia/normativa/acuerdos-interinstitucionales/` (52177) | `Acuerdo` | `A_DPS_{número}_{año}` | 1 |

**Fuera de alcance (usuario, 2026-11-26):** las páginas de Decretos (1207,
114 filas desde 2015) y Leyes (1202, 22 filas). Decretos y leyes **no son
actos del DPS**: son decretos del Gobierno
nacional y leyes del Congreso que afectan al sector. El worker los reconoce
por el código `D…`/`L…`, pero **hoy sólo en un sentido**: el chequeo de
`worker/tasks.py` (`list_ministerio_documents_by_title`) busca el código en
las familias de `_MINISTERIO_FAMILIES` (`core/db/repository.py`), y `dps` no
está ahí. Un decreto del DPS se saltaría si un ministerio ya lo tiene, pero un
ministerio (o `funcion_publica`) no se saltaría uno que ya tenga el DPS. (No
existe una familia de Presidencia.) **Aprobado por el administrador el
2026-11-26:** `dps` y `funcion_publica` entran al chequeo, para que funcione en
todos los sentidos (ver Integración).

Familia **con anexos** (`_A01`, `_A02`) cuando una fila trae varios PDF;
sin actuaciones, sin `family_params`.

Las resoluciones de WordPress son una **selección** de interés general
(grupos de trabajo, planta, delegaciones, programas, Renta Ciudadana…), no
todo lo que expide el DPS.

## Construcción del sitio

- **WordPress + Elementor** (nginx con caché FastCGI). Sin WAF, sin captcha,
  sin JavaScript obligatorio. TLS válido en los tres hosts
  (`prosperidadsocial.gov.co`, `dpsco.sharepoint.com`, el Normograma). Pone
  una cookie `cookiesession1` que no hace falta.
- **API REST de WordPress** (familia modelo: `adr`):
  `GET /wp-json/wp/v2/pages/<id>?_fields=id,modified,content` → `content.rendered`
  trae **todos los años de la sección en una sola respuesta** (resoluciones:
  373 KB, 0,4-0,9 s). Sin paginación: **una petición por sección**.
- Cada sección es un acordeón con un panel por año
  (`div.elementor-toggle-item`; título `a.elementor-toggle-title` = el año,
  o "Circulares 2017"). Dentro, una tabla `TIPO | FECHA | No. | CONTENIDO`
  (la primera fila es la cabecera):

  ```html
  <tr><td><span>Resolución</span><span><br /></span></td>
  <td><span>06 de noviembre de 2026</span></td>
  <td><a href="https://dpsco.sharepoint.com/:b:/s/CentroDocumentacionPSF/IQDxi_Cdx4pZTbeBqbqmjb91AQlcY45dh4rWarJWRzgsVbo" target="_blank"><span>243654</span></a></td>
  <td><span>Por medio de la cual se modifica la Resolución No. 00157 del 07 de febrero de 2025 …</span></td></tr>
  ```

| Dato | De dónde |
|---|---|
| tipo | celda 1 (`Resolución`, `RESOLUCION`, `RESOLUCIÓN CONJUNTA`) |
| fecha de expedición | celda 2 (muchas veces **sin año**) |
| año | título del panel; si la fecha trae año, coincide siempre |
| número | texto del primer `<a>` SharePoint de la celda 3 |
| enlace(s) | `href` de los `<a>` `dpsco.sharepoint.com/:b:` de la fila |
| epígrafe | celda 4 |

- **Espacios de ancho cero (`\u200b`)** por todas partes, incluso dentro del
  número (`1\u200b997`) y del tipo (`RESOLUCIO\u200b\u200bN`): se quitan
  antes de leer nada.

### Descarga (SharePoint, nuevo en el proyecto)

- El enlace compartido tal cual abre un visor HTML. Con **`?download=1`**
  (o `&download=1` si ya trae `?e=XXXX`, como los enlaces viejos) responde
  `302` → el PDF real: `200`, `Content-Type: application/pdf`,
  `Content-Length`, `ETag`, `Last-Modified`, sin `Content-Disposition` (la
  extensión sale del `Content-Type`). El primer salto pone una cookie
  anónima `FedAuth` que `requests` arrastra solo dentro de la cadena de
  redirecciones; no hace falta iniciar sesión.
- `link = {"url": "<enlace compartido>?download=1", "method": "GET"}`. Se
  guarda el enlace compartido (estable), no la URL final
  (`…/download.aspx?…`).
- **`HEAD` con redirecciones funciona** (mismos encabezados): la revisión de
  republicación por tamaño sirve (`checks_for_republication = True`, por
  defecto); `check_remote_content_length` ya hace `HEAD` con
  `allow_redirects=True` y `User-Agent: Mozilla/5.0`.
- HEAD masivo a los **699 enlaces únicos** de todas las secciones: 698 PDF y
  1 carpeta (`:f:`, de la página del Decreto Único, fuera de alcance);
  **0 rotos**. Mediana 0,72 s.
- Tamaño: mediana 0,9 MB, ≈ 2,1 GB en total; 11 PDF de más de 20 MB, el
  mayor 99,5 MB (Decreto 1649 de 2023). Cabe en el tope `MAX_DOWNLOAD_MB`
  (300 MB por defecto).

## Fechas y filtro

- Formatos de la celda FECHA (todos aparecen):

  | Formato | Ejemplo |
  |---|---|
  | `dd de <mes> de aaaa` / `dd de <mes> aaaa` | `06 de noviembre de 2026`, `19 de junio 2024` |
  | `dd-mmm-aa` / `dd-mmm-aaaa` / `dd-mmm- aaaa` | `27-feb-15`, `01-Sept-2020`, `31-jul- 2018` |
  | `dd-mmm.-aa` (punto tras el mes) | `05-ene.-17`, `30-dic.-16`, `13-may.-20` (resoluciones 2016-2017 y un decreto de 2020) |
  | `dd-mmm-aaa` (año de 3 cifras, error de digitación) | `28-sep-018` (resolución 02349 de 2018): se lee como `2018` si coincide con el panel |
  | `dd-mmm` sin año / `dd – mmm` | `06-mar`, `24 – ene` |
  | `mmm-dd` / `mmm-d` sin año (orden invertido) | `sept-20`, `oct-8`, `Nov-18`, `JUL-26` (resoluciones 2021, decretos 2022) |

  Meses en español con variantes (`sep`, `sept`, `Sept`, `Dic`…). Se usa
  `core/fecha_es.py` donde sirva y un lector pequeño para las formas cortas;
  **año = el del panel** cuando la fecha no lo trae. Fecha ilegible → fila
  omitida con aviso.
- `f_public = f_providencia` = fecha de expedición (WordPress no da fecha de
  publicación). Filtro `fini <= fecha <= ffin`. **Piso:** 2015.
- **Retraso de carga:** días o semanas (la 243654, expedida el 06-11, se
  subió el 10-11). Como cada corrida lee la página entera con una petición,
  mirar atrás no cuesta: **`scheduled_min_lookback_days = 60`**.
- Alternativa (pregunta 4): usar el `Last-Modified` de SharePoint como fecha
  de publicación. Se descarta como propuesta: costaría un `HEAD` por fila en
  cada corrida y cambia si el DPS reemplaza el archivo.
- **Identidad del documento:** `doc_id_uses_publication_date = False`
  (`doc_id` = sólo el enlace, como `minsalud`, `procuraduria` e `icbf`). La
  fecha se arma con texto libre de la celda + el año del panel; si el DPS
  corrige o reescribe ese texto (`05-ene.-17` → `05 de enero de 2017`), con
  la fecha dentro del `doc_id` el mismo PDF entraría como documento nuevo. El
  enlace compartido de SharePoint es estable y único por archivo (y ya se
  deduplica por enlace, ver casos raros).
- **Salud de fuentes:** Circulares está parada desde 2021 y Acuerdos tiene una
  sola fila; Resoluciones publica a tandas. Se fija **`alerta_margen_dias`**
  tras la corrida real, con la pausa más larga entre resoluciones de los
  últimos años, para que la alerta de "fuente que puede estar fallando" no
  salte por eso.

## Número y nombre canónico

- Número = texto del enlace sin `\u200b` ni espacios de los extremos,
  **tal cual lo escribe el DPS**, sin quitar ni poner ceros (decisión del
  administrador, 2026-11-26; reemplaza el "relleno a 4" de la primera
  versión): `00464` → `R_DPS_00464_2016`; `243654` → `R_DPS_243654_2026`;
  circular `018` → `C_DPS_018_2021`. Desde mayo de 2026 el DPS numera con el
  consecutivo de su gestor documental (5-6 cifras, no consecutivo).
- Para **comparar** números (dedup por número repetido) se usa el valor
  numérico (`int`): `2418` y `02418` son el mismo número. El título conserva
  el texto de la fila que se queda.
- `Resolución conjunta` (2 desde 2015): mismo prefijo `R` (pregunta 5).
- Número con texto (`0079 Anexo`, 2024): se toma la parte numérica; los dos
  PDF de la fila quedan como resolución y anexo.
- Número que no es `\d+` tras limpiar (0 casos más hoy) → texto saneado,
  `title_unverified=True` y aviso.
- (No aplica en v1: decretos y leyes quedaron fuera.) Decretos y leyes: `codigo_ley_decreto("D"|"L", número, año)`. Aquí **no**
  aplica la regla de "número tal cual": el código común de `core/naming.py`
  rellena a 4 a propósito, porque es lo que permite reconocer el mismo
  decreto o ley en varias fuentes.
- **Anexos:** si la fila trae varios enlaces SharePoint (`00460` de 2026 con
  3 PDF, `1519` de 2020 con 4), el primero es el documento y los demás
  `_A01`, `_A02`… Los enlaces que no son de SharePoint (SUIN, SafeLinks,
  el host viejo `centrodedocumentacion…`) se ignoran. Si al ignorarlos la
  fila se queda **sin ningún** enlace SharePoint, se trata como "fila sin
  enlace": se omite **con aviso**, nunca en silencio. Caso real: la Ley 1878
  de 2016 sólo trae un enlace a SUIN-Juriscol.
- `detalle` = epígrafe.
- `save_path = storage_path(_SOURCE, fecha, tipo, f"{title}(extension)")`.

## Casos raros del sitio

| Caso | Qué se hace |
|---|---|
| Fila sin enlace, o sin ningún enlace SharePoint (hoy: Ley 1878 de 2016, sólo con enlace a SUIN-Juriscol) | Se omite **con aviso**. (El ejemplo original, una segunda fila `208303` de 2026 sin enlace, ya no está: el 2026-11-26 queda una sola fila `208303`, del 06-08-2026, con su PDF. Hoy no hay resoluciones sin enlace; la regla y su prueba se mantienen.) |
| Mismo número dos veces en el año con PDF distintos (`2418`/`02418` de 2020) | Dedup por (sección, valor numérico del número, año): se queda la primera y se avisa. |
| Mismo número dos veces con el mismo PDF (`860`/`00860` de 2015) | Dedup por enlace, en silencio. |
| Mismo PDF para dos números distintos (`02163`/`02000` de 2024; `01780`/`01572` de 2020; circulares `01` de 2018 y de 2019) | Error de carga del sitio: se guarda la primera y se avisa con los dos números. No se "arregla". |
| Circular `007` dos veces en 2017 con PDF distintos | Dedup por (sección, número, año) + aviso. |
| Enlace `:f:` (carpeta) | No es documento: se ignora. |

## Volumen esperado (WordPress, desde 2015)

| Sección | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Resoluciones | 12 | 42 | 28 | 37 | 30 | 50 | 48 | 30 | 30 | 33 | 86 | 53 | 479 |
| Decretos | 9 | 12 | 19 | 8 | 2 | 12 | 5 | 14 | 13 | 5 | 10 | 5 | 114 |
| Leyes | 4 | 5 | 0 | 3 | 1 | 0 | 0 | 0 | 3 | 3 | 3 | 0 | 22 |
| Circulares | 0 | 6 | 6 | 2 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 16 |
| Acuerdos | | | | | | | | | | | 1 | | 1 |

Corrida completa con todo: **~630 PDF, ≈ 2 GB, 10-15 min**. Sólo
resoluciones + circulares + acuerdo: ~495 PDF. Corrida diaria: ≤ 5
peticiones de listado y 0-3 PDF nuevos.

## Fuera de alcance (v1)

- **Normograma** (`normograma.prosperidadsocial.gov.co/Home/AdvanceSearch`):
  una página de 1,4 MB (8,4 s) con 1.198 normas y fecha `dd/mm/aaaa` limpia.
  Tiene **~78 resoluciones 2015-2026 que no están en WordPress** y **127 conceptos jurídicos** (2017-2023, la
  sección está parada desde 2023). Cruce por número, 2015-2026: 389 en
  ambos, 87 sólo en WordPress, 78 sólo en el Normograma. Sus PDF están en un contenedor privado
  de Azure Blob; el propio sitio entrega un token de lectura de 24 h por
  `POST /home/getdocumentbyid` (es lo que hace el navegador al hacer clic,
  no un salto de protección), pero el `link` guardado no puede llevar un
  token que caduca: habría que pedirlo al descargar. Se propone como v2 si
  el usuario lo quiere (pregunta 2).
- Decreto Único Reglamentario (página 1185): tabla distinta y redundante con
  Decretos.
- Directivas (un solo enlace, a una carpeta) y avisos de tutelas de la
  página "Normativa" (no es normativa).
- Proyectos de actos administrativos, agenda regulatoria, informes globales.
- Antes de 2015 (30 resoluciones, 13 decretos).

## Integración

**Archivos nuevos:** `core/scrapers/families/dps.py`
(`@register_family("dps")`), `tests/families/test_dps.py`.

**Archivos que se tocan:** `core/scrapers/families/__init__.py`,
`core/seed.py` (`_SOURCE = "Departamento Administrativo para la Prosperidad Social"`,
`family_params={}`), `tests/test_seed.py` (conteos), ficha en
`docs/guia-despliegue-sistemas.md`.

**Cambio fuera de la familia (aprobado por el administrador el 2026-11-26):
dedup de decretos y leyes en todos los sentidos.**

Con decretos y leyes fuera del `dps` v1, el cambio sigue valiendo para
`funcion_publica` y se programa con esa familia (no en `dps.py`); deja
`dps` en el conjunto para cuando se sumen.

- `core/db/repository.py`: `list_ministerio_documents_by_title` (el chequeo
  que usa `worker/tasks.py:418` antes de bajar un `D…`/`L…`) pasa a buscar
  también en las familias `dps` y `funcion_publica`. Se hace con un conjunto
  propio para este chequeo, p. ej.
  `_FAMILIAS_DEDUP_LEY_DECRETO = _MINISTERIO_FAMILIES | {"dps", "funcion_publica"}`,
  **sin** meterlas en `_MINISTERIO_FAMILIES`: ese conjunto también lo usan
  `core/backfill_leyes_decretos.py` y `core/backfill_directiva_prefix.py`,
  que renombran títulos de ministerios y no deben tocar estas dos fuentes si
  se vuelven a correr. Se actualiza el docstring de la función.
- `tests/test_tasks.py`: prueba nueva junto a
  `test_scrape_source_task_skips_a_ley_already_published_by_another_ministerio`:
  un decreto `D…` que ya está guardado en `dps` no se vuelve a bajar desde
  una fuente de ministerio, y al revés (ministerio → `dps`). La misma prueba
  cubre `funcion_publica` (ver su diseño); si los dos diseños se programan
  por separado, el que llegue primero agrega las dos familias al conjunto y
  la prueba.
- Lo que gana es el que ya está guardado (regla de siempre, ver
  `2026-09-03-formato-leyes-decretos-ministerios`).

Sin migración Alembic. En producción: `python -m core.seed` una vez.

## Pruebas

`tests/families/test_dps.py`, con `responses` y JSON real de `wp-json`:

1. Limpieza de `\u200b` en tipo, fecha y número.
2. Fechas: cada formato de la tabla, incluidos los que salieron en la
   revisión del 2026-11-26: `05-ene.-17` (punto tras el mes), `28-sep-018`
   (año de 3 cifras, panel 2018), `oct-8` y `JUL-26` (`mmm-d`/`mmm-dd` sin
   año, año del panel), `24 – ene`; fecha ilegible → omitida con aviso.
3. Número → título, tal cual: `00464` → `R_DPS_00464_2016`; `243654` →
   `R_DPS_243654_2026`; `0079 Anexo` → `R_DPS_0079_2024`; circular `018` →
   `C_DPS_018_2021`; decreto `1110` de 2026 → `D1110026` (código común,
   rellenado); ley → `L…`.
4. Enlace: `…/IQD…` → `…/IQD…?download=1`; `…?e=LNo08f` → `…?e=LNo08f&download=1`.
5. Fila con 3 PDF → documento + `_A01` + `_A02`; enlaces no SharePoint y `:f:`
   ignorados.
6. Fila sin enlace, número repetido (`2418` y `02418` cuentan como el mismo),
   mismo PDF con dos números → avisos y dedup como en la tabla de casos raros.
   Fila con sólo un enlace no SharePoint (como la Ley 1878 de 2016, con
   enlace a SUIN) → omitida **con aviso**.
7. Filtro por fecha y piso; `scheduled_min_lookback_days == 60`;
   `doc_id_uses_publication_date is False`; `alerta_margen_dias` con el valor
   fijado tras la corrida real.
8. `stop_event`, `limit`, una sección que falla (aviso y sigue), sección
   vacía → aviso.
9. Dedup de decretos/leyes en todos los sentidos: prueba en
   `tests/test_tasks.py` (ver Integración).

## Preguntas para el usuario / administrador

1. **Secciones:** ¿sólo lo propio del DPS (resoluciones, circulares,
   acuerdo), o también decretos y leyes del sector? **Respondida:** sólo lo
   propio del DPS (usuario, 2026-11-26). Sin decretos ni leyes.
2. **Normograma:** ¿se suma en una v2 para las ~78 resoluciones que faltan
   en WordPress y los 127 conceptos jurídicos? **Se toma la propuesta (aprobación del 2026-11-26).**
3. **Piso:** ¿2015? **Se toma la propuesta (aprobación del 2026-11-26).**
4. **Fecha:** ¿`f_public` = fecha de expedición (propuesto) o el
   `Last-Modified` de SharePoint como fecha de publicación? **Se toma la propuesta (aprobación del 2026-11-26).**
5. **Resoluciones conjuntas** (2): ¿`R_DPS_…` (propuesto) o prefijo propio? **Se toma la propuesta (aprobación del 2026-11-26).**
6. **Sigla `DPS`:** ¿se aprueba? (La entidad hoy se llama a sí misma
   "Prosperidad Social", pero `DPS` es la sigla de sus resoluciones y de su
   SharePoint.) **Se toma la propuesta (aprobación del 2026-11-26).**
7. **Número:** **Respondida por el administrador el 2026-11-26:** el número
   se copia tal cual lo escribe la entidad, sin quitar ni poner ceros, en las
   tres fuentes (ADRES, DPS y Función Pública): `R_DPS_00464_2016`. Reemplaza
   el "relleno a 4" de la primera versión de este diseño. Los decretos y leyes
   siguen con el código común `D…`/`L…` de `core/naming.py`.
8. **Dedup de decretos y leyes:** **Respondida por el administrador el
   2026-11-26:** `dps` y `funcion_publica` entran al chequeo de
   `list_ministerio_documents_by_title`, para que la dedup funcione en todos
   los sentidos (ver Integración). Si al final se decide no traer Decretos ni
   Leyes (pregunta 1), el cambio igual sirve para `funcion_publica`.

## Resultado de la implementación (2026-11-26)

Corrida real del scraper contra el sitio (sin base de datos), de 2015-01-01
a hoy, en 1,2 s: **498 documentos**: 482 resoluciones (6 de ellas anexos
`_A01`…), 15 circulares y 1 acuerdo. 0 sin verificar, 0 fechas ilegibles,
0 filas sin enlace. Una segunda pasada devuelve exactamente lo mismo.
Avisos: `02418`/`2418` de 2020 y `00860`/`860` de 2015 (en ambos casos los
dos enlaces bajan el **mismo** archivo: mismo tamaño y `ETag`; se queda la
primera fila), `01572`/`01780` de 2020 con el mismo enlace, y la circular
`007` dos veces en 2017. Los casos `02163`/`02000` de 2024 y las circulares
`01` de 2018/2019 ya no aparecen en el sitio. La circular `018` de 2021 sale
con fecha `22-sept`.

Cambios frente al diseño:

- La página de Circulares **no tiene fila de cabecera**: la cabecera se
  reconoce por su texto (`TIPO`/`FECHA`), no por ser la primera fila.
- Si la fecha trae un año distinto al del panel, manda el panel (no hay
  casos hoy).
- Dedup: se recorren todas las filas desde el piso, aunque caigan fuera de
  la ventana, para que el documento que se queda no dependa del rango.
- `alerta_margen_dias = 120`: la pausa más larga entre resoluciones desde
  2020 es de 53 días (142 entre ago-2019 y ene-2020), más el retraso de
  carga.

## Plan de implementación

1. Prueba + limpieza de `\u200b`, lector de fechas y número → título
   (casos 1-3).
2. Prueba + lectura del acordeón con JSON real, enlaces y anexos (casos 4-6).
3. Prueba + `scrap()` con el sitio simulado (casos 7-8).
4. Import en `families/__init__.py`, seed y `tests/test_seed.py`.
5. Prueba + dedup de decretos/leyes en todos los sentidos
   (`core/db/repository.py`, `tests/test_tasks.py`; caso 9), si no lo hizo
   ya `funcion_publica`.
6. Corrida real local desde 2015 y segunda corrida sin descargas nuevas.
   Fijar `alerta_margen_dias` con lo que salga.
7. Ficha en `docs/guia-despliegue-sistemas.md`.
