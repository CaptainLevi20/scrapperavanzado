# Fuente Cámara de Comercio de Medellín — diseño

**Fecha:** 2026-11-23 (revisado 2026-11-26 con las decisiones del administrador)
**Entidad:** Cámara de Comercio de Medellín para Antioquia — Centro de
Conciliación, Arbitraje y Amigable Composición (`cc_medellin`, sigla
`CCMA`, aprobada por el administrador el 2026-11-26)
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
`family_params`. **Sin piso de año:** entra todo el acordeón, desde 1999
(decisión del administrador del 2026-11-26, pregunta 4).

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
  encabezado visto (`<li>` o `<strong>`) antes de él. Comprobado el
  2026-11-26 en los 27 paneles: 299 enlaces, 293 PDF distintos; las 299
  filas tienen encabezado y fecha legible. Antes de 2015 el encabezado varía
  más: `Radicado1999 A 023. Laudo emitido el …` (sin espacio) y
  `Radicado 6 de agosto de 2014- 2013 A 031` (la fecha antes del radicado).

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
  (`parse_fecha_providencia_es`). Las 299 cabeceras (192 desde 2015 y 107
  antes) se leen bien con el lector común (probado el 2026-11-26), también
  las variantes "10 febrero de 2021",
  "29 DE MARZO DE 2017" y `&nbsp;`. No hay fecha de publicación (como en las
  otras cámaras).
- **Respaldos**, en orden: fecha del nombre del PDF (`dd-mm-aaaa`, o
  `dd de <mes> de aaaa` con guiones o `_`); si ninguna sirve → fila omitida
  con aviso. Hoy no pasa en ningún año.
- **Fecha imposible:** si el año de la fecha es anterior al año del
  radicado, es un error de digitación. Hoy hay un caso: `2019 A 0087`,
  "12 de agosto de **2010**", en el panel 2020 (Dat@rbitral repite el
  error). En ese caso se usa la fecha del nombre del PDF; si el nombre no
  trae año (`… 12 AGO.pdf`), se usa el día y mes del encabezado con el año
  del panel, y se avisa → `2020-08-12`.
- Si el encabezado y el nombre del PDF no coinciden en la fecha (3 casos
  desde 2015, por 1-2 días o por el año), **gana el encabezado**, **con
  aviso** ("el encabezado dice X y el nombre del archivo Y"), como en el
  resto de los casos dudosos. Ejemplo: en `2022 A 0048` el encabezado dice
  24-01-2025 y el archivo 22-01-2025; Dat@rbitral también dice el 24.
- Filtro `fini <= fecha <= ffin`. **Sin piso:** todo el acordeón, desde 1999
  (decisión del administrador del 2026-11-26, pregunta 4). El laudo más viejo
  es del 31 de mayo de 1999 (`1998 A 016`).
- **Retraso de carga muy grande:** el `Last-Modified` de los PDF muestra que
  el Centro sube los laudos **por tandas** (2024-01/02, 2024-06, 2025-02,
  2025-08, 2026-07), entre **2 y 29 meses** después de la fecha del laudo.
  Hoy solo hay 3 laudos de 2026, subidos el 2026-07-07. Como toda la tabla
  llega en una petición, la corrida diaria la revisa entera:
  **`scheduled_min_lookback_days = 20_000`** (~55 años). Tiene que ser mayor
  que los días desde el laudo más viejo: con `10_000` (Armenia) la ventana
  llegaría hoy hasta el 12-07-1999 y dejaría fuera el laudo del 31-05-1999.
  Es el mismo valor en las cuatro cámaras nuevas.
- **Alerta de salud:** **no** se pone `alerta_margen_dias` (antes se proponía
  400). El aviso toma el mayor entre `scheduled_min_lookback_days` y
  `alerta_margen_dias` (`api/routers/sources.py`), así que con 20.000 días el
  margen no cambia nada. Lo que sí pasa (`core/salud_fuentes.py`): el aviso
  de "fuente que puede estar fallando" sale **cuando no hay ningún laudo con
  fecha de los últimos 12 meses**. Hoy hay 3 de 2026 (marzo-mayo), así que no
  sale; como el Centro sube por tandas con meses de retraso, puede salir
  entre tanda y tanda. Se acepta, como en Armenia (pregunta 6).

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
- **Título:** `LA_CCMA_{año_rad}-{A|AP}-{consecutivo tal cual}_{año_laudo}`.
  El consecutivo se copia **como lo escribe la Cámara en el nombre del
  archivo**, sin rellenar ni quitar ceros (decisión del administrador del
  2026-11-26): ejemplos `LA_CCMA_2025-A-0032_2026`,
  `LA_CCMA_2022-AP-0002_2023`, `LA_CCMA_2016-A-004_2017`,
  `LA_CCMA_2013-A-034_2015`. Solo se unifican los separadores (espacio, `_`
  o `-` → `-`) y la letra en mayúscula (`2022 a 0001` → `2022-A-0001`).
  Respeta la forma `{PREFIJO}_{SIGLA}_{número}_{año}`. El radicado completo
  es el número: sin el año de radicación habría choques (`2019 A 0059` y
  `2021 A 0059` existen los dos). Alternativa sin guiones:
  `LA_CCMA_2025A0032_2026` (pregunta 5).
- **Para comparar** encabezado y nombre (y detectar un PDF repetido) el
  consecutivo se compara como número (`2016 A 004` = `2016 A 0004`); el
  título sigue siendo el texto tal cual del nombre.
- Nombre sin radicado (0 casos desde 2015; 1 antes:
  `21-de-mayo-de-2010-2009- 059-ilovepdf-compressed.pdf`, sin la `A`):
  radicado del encabezado (`2009 A 059`), `title_unverified=True` y aviso.
- **Un PDF que aparece en una sola fila siempre se queda**, aunque el
  encabezado diga otro radicado: el título sale del nombre, con
  `title_unverified=True` y aviso. Una fila solo se omite cuando su PDF (o el
  mismo archivo con otro nombre) ya lo tiene otra fila cuyo encabezado sí
  coincide (ver "Casos raros"). Así cubre el error de digitación (4 casos
  desde 2015, 2 antes) y también los **enlaces cruzados** de 2014, donde dos
  filas se intercambian los PDF y la regla "hay otra fila con ese
  encabezado" las habría omitido a las dos.
- `detalle` = partes (texto del enlace sin `Partes:`; si el texto del enlace
  repite el encabezado, como en 2014, va vacío).
- `save_path = storage_path(_SOURCE, fecha, "Laudo arbitral", f"{title}(extension)")`.
- **Sigla `CCMA`** (aprobada por el administrador el 2026-11-26): es la que
  usa la propia Cámara (tema del sitio `skins/ccma`, archivos `…_CCMA_…`).
  No choca con ninguna sigla del proyecto (`CCB`, `CCAQ`, `CDMB`, `CORANT`…
  ni las nuevas `CCBAR`, `CCC`, `CCCAR`).

## Casos raros del sitio

Se revisaron los 192 encabezados desde 2015 frente a su PDF: se abrieron los
dudosos (`pdftotext`) y se cotejaron con Dat@rbitral, que se armó con la
misma matriz y repite los errores del acordeón. Los 107 anteriores se
cotejaron solo encabezado contra nombre del archivo (2026-11-26).

| Caso | Ejemplos | Qué se hace |
|---|---|---|
| **Enlace copiado de otro laudo:** la fila enlaza el PDF de otra fila, y las partes no son las del archivo | `2020 A 0007` → PDF de `2020 A 0025`; `2021 A 0048` → `2021 A 0044`; `2019 A 0035` → `2019 A 0059`; `2018 A 0032` → `2018 A 0013`; `2022 AP 0001` → `2022 A 0001` | La fila cuyo encabezado coincide con el archivo se queda; la otra **se omite con aviso** ("el sitio enlaza el laudo X al PDF de Y"). Ese laudo no está descargable en el sitio. |
| Mismo PDF subido con dos nombres | `2016 A 004 LAUDO ARBITRAL - Feb-11.pdf` y `2016 A 004-24-02-2017.pdf` (md5 iguales); la segunda fila dice `2016 A 012` | Mismo radicado de archivo dos veces → se queda la fila cuyo encabezado coincide; la otra se omite con aviso (el laudo `2016 A 012` falta en el sitio). |
| Enlace copiado, antes de 2015 | `2010 A 051` → PDF de `2011 A 050` (panel 2012) | Igual: se omite la fila que no coincide, con aviso. |
| Error de digitación del radicado en el encabezado (las partes sí son las del PDF) | `2023 A 0004` vs archivo `2023 A 0037` (PDF: "Radicado No. 2023 A 0037"); `2021 A 0072` vs `2021 A 0059`; `2021 A 0051` vs `2021 A 0068`; `2017 A 0031` vs `2017 A 0024`; antes de 2015: `2013 A 033` vs `2012_A_033`, `2013 A 028` vs `2013 A 052` | Título del nombre del archivo, `title_unverified=True`, aviso. |
| **Enlaces cruzados** (dos filas se intercambian los PDF) | Panel 2014: la fila `2013 A 007` enlaza `…2013-A-031.pdf` y la fila `2013 A 031` enlaza `…2013_A_007.pdf`. Los dos PDF son escaneos: no se puede saber cuál está bien. | Cada PDF aparece una sola vez → **se quedan los dos**, título del nombre del archivo, `title_unverified=True`, aviso. No se omite ninguno. |
| Año imposible en la fecha | `2019 A 0087`, "12 de agosto de 2010" | Ver "Fechas". |
| Fecha distinta entre encabezado y nombre | `2022 A 0048`, `2019 A 0003`, `2019 A 0052` (nombre dice 2022) | Gana el encabezado, con aviso. |
| Laudo de diciembre en el panel del año siguiente | `2022 A 0026` (02-12-2024, panel 2025) | Nada: se usa la fecha del laudo, no el panel. |
| Mayúsculas y separadores variados en el nombre | `2022 a 0001`, `2017-a-0013-…`, `Rad_ 2018 A 0018- …f5d8.pdf` | El lector del nombre los acepta. |
| Dos radicados distintos con el mismo PDF distinto y ambos encabezados coinciden (laudo + aclaración) | 0 casos desde 2015 (`2015 A 025` "aclaración" es única) | Si aparece: se queda el primero y se avisa (pregunta 7). |

**Resumen desde 2015:** 192 filas → **186 laudos** (6 filas omitidas por
enlace copiado o archivo repetido), de los que **4** van con
`title_unverified`.

**Resumen antes de 2015:** 107 filas → **106 laudos** (1 fila omitida por
enlace copiado), de los que **5** van con `title_unverified` (2 por error de
digitación, 2 por el enlace cruzado, 1 sin radicado en el nombre).

**Total:** 299 filas → **292 laudos**, 11 con `title_unverified`.

## Volumen esperado

| Panel | 1999 | 2000 | 2001 | 2003 | 2004 | 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PDF únicos | 1 | 1 | 1 | 2 | 3 | 4 | 6 | 4 | 5 | 5 | 15 | 9 | 15 | 16 | 19 |

| Panel | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PDF únicos | 13 | 12 | 19 | 20 | 13 | 16 | 11 | 22 | 23 | 18 | 17 | 3 | 293 |

(No hay panel 2002. 1 de 2016-2017 es el PDF repetido con otro nombre → 292
laudos.) 1999-2014: 106 PDF, 194 MB; desde 2015: 186, 271 MB.

Primera corrida: **1 petición de listado + 292 PDF (~465 MB)**, unos
5-8 min. Corrida diaria: 1 petición (~210 KB, < 1 s) y casi siempre 0 PDF;
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

Atributos: `scheduled_min_lookback_days = 20_000`,
`checks_for_republication = True` (por defecto), sin `alerta_margen_dias`.

Sin cambios en `core/downloader.py`, sin migración Alembic. En producción:
`python -m core.seed` una vez.

## Pruebas

`tests/families/test_cc_medellin.py`, con `responses` y un fragmento real de
la página (paneles 2026, 2022, 2019, 2015, 2014 y 2001, que cubren las
maquetas del encabezado, también las de antes de 2015):

1. Radicado del nombre: cada forma de la tabla (`2025 A 0032 13-03-2026.pdf`,
   `2017-a-0013-25-ene-18.pdf`, `Rad_ 2018 A 0018- LAUDO- …f5d8.pdf`,
   `29-de-enero-de-2015-2013-A-034.pdf`, `2022 AP 0002 …`) → título con el
   consecutivo tal cual (`LA_CCMA_2013-A-034_2015`,
   `LA_CCMA_2022-AP-0002_2023`, `LA_CCMA_2016-A-004_2017`; sin relleno);
   `2022 a 0001` → `2022-A-0001`.
2. Fecha del encabezado con `fecha_es`; respaldo por nombre; año imposible
   (`2019 A 0087`, 2010 → 2020-08-12, con aviso); encabezado y nombre con
   fecha distinta (`2022 A 0048`) → gana el encabezado, con aviso.
3. Emparejamiento encabezado–enlace en las maquetas `<p><strong>…</strong><br/><a>`
   y `<ul><li>…</li></ul><p><a>`, y los encabezados viejos
   `Radicado1999 A 023. …` y `Radicado 6 de agosto de 2014- 2013 A 031`.
4. Enlace copiado (`2020 A 0007` → PDF de `2020 A 0025`): queda una sola fila,
   la que coincide, y se avisa.
5. Mismo PDF con dos nombres (`2016 A 004` / `2016 A 012`): una sola fila y
   aviso.
6. Error de digitación (`2023 A 0004` vs `2023 A 0037`): título del archivo,
   `title_unverified=True`, aviso.
7. Enlaces cruzados (panel 2014, `2013 A 007` ↔ `2013 A 031`): se quedan las
   dos filas, cada una con el título de su archivo, `title_unverified=True` y
   aviso.
8. URL: `?ver=` quitado, espacios como `%20`, ruta relativa → absoluta.
9. `detalle` sin `Partes:`; filtro por fecha, sin piso (entra 1999);
   `scheduled_min_lookback_days == 20_000`; sin `alerta_margen_dias`.
10. `stop_event`, `limit`, la página que falla (aviso y lista vacía) y la
    página sin paneles (aviso).

## Preguntas para el usuario / administrador

1. **Sigla `CCMA`** y clave `cc_medellin`: **Respondida por el administrador
   el 2026-11-26:** sigla `CCMA` aprobada. (La clave `cc_medellin` no tuvo
   objeción.)
2. **Nombre de la fuente** en el seed: "Cámara de Comercio de Medellín para
   Antioquia" (nombre legal) o "Cámara de Comercio de Medellín". (sigue
   abierta).
3. **Laudos de validación de acuerdos de recuperación** (`AP`, 4): ¿entran
   con el mismo tipo `Laudo arbitral` (propuesto)? (sigue abierta).
4. **Piso:** **Respondida por el administrador el 2026-11-26:** sin piso,
   todo desde 1999 (292 laudos).
5. **Título:** **Respondida por el administrador el 2026-11-26:** el
   consecutivo se copia tal cual, sin rellenar (`LA_CCMA_2016-A-004_2017`).
   Sigue abierto solo el separador: `LA_CCMA_2025-A-0032_2026` (propuesto) o
   `LA_CCMA_2025A0032_2026`.
6. **Alerta de salud:** `alerta_margen_dias` no tiene efecto con
   `scheduled_min_lookback_days = 20_000`; el aviso sale solo si pasa un año
   sin laudos con fecha reciente (puede pasar entre tandas). ¿Se acepta, como
   en Armenia? (sigue abierta, propuesta: sí).
7. **Dos PDF distintos con el mismo radicado** (laudo + aclaración, 0 casos
   hoy): ¿quedarse con el primero y avisar (propuesto), o actuaciones como
   Bogotá? (Actuaciones exigiría registrar la familia fuera de ella:
   `core/naming.py`, `core/db/repository.py` y un patrón en `core/utils.py`.)
   (sigue abierta).
8. **Dat@rbitral:** ¿interesa una v2 que agregue árbitros y temas al
   `detalle`? (sigue abierta).
9. ¿Se avisa a la Cámara de los **7 laudos con enlace equivocado**
   (`2020 A 0007`, `2021 A 0048`, `2019 A 0035`, `2018 A 0032`, `2016 A 012`,
   `2022 AP 0001` y, antes de 2015, `2010 A 051`) y del **enlace cruzado**
   de 2014 (`2013 A 007` ↔ `2013 A 031`)? (sigue abierta).

## Plan de implementación (cuando se apruebe)

1. Prueba + lector de radicado del nombre, título y URL (casos 1, 8).
2. Prueba + fechas: encabezado, respaldos, año imposible (caso 2).
3. Prueba + lectura del acordeón y emparejamiento con HTML real (caso 3).
4. Prueba + reglas de enlace copiado, PDF repetido, error de digitación y
   enlace cruzado (casos 4-7).
5. Prueba + `scrap()` con el sitio simulado (casos 9-10).
6. Import en `families/__init__.py`, seed y `tests/test_seed.py`.
7. Corrida real local completa (desde 1999) y segunda corrida sin descargas
   nuevas.
8. Ficha en `docs/guia-despliegue-sistemas.md`.
