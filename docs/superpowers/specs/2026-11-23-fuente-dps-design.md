# Fuente Prosperidad Social (DPS) — diseño

**Fecha:** 2026-11-23
**Entidad:** Departamento Administrativo para la Prosperidad Social (`dps`, sigla propuesta `DPS`)
**Estado:** pendiente de aprobación del administrador. No se programa nada
hasta que se apruebe.

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
Propuesta (a confirmar, pregunta 1):

| Sección | Página WP (id) | tipo | título | Filas desde 2015 |
|---|---|---|---|---|
| Resoluciones | `/transparencia/normativa/resoluciones/` (33139) | `Resolución` | `R_DPS_{número}_{año}` | 479 |
| Circulares | `/transparencia/normativa/circulares/` (1221) | `Circular` | `C_DPS_{número}_{año}` | 16 (la última es de 2021) |
| Acuerdos interinstitucionales | `/transparencia/normativa/acuerdos-interinstitucionales/` (52177) | `Acuerdo` | `A_DPS_{número}_{año}` | 1 |
| Decretos (opcional) | `/transparencia/normativa/decretos/` (1207) | `Decreto` | `D{número:04}{año:03}` (regla común) | 114 |
| Leyes (opcional) | `/transparencia/normativa/leyes/` (1202) | `Ley` | `L{número:04}{año:03}` (regla común) | 22 |

Decretos y leyes **no son actos del DPS**: son decretos del Gobierno
nacional y leyes del Congreso que afectan al sector. El worker ya los
deduplica con los de Presidencia y ministerios por el código `D…`/`L…`.

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
  | `dd-mmm` sin año / `dd – mmm` | `06-mar`, `24 – ene` |
  | `mmm-dd` sin año (orden invertido) | `sept-20`, `Nov-18` |

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

## Número y nombre canónico

- Número = texto del enlace sin `\u200b`, sin ceros a la izquierda, relleno a
  4 y nunca recortado (como ICA): `00464` → `R_DPS_0464_2016`; `243654` →
  `R_DPS_243654_2026`. Desde mayo de 2026 el DPS numera con el consecutivo
  de su gestor documental (5-6 cifras, no consecutivo).
- `Resolución conjunta` (2 desde 2015): mismo prefijo `R` (pregunta 5).
- Número con texto (`0079 Anexo`, 2024): se toma la parte numérica; los dos
  PDF de la fila quedan como resolución y anexo.
- Número que no es `\d+` tras limpiar (0 casos más hoy) → texto saneado,
  `title_unverified=True` y aviso.
- Decretos y leyes: `codigo_ley_decreto("D"|"L", número, año)`.
- **Anexos:** si la fila trae varios enlaces SharePoint (`00460` de 2026 con
  3 PDF, `1519` de 2020 con 4), el primero es el documento y los demás
  `_A01`, `_A02`… Los enlaces que no son de SharePoint (SUIN, SafeLinks,
  el host viejo `centrodedocumentacion…`) se ignoran.
- `detalle` = epígrafe.
- `save_path = storage_path(_SOURCE, fecha, tipo, f"{title}(extension)")`.

## Casos raros del sitio

| Caso | Qué se hace |
|---|---|
| Fila sin enlace (`208303`, 06-11-2026) | Se omite con aviso. |
| Mismo número dos veces en el año con PDF distintos (`2418`/`02418` de 2020; `208303` de 2026, una sin enlace) | Dedup por (sección, número, año): se queda la primera y se avisa. |
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

Sin migración Alembic. En producción: `python -m core.seed` una vez.

## Pruebas

`tests/families/test_dps.py`, con `responses` y JSON real de `wp-json`:

1. Limpieza de `\u200b` en tipo, fecha y número.
2. Fechas: cada formato de la tabla, incluido sin año (año del panel) y
   `mmm-dd`; fecha ilegible → omitida con aviso.
3. Número → título: `00464` → `R_DPS_0464_2016`; `243654` →
   `R_DPS_243654_2026`; `0079 Anexo` → `R_DPS_0079_2024`; decreto `1110` de
   2026 → `D1110026`; ley → `L…`.
4. Enlace: `…/IQD…` → `…/IQD…?download=1`; `…?e=LNo08f` → `…?e=LNo08f&download=1`.
5. Fila con 3 PDF → documento + `_A01` + `_A02`; enlaces no SharePoint y `:f:`
   ignorados.
6. Fila sin enlace, número repetido, mismo PDF con dos números → avisos y
   dedup como en la tabla de casos raros.
7. Filtro por fecha y piso; `scheduled_min_lookback_days == 60`.
8. `stop_event`, `limit`, una sección que falla (aviso y sigue), sección
   vacía → aviso.

## Preguntas para el usuario / administrador

1. **Secciones:** ¿sólo lo propio del DPS (resoluciones, circulares,
   acuerdo), o también decretos y leyes del sector?
2. **Normograma:** ¿se suma en una v2 para las ~78 resoluciones que faltan
   en WordPress y los 127 conceptos jurídicos?
3. **Piso:** ¿2015?
4. **Fecha:** ¿`f_public` = fecha de expedición (propuesto) o el
   `Last-Modified` de SharePoint como fecha de publicación?
5. **Resoluciones conjuntas** (2): ¿`R_DPS_…` (propuesto) o prefijo propio?
6. **Sigla `DPS`:** ¿se aprueba? (La entidad hoy se llama a sí misma
   "Prosperidad Social", pero `DPS` es la sigla de sus resoluciones y de su
   SharePoint.)

## Plan de implementación (cuando se apruebe)

1. Prueba + limpieza de `\u200b`, lector de fechas y número → título
   (casos 1-3).
2. Prueba + lectura del acordeón con JSON real, enlaces y anexos (casos 4-6).
3. Prueba + `scrap()` con el sitio simulado (casos 7-8).
4. Import en `families/__init__.py`, seed y `tests/test_seed.py`.
5. Corrida real local desde 2015 y segunda corrida sin descargas nuevas.
6. Ficha en `docs/guia-despliegue-sistemas.md`.
