# Nueva fuente: Superintendencia de Notariado y Registro (SNR) — Design

## Problema

La Superintendencia de Notariado y Registro publica su normatividad en
`https://www.supernotariado.gov.co/transparencia/normatividad-vigente/`
(WordPress). El equipo de fuentes quiere **Circulares** y **Resoluciones**
bajo una sola fuente. Familia técnica nueva: `snr`.

El sitio es alcanzable (sin bot-manager, HTML del servidor, `requests`
funciona), pero **su listado no tiene paginación usable** — hay que
enumerar el catálogo con una búsqueda adaptativa por prefijo de número.
El usuario aceptó ese costo/fragilidad.

## Descubrimiento

### Estructura del sitio

- **WordPress + Elementor.** La página `normatividad-vigente/` es solo un
  índice con 10 botones de categoría; cada botón lleva a una URL propia:
  `https://www.supernotariado.gov.co/transparencia/normatividad/<categoria>/`.
  Casing real de las dos que nos interesan: **`circulares`** (minúscula) y
  **`Resoluciones`** (con mayúscula inicial). `Circular`/`Decreto` en
  singular → 301 a la forma correcta.
- Cada página de categoría trae una lista `<ul class="docs_download">` de
  `<li>` (tarjetas), servida en el HTML. Sin JS necesario para el
  contenido.
- Los PDF viven en un host aparte: `https://servicios.supernotariado.gov.co/files/…`.
  **Descarga directa verificada**: `GET` → `200 application/pdf`, magic
  `%PDF-`. Sin bot-manager en ese host.

### Estructura de la tarjeta (`<li>`)

```html
<li>
  <div class="download">
    <!--<a href="https://servicios.supernotariado.gov.co/files/snrcirculares/circular-348-20260903154959.pdf" target="_blank"> -->
    <img src="https://servicios.supernotariado.gov.co/vista/img/bigpdf.png">
    <!--<br>Descargar</a> -->
    <br><span style="font-size:12px;">0 Mg</span>
  </div>
  <div class="contenido_download">
    <span class="lettercap"></span> 348<br>
    <a href="https://servicios.supernotariado.gov.co/files/snrcirculares/circular-348-20260903154959.pdf" target="_blank" rel="nofollow">CIR-2026-000348-4 del 03 de septiembre del 2026 "Información de autos que ordenan reportar…"</a><br>
    <span>Publicación: 2026-09-03</span><br>
    <span>Desfijacion: 2026-09-14</span>
  </div>
  <div class="border-download"></div>
</li>
```

- El botón de descarga arriba está **comentado** (`<!-- -->`); el enlace
  real y funcional es **el `<a>` del título** dentro de
  `div.contenido_download`.
- `span class="lettercap"` (vacío) + texto ` 348` = número corto.
- Texto del `<a>`: `CIR-2026-000348-4 del 03 de septiembre del 2026 "…"`
  = código + fecha en prosa + descripción entre comillas.
- `Publicación: AAAA-MM-DD` (ISO limpio). `Desfijacion:` se ignora.
- **Tarjetas sin `<a>`**: existen (las de "Notificación por aviso –
  Resolución No. …" en la categoría Resoluciones — procesales, sin PDF).
  Se **descartan** (con conteo vía `on_progress`).
- **Tarjetas duplicadas**: se observaron (mismo número dos veces). El
  pipeline deduplica por `doc_id`; no hace falta lógica extra.

### Código de norma

`<TIPO>-<AÑO>-<NNNNNN>-<D>`:
- `TIPO` = `CIR` (Circular) / `RES` (Resolución).
- `AÑO` = 4 dígitos.
- `NNNNNN` = consecutivo del año, 6 dígitos con ceros (`000348` → 348).
  Coincide con el número corto que muestra la tarjeta aparte.
- `-D` = un dígito de sufijo (dependencia/tipo), se ignora.

Formas viejas que no calzan (`RES.445-2019`, títulos sin código) →
`title_unverified`.

### El problema del listado: sin paginación

- La vista por defecto de cada categoría muestra **solo ~20 tarjetas**
  (las más recientes) de un total de miles. **No hay paginador** — ni
  botón "Siguiente", ni `?page=`, ni `?pagina=`, ni `?p=` (probados:
  301/404/ignorados).
- Hay una búsqueda: `POST` al mismo URL de categoría con
  `Content-Type: application/x-www-form-urlencoded` y cuerpo `r=<texto>`.
  Filtra por coincidencia de texto en la descripción/código, y la
  respuesta trae `Resultados <N>` (total de coincidencias).
- **La búsqueda también corta a ~20 tarjetas mostradas** sin importar
  `N` (probado: `r=CIR-2026-0003` → `Resultados 47`, 20 tarjetas; no hay
  página 2).
- **Excepción observada**: `POST r=<año>` en la categoría **Resoluciones**
  devolvió las ~2.634 tarjetas del año en una sola respuesta de ~2,4 MB
  (~96 s). Comportamiento inconsistente con Circulares; se aprovecha
  cuando ocurre pero no se depende de él (ver algoritmo).
- Circulares por año: 236–543 (2015–2026) — siempre > 20, así que buscar
  por año nunca alcanza en Circulares.
- **El prefijo hace *prefix match*** sobre el código: `r=CIR-2026-0003`
  devuelve exactamente el bloque `000300`–`000399` (Resultados 47). Esto
  es lo que hace viable la enumeración.

## Alcance (v1)

- **Categorías**: Circulares + Resoluciones.
- **Piso de cobertura: `2015-01-01`.** El rango pedido en la corrida se
  acota además a este piso.
- Solo tarjetas con enlace a PDF (`<a>` en `contenido_download`). Las de
  "notificación por aviso" sin archivo se descartan.
- Sin manejo especial de anexos (una tarjeta = un documento).
- Todo entra con `review_status` por defecto (`pending`). Sin
  `auto_review_status` en el seed.

## Familia técnica: `snr`

Archivo nuevo `core/scrapers/families/snr.py` (módulo plano, estilo
`mincit`, ~230 líneas — más grande que las otras familias por el
algoritmo de enumeración).

- `@register_family("snr")` `class ScrapSNR(BaseScrapper)`.
- `self.source = "Superintendencia de Notariado y Registro"`.
- `scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]`.

Registro en `core/scrapers/families/__init__.py`: añadir `snr`.

**Flags de `BaseScrapper`**:

- `filters_by_publication_date = True` — se filtra por la fecha que
  parseamos de la tarjeta (prosa del título; respaldo `Publicación:`).
- `checks_for_republication = True` (default) — URL directa al PDF.
- `doc_id_uses_publication_date = True` (default).

### Transporte (funciones internas)

- `_BASE = "https://www.supernotariado.gov.co/transparencia/normatividad"`.
- `_UMBRAL = 18` — tope observado de tarjetas que el listado/búsqueda
  muestra sin paginación (la vista real corta en ~20; 18 deja margen).
- `_ANIO_MIN = 2015`.
- `_buscar(session, categoria: str, termino: str) -> tuple[int, str]`:
  `POST {_BASE}/{categoria}/` con `data={"r": termino}`,
  `timeout=200` (la respuesta puede tardar ~96 s), `User-Agent` de
  navegador. Devuelve `(resultados_total, html)` donde `resultados_total`
  se lee de `Resultados\s*([\d.,]+)` (o `-1` si no aparece).
- `_tarjetas(html) -> list[dict]`: parsea `ul.docs_download > li`. Por
  cada `<li>` con un `<a href>` en `div.contenido_download`:
  `{"num_corto": <texto antes del <a>>, "codigo": <primeras palabras del
  texto del <a> que casen `<TIPO>-\d{4}-\d{6}-\d`>, "titulo_txt": <texto
  del <a>>, "publicacion": <fecha ISO tras "Publicación:">,
  "pdf_url": <href>}`. Las `<li>` sin `<a>` se cuentan y se omiten.

### Enumeración por año y prefijo (`_enumerar_categoria`)

Para cada `(categoria, tipo, letra)` de
`[("circulares", "Circular", "C"), ("Resoluciones", "Resolución", "R")]`
y cada `anio` en `range(max(2015, int(fini[:4])), int(ffin[:4]) + 1)`:

`tipo_code = tipo[:3].upper()` → `"CIR"` para `"Circular"`, `"RES"` para
`"Resolución"`.

1. **Intento directo por año**: `total, html = _buscar(session, categoria, str(anio))`.
   `docs_pagina = _tarjetas(html)`. Si `len(docs_pagina) > _UMBRAL` (la
   búsqueda devolvió más que el tope de ~20 → no cortó, dio todo — caso
   Resoluciones) **o** `len(docs_pagina) >= total` (devolvió todo lo que
   había): procesar `docs_pagina` y pasar al siguiente año.
2. **Si no** (la búsqueda cortó a ~20 y hay más): enumeración adaptativa
   por prefijo del código `{tipo_code}-{anio}-`:
   - Función recursiva `_bloque(prefijo_digitos: str)` donde
     `prefijo_digitos` es un prefijo de 1–6 dígitos del consecutivo:
     - `termino = f"{tipo_code}-{anio}-{prefijo_digitos}"`.
     - `total, html = _buscar(session, categoria, termino)`.
     - Si `total == 0`: return `[]`.
     - Si `total <= _UMBRAL` (18) **o** `len(_tarjetas(html)) >= total`:
       return `_tarjetas(html)` (están todas las de este prefijo).
     - Si `len(prefijo_digitos) >= 5`: return `_tarjetas(html)` (bloque de
       ≤10; ya no se puede afinar más de forma útil — se acepta el corte,
       con aviso `on_progress` de que un bloque de 10 tenía > 18, caso no
       esperado).
     - Si no: concatenar `_bloque(prefijo_digitos + d)` para `d` en
       `"0".."9"`.
   - Arrancar en `_bloque("0")` … `_bloque("9")` (1 dígito): cubre
     consecutivos 0–999999. En la práctica solo `"0"` tiene algo (los
     consecutivos anuales van hasta ~1.000). Los demás devuelven
     `total == 0` de inmediato.
   - **Poda por rango de fechas**: no aplica a nivel de prefijo (el
     prefijo es por número, no por fecha); el filtro por `[fini, ffin]`
     se hace por documento al armar el `RawDocModel`.
3. Deduplicar la lista resultante por `codigo` antes de mapear (la
   recursión no debería solapar, pero el sitio repite tarjetas).
4. Respetar `stop_event` entre años y entre llamadas `_buscar`. Respetar
   `limit` (cortar y `return docs[:limit]`).
5. Una llamada `_buscar` que falle (timeout, 5xx) se registra vía
   `on_progress` con `"Error"` y se sigue con el siguiente año/prefijo
   (no aborta la corrida).

> Coste estimado de un backfill completo (2015–2026): Resoluciones ~12
> POST (uno por año, ~96 s c/u); Circulares ~40–50 POST por año
> (bloques de 100 y sub-bloques de 10), ~1–2 s c/u → ~10–15 min. Una
> corrida incremental (rango de una semana) toca solo el año en curso y
> sus bloques recientes → pocos POST.

### Tarjeta → `RawDocModel`

- `codigo` → regex `^(CIR|RES)-(\d{4})-(\d{6})-\d`:
  - `letra` = `C` / `R` según el grupo 1.
  - `numero` = `int(grupo 3)`.
  - `anio_codigo` = `int(grupo 2)`.
- **Fecha**: `parse_fecha_providencia_es(titulo_txt)` (la prosa
  `"del 03 de septiembre del 2026"`; el helper ya tolera `del` antes del
  año). Respaldo: la fecha ISO de `publicacion`. Si ninguna →
  `on_progress` "sin fecha" y se **descarta** la tarjeta.
- **Filtro**: descartar si `fecha.year < 2015`, o `iso < fini`, o
  `iso > ffin`.
- **Título**:
  - Con `codigo` válido: `f"{letra}_SNR_{numero:04d}_{fecha.year}"`
    (ej. `C_SNR_0348_2026`, `R_SNR_21492_2026`). *(Nota: los consecutivos
    de Resoluciones llegan a 5 dígitos — `21492` — el `:04d` no los
    recorta.)*
  - Sin `codigo` válido: `title` = `titulo_txt` (o `num_corto`) recortado
    a 120, `title_unverified = True`.
- `link = {"url": pdf_url, "method": "GET"}` (el `href` tal cual; ya es
  absoluto en `servicios.supernotariado.gov.co`).
- `tipo` = `"Circular"` / `"Resolución"`.
- `f_public = f_providencia = fecha.isoformat()`.
- `detalle` = `titulo_txt` (o la parte entre comillas si se extrae
  limpio; si no, el texto completo).
- `save_path = storage_path(source, f_public, tipo,
  f"{safe_title}(extension)")` con
  `safe_title = re.sub(r'[\\/*?:"<>|]', "-", title)[:120].strip(" .")`.
  La extensión la resuelve `core/downloader.py` (`.pdf` en la URL /
  Content-Type).

## Nomenclatura

Formato `{SIGLA_DCTO}_SNR_{NÚMERO}_{AÑO}`:

| Tipo | Sigla | Número | Año | Ejemplo |
|---|---|---|---|---|
| Circular | `C` | consecutivo del código (`000348` → 348), 4 díg. con ceros | año del código | `C_SNR_0348_2026` |
| Resolución | `R` | consecutivo del código (5 díg. sin recortar) | año del código | `R_SNR_21492_2026` |

- **Sigla de entidad**: `SNR`.
- **Sin código reconocible**: `title` = texto crudo del título /
  número corto, recortado a 120, `title_unverified = True`. Sin
  `resolve_unverified_document` en v1.
- No se usa `codigo_ley_decreto` (solo Leyes/Decretos).

## Seed

En `core/seed.py`:

- Nueva entrada en `_FAMILIES`:
  `"snr": ("Superintendencia de Notariado y Registro", "Normativa (circulares y resoluciones) publicada por la Superintendencia de Notariado y Registro")`.
- `repository.create_source_if_missing(db, family_key="snr",
  name="Superintendencia de Notariado y Registro", family_params={})`.

## `tests/test_seed.py`

Subir `len(families)` de 23 a **24**; añadir `"snr"` al set de claves de
`test_seed_populates_families_and_sources_and_is_idempotent`; subir el
término de fuentes únicas de `20` a **21** en las dos aserciones
`assert len(sources) == 1 + 28 + <N> + 33 + 6` (con su comentario).

## Migración

Ninguna. Solo código nuevo + una entrada en `core/seed.py`.

## Pruebas

`tests/families/test_snr.py` — con `responses` mockeando el `POST` de
búsqueda por categoría y fixtures HTML reales recortados:

- `_tarjetas`: parsea `ul.docs_download > li`; toma el `<a>` de
  `contenido_download` (no el botón comentado); extrae num_corto, codigo,
  titulo_txt, publicacion, pdf_url; **omite** las `<li>` sin `<a>` y las
  cuenta.
- Código válido → `_titulo` `C_SNR_0348_2026` / `R_SNR_21492_2026`
  (5 dígitos sin recorte).
- Código no reconocible (`RES.445-2019`, título libre) →
  `title_unverified` con texto crudo.
- Fecha: `parse_fecha_providencia_es("… del 03 de septiembre del 2026")`
  → `2026-09-03`; respaldo a `Publicación:` cuando la prosa no parsea;
  descarte + aviso cuando ninguna.
- Filtro por rango de fechas y por piso 2015.
- **Enumeración**:
  - `_buscar` mockeado: `r="2026"` para Resoluciones devuelve un HTML con
    N tarjetas y `Resultados N` → se usa directo (no se recurre a
    prefijos).
  - `r="2026"` para Circulares devuelve `Resultados 355` con solo 18
    tarjetas → se dispara la recursión por prefijo; `r="CIR-2026-0"`
    (Resultados 355) → recurre; `r="CIR-2026-00"` … hasta que un
    `termino` da `Resultados <= 18` y se parsean sus tarjetas; unión y
    dedup por `codigo`.
    - `total == 0` para un prefijo → poda inmediata (no recurre).
    - prefijo de 5 dígitos con `Resultados > 18` → se parsea igual + aviso.
  - `stop_event` seteado entre años corta y devuelve lo recolectado.
  - Un `POST` que devuelve 500 no aborta el resto (aviso con `"Error"`).
- `save_path` = nombre canónico bajo `source / f_public / tipo`.
- `link.url` = el `href` del `<a>` verbatim.

Registro/seed:

- `snr` en `FAMILY_REGISTRY`, sembrada como **una sola** fuente.
- `tests/test_seed.py` pasa con los conteos actualizados (24 familias).

## Documentación

- Nota en `docs/guia-despliegue-sistemas.md` §10: la fuente nueva, su
  alcance (Circulares + Resoluciones de la SNR, desde 2015), la
  particularidad de que el listado no tiene paginación y se enumera con
  búsqueda adaptativa por prefijo de número (corrida de backfill lenta,
  ~10–15 min; incremental rápida), y que **producción necesita `python -m
  core.seed` una vez** tras actualizar (sin migración).

## Frontend

Sin cambios.
