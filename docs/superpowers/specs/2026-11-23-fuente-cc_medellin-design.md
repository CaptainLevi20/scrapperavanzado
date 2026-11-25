# Fuente Cámara de Comercio de Medellín — diseño

**Fecha:** 2026-11-23
**Entidad:** Cámara de Comercio de Medellín para Antioquia — Centro de
Conciliación, Arbitraje y Amigable Composición (`cc_medellin`, sigla
propuesta `CCMA`)
**Estado:** pendiente de aprobación del administrador. No se programa nada
hasta que se apruebe.

> El enlace que dio el usuario
> (`/quiero-un-servicio-para-mi-empresa/solucion-de-conflictos/arbitraje/laudos-arbitrales`)
> **es el listado real**: una sola página con un acordeón por año
> (1999-2026) y un enlace directo a cada PDF. No hace falta un cambio en el
> descargador ni nada fuera de la familia.
>
> La Cámara tiene además un buscador aparte, **Dat@rbitral**
> (`/consulta-laudos/index.html`), con árbitros, temas y cuantía de cada
> laudo. Es un subconjunto atrasado del acordeón (ver "Fuera de alcance").

## Objetivo

Familia de scraper nueva `cc_medellin` con una sección:

| Sección | URL de listado | tipo | prefijo de título |
|---|---|---|---|
| Laudos | `GET https://www.camaramedellin.com.co/quiero-un-servicio-para-mi-empresa/solucion-de-conflictos/arbitraje/laudos-arbitrales` | `Laudo arbitral` | `LA` |

Igual que en las otras cámaras (`cc_armenia`, `ccb`, `cc_barranquilla`):
prefijo `LA`, tipo `Laudo arbitral`, un `RawDocModel` por PDF, las partes en
`detalle`. Familia **plana**: sin anexos, sin actuaciones, sin
`family_params`.

Incluye los laudos de **arbitraje nacional** (radicado `AAAA A NNNN`) y los
de **validación de acuerdos de recuperación empresarial** (Decreto 560 de
2020, radicado `AAAA AP NNNN`, 4 desde 2023), que el Centro publica en la
misma lista (pregunta 3).

## Construcción del sitio

- **DNN (DotNetNuke)** con el módulo de noticias **EasyDNNnews** (plantilla
  "acordeón"), detrás de **Cloudflare** (`Server: cloudflare`,
  `cf-cache-status: DYNAMIC`). **Sin desafío de JavaScript ni captcha**: la
  página llega completa (200, ~210 KB, UTF-8) a `requests` con un
  `User-Agent` de navegador. Pone cookies de DNN (`.ASPXANONYMOUS`,
  `language`, `__RequestVerificationToken`) que no hacen falta.
- 293 `HEAD` seguidos (uno cada 0,3 s) respondieron todos `200`, sin
  bloqueos ni límites de ritmo.
- **TLS válido** (Google Trust Services WE1, vence 2027-02-02).
- `robots.txt` solo prohíbe `/admin/`, `/*/ctl/`, login y registro.
- **Sin paginación:** todos los años (27 paneles, 1999-2026; no hay 2002)
  vienen en el HTML de una sola petición. Cada panel es un artículo de
  EasyDNNnews:

  ```html
  <div class="acordeon__item">
    <div class="acordeon_title"><h2>Laudos 2026</h2></div>
    <div class="acordeon_content">
      <p><strong>Radicado: 2025 A 0032. Laudo proferido el 13 de marzo de 2026.</strong><br />
      <a href="https://www.camaramedellin.com.co/Portals/0/Documentos/Laudos/2026/2025 A 0032 13-03-2026.pdf?ver=h34xuLdGhk-_eC8SJCWYZg%3d%3d"
         target="_blank">Partes: JORGE IVÁN PENAGOS GARCÉS contra LA FUNDACIÓN CLÍNICA DEL NORTE.</a></p>
      …
  ```

  En los años anteriores el **encabezado** de cada laudo va en un
  `<ul><li>` (con o sin `<strong>`) y el enlace en el `<p>` siguiente.
  La lectura es en orden: cada `<a>` a `/Portals/` se empareja con el último
  encabezado visto (`<li>` o `<strong>`) antes de él.

| Dato | De dónde |
|---|---|
| radicado | **nombre del PDF** (ver "Número"); el encabezado se usa para cotejar |
| fecha del laudo | encabezado ("Laudo proferido/emitido el …") |
| partes | texto del enlace, sin el prefijo `Partes:` |
| enlace | `href` del `<a>` (absoluto o relativo a la raíz) |
| año del panel | `<h2>Laudos AAAA</h2>` (respaldo de la fecha) |

### Descarga

- PDF estáticos de DNN bajo `/Portals/0/Documentos/Laudos/<año>/` (y
  `/Portals/0/Documentos/Arbitraje/2025/` para parte de 2025). `GET` y `HEAD`
  responden `200`, `Content-Type: application/pdf`, `Content-Length`,
  `ETag`, `Last-Modified`: la revisión de republicación por tamaño sirve
  (`checks_for_republication = True`, por defecto).
- Los nombres traen **espacios**: el enlace se guarda con la ruta codificada
  (`%20`) para que la URL sea siempre la misma.
- **Se quita `?ver=…`**: es un sello de versión de DNN que el editor no pone
  siempre (Dat@rbitral enlaza algunos PDF sin él). El archivo responde
  igual con o sin el parámetro (mismo `ETag` y tamaño). Como
  `doc_id = sha1(url + f_public)`, quitarlo evita que un cambio del sello
  duplique el laudo.
- `link = {"url": <URL absoluta sin ?ver>, "method": "GET"}`.
- Tamaño (HEAD de los 293 PDF): mediana 1,15 MB, máximo 14,8 MB; 465 MB en
  total, **271 MB desde 2015**. 0 enlaces rotos.

## Fechas y filtro

- `f_public = f_providencia` = **fecha del laudo** del encabezado
  ("proferido el 13 de marzo de 2026"), leída con `core/fecha_es.py`
  (`parse_fecha_providencia_es`). Las 192 cabeceras desde 2015 se leen bien
  con el lector común, también las variantes "10 febrero de 2021",
  "29 DE MARZO DE 2017" y `&nbsp;`. No hay fecha de publicación (como en las
  otras cámaras).
- **Respaldos**, en orden: fecha del nombre del PDF (`dd-mm-aaaa`, o
  `dd de <mes> de aaaa` con guiones o `_`); si ninguna sirve → fila omitida
  con aviso. Hoy no pasa desde 2015.
- **Fecha imposible:** si el año de la fecha es anterior al año del
  radicado, es un error de digitación. Hoy hay un caso: `2019 A 0087`,
  "12 de agosto de **2010**", en el panel 2020 (Dat@rbitral repite el
  error). En ese caso se usa la fecha del nombre del PDF; si el nombre no
  trae año (`… 12 AGO.pdf`), se usa el día y mes del encabezado con el año
  del panel, y se avisa → `2020-08-12`.
- Si el encabezado y el nombre del PDF no coinciden en la fecha (3 casos
  desde 2015, por 1-2 días o por el año), **gana el encabezado**, en
  silencio. Ejemplo: en `2022 A 0048` el encabezado dice 24-01-2025 y el
  archivo 22-01-2025; Dat@rbitral también dice el 24.
- Filtro `fini <= fecha <= ffin`. **Piso:** 2015 por fecha del laudo
  (pregunta 4).
- **Retraso de carga muy grande:** el `Last-Modified` de los PDF muestra que
  el Centro sube los laudos **por tandas** (2024-01/02, 2024-06, 2025-02,
  2025-08, 2026-07), entre **2 y 29 meses** después de la fecha del laudo.
  Hoy solo hay 3 laudos de 2026, subidos el 2026-07-07. Como toda la tabla
  llega en una petición, la corrida diaria la revisa entera, igual que
  Armenia: **`scheduled_min_lookback_days = 10_000`**.
- **Alerta de salud:** con tandas cada ~6 meses, el aviso de "fuente que
  puede estar fallando" saldría entre tanda y tanda. Se propone
  `alerta_margen_dias = 400` (pregunta 6).

## Número y nombre canónico

Radicado del Centro: `AAAA A NNNN` (año de radicación + `A` de arbitraje +
consecutivo) o `AAAA AP NNNN` (validación de acuerdos de recuperación). En
los años viejos el consecutivo trae 3 cifras (`2016 A 004`).

**El radicado sale del nombre del PDF, no del encabezado.** El nombre dice
qué archivo es de verdad: el texto de los PDF abiertos coincidió siempre con
su nombre, también cuando el encabezado decía otra cosa. El encabezado tiene
errores de digitación y, sobre todo, **enlaces copiados de otro laudo** (ver
"Casos raros").

- Lector del nombre: `(\d{4})[\s_-]*(AP|A)[\s_-]*(\d{1,4})` sin importar
  mayúsculas. Sirve para todas las formas desde 2015: `2025 A 0032
  13-03-2026.pdf`, `2017-a-0013-25-ene-18.pdf`,
  `Rad_ 2018 A 0018- LAUDO- 24-04-2019f5d8.pdf`, `2022 AP 0002 …`,
  `29-de-enero-de-2015-2013-A-034.pdf` (radicado al final). El primer
  `\d{4}` que va seguido de `A`/`AP` es el radicado, nunca el año de la
  fecha.
- **Título:** `LA_CCMA_{año_rad}-{A|AP}-{consecutivo:04}_{año_laudo}`.
  Ejemplos: `LA_CCMA_2025-A-0032_2026`, `LA_CCMA_2022-AP-0002_2023`,
  `LA_CCMA_2016-A-0004_2017`. Respeta la forma `{PREFIJO}_{SIGLA}_{número}_{año}`.
  El radicado completo es el número: sin el año de radicación habría
  choques (`2019 A 0059` y `2021 A 0059` existen los dos). Alternativa más
  corta: `LA_CCMA_2025A0032_2026` (pregunta 5).
- Nombre sin radicado (0 casos desde 2015; sí hay antes de 2015): radicado
  del encabezado, `title_unverified=True` y aviso.
- Encabezado y nombre con radicado distinto, y **sin otra fila** cuyo
  encabezado tenga el radicado del archivo: el título sale del nombre, con
  `title_unverified=True` y aviso. Es un error de digitación del encabezado
  (4 casos desde 2015; ver tabla).
- `detalle` = partes (texto del enlace sin `Partes:`; si el texto del enlace
  repite el encabezado, como en 2014, va vacío).
- `save_path = storage_path(_SOURCE, fecha, "Laudo arbitral", f"{title}(extension)")`.
- **Sigla `CCMA`:** es la que usa la propia Cámara (tema del sitio
  `skins/ccma`, archivos `…_CCMA_…`). No choca con ninguna sigla del
  proyecto (`CCB`, `CCAQ`, `CDMB`, `CORANT`… y la propuesta `CCBAR`).

## Casos raros del sitio (desde 2015)

Se revisaron los 192 encabezados frente a su PDF: se abrieron los dudosos
(`pdftotext`) y se cotejaron con Dat@rbitral, que se armó con la misma
matriz y repite los errores del acordeón.

| Caso | Ejemplos | Qué se hace |
|---|---|---|
| **Enlace copiado de otro laudo:** la fila enlaza el PDF de otra fila, y las partes no son las del archivo | `2020 A 0007` → PDF de `2020 A 0025`; `2021 A 0048` → `2021 A 0044`; `2019 A 0035` → `2019 A 0059`; `2018 A 0032` → `2018 A 0013`; `2022 AP 0001` → `2022 A 0001` | La fila cuyo encabezado coincide con el archivo se queda; la otra **se omite con aviso** ("el sitio enlaza el laudo X al PDF de Y"). Ese laudo no está descargable en el sitio. |
| Mismo PDF subido con dos nombres | `2016 A 004 LAUDO ARBITRAL - Feb-11.pdf` y `2016 A 004-24-02-2017.pdf` (md5 iguales); la segunda fila dice `2016 A 012` | Mismo radicado de archivo dos veces → se queda la fila cuyo encabezado coincide; la otra se omite con aviso (el laudo `2016 A 012` falta en el sitio). |
| Error de digitación del radicado en el encabezado (las partes sí son las del PDF) | `2023 A 0004` vs archivo `2023 A 0037` (PDF: "Radicado No. 2023 A 0037"); `2021 A 0072` vs `2021 A 0059`; `2021 A 0051` vs `2021 A 0068`; `2017 A 0031` vs `2017 A 0024` | Título del nombre del archivo, `title_unverified=True`, aviso. |
| Año imposible en la fecha | `2019 A 0087`, "12 de agosto de 2010" | Ver "Fechas". |
| Fecha distinta entre encabezado y nombre | `2022 A 0048`, `2019 A 0003`, `2019 A 0052` (nombre dice 2022) | Gana el encabezado. |
| Laudo de diciembre en el panel del año siguiente | `2022 A 0026` (02-12-2024, panel 2025) | Nada: se usa la fecha del laudo, no el panel. |
| Mayúsculas y separadores variados en el nombre | `2022 a 0001`, `2017-a-0013-…`, `Rad_ 2018 A 0018- …f5d8.pdf` | El lector del nombre los acepta. |
| Dos radicados distintos con el mismo PDF distinto y ambos encabezados coinciden (laudo + aclaración) | 0 casos desde 2015 (`2015 A 025` "aclaración" es única) | Si aparece: se queda el primero y se avisa (pregunta 7). |

**Resumen desde 2015:** 192 filas → **186 laudos** (6 filas omitidas por
enlace copiado o archivo repetido), de los que **4** van con
`title_unverified`.

## Volumen esperado

| Año del laudo | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PDF únicos (panel) | 13 | 12 | 19 | 20 | 13 | 16 | 11 | 22 | 23 | 18 | 17 | 3 | 187 |

(1 de 2016-2017 es el PDF repetido → 186 laudos.) Antes de 2015 hay 106 PDF
más (1999-2014, 194 MB).

Corrida completa: **1 petición de listado + 186 PDF (~271 MB)**, unos
3-5 min. Corrida diaria: 1 petición (~210 KB, < 1 s) y casi siempre 0 PDF;
una tanda de ~10-20 cada medio año.

## Riesgos

- **Cloudflare:** hoy deja pasar a `requests` sin desafío. Si un día exige
  JavaScript, la fuente se pausa y no se intenta saltar (guía, paso 2).
- La página la edita una persona a mano (EasyDNNnews): los errores de
  enlace copiado pueden repetirse. El scraper los detecta y avisa, pero no
  puede sacar el laudo que falta.

## Fuera de alcance (v1)

- **Dat@rbitral** (`/consulta-laudos/index.html`): un HTML estático
  (~560 KB) con los datos embebidos en `const ALL_CASES = [...]`
  ("generated from Matriz final.csv"), 315 filas y 289 enlaces. Trae
  árbitros, presidente, secretario, cuantía, estado, temas y normas
  citadas. Pero:
  - es un **subconjunto atrasado**: sus 277 PDF únicos están todos en el
    acordeón, y le faltan 16, entre ellos los 3 de 2026 y 9 de 2025;
  - repite los mismos errores de enlace;
  - el texto viene **doblemente codificado** (UTF-8 leído como cp1252:
    `Radicación` aparece como `RadicaciÃ³n`).

  Podría servir en una v2 para enriquecer `detalle` (árbitros, temas),
  cruzando por la URL del PDF (pregunta 8).
- Laudos antes de 2015 (si el piso queda en 2015).
- Reglamentos, listas de árbitros, circulares del Centro
  (`/Portals/0/Documentos/Arbitraje/…`): no son laudos.
- Conciliación y amigable composición: el sitio no publica actas.

## Integración

**Archivos nuevos:** `core/scrapers/families/cc_medellin.py`
(`@register_family("cc_medellin")`), `tests/families/test_cc_medellin.py`.

**Archivos que se tocan:** `core/scrapers/families/__init__.py`,
`core/seed.py` (`_SOURCE = "Cámara de Comercio de Medellín para Antioquia"`,
`family_params={}`), `tests/test_seed.py` (conteos), ficha en
`docs/guia-despliegue-sistemas.md`.

Sin cambios en `core/downloader.py`, sin migración Alembic. En producción:
`python -m core.seed` una vez.

## Pruebas

`tests/families/test_cc_medellin.py`, con `responses` y un fragmento real de
la página (paneles 2026, 2022, 2019 y 2015, que cubren las tres maquetas del
encabezado):

1. Radicado del nombre: cada forma de la tabla (`2025 A 0032 13-03-2026.pdf`,
   `2017-a-0013-25-ene-18.pdf`, `Rad_ 2018 A 0018- LAUDO- …f5d8.pdf`,
   `29-de-enero-de-2015-2013-A-034.pdf`, `2022 AP 0002 …`) → título
   (`LA_CCMA_2013-A-0034_2015`, `LA_CCMA_2022-AP-0002_2023`; relleno a 4).
2. Fecha del encabezado con `fecha_es`; respaldo por nombre; año imposible
   (`2019 A 0087`, 2010 → 2020-08-12, con aviso).
3. Emparejamiento encabezado–enlace en las maquetas `<p><strong>…</strong><br/><a>`
   y `<ul><li>…</li></ul><p><a>`.
4. Enlace copiado (`2020 A 0007` → PDF de `2020 A 0025`): queda una sola fila,
   la que coincide, y se avisa.
5. Mismo PDF con dos nombres (`2016 A 004` / `2016 A 012`): una sola fila y
   aviso.
6. Error de digitación (`2023 A 0004` vs `2023 A 0037`): título del archivo,
   `title_unverified=True`, aviso.
7. URL: `?ver=` quitado, espacios como `%20`, ruta relativa → absoluta.
8. `detalle` sin `Partes:`; filtro por fecha y piso;
   `scheduled_min_lookback_days == 10_000`; `alerta_margen_dias`.
9. `stop_event`, `limit`, la página que falla (aviso y lista vacía) y la
   página sin paneles (aviso).

## Preguntas para el usuario / administrador

1. **Sigla `CCMA`** y clave `cc_medellin`: ¿se aprueban?
2. **Nombre de la fuente** en el seed: "Cámara de Comercio de Medellín para
   Antioquia" (nombre legal) o "Cámara de Comercio de Medellín".
3. **Laudos de validación de acuerdos de recuperación** (`AP`, 4): ¿entran
   con el mismo tipo `Laudo arbitral` (propuesto)?
4. **Piso:** ¿2015 (186 laudos) o todo desde 1999 (+106, como Armenia desde
   2006)?
5. **Título:** `LA_CCMA_2025-A-0032_2026` (propuesto) o
   `LA_CCMA_2025A0032_2026`.
6. **Alerta de salud:** ¿`alerta_margen_dias = 400` por las tandas cada ~6
   meses, o se acepta la alerta como en Armenia?
7. **Dos PDF distintos con el mismo radicado** (laudo + aclaración, 0 casos
   hoy): ¿quedarse con el primero y avisar (propuesto), o actuaciones como
   Bogotá?
8. **Dat@rbitral:** ¿interesa una v2 que agregue árbitros y temas al
   `detalle`?
9. ¿Se avisa a la Cámara de los **6 laudos con enlace equivocado**
   (`2020 A 0007`, `2021 A 0048`, `2019 A 0035`, `2018 A 0032`, `2016 A 012`,
   `2022 AP 0001`)?

## Plan de implementación (cuando se apruebe)

1. Prueba + lector de radicado del nombre, título y URL (casos 1, 7).
2. Prueba + fechas: encabezado, respaldos, año imposible (caso 2).
3. Prueba + lectura del acordeón y emparejamiento con HTML real (caso 3).
4. Prueba + reglas de enlace copiado, PDF repetido y error de digitación
   (casos 4-6).
5. Prueba + `scrap()` con el sitio simulado (casos 8-9).
6. Import en `families/__init__.py`, seed y `tests/test_seed.py`.
7. Corrida real local desde el piso y segunda corrida sin descargas nuevas.
8. Ficha en `docs/guia-despliegue-sistemas.md`.
