# Fuente Cámara de Comercio de Cartagena — diseño

**Fecha:** 2026-11-23
**Entidad:** Cámara de Comercio de Cartagena — Centro de Arbitraje y
Conciliación (`cc_cartagena`, sigla `CCCAR`)
**Estado:** **aplazada** por el administrador (2026-11-25): sólo hay laudos
hasta 2019, así que por ahora no vale la pena. No se programa.

> **Fuente pequeña y quieta.** La página que dio el usuario
> (`https://www.cccartagena.org.co/es/laudos-arbitrales`) **es** el listado
> real: 17 laudos, de **2014 a 2019**. No hay nada publicado después de
> septiembre de 2019. Es viable sin saltar ninguna protección, pero la
> corrida diaria casi nunca va a traer algo nuevo (pregunta 5).

## Objetivo

Familia de scraper nueva `cc_cartagena` con una sección:

| Sección | URL de listado | tipo asignado | prefijo de título |
|---|---|---|---|
| Laudos | `GET https://www.cccartagena.org.co/es/laudos-arbitrales` | `Laudo arbitral` | `LA` |

Cada laudo (PDF) entra como un `RawDocModel`. Familia **plana**: sin
actuaciones, sin anexos, sin `family_params`. Mismas convenciones que las
otras cámaras (`cc_armenia`, `ccb`, `cc_barranquilla`).

## Construcción del sitio

- CMS propio ("Smartinfo", PHP sobre Apache). TLS válido (cadena completa,
  `requests` con `verify=True` funciona). Sin WAF, sin captcha, sin
  JavaScript obligatorio. Pone una cookie `smartinfoWeb` que no hace falta.
- **El listado completo viene en el HTML de la página** (~69 KB, una
  petición, < 1 s). La página tiene un buscador (nombre, fecha inicial/final,
  "acordeones por página") que llama por AJAX a
  `POST /contenido.php` (`accion=getDocumentos&tipo=Laudos_arbitrales&…`).
  Se probó y devuelve lo mismo (17 tarjetas; la página 2 dice "No se
  encontraron documentos"). **No se usa**: `robots.txt` prohíbe
  `/contenido.php`, y la página normal ya trae todo.
- La paginación del buscador es por **acordeones** (grupos), no por
  documentos; hay un solo acordeón, "Laudos Arbitrales". Sin paginación real.
- La versión en inglés (`/en/laudos-arbitrales`) trae las mismas 17
  tarjetas; se usa sólo la española.

### La tarjeta

```html
<div class="col-lg-4 p-2"><div class="fondo-bc1 p-3 d-flex" style="height: 230px;">
  …
  <b class="txt_bold txt_color_azul_fuente txt_pdf" style="font-size:15px">Laudo arbitral Portal Calicanto S.A.S. contra Transcaribe</b>
  <div class="pt-2">Fecha de inicio: 19/09/2019</div>
  <p class="text-start pt-2 fs-5">Laudo arbitral Portal Calicanto S.A.S. contra Transcaribe.</p>
  <div class="d-flex justify-content-end">
    <a href="https://www.cccartagena.org.co/recursos/docs/pdfs/file-20251015552019LaudoarbitralPortalCalicantoS.A.ScontraTranscaribe.pdf" target="_blank" class="pt-2">…Ver PDF…</a>
    <a href="…mismo enlace…" download="Laudo arbitral Portal Calicanto S.A.S. contra Transcaribe.pdf" target="_blank">…Descargar PDF…</a>
  </div>
</div></div>
```

| Dato | De dónde |
|---|---|
| partes | `b.txt_pdf` (quitando "Laudo arbitral"/"Laudo abritral" del inicio) |
| fecha | `Fecha de inicio: DD/MM/AAAA` (ver "Fechas") |
| enlace | primer `<a href>` a `/recursos/docs/pdfs/…` de la tarjeta (los dos enlaces son el mismo) |
| radicado | **no hay** (ni en la tarjeta ni en el nombre del archivo) |

- El nombre del archivo es `file-<AAAAMMDD de subida><2 cifras><año><nombre original>.pdf`.
  Ej.: `file-20251015` (subido el 15-10-2025, cuando se migró el sitio) +
  `55` + `2019` + `LaudoarbitralPortal…`. El año del nombre sirve para
  **comprobar** la fecha de la tarjeta (ver "Casos raros").

### Descarga

- `GET` directo al PDF: `200`, `application/pdf`, **sin `Content-Length`**
  (respuesta por bloques), sin `Last-Modified` ni `ETag`. Los 17 bajan bien
  (0 rotos), 123 MB en total; el mayor, 64 MB (Calicanto 2019, escaneo de
  256 páginas). Cabe en `MAX_DOWNLOAD_MB` (300).
- `HEAD` responde `200` pero **sin `Content-Length`**: la revisión de
  republicación por tamaño no sirve (`check_remote_content_length` devuelve
  `None` y el worker volvería a bajar los 17 en cada corrida). Por eso
  **`checks_for_republication = False`** (como `ccb`).
- `link = {"url": <enlace del PDF>, "method": "GET"}`.

## Fechas y filtro

- La tarjeta dice **"Fecha de inicio"**, pero en 13 de los 14 PDF con texto
  coincide con la **"FECHA LAUDO"** de la ficha de relatoría que abre el
  PDF (ej. Doris Charry: tarjeta `23/04/2018`, PDF "FECHA LAUDO: 23 de abril
  de 2018"). Se toma como **fecha del laudo**. Los otros 4 son escaneos y no
  se pueden comprobar (la fecha de escaneo de cada uno es posterior a la de
  la tarjeta, que cuadra).
- La única excepción (Gilberto Álvarez vs. Barcelona de Indias): tarjeta
  `05/07/2018`, laudo del **17 de mayo de 2019** (dice el PDF), nombre de
  archivo `…2019…`. Ver "Casos raros".
- `f_public = f_providencia` = fecha de la tarjeta. Filtro
  `fini <= fecha <= ffin`.
- **Piso:** propuesta: todo lo que hay, desde **2014** (17 laudos; desde
  2015 serían 12). Pregunta 3.
- Como leer el listado es una sola petición, la corrida diaria **recorre
  todo siempre**: `scheduled_min_lookback_days = 10_000` (como Armenia y
  Barranquilla).
- **Alerta de salud:** el último laudo es de 2019. La alerta de "fuente que
  puede estar fallando" va a salir siempre. En Armenia se aceptó una alerta
  perpetua; aquí se propone lo mismo o subir `alerta_margen_dias`
  (pregunta 5).

## Número y nombre canónico

Sin radicado en la página ni en el nombre del archivo. Algunos PDF citan
radicados de **otros** procesos (sentencias citadas), así que leerlo del
texto no es fiable, y 4 de 17 son escaneos.

Se reutiliza la propuesta de Barranquilla (pregunta 4):

- **Título:** `LA_CCCAR_{MMDD}_{año}` — la fecha (mes y día) hace de número,
  manteniendo la forma `{PREFIJO}_{SIGLA}_{número}_{año}`. Ej.:
  `LA_CCCAR_0919_2019`.
- Misma fecha dos veces (hoy: los dos Assignia del 05/05/2014): el segundo
  lleva `_2` y aviso → `LA_CCCAR_0505_2014_2`.
- `detalle` = las partes, desde `b.txt_pdf` sin la palabra "Laudo arbitral"
  (`Portal Calicanto S.A.S. contra Transcaribe`).
- `save_path = storage_path(_SOURCE, fecha, "Laudo arbitral", f"{title}(extension)")`.
- Sigla `CCCAR`, decidida por el administrador el 2026-11-25 (pregunta 1).
  No choca con las existentes (`CCB`, `CCAQ`, `CC`, `CCIR`, `CCO`, la
  propuesta `CCBAR`, ni `CCC`, que es Cali).

## Casos raros del sitio

| Caso | Qué se hace |
|---|---|
| **Gilberto Álvarez**: tarjeta `05/07/2018`, laudo real 17-05-2019, archivo `…2019…` | Año de la tarjeta ≠ año del nombre del archivo → se usa la fecha de la tarjeta, `title_unverified=True` y aviso (como el cruce de ICA). Alternativa en pregunta 6. |
| **Dos Assignia contra Transcaribe del 05/05/2014**: uno con ficha + texto (731 págs., la ficha dice Assignia **y Concrescol**), otro escaneado (573 págs., tarjeta "Assignia y Concrescol") | Muy probablemente el **mismo laudo** en dos archivos. Se guardan los dos (`…_0505_2014` y `…_0505_2014_2`) con aviso; no se "arregla". Pregunta 7. |
| **Portal Calicanto 2016** (02/05/2016): el PDF tiene **2 páginas**, sólo la ficha de relatoría, sin el laudo | Se guarda tal cual (es lo que publica la Cámara). Se documenta. |
| Errata "Laudo **abritral**" (Luis Felipe Aponte) | Se quita igual del inicio para el `detalle`. |
| Mismo enlace dos veces en la tarjeta (ver/descargar) | Dedup por enlace. |
| Tarjeta sin enlace o sin fecha (0 hoy) | Se omite con aviso. |
| Fecha con otro formato (0 hoy) | Se omite con aviso. |

## Volumen esperado

| 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020-2026 | Total |
|---|---|---|---|---|---|---|---|
| 5 | 1 | 4 | 1 | 3 | 3 | 0 | **17** |

(por fecha de la tarjeta). Corrida completa: 17 PDF, ≈ 123 MB, 1-2 min.
Corrida diaria: 1 petición y 0 descargas.

## Riesgos

- **Identidad del documento:** el `doc_id` sale del enlace + fecha. El
  enlace lleva la fecha de subida (`file-20251015…`); si la Cámara vuelve a
  subir un laudo (como hizo con Calicanto 2016 el 20-11-2025), el enlace
  cambia y entra como documento nuevo con el mismo título. Se detecta en la
  revisión de la corrida; no se intenta evitar.
- El sitio se migró en octubre de 2025; otra migración cambiaría el HTML.
  Si la página deja de traer tarjetas, la corrida avisa "0 laudos" (error
  visible, no silencioso).

## Fuera de alcance (v1)

- Conciliaciones, amigable composición, insolvencia, listas de árbitros,
  tarifas, reglamentos, noticias del Centro.
- El buscador AJAX (`/contenido.php`, prohibido en `robots.txt`).
- Leer el radicado o la fecha desde el PDF (`resolve_unverified_document`):
  para 17 documentos y 1 caso dudoso no compensa.

## Integración

**Archivos nuevos:** `core/scrapers/families/cc_cartagena.py`
(`@register_family("cc_cartagena")`), `tests/families/test_cc_cartagena.py`.

**Archivos que se tocan:** `core/scrapers/families/__init__.py`,
`core/seed.py` (`_SOURCE = "Cámara de Comercio de Cartagena"`,
`family_params={}`), `tests/test_seed.py` (conteos), ficha en
`docs/guia-despliegue-sistemas.md`.

Sin cambios en el descargador. Sin migración Alembic. En producción:
`python -m core.seed` una vez.

## Pruebas

`tests/families/test_cc_cartagena.py`, con `responses` y un fragmento real
del HTML de la página:

1. Lectura de tarjetas: partes, fecha `DD/MM/AAAA`, enlace (dedup de los dos
   `<a>`); errata "abritral".
2. Título: `LA_CCCAR_0919_2019`; misma fecha dos veces → `_2` + aviso;
   `detalle` = partes.
3. Cruce del año de la tarjeta con el del nombre del archivo: distinto →
   `title_unverified=True` + aviso; nombre sin el patrón → sin cruce.
4. Tarjeta sin enlace / sin fecha / fecha ilegible → omitida con aviso.
5. Filtro por fecha y piso; `scheduled_min_lookback_days == 10_000`;
   `checks_for_republication is False`.
6. `stop_event`, `limit`, página que falla (aviso, sin tumbar), página sin
   tarjetas → aviso.

## Preguntas para el usuario / administrador

1. **Clave y sigla:** **Respondida (administrador, 2026-11-25):** sigla `CCCAR`. Clave `cc_cartagena` sin
   objeción.
2. **¿Vale la pena la fuente?** **Respondida (administrador, 2026-11-25):** **por ahora no**. Se
   retoma si la Cámara publica laudos recientes.
3. **Piso:** ¿todo desde 2014 (propuesto, 17) o desde 2015 (12)?
4. **Título sin radicado:** ¿`LA_CCCAR_{MMDD}_{año}` (igual que la propuesta
   de Barranquilla) o el título descriptivo con las partes?
5. **Alerta de salud:** saldrá siempre (último laudo 2019). ¿Se acepta como
   en Armenia, o se sube `alerta_margen_dias`?
6. **Gilberto Álvarez** (fecha de la tarjeta 2018, laudo 2019): ¿se deja la
   fecha de la tarjeta con `title_unverified` (propuesto) o se corrige a
   mano a `2019-05-17` en el código?
7. **Los dos Assignia del 05/05/2014** (probablemente el mismo laudo): ¿se
   guardan los dos (propuesto) o sólo el que tiene texto?

## Plan de implementación (cuando se apruebe)

1. Prueba + lector de tarjetas con HTML real (casos 1, 4).
2. Prueba + título, `_2` y cruce de año (casos 2-3).
3. Prueba + `scrap()` con el sitio simulado (casos 5-6).
4. Import en `families/__init__.py`, seed y `tests/test_seed.py`.
5. Corrida real local completa y segunda corrida sin descargas nuevas.
6. Ficha en `docs/guia-despliegue-sistemas.md`.
