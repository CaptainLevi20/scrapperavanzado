# Fuente ICBF (conceptos) — diseño

**Fecha:** 2026-11-10
**Entidad:** Instituto Colombiano de Bienestar Familiar (`icbf`, sigla `ICBF`)
**Estado:** pendiente de aprobación del administrador — **no implementar todavía**

> El enlace que dio el usuario (`https://www.icbf.gov.co/concepto`) es el
> listado real: una vista de Drupal (`views-exposed-form-normograma-page-3`)
> del normograma del ICBF filtrada a la categoría CONCEPTO. Cada fila enlaza
> a una página de detalle (`/normograma/concepto-<n>-de-<año>`) que trae el
> archivo `.docx`.

## Objetivo

Familia de scraper nueva `icbf` con una sola sección, desde **2015**:

| Sección | URL | tipo asignado | prefijo de título |
|---|---|---|---|
| Conceptos | `https://www.icbf.gov.co/concepto` | `Concepto` | `CTO` |

Familia **plana**: sin actuaciones, sin anexos, sin `family_params`.

## Construcción del sitio

- Drupal 9/10 (vistas con `better_exposed_filters`). HTML servido en el
  servidor: sin JavaScript, sin WAF, sin captcha, sin cookies. Certificado
  TLS válido. UTF-8.
- **Listado:** `GET /concepto?page=<p>` (p desde 0), **100 filas por página**,
  ordenado por año y número descendente. Hoy 901 conceptos en 10 páginas
  (la 10.ª trae 1 fila; la 11.ª, 0).
- **Filtro por año:** `GET /concepto?field_anio_value=<año>&page=<p>`
  devuelve sólo ese año (probado: 2025 → los 10 conceptos de 2025). Es lo que
  usa la familia: así la corrida diaria pide una sola página.
- Cada fila es un `<tr>` con cuatro celdas y un enlace:

  | Celda | Ejemplo |
  |---|---|
  | Categoría | `CONCEPTO` (los 901) |
  | Número | `10`, `3C`, `132 A`, `142-1` |
  | Año | `2026` |
  | Temática (epígrafe) | `Representación legal de niños, niñas y adolescentes…` |
  | Enlace | `<a href="/normograma/concepto-10-de-2026">Consultar</a>` |

- **Detalle:** `GET /normograma/concepto-<n>-de-<año>` → un único
  `<a class="btn-documento" href="/sites/default/files/normas/CONCEPTO%2010%20DE%202026.docx">`.
  El slug **no** se arma a mano: se usa el `href` de la fila (hay slugs
  irregulares como `concepto-132-de-2017-0` y `concepto-1421-de-2015`).
- **Descarga:** el `.docx` responde `200`,
  `Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
  con `Last-Modified` y `ETag`, sin `Content-Disposition`. El descargador ya
  deduce `.docx` del `Content-Type`. Republicación por `HEAD`: funciona
  (`checks_for_republication = True`, por defecto).

## Fechas y filtro

El sitio **no da ninguna fecha** del concepto: ni en el listado ni en el
detalle (la página de detalle sólo tiene `body`, sin campos de fecha). Sólo el
año. Como pidió el usuario, se usa el año:

- `f_public = f_providencia = "<año>-01-01"` (fecha de relleno, misma regla
  que los conceptos de Supertransporte).
- **Filtro por año:** entra el concepto si `int(fini[:4]) <= año <= int(ffin[:4])`.
- **Piso:** `_ANIO_MINIMO = 2015`. Se piden sólo los años
  `max(fini.año, 2015) … ffin.año`.
- **Corrida diaria:** `fini` y `ffin` caen en el año en curso → una página
  del año actual (≤ 15 filas) + un detalle por concepto. Los que ya están
  guardados no se vuelven a bajar (el worker deduplica por `doc_id`); un
  concepto nuevo del año aparece el día en que el ICBF lo publica, aunque su
  fecha quede en el 1 de enero. En enero la corrida diaria cubre también los
  últimos días de diciembre (el año anterior), así que un concepto subido a
  finales de año no se pierde.
- No hace falta `scheduled_min_lookback_days`.
- **Aviso de salud de fuentes:** con una sola fecha por año, la fuente nunca
  llega a las 6 fechas distintas que pide `core/salud_fuentes.py`, así que no
  dispara alertas de "puede estar fallando". Es aceptable para una fuente de
  ~10 documentos al año.

## Número y nombre canónico

`CTO_ICBF_{número}_{año}`:

- Número sólo dígitos → relleno a 4: `10` → `CTO_ICBF_0010_2026`.
- Número con sufijo (letra o `-n`) → se rellena la parte numérica y se
  conserva el sufijo en mayúscula, sin espacios: `3C` → `CTO_ICBF_0003C_2020`;
  `132 A` → `CTO_ICBF_0132A_2017`; `142-1` → `CTO_ICBF_0142-1_2015`.
  (Hoy son 11 de 901; los sufijos distinguen conceptos distintos, como
  `11A`/`11B` de 2018.)
- Patrón: `^(\d+)\s*([A-Za-z]|-\d+)?$`. Lo que no cumpla → número saneado
  tal cual, `title_unverified=True` y aviso `on_progress` (0 casos hoy).
- El año del título sale de la columna Año. `title_unverified=False` en el
  caso normal.
- `detalle` = epígrafe (columna Temática), sin cortar.

## Recorrido

1. Para cada año en `[max(fini.año, 2015), ffin.año]`: `GET /concepto?field_anio_value=<año>&page=0, 1, …`
   hasta una página con menos de 100 filas (tope duro de 5 páginas por año;
   el año más grande, 2016, tiene 166).
2. Para cada fila con categoría `CONCEPTO`: `GET` del detalle y se toma el
   `href` de `a.btn-documento`.
3. Se arma el `RawDocModel` con el `.docx`.

Corrida completa desde 2015: ~13 páginas de listado + ~717 detalles ≈ 4-5
minutos (≈0,3 s por petición, medido). Corrida diaria: 1 listado + ≤ 15
detalles.

## Casos raros del sitio

- **Concepto sin archivo:** `concepto-75-de-2015` no trae `btn-documento`.
  → se omite con aviso `on_progress` (no hay nada que descargar).
- **Números con sufijo:** ver "Número y nombre canónico".
- Huecos en la numeración (2026: 1, 2, 4, 5, 7, 10; 2023: 1-4, 7, 9, 11-15):
  el ICBF no publica todos los conceptos. No es un error de la familia.
- Duplicados: 0 pares `(número, año)` repetidos hoy. Dedup dentro de la
  corrida por la URL del `.docx`; si dos filas apuntan al mismo archivo, se
  queda la primera y se avisa.

## `save_path` / almacenamiento

`storage_path(_SOURCE, f_public, "Concepto", f"{title}(extension)")`.
`_SOURCE = "Instituto Colombiano de Bienestar Familiar"` (igual al `name` del
seed).

## Volumen esperado

| Año | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Conceptos | 130 | 166 | 153 | 80 | 61 | 44 | 32 | 13 | 11 | 11 | 10 | 6 |

Corrida completa desde 2015: **~716 documentos** (717 filas menos el que no
tiene archivo). Todos `.docx` (sin vista previa PDF salvo que el sistema
convierta Word; se ve como los demás `.docx` del proyecto).

## Fuera de alcance (v1)

- Conceptos de 2014 (184): anteriores al piso.
- El resto del normograma del ICBF (resoluciones, circulares, acuerdos…):
  no los pidió el usuario.
- El texto del concepto en HTML (el detalle sólo lo muestra embebido en el
  visor de Google Docs).

## Integración

**Archivos nuevos:**

- `core/scrapers/families/icbf.py` — `@register_family("icbf")`,
  `class ScrapIcbf(BaseScrapper)`.
- `tests/families/test_icbf.py`.

**Archivos que se tocan:**

- `core/scrapers/families/__init__.py` — añadir `icbf` al import.
- `core/seed.py` — entrada en `_FAMILIES` y
  `create_source_if_missing(db, family_key="icbf", name=_SOURCE, family_params={})`.
- `tests/test_seed.py` — sumar uno al número de familias y al bloque de
  "fuente única", añadir `"icbf"` al conjunto de claves. Los conteos se suben
  sobre lo que haya en la rama al implementar (hoy 36 familias /
  `1 + 28 + 33 + 33 + 6`; el ICA se diseña a la vez).
- `docs/guia-despliegue-sistemas.md` — ficha de la fuente (paso 7).

Sin migración Alembic. En producción: `python -m core.seed` una vez.

## Pruebas

`tests/families/test_icbf.py`, con fragmentos reales del HTML y `responses`,
sin internet:

1. Número → título: `10` → `CTO_ICBF_0010_2026`; `3C` → `CTO_ICBF_0003C_2020`;
   `132 A` → `CTO_ICBF_0132A_2017`; `142-1` → `CTO_ICBF_0142-1_2015`.
2. Número fuera del patrón → título saneado, `title_unverified=True`, aviso.
3. Parseo de la fila (número, año, epígrafe, `href` del detalle).
4. Parseo del detalle → URL absoluta del `.docx`.
5. Un documento completo → `tipo="Concepto"`, `f_public="2026-01-01"`,
   `f_providencia`, `detalle`, `link`, `save_path`.
6. Años pedidos: `fini=2010-01-01, ffin=2016-06-30` → sólo 2015 y 2016;
   `fini=ffin=2026-11-10` → sólo 2026.
7. Paginación: página de 100 → pide la siguiente; menos de 100 → se detiene.
8. Detalle sin `btn-documento` → omitido con aviso.
9. Dedup por URL del `.docx`.
10. `stop_event` activado → corta y devuelve lo acumulado.
11. Falla del listado de un año (500) → aviso y sigue con el siguiente año;
    falla de un detalle → aviso y sigue.
12. `limit` respetado.

Se corren dirigidas: `pytest tests/families/test_icbf.py tests/test_seed.py`.

## Riesgos y notas

- **Fechas de relleno:** todos los conceptos de un año quedan con fecha
  1 de enero. En el frontend se ordenan por año, no por fecha real.
- Los nombres de archivo del sitio (`CONCEPTO 10 DE 2026.docx`) no se usan
  para el título; si el ICBF sube un archivo equivocado, se guarda con el
  título de la fila.
- Si el ICBF cambia la vista de Drupal (por ejemplo, quita el filtro por año),
  la corrida dará 0 filas. El scraper avisa "Error: el listado no trajo
  ningún concepto" sólo cuando **todos** los años pedidos vienen vacíos y
  alguno es anterior al año en curso (en enero es normal que el año nuevo
  todavía no tenga conceptos).

## Decisiones (2026-11-10)

1. **Alcance:** sólo conceptos.
2. **Fecha:** se usa el año del concepto (`<año>-01-01`), pedido por el
   usuario.
3. **Piso:** 2015.
4. **Familia propia** `icbf`, separada del ICA.

## Preguntas abiertas

- **Sigla** `ICBF` y prefijo `CTO` (el mismo de Procuraduría y SSF). Se
  proponen así; confirmar.

## Plan de implementación (cuando se apruebe)

1. Prueba + función de número → título (casos 1-2).
2. Prueba + parseo de fila y de detalle con HTML real (casos 3-4).
3. Prueba + `scrap()` con el sitio simulado (casos 5-12).
4. Import en `families/__init__.py`, seed y `tests/test_seed.py`.
5. Corrida real local desde 2015 y segunda corrida sin descargas nuevas.
6. Ficha en `docs/guia-despliegue-sistemas.md`.
