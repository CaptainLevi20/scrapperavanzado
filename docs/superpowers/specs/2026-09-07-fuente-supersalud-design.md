# Nueva fuente: Superintendencia Nacional de Salud (Supersalud) — Design

## Problema

La Superintendencia Nacional de Salud publica su normatividad en un
portal **SharePoint** (`https://www.supersalud.gov.co/es-co/normatividad/…`).
El equipo de fuentes quiere dos de sus secciones bajo **una sola fuente**
en el catálogo:

1. **Resoluciones** — `.../normatividad/resoluciones`
2. **Circulares Externas** — `.../normatividad/circulares-externas`

La tercera sección ofrecida (**Actas de Conciliación**) queda **fuera de
alcance** por decisión del usuario: son 13 documentos, títulos muy
irregulares, sin publicaciones desde 2022.

Ninguna de las 21 familias existentes cubre este molde de sitio
(SharePoint con búsqueda CSOM). Es hermana conceptual de
`superfinanciera` (una Superintendencia, mismos tipos de documento —
circulares externas y resoluciones —, y presencia de anexos), y hereda
su convención de nomenclatura `{SIGLA_DCTO}_{SIGLA_ENTIDAD}_{NÚMERO}_{AÑO}`.

## Descubrimiento — cómo está construido el sitio

- El portal es **SharePoint** (`GENERATOR: Microsoft SharePoint`). La
  tabla que se ve (columnas `Número`, `Título`, `Descripción`, `Fecha de
  Publicación`, con filtros `Año` y `Mes`) **no viene en el HTML**: la
  pinta un *Content Search Web Part* con render de cliente, que pide los
  datos vía CSOM.
- Los archivos viven en **otro host**:
  `https://docs.supersalud.gov.co/PortalWeb/Juridica/<carpeta>/<archivo>`.
  Carpetas: `Resoluciones`, `CircularesExterna` (sin la "s" final),
  `Actasdeconciliacion` (esta última fuera de alcance).
- **Hay un cortafuegos anti-scraping.** El endpoint REST documentado de
  SharePoint (`/_api/search/query`) devuelve una página HTML **"Acceso
  Bloqueado"** (HTTP 500) en cuanto la petición lleva parámetros de
  búsqueda reales (`querytemplate`, `selectproperties`, `path:`…).
  Verificado desde el navegador y desde `curl`.
- **La vía que usa la propia web sí funciona desde fuera** y **sin
  navegador** — verificada de punta a punta con `requests` puro:
  1. `POST https://www.supersalud.gov.co/es-co/_api/contextinfo` (sin
     cuerpo) → JSON con `FormDigestValue` (la respuesta trae BOM UTF-8;
     hay que decodificar con `utf-8-sig`). Este endpoint **no** está
     bloqueado.
  2. `POST https://www.supersalud.gov.co/es-co/_vti_bin/client.svc/ProcessQuery`
     con cuerpo XML CSOM (`Content-Type: text/xml`) y cabecera
     `X-RequestDigest: <FormDigestValue>`. Devuelve `200` con JSON
     (también con BOM) que contiene `ResultTables[0].ResultRows`. Sin el
     digest responde `403` ("La validación de seguridad de esta página no
     es válida").
  3. `GET` directo a cada `Path` en `docs.supersalud.gov.co` → `200`,
     `application/pdf` (o `.zip` en algunos registros de 2016), descarga
     con `User-Agent` de navegador normal. Sin trucos.
- El cuerpo CSOM es el de una `KeywordQuery` + `SearchExecutor`. GUIDs de
  constructor confirmados en el tráfico real:
  `KeywordQuery = {80173281-fffd-47b6-9a49-312e06ff8428}`,
  `SearchExecutor = {8d2ac302-db2f-46fe-9015-872b35f15098}`.
- Parámetros de la consulta (extraídos del `ProcessQuery` real de cada
  sección):
  - `QueryText`: `*`
  - `QueryTemplate`:
    `path:"https://docs.supersalud.gov.co/PortalWeb/Juridica/<carpeta>" (IsDocument:"True" OR contentclass:"STS_ListItem")`
    (la sección Circulares añade además
    `SPSFechaPublicacion<{Today}` y `-SPSFechaCaducidad:1900-01-01..{Today-1}`
    — filtro de "vigentes"; **no se replica**, se traen todas y se filtra
    por rango de fechas del lado del cliente como el resto de familias).
  - `RowLimit`: hasta **500** por llamada (probado). Paginación por
    `StartRow` (probado: `StartRow=500` devuelve la página siguiente).
  - `ClientType`: `ContentSearchRegular`. `TrimDuplicates`: `false`.
    `Culture`: `3082`.
  - Orden: `SortList.Add("FechadePublicacionOWSDATE", 1)` (1 =
    descendente).
  - Filtro de año: `RefinementFilters.Add('RefinableString00:"ǂǂ<hex>"')`
    donde `<hex>` es el UTF-8 del año en hex (`"2026"` →
    `32303236`) y `ǂ` es `U+01C2` (delimitador FQL). Probado.
- `SelectProperties` a pedir: `Title`, `Path`, `NumeroOWSTEXT`,
  `DescripcionOWSMTXT`, `FechadePublicacionOWSDATE`, `RefinableString00`
  (año), `FileExtension`.
- **`FechadePublicacionOWSDATE`** llega duplicada, separada por `\n\n`
  (`"2026-09-04T05:00:00Z\n\n2026-09-04T05:00:00.0000000Z"`); se toma la
  primera y se corta a `YYYY-MM-DD`.

## Volumen y forma de los datos (muestra real)

- **Circulares Externas**: ~227 en total (2007–2026). Es la sección
  sustantiva.
- **Resoluciones**: miles (2007–2024). La mayoría son administrativas
  (nombramientos, encargos, comisiones de personal). Decisión del
  usuario: **incluir todas, sin filtrar**.
- **Cobertura**: desde **2015** (decisión del usuario). 2007–2014 queda
  fuera — es el tramo donde los títulos son puro texto descriptivo y no
  hay número parseable.

Los números **no tienen estándar** a lo largo de los años:

| Época | Ejemplo `NumeroOWSTEXT` | Ejemplo `Title` |
|---|---|---|
| Circulares 2022–2026 | `2026151000000002-5` | `Circular externa número 2026151000000002-5 de 2026` |
| Circulares 2015–2021 | `47`, `000007`, `001 de 2019`, `20211510000000075 DE 2021` | `Circular Externa 006 de 2016.zip`, `CIRCULAR EXTERNA No. 010 DE 2017` |
| Resoluciones 2022–2024 | `2024910010006787-6` | `Resolución número 2024910010006787-6 de 2024` |
| Resoluciones 2015–2021 | `003 de 2019`, `10924 de 2018`, `3418` | `Por medio de la cual se ordena la toma...` (el título suele ser la descripción) |

Observaciones que el parser debe tolerar:

- `NumeroOWSTEXT` viene **vacío / `None`**, con **espacios sobrantes**,
  con ` de 20XX` / ` DE 20XX` pegado, a veces con el **título entero**
  adentro, a veces con basura y saltos de línea largos.
- **Forma radicado** (`AÑO` + 12 dígitos + `-D`): el bloque de 12 dígitos
  es `dependencia(6) + consecutivo(6)`. Consecutivo = últimos 6 dígitos
  → entero. Ej. `2026151000000002-5` → `2`; `2022130000000054-5` → `54`;
  `2024910010006787-6` → `6787`. El guion antes del último dígito a veces
  falta (`20221300000000545`).
- **Forma clásica**: entero, a veces con ceros a la izquierda (`047`,
  `0720`), a veces de 5 dígitos (`10924`).
- **Anexos**: filas de búsqueda independientes cuyo `Title` empieza con
  `Anexo` / `ANEXO` (ej. `Anexo resolución número 2024910010006782-6 de
  2024`, `ANEXO RESOLUCION No. 2022910010007513-6 de 2022`). Tienen
  **su propio radicado**, distinto del de su resolución/circular madre.
- Extensiones: casi todo `.pdf`; algunos `.zip` (Circulares 2016). Se usa
  el `Path` devuelto tal cual (no se reconstruye la URL).

## Alcance (v1)

- **Secciones**: Resoluciones + Circulares Externas. **Sin** Actas de
  Conciliación.
- **Cobertura**: publicaciones con `FechadePublicacionOWSDATE` en el
  rango de la corrida, **acotado a `>= 2015`** (si el rango pedido
  empieza antes, se sube el piso a `2015-01-01`).
- **Resoluciones**: todas, sin filtro de contenido administrativo.
- **Anexos**: cada anexo entra como **documento propio** (una fila
  `documents`), titulado desde su propio número igual que cualquier otra
  fila. **Sin** agrupación madre↔anexo en v1: el sitio no expone la
  relación entre un anexo y su documento madre (radicados distintos, sin
  metadato de vínculo). No se implementa nada del andamiaje de "N anexos"
  de `superfinanciera` (chip, endpoint, colapso en listado, expansión en
  descarga masiva). Queda como posible v2 si aparece un metadato que los
  enlace.
- Todo entra con el `review_status` por defecto (`pending`, revisión
  manual). Sin `auto_review_status` en el seed.

## Familia técnica: `supersalud`

Archivo nuevo `core/scrapers/families/supersalud.py` (módulo plano, al
estilo `mincit` — un solo scraper, ~200 líneas):

- `@register_family("supersalud")`
  `class ScrapSupersalud(BaseScrapper)`.
- `self.source = "Superintendencia Nacional de Salud"`.
- `scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]`.

Registro en `core/scrapers/families/__init__.py`: añadir `supersalud` al
`from . import …` existente.

**Flags de `BaseScrapper`**:

- `filters_by_publication_date = True` — el buscador ordena y filtra por
  `FechadePublicacionOWSDATE` / `RefinableString00` (año de publicación);
  el día exacto se afina en cliente.
- `checks_for_republication = True` (default) — hay URL directa al
  archivo, apta para el HEAD barato.
- `doc_id_uses_publication_date = True` (default) — `f_public` es la
  fecha propia e intrínseca del acto, no una ocurrencia de listado que
  se repita.

### Transporte (funciones internas del módulo)

- `_form_digest(session) -> str`: `POST .../_api/contextinfo`, parsear
  `json.loads(resp.content.decode("utf-8-sig"))["FormDigestValue"]`.
- `_process_query(session, digest, carpeta, anio, start_row, row_limit=500) -> list[dict]`:
  arma el cuerpo CSOM (plantilla constante con marcadores para
  `QueryTemplate`, `RowLimit`, `StartRow` y el filtro de año), hace el
  `POST .../client.svc/ProcessQuery` con `X-RequestDigest`, decodifica
  con `utf-8-sig`, y devuelve `ResultTables[0].ResultRows` (lista de
  dicts con las claves de `SelectProperties`). Si la respuesta trae
  `ErrorInfo != null`, lanza para que el llamador lo registre vía
  `on_progress` sin abortar el resto.
- El digest se pide **una vez** al inicio de `scrap` y se reutiliza; si
  una llamada a `ProcessQuery` falla con error de validación de
  seguridad, se pide un digest nuevo y se reintenta una vez.

### `scrap(...)`

1. `session = requests.Session()` con `User-Agent: Mozilla/5.0 (Windows
   NT 10.0; Win64; x64)`.
2. `digest = _form_digest(session)`.
3. `anio_ini = max(2015, int(fini[:4]))`, `anio_fin = int(ffin[:4])`.
4. Para cada `(carpeta, tipo, letra)` en
   `[("Resoluciones", "Resolución", "R"), ("CircularesExterna", "Circular Externa", "C")]`:
   - `on_progress(f"[{self.source}] Procesando {tipo}...")`.
   - Para cada `anio` en `range(anio_ini, anio_fin + 1)`:
     - `start = 0`; bucle: `rows = _process_query(session, digest,
       carpeta, anio, start)`; procesar filas; si `len(rows) < 500` →
       fin del año; si no, `start += 500`.
     - Respetar `stop_event` entre páginas y entre años (return de lo ya
       recolectado).
   - Un año cuyo `ProcessQuery` falle se registra vía `on_progress` y no
     aborta los demás años/tipos (patrón de todas las familias).
5. Aplicar `limit` de forma incremental (cortar y `return` cuando
   `len(docs) >= limit`).

### Fila → `RawDocModel`

- `f_public`: primera mitad de `FechadePublicacionOWSDATE` (antes del
  `\n`), cortada a `YYYY-MM-DD`. **`FechadePublicacionOWSDATE` es la
  columna por la que el propio buscador ordena y refina**, así que en la
  práctica siempre viene poblada. Si aun así no parsea, se **descarta**
  la fila con aviso `on_progress`: con `filters_by_publication_date =
  True` y una corrida acotada por rango de fechas, un documento sin fecha
  de publicación no se puede ubicar. No hay respaldo tipo "año de la
  página" como en otras familias (acá el año está en el refiner, pero sin
  día no se puede filtrar con precisión). Es un caso de borde.
- Filtro: conservar solo si `fini <= f_public <= ffin`.
- `es_anexo = Title.strip()` empieza (sin acentos, *case-insensitive*)
  con `anexo`.
- **Número** (`_parse_numero(numero_raw, title) -> (int | None)`):
  1. `base = numero_raw or title`; quitar prefijo `anexo` si `es_anexo`;
     `strip()`, colapsar espacios, quitar sufijo `\s+de\s+\d{4}$`
     (*case-insensitive*).
  2. Radicado: `re.match(r"^(\d{4})(\d{12})-?\d?$", base)` →
     `int(grupo2[-6:])`.
  3. Clásico: `re.match(r"^0*(\d{1,5})$", base)` → `int(grupo1)`.
  4. Si nada matchea → `None`.
- **Título**:
  - Con número → `f"{letra}_SNS_{numero:04d}_{f_public[:4]}"`
    (año = año de **publicación**). Anexo verificado →
    `f"{letra}_SNS_{numero:04d}_{f_public[:4]}_A01"` (sufijo fijo `_A01`;
    ver "Nomenclatura → Anexos").
  - Sin número → `title` = `Title` original saneado y cortado a 120,
    `title_unverified = True`.
- `link = {"url": Path, "method": "GET"}` (el `Path` de la búsqueda; ya
  es absoluto y sirve `.pdf` y `.zip`).
- `tipo`: `"Resolución"` / `"Circular Externa"`.
- `f_providencia = f_public`.
- `detalle = DescripcionOWSMTXT` (o `None`).
- `save_path = storage_path(self.source, f_public, tipo,
  f"{safe_title}(extension)")` — el archivo se guarda con el nombre
  canónico (precedente: `mincit`, `superfinanciera`). `safe_title` =
  `re.sub(r'[\\/*?:"<>|]', "-", title)[:120].strip(" .")`.
- `title_unverified` según lo anterior.

## Nomenclatura

Formato `{SIGLA_DCTO}_SNS_{NÚMERO}_{AÑO}`:

| Tipo | Sigla | Número | Año | Ejemplo |
|---|---|---|---|---|
| Circular Externa | `C` | consecutivo, 4 dígitos con ceros | año de publicación | `C_SNS_0002_2026` |
| Resolución | `R` | consecutivo, 4 dígitos con ceros | año de publicación | `R_SNS_6787_2024` |
| Anexo (con número) | `C` / `R` | consecutivo propio del anexo | año de publicación | `R_SNS_6782_2024_A01` |

- **Sigla de entidad**: `SNS` (Superintendencia Nacional de Salud) —
  decisión del usuario.
- **Consecutivo de la forma radicado**: últimos 6 dígitos del bloque de
  12 (`dependencia(6) + consecutivo(6)`), como entero. **Riesgo
  conocido**: dos documentos del mismo año con distinta dependencia
  (`151000` vs `130000`) y el mismo consecutivo colisionarían en el
  título. En la muestra 2015–2026 no se observó colisión real; si
  ocurre, el `save_path` usa el `title` ya resuelto, así que los archivos
  no se sobrescriben, pero sí habría dos documentos con el mismo `title`.
  Se acepta para v1; mitigación en v2 = incluir 1–2 dígitos de la
  dependencia cuando se detecte choque en el lote de la corrida.
- **Anexos**: como no hay relación con la madre, el sufijo `_A01` es
  **fijo** (no se numera `_A02`, `_A03`…): distingue el anexo de un
  eventual documento no-anexo con el mismo `{letra}_SNS_{n}_{año}` sin
  pretender ordenar varios anexos de una misma madre. Si el anexo no
  tiene número parseable → `title_unverified` con el `Title` crudo (sin
  sufijo).
- **Sin patrón reconocible**: `title` = `Title` crudo saneado y cortado a
  120, `title_unverified = True`. El worker podría recuperar el título
  del contenido del archivo (`resolve_unverified_document`) — **no** se
  implementa para esta familia en v1 (igual que `superfinanciera`).
- No se usa `codigo_ley_decreto` de `core/naming.py` (ese código canónico
  sin sigla es solo para Leyes y Decretos).

## Seed

En `core/seed.py`:

- Nueva entrada en `_FAMILIES`:
  `"supersalud": ("Superintendencia Nacional de Salud", "Normativa (resoluciones y circulares externas) publicada por la Superintendencia Nacional de Salud")`.
- `repository.create_source_if_missing(db, family_key="supersalud",
  name="Superintendencia Nacional de Salud", family_params={})`.

## Migración

Ninguna, de esquema ni de datos. Solo código nuevo + una entrada en
`core/seed.py`. Los anexos son filas `documents` normales.

## Pruebas

`tests/families/test_supersalud.py` — con `responses` (o
`requests-mock`, según el patrón de los demás `test_*` de familias)
mockeando `/_api/contextinfo` y `/_vti_bin/client.svc/ProcessQuery` con
**fixtures JSON reales recortados** (una respuesta de Resoluciones y una
de Circulares, con 3–5 filas cada una cubriendo los casos):

- `contextinfo` con BOM se decodifica y el digest se manda en
  `X-RequestDigest`.
- Respuesta `ProcessQuery` con BOM se decodifica; se leen las filas de
  `ResultTables[0].ResultRows`.
- Número **forma radicado**: `2026151000000002-5` → `C_SNS_0002_2026`;
  `2024910010006787-6` → `R_SNS_6787_2024`; sin guion
  (`20221300000000545`) → `..._0054_...`.
- Número **forma clásica**: `047` → `C_SNS_0047_20XX`; `10924 de 2018`
  → `R_SNS_10924_2018` (5 dígitos, sin recorte).
- `NumeroOWSTEXT` vacío / con el título entero / con basura →
  `title_unverified = True` y `title` = `Title` saneado.
- Anexo (`Title` empieza con `Anexo`/`ANEXO`) con número →
  `R_SNS_####_AAAA_A01`; anexo sin número → `title_unverified`, sin
  sufijo.
- `FechadePublicacionOWSDATE` doblada (`...\n\n...`) → `f_public` =
  `YYYY-MM-DD`; `f_providencia == f_public`.
- Filtro por rango de fechas: fila dentro se conserva, fila fuera se
  descarta; una fila con `f_public` de 2014 no aparece aunque el rango
  pedido empiece en 2013 (piso 2015).
- `save_path` = nombre canónico bajo `source / f_public / tipo`.
- `link.url` = el `Path` devuelto (incluye un caso `.zip`).
- Paginación: una respuesta de 500 filas dispara una segunda llamada con
  `StartRow=500`; una de <500 detiene el año.
- `ProcessQuery` con `ErrorInfo != null` para un año no aborta los demás
  años/tipos (se registra vía `on_progress`).
- `stop_event` seteado entre páginas corta y devuelve lo recolectado.

Registro/seed:

- `supersalud` queda en `FAMILY_REGISTRY` y sembrada como **una sola**
  fuente `"Superintendencia Nacional de Salud"`.

## Documentación

- Nota en `docs/guia-despliegue-sistemas.md` (o donde se listen las
  fuentes) describiendo la fuente nueva, su alcance (Resoluciones +
  Circulares Externas, desde 2015) y la particularidad del transporte
  (SharePoint CSOM + digest; endpoint REST bloqueado por WAF).

## Frontend

Sin cambios.
