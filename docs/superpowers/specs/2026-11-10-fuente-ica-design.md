# Fuente ICA — diseño

**Fecha:** 2026-11-10
**Entidad:** Instituto Colombiano Agropecuario (`ica`, sigla `ICA`)
**Estado:** pendiente de aprobación del administrador — **no implementar todavía**

> Los dos enlaces que dio el usuario son los listados reales, dentro de
> "Normativa › Normas ICA" del sitio (Kentico CMS, ASP.NET). Ojo con los
> nombres: la página `resoluciones-oficinas-nacionales` se titula en el sitio
> **"Resoluciones MSF y RT"** (resoluciones nacionales de medidas sanitarias y
> fitosanitarias y reglamentos técnicos); `resoluciones-seccionales` es
> **"Resoluciones Gerencias Seccionales"**.

## Objetivo

Familia de scraper nueva `ica` con dos secciones, desde **2015** (año de
expedición):

| Sección | URL | tipo asignado | título |
|---|---|---|---|
| Resoluciones seccionales | `https://www.ica.gov.co/normatividad/normas-ica/resoluciones-seccionales` | `Resolución` | `R_ICA_S{número}_{año}` |
| Resoluciones nacionales (MSF y RT) | `https://www.ica.gov.co/normatividad/normas-ica/resoluciones-oficinas-nacionales` | `Resolución` | `R_ICA_{número}_{año}` |

Ejemplos pedidos por el usuario: `R_ICA_S19595_2026` (seccional) y
`R_ICA_22227_2026` (nacional). Familia **plana**: sin actuaciones, sin
anexos, sin `family_params`.

## Construcción del sitio

- Kentico CMS sobre ASP.NET. HTML servido en el servidor: sin JavaScript para
  el listado, sin WAF, sin captcha, sin cookies. Certificado TLS válido.
  UTF-8. Cada página tarda 0,4-0,9 s.
- **Paginación:** `?page=<p>` (p desde 1; la 1 es la URL sin parámetro),
  **4 resoluciones por página**. Hoy: seccionales 59 páginas (234 filas),
  nacionales 155 páginas (617 filas).
- **Cuidado:** una página fuera de rango (`?page=999`) **no** viene vacía:
  devuelve `200` con el contenido de la página 1. El número de la última
  página se lee del enlace `aria-label="Ultima"` de la página 1 y no se pasa
  de ahí.
- **Orden:** ambos listados están ordenados por **fecha de expedición
  descendente**, sin una sola excepción en las 851 filas. Por fecha de
  publicación **no** están ordenados (47 y 82 saltos).
- Cada resolución es un `div.row.py-3`:

  ```html
  <div class="row py-3">
    <div class="col-md-2 ..."><a href="/getattachment/9b51243d-…/2026R000019595.aspx" title="Descargar el documento Resolución 19595 de 2026">…</a><div>302 kb</div></div>
    <div class="col-md-10">
      <div class="tiponorma">Resolución</div>
      <h2><a href="/getattachment/9b51243d-…/2026R000019595.aspx" class="text-5">Resolución 19595 de 2026 - “Por la cual se modifican…”.</a></h2>
      <div>Publicación: 02 de octubre de 2026 | Expedición: 02 de octubre de 2026</div>
      <div>Observación: … <a href="/getattachment/…/2026R00015837.aspx">artículo 4 de la Resolución No. 00015837…</a></div>
      <!-- sólo nacionales: --> <a href="imprenta.gov.co/diario-oficial">Diario Oficial: 53685</a> (09/11/2026)
    </div>
  </div>
  ```

| Dato | De dónde |
|---|---|
| enlace | `href` del `h2 a` (igual al del ícono en las 851 filas) |
| número y año | texto del `h2 a`: `<Palabra> <número> de <año> - <epígrafe>` |
| epígrafe | el resto del texto del `h2 a` |
| fecha de publicación | `Publicación: DD de <mes> de AAAA` |
| fecha de expedición | `Expedición: DD de <mes> de AAAA` |
| observación | `div` con "Observación:" (opcional) |
| Diario Oficial | número y fecha (sólo nacionales, opcional) |

Los enlaces dentro de "Observación" apuntan a **otras** resoluciones
(modificadas o derogadas) y se ignoran.

- **Descarga:** `GET /getattachment/<guid>/<nombre>.aspx` → `200`,
  `Content-Type: application/pdf`, `Content-Disposition: inline;
  filename="Resolucion-00019595-del-02-de-octubre-2026-G-S-Tolima.pdf"`,
  `ETag` y `Last-Modified`. El descargador toma la extensión `.pdf` del
  `Content-Disposition` (la URL termina en `.aspx`). Republicación por
  `HEAD`: funciona (`checks_for_republication = True`, por defecto).

## Número y nombre canónico

- Regex sobre el texto del enlace:
  `^\s*(?:Resoluci[oó]n|Norma|Acuerdo)\s+(?:No\.?\s*)?(\d+)\s+de\s+(\d{4})`.
- Número **sin ceros a la izquierda** y relleno a 4 (`{n:04d}`), nunca
  recortado: `19595` → `19595`, `805` → `0805`, `20263040030395` →
  `20263040030395` (un número tipo radicado de SINAD que el ICA usó en 2026).
  Hoy hay números de 1 a 6 cifras más ese de 14.
- Seccional → `R_ICA_S{número}_{año}`; nacional → `R_ICA_{número}_{año}`.
  El ICA usa un consecutivo único para todo el instituto, así que la `S` sólo
  marca la sección, como pidió el usuario.
- El año del título es el del texto del enlace. Si no coincide con el año de
  expedición se avisa por `on_progress` y se deja el del texto (8 casos, todos
  errores de carga del sitio, p. ej. "Resolución 899 de 2021" expedida el
  31-01-2022 con archivo `2022R889`).
- Texto que no cumple la regex (0 casos hoy) → título `R_ICA_[S]<texto saneado>`,
  `title_unverified=True` y aviso.
- `detalle` = epígrafe; si hay observación, se agrega después de " — ". En
  nacionales también "Diario Oficial <n> (<fecha>)".

### `tiponorma` mal puesto

Cuatro filas no dicen "Resolución" en `tiponorma` ni en el texto, pero son
resoluciones (el archivo es `…R…` y el texto empieza "Por la cual…"):
`Norma 8970 de 2024` y `Acuerdo 97962 de 2021` (seccionales),
`Norma 11537 de 2025` y `Norma 106407 de 2021` (nacionales). Se toman como
`Resolución` igual que las demás: la sección entera es de resoluciones.

## Fechas y filtro

- `f_public` = Publicación; `f_providencia` = Expedición.
- **`filters_by_publication_date = True`**: entra la resolución cuya fecha de
  **publicación** cae en `[fini, ffin]`. Motivo: el ICA publica con retraso
  (desde 2020: mediana 4-6 días, p99 133-210 días, máximo 1.964 días), y si
  se filtrara por expedición la corrida diaria perdería lo publicado tarde.
- **Piso:** se descarta lo **expedido** antes de 2015-01-01
  (`_ANIO_MINIMO = 2015`). Ej.: las ~200 normas viejas (1970-2008) que el ICA
  cargó en las nacionales en 2009-2010 no entran.
- **Hasta dónde se pagina:** como el listado va por expedición descendente,
  se recorren páginas hasta que la última fila de una página tenga expedición
  anterior a `max(2015-01-01, fini − 730 días)`, o hasta la última página.
  Los 730 días de margen cubren todo lo publicado desde 2015 salvo un caso
  (Resolución nacional 93858 de 2021, expedida 26-03-2021 y publicada
  11-08-2026). Ese tipo de caso sólo lo trae una corrida manual completa.
  Ver "Preguntas abiertas".
- Corrida diaria con ese margen: ~10 páginas de seccionales + ~20 de
  nacionales ≈ 20 s. Corrida completa desde 2015: ~55 + ~92 páginas ≈ 1,5 min.
- No hace falta `scheduled_min_lookback_days` (la corrida ya mira dos años
  atrás por expedición y filtra por publicación).
- Fecha ilegible (0 casos hoy) → fila descartada con aviso.
- Hay una fila con publicación 3 días **antes** que la expedición (30392 de
  2018): error del sitio, se deja tal cual.

## Deduplicación dentro de una corrida

- Clave: (sección, número, año). La seccional **28027 de 2018** aparece dos
  veces con archivos distintos (dos GUID, mismo texto) → se queda la primera
  y se avisa.
- Hoy no hay URL repetidas ni números repetidos entre las dos secciones (y si
  los hubiera, la `S` los separa).

## `save_path` / almacenamiento

`storage_path(_SOURCE, f_public, "Resolución", f"{title}(extension)")`.
`_SOURCE = "Instituto Colombiano Agropecuario"` (igual al `name` del seed).

## Volumen esperado

Por año de expedición:

| Sección | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Seccionales | 13 | 20 | 20 | 18 | 20 | 11 | 17 | 20 | 19 | 20 | 24 | 19 | 221 |
| Nacionales (MSF y RT) | 13 | 19 | 25 | 27 | 20 | 35 | 47 | 32 | 31 | 41 | 38 | 39 | 367 |

Corrida completa desde 2015: **~587 documentos** (588 filas menos el
duplicado 28027). Unos 5 por mes.

## Fuera de alcance (v1)

Las otras páginas de "Normas ICA", que el usuario no pidió:

- Acuerdos, Conceptos Jurídicos, Memorandos de Entendimiento,
  Normatividad COVID-19, Resoluciones de Carácter Administrativo,
  Resoluciones OVM.
- Resoluciones expedidas antes de 2015.
- El nombre de la seccional (Tolima, Cesar…): sólo viene en el nombre del
  archivo al descargarlo (`…-G-S-Tolima.pdf`), no en el listado. No va en el
  título.

## Integración

**Archivos nuevos:**

- `core/scrapers/families/ica.py` — `@register_family("ica")`,
  `class ScrapIca(BaseScrapper)`, `filters_by_publication_date = True`.
- `tests/families/test_ica.py`.

**Archivos que se tocan:**

- `core/scrapers/families/__init__.py` — añadir `ica` al import.
- `core/seed.py` — entrada en `_FAMILIES` y
  `create_source_if_missing(db, family_key="ica", name=_SOURCE, family_params={})`.
- `tests/test_seed.py` — sumar uno al número de familias y al bloque de
  "fuente única", añadir `"ica"` al conjunto de claves. Los conteos se suben
  sobre lo que haya en la rama al implementar (hoy 36 familias /
  `1 + 28 + 33 + 33 + 6`; el ICBF se diseña a la vez).
- `docs/guia-despliegue-sistemas.md` — ficha de la fuente (paso 7).

Sin cambios en el descargador. Sin migración Alembic. En producción:
`python -m core.seed` una vez.

## Pruebas

`tests/families/test_ica.py`, con fragmentos reales del HTML y `responses`,
sin internet:

1. Texto → título: `Resolución 19595 de 2026` seccional →
   `R_ICA_S19595_2026`; `Resolución 22227 de 2026` nacional →
   `R_ICA_22227_2026`; `Resolución 805 de 2025` → `R_ICA_S0805_2025`;
   `Resolución 20263040030395 de 2026` → número completo.
2. `Norma 8970 de 2024` y `Acuerdo 97962 de 2021` → `Resolución`,
   `R_ICA_S8970_2024`, `R_ICA_S97962_2021`.
3. Texto fuera de la regex → título saneado, `title_unverified=True`, aviso.
4. Fechas en español ("02 de octubre de 2026") → `f_public` y
   `f_providencia`.
5. Año del texto distinto del de expedición → se deja el del texto y se avisa.
6. `detalle` con epígrafe + observación (+ Diario Oficial en nacionales).
7. Última página leída de `aria-label="Ultima"`; no se pide más allá.
8. Corte de paginación: página cuya última fila es anterior a
   `fini − 730 días` → no se pide la siguiente.
9. Filtro por publicación: expedida en rango pero publicada fuera → no entra;
   expedida meses antes y publicada en rango → entra.
10. Piso: expedida en 2014 y publicada en 2015 → descartada.
11. Dedup (28027 de 2018 dos veces) → una sola, con aviso.
12. `stop_event` → corta y devuelve lo acumulado.
13. Falla de una página (500) → aviso y se sigue con la otra sección;
    falla de la página 1 → aviso, sección vacía.
14. `limit` respetado.

Se corren dirigidas: `pytest tests/families/test_ica.py tests/test_seed.py`.

## Riesgos y notas

- **Publicación tardía:** casi todo sale en días, pero hay resoluciones
  publicadas meses o años después. La corrida diaria mira dos años de
  expedición; lo que salga más tarde sólo entra con una corrida manual.
- **Errores de carga del sitio:** años del título que no cuadran con la
  expedición, un duplicado, `tiponorma` mal puesto. Se documentan; no se
  corrigen.
- Las URL de descarga llevan un GUID de Kentico; si el ICA reemplaza el
  archivo con otro GUID, el sistema lo verá como documento nuevo con el mismo
  título.
- Si el ICA cambia la plantilla (clases `row py-3`, `tiponorma`, `text-5`),
  la sección dará 0 filas: el scraper avisa "Error: <sección> no trajo
  ninguna resolución" cuando la página 1 no tiene filas.

## Decisiones (2026-11-10)

1. **Alcance:** resoluciones seccionales y resoluciones nacionales MSF y RT
   (las dos URL del usuario).
2. **Títulos:** `R_ICA_S<número>_<año>` para seccionales y
   `R_ICA_<número>_<año>` para nacionales; el número puede tener más de 5
   cifras.
3. **Piso:** 2015, por año de expedición.
4. **Familia propia** `ica`, separada del ICBF, con las dos secciones.

## Preguntas abiertas

1. **¿`tipo` distinto para seccionales?** Se propone `Resolución` en las dos
   (la `S` del título ya las separa). Alternativa: `Resolución Seccional`,
   para poder filtrarlas aparte en el frontend.
2. **Margen de paginación de la corrida diaria:** se proponen 730 días
   (~30 páginas, ~20 s). Alternativa: recorrer siempre las ~215 páginas
   (~2-3 min, no se pierde ni el caso de 5 años de retraso).

## Plan de implementación (cuando se apruebe)

1. Prueba + función de texto → número, año y título (casos 1-3, 5).
2. Prueba + parseo de una fila y de la paginación con HTML real (casos 4, 6, 7).
3. Prueba + `scrap()` con el sitio simulado (casos 8-14).
4. Import en `families/__init__.py`, seed y `tests/test_seed.py`.
5. Corrida real local desde 2015 y segunda corrida sin descargas nuevas.
6. Ficha en `docs/guia-despliegue-sistemas.md`.
