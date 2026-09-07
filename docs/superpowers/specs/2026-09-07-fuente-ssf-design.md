# Nueva fuente: Superintendencia del Subsidio Familiar (SSF) — Design

## Problema

La Superintendencia del Subsidio Familiar ("Supersubsidio") publica su
normatividad en un portal **Liferay**. El equipo de fuentes quiere dos
secciones bajo **una sola fuente** en el catálogo:

1. **Resoluciones** — `https://www.ssf.gov.co/web/guest/resoluciones2`
2. **Circulares Externas** — `https://www.ssf.gov.co/web/guest/normativa-circulares`

Ninguna de las 22 familias existentes cubre este sitio, pero el molde
("tabla HTML de normatividad servida por el servidor, sin API") es el
mismo que `mincit` / `superfinanciera.normativa`. Familia técnica nueva:
`ssf`.

## Descubrimiento — cómo está construido el sitio

- Portal **Liferay**, HTML renderizado en el servidor. **Todas las tablas
  y enlaces vienen en el HTML crudo** — sin JavaScript, sin cortafuegos,
  sin endpoints ocultos. `curl` con `User-Agent` de navegador trae la
  página completa (`resoluciones2` ~350 KB / 252 filas de datos;
  `normativa-circulares` ~490 KB / 182 filas de datos).
- **No hay filtro de fecha, ni año en la URL, ni paginación.** Toda la
  data de cada sección está en una sola página. (El único "paginador"
  que aparece en el HTML es un enlace suelto a
  `gestordoc.ssf.gov.co/softexpert/login`, otro sistema, no paginación.)
  `.../web/guest/resoluciones` (sin el `2`) devuelve **404**:
  `resoluciones2` es la única página.
- Cada página es **de un solo propósito**: toda fila de datos de
  `resoluciones2` es una Resolución; toda fila de datos de
  `normativa-circulares` es una Circular Externa. No hay que clasificar
  filas por tipo.
- La página tiene varias `<table>` (layout + datos). Una tabla es **de
  datos** si su fila de encabezado es `Documento | Asunto | Enlace`
  (resoluciones) o `Número | Fecha | Asunto | Adjunto` (circulares). Las
  demás se ignoran. `resoluciones2` trae **2 tablas de datos** (72 + 187
  filas, formatos ligeramente distintos, ver abajo); `normativa-circulares`
  trae ~14 tablas de datos, una por época.

### Resoluciones — estructura de fila

Dos tablas, mismas 3 columnas `Documento | Asunto | Enlace`, con formatos
distintos en la columna `Documento`:

| Tabla | `Documento` (ejemplo) | `Asunto` (ejemplo) |
|---|---|---|
| 0 (72 filas, 2026) | `RESOLUCIÓN RES. 0789 DE 15-09-26` | `Resolución 0789 del 15 de Agosto de 2026 "..."` |
| 1 (187 filas, 2025 y atrás) | `RESOLUCIÓN 1617 del 30 de diciembre de 2025` | `Resolución 1617 del 30 de diciembre de 2025 "..."` |

- **Número**: en el `Asunto` con `Resolución\s+(\d+)`; respaldo en
  `Documento` con `RES\.?\s*(\d+)` o `RESOLUCI[ÓO]N\s+(\d+)`.
- **Fecha**: decisión del usuario = **preferir la fecha en prosa del
  `Asunto`** (`"15 de Agosto de 2026"` →
  `core/fecha_es.parse_fecha_providencia_es`, que ya tolera mayúsculas y
  saltos de línea). Respaldo: la fecha corta de `Documento`
  (`DD-MM-YY` → `20YY-MM-DD`). La columna `Documento` a veces trae una
  fecha distinta del `Asunto` (p. ej. `DE 15-09-26` vs `del 15 de
  Agosto de 2026`) y parece ser de carga, no de expedición.
- **Enlace**: `<a href>` de la celda `Enlace` (o el primer `<a href>` no-
  `javascript` de la fila). URL amigable Liferay
  `/documents/d/guest/<slug>` (unas absolutas, otras relativas →
  `urljoin` con `https://www.ssf.gov.co`). El `<slug>` es arbitrario
  (a veces el nombre de una persona) — **no se parsea**, solo se usa
  para descargar.
- Texto con errores tipo OCR (`I` por `l`: "por Ia cual", "a Ia
  servidora") — no afecta número/fecha; queda en `detalle` tal cual.

### Circulares Externas — estructura de fila

Tablas `Número | Fecha | Asunto | Adjunto` (la de años recientes trae
`class="Table"` en algunas, no es fiable como selector — usar el
encabezado).

| `Número` | `Fecha` | `Adjunto` (texto) | `href` |
|---|---|---|---|
| `00002` | `24/07/2026` | `Circular externa SSF 2026-00002` | `/documents/d/guest/circular-externa-ssf-2026-00002-2-` |
| `CE 00011` | `17/12/2025` | `Circular externa 00011-2025` | `/documents/d/guest/circular-externa-0011-de-2025` |
| `CE 0003A` | `28/06/2024` | `Circular externa 0003A` | `/documents/d/guest/circular-externa-no-2024-00003a` |

- **Número**: de la columna `Número`. Quitar prefijo `CE\s*`, tomar los
  dígitos líderes → entero. Si hay un **sufijo de letra** (`0003A`), se
  conserva pegado al número con ceros: `C_SSF_0003A_2024` (una fila en
  la muestra; marca de revisión de la circular).
- **Fecha**: columna `Fecha`, formato `DD/MM/YYYY` (limpio en las filas
  ≥ 2024).
- **Enlace**: `<a href>` de la celda `Adjunto`. URL amigable
  `/documents/d/guest/<slug>` (absoluta o relativa → `urljoin`).
- **Anexos**: algunos slugs dicen `...-y-anexo-tecnico-2-`. Decisión del
  usuario: **una fila = un documento**, sin manejo especial de anexos
  (el anexo va dentro del mismo PDF / mismo enlace).

### Descarga

- URL amigable `/documents/d/guest/<slug>` → **`GET` directo, `200`,
  `application/pdf`**, con `Content-Disposition: inline; filename="RES.
  0612 DE 03-08-26.pdf"`. Verificado con `fetch` real en resoluciones y
  circulares. `core/downloader.py` ya resuelve la extensión desde el
  `Content-Disposition` (`extract_filename` en `core/utils.py`) — mismo
  mecanismo que `superfinanciera`.
- **Solo las URLs amigables** (documentos de 2024 en adelante). Las
  circulares viejas (2001–2010) usan la URL clásica
  `/documents/N/N/x.pdf/<uuid>` y **devuelven `200` con 0 bytes**
  (probadas dos, ambas vacías) — quedan **fuera de alcance** (ver
  "Alcance").

## Volumen y cobertura

Conteo por año (aprox., de la muestra):

- **Resoluciones**: 2025 → 182, 2026 → 66, + 4 filas sueltas de
  2024/2021. El historial en esta página arranca en la práctica en 2025.
- **Circulares**: 2024–2026 → ~15 filas (URLs amigables). Luego un
  **hueco 2011–2023** (nada). Luego 2001–2010 → ~167 filas (URLs
  clásicas que no descargan).

## Alcance (v1)

- **Secciones**: Resoluciones + Circulares Externas.
- **Piso de cobertura: `2024-01-01`.** Decisión del usuario. Solo entran
  documentos con `f_public >= 2024-01-01`; esto deja fuera las ~167
  circulares 2001–2010 cuyas URLs de descarga devuelven vacío, y el
  hueco 2011–2023 (que igual no tiene nada). El rango pedido en la
  corrida se acota además a este piso.
- **Resoluciones**: todas (mayoría son administrativas —
  nombramientos/renuncias de personal—, se incluyen igual).
- **Anexos**: sin manejo especial (una fila = un documento).
- Todo entra con `review_status` por defecto (`pending`). Sin
  `auto_review_status` en el seed.

## Familia técnica: `ssf`

Archivo nuevo `core/scrapers/families/ssf.py` (módulo plano, estilo
`mincit`, ~150 líneas):

- `@register_family("ssf")` `class ScrapSSF(BaseScrapper)`.
- `self.source = "Superintendencia del Subsidio Familiar"`.
- `scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]`.

Registro en `core/scrapers/families/__init__.py`: añadir `ssf` al
`from . import …`.

**Flags de `BaseScrapper`**:

- `filters_by_publication_date = True` — la fecha de la fila (columna
  `Fecha` en circulares, prosa del `Asunto` en resoluciones) es la fecha
  de publicación/expedición; el filtro por rango se hace en cliente.
- `checks_for_republication = True` (default) — URL directa al archivo,
  apta para el HEAD barato.
- `doc_id_uses_publication_date = True` (default) — `f_public` es
  intrínseca del documento.

### `scrap(...)`

1. `session = requests.Session()` con `User-Agent: Mozilla/5.0 (Windows
   NT 10.0; Win64; x64)`.
2. `anio_min = 2024`.
3. Para cada `(url, tipo, letra, columnas_encabezado)` de:
   - `("https://www.ssf.gov.co/web/guest/resoluciones2", "Resolución", "R", {"documento","asunto","enlace"})`
   - `("https://www.ssf.gov.co/web/guest/normativa-circulares", "Circular Externa", "C", {"número","fecha","asunto","adjunto"})`

   a. `GET` la página; si falla, `on_progress` con `"Error"` y seguir con
      la otra sección (no abortar).
   b. `BeautifulSoup(html, "html.parser")`. Recorrer `soup.find_all("table")`;
      quedarse con las que su primera fila (encabezado) tenga, en
      minúsculas y sin acentos, el conjunto de columnas esperado.
   c. Por cada `<tr>` de datos (con `<td>` y un `<a href>` no-javascript):
      mapear a `RawDocModel` (ver abajo). Respetar `stop_event` entre
      tablas; respetar `limit` (cortar y `return docs[:limit]`).
4. `return docs[:limit]`.

### Fila → `RawDocModel`

- **Resolución**:
  - `numero_raw`: `re.search(r"[Rr]esoluci[óo]n\s+(\d+)", asunto)`; si no,
    `re.search(r"RES\.?\s*(\d+)|RESOLUCI[ÓO]N\s+(\d+)", documento)`.
  - `fecha`: `parse_fecha_providencia_es(asunto)`; si `None`, parsear la
    fecha corta de `documento` (`(\d{1,2})-(\d{1,2})-(\d{2})` →
    `date(2000+yy, mm, dd)`). Si tampoco → se **descarta** la fila con
    aviso `on_progress` (sin fecha no se ubica en el rango).
  - `letra = "R"`, `tipo = "Resolución"`, `detalle = asunto`.
- **Circular Externa**:
  - `numero_raw`: de la celda `Número` — `re.sub(r"^\s*CE\s*", "",
    celda, flags=re.I).strip()`, luego `re.match(r"0*(\d+)([A-Za-z]?)",
    …)` → grupo de dígitos + sufijo de letra opcional.
  - `fecha`: celda `Fecha`, `re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})")`
    → `date(yyyy, mm, dd)`. Si no → descartar con aviso.
  - `letra = "C"`, `tipo = "Circular Externa"`, `detalle = asunto`.
- **Común**:
  - `f_public = f_providencia = fecha.isoformat()`.
  - **Filtro**: descartar si `f_public < fini`, `f_public > ffin`, o
    `fecha.year < anio_min`.
  - **Título**:
    - Con número: `f"{letra}_SSF_{int(digitos):04d}{sufijo_letra}_{fecha.year}"`
      (ej. `R_SSF_0789_2026`, `C_SSF_0011_2025`, `C_SSF_0003A_2024`).
    - Sin número parseable: `title` = texto crudo recortado a 120 con
      `title_unverified = True` — para Resolución el texto de `Documento`
      (respaldo `Asunto`); para Circular el texto de la celda `Número`
      (respaldo `Asunto`).
  - `url`: `urljoin("https://www.ssf.gov.co", href)`.
  - `link = {"url": url, "method": "GET"}`.
  - `save_path = storage_path(source, f_public, tipo,
    f"{safe_title}(extension)")` con
    `safe_title = re.sub(r'[\\/*?:"<>|]', "-", title)[:120].strip(" .")`.
    La extensión la resuelve `core/downloader.py` desde el
    `Content-Disposition`.

## Nomenclatura

Formato `{SIGLA_DCTO}_SSF_{NÚMERO}_{AÑO}`:

| Tipo | Sigla | Número | Año | Ejemplo |
|---|---|---|---|---|
| Circular Externa | `C` | dígitos de la columna Número, 4 cifras con ceros (+ letra final si la trae) | año de la Fecha | `C_SSF_0011_2025`, `C_SSF_0003A_2024` |
| Resolución | `R` | nº del Asunto (respaldo Documento), 4 cifras con ceros | año de la fecha | `R_SSF_0789_2026` |

- **Sigla de entidad**: `SSF` (la que usa el propio dominio).
- **Sin patrón reconocible**: `title` = texto crudo (`Documento` /
  `Asunto` / celda `Número`) recortado a 120 y saneado,
  `title_unverified = True`. No se implementa
  `resolve_unverified_document` para esta familia en v1 (igual que
  `superfinanciera` / `supersalud`).
- No se usa `codigo_ley_decreto` (solo para Leyes/Decretos).

## Seed

En `core/seed.py`:

- Nueva entrada en `_FAMILIES`:
  `"ssf": ("Superintendencia del Subsidio Familiar", "Normativa (resoluciones y circulares externas) publicada por la Superintendencia del Subsidio Familiar")`.
- `repository.create_source_if_missing(db, family_key="ssf",
  name="Superintendencia del Subsidio Familiar", family_params={})`.

## `tests/test_seed.py`

`tests/test_seed.py` lleva el conteo/lista canónica de familias en tres
aserciones que rompen con cada `_FAMILIES` nuevo (ver
`memory/dev_env_gotchas`): subir `len(families)` de 22 a **23**, añadir
`"ssf"` al set de claves de
`test_seed_populates_families_and_sources_and_is_idempotent`, y subir el
término de fuentes únicas de `19` a **20** en las dos aserciones
`assert len(sources) == 1 + 28 + <N> + 33 + 6` (con su comentario).

## Migración

Ninguna, de esquema ni de datos. Solo código nuevo + una entrada en
`core/seed.py`.

## Pruebas

`tests/families/test_ssf.py` — con fixtures HTML reales recortados
(una tabla de resoluciones de cada formato, una tabla de circulares),
sin red:

- Selección de tablas de datos por encabezado; se ignoran las tablas de
  layout.
- **Resolución formato 2026** (`RESOLUCIÓN RES. 0789 DE 15-09-26` /
  `Resolución 0789 del 15 de Agosto de 2026`): número `0789` del Asunto;
  fecha `2026-08-15` (prosa del Asunto, no la de `Documento`);
  `R_SSF_0789_2026`.
- **Resolución formato 2025** (`RESOLUCIÓN 1617 del 30 de diciembre de
  2025`): número `1617`, fecha `2025-12-30`, `R_SSF_1617_2025`.
- **Resolución sin fecha en prosa** → respaldo a la fecha corta de
  `Documento` (`15-09-26` → `2026-09-15`).
- **Circular** (`CE 00011`, `17/12/2025`): número `11`, fecha
  `2025-12-17`, `C_SSF_0011_2025`.
- **Circular con sufijo de letra** (`CE 0003A`, `28/06/2024`) →
  `C_SSF_0003A_2024`.
- **Circular sin `CE`** (`00002`, `24/07/2026`) → `C_SSF_0002_2026`.
- **Filtro por rango de fechas**: fila dentro se conserva, fila fuera se
  descarta.
- **Piso 2024**: una fila de 2021 (existe una en resoluciones) se
  descarta aunque el rango pedido empiece antes.
- **Número no parseable** → `title_unverified = True` con el texto crudo;
  `save_path` saneado (4 segmentos, sin caracteres inválidos en el
  nombre de archivo).
- **`href` relativo** → se resuelve contra `https://www.ssf.gov.co`.
- **`save_path`** = nombre canónico bajo `source / f_public / tipo`.
- Una sección cuyo `GET` falla no aborta la otra (aviso vía
  `on_progress` con `"Error"`).
- `stop_event` seteado entre tablas corta y devuelve lo recolectado.

Registro/seed:

- `ssf` queda en `FAMILY_REGISTRY` y sembrada como **una sola** fuente
  `"Superintendencia del Subsidio Familiar"`.
- `tests/test_seed.py` pasa con los conteos actualizados (23 familias).

## Documentación

- Nota en `docs/guia-despliegue-sistemas.md` (§10 "Notas por fuente" y la
  mención de `core.seed` en §7): la fuente nueva, su alcance
  (Resoluciones + Circulares Externas de la SSF, desde 2024), que es un
  portal Liferay servido entero en HTML, y que **producción necesita
  correr `python -m core.seed` una vez** tras actualizar (sin
  migración).

## Frontend

Sin cambios.
