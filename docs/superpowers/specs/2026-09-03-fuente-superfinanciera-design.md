# Nueva fuente: Superintendencia Financiera de Colombia (SFC) — Design

## Problema

La Superintendencia Financiera de Colombia publica su normatividad en dos
lugares con mecánicas de sitio completamente distintas, y el equipo de
fuentes quiere ambos bajo **una sola fuente** en el catálogo:

1. **Circulares Externas, Cartas Circulares y Resoluciones** —
   `https://www.superfinanciera.gov.co/publicaciones/20149/normativanormativa-generalcirculares-externas-cartas-circulares-y-resoluciones-desde-el-ano-20149/`
   HTML server-side: una página índice con 3 columnas (Circulares
   Externas, Cartas Circulares, Resoluciones) × 22 años (2005–2026); cada
   enlace de año lleva a una página con **una sola tabla** (`Número`,
   `Fecha`, `Descripción`, `Boletín*`), sin paginación (se confirmó una
   tabla de 131 filas servida entera). El enlace de la columna `Número`
   descarga el PDF vía `loader.php`; la celda `Descripción` a veces trae
   enlaces `Anexo` adicionales.

2. **Doctrina y Conceptos** —
   `https://www.superfinanciera.gov.co/ABCD/superfinanciera/php/buscar_integrada.php`
   Catálogo de biblioteca **ABCD** (software OPAC). Dentro del "Catálogo
   jurídico" (`base=juris`) hay una colección **"Doctrina y conceptos"**
   con ~3.431 registros. **No hay API/JSON**: son páginas HTML de
   resultados por POST, 25 registros por página (~138 páginas). El
   documento descarga en **Word `.docx`** vía `loader.php`.

Ninguna de las 18 familias existentes cubre estos moldes.

## Descubrimiento — sitio 1 (Circulares / Cartas Circulares / Resoluciones)

- La página índice enlaza los 66 destinos (3 tipos × 22 años). Los
  enlaces resuelven a páginas `/publicaciones/<id>/…-<tipo>--<id>/` (o a
  un id corto `/<id>` que redirige a la misma). La estructura de la
  tabla es **idéntica en todos los años**, de 2005 a 2026 (verificado en
  2005, 2020, 2025, 2026).
- Columnas: `Número` (ej. `008`, `1215` — 3–4 dígitos, con un enlace
  `loader.php` al PDF), `Fecha` (`"Septiembre 01"` / `"Diciembre 30"` —
  **mes y día en español, SIN año**; el año está en el título de la
  página), `Descripción` (texto libre; 0–N enlaces `Anexo` a
  `loader.php`), `Boletín*` (número de boletín).
- Descarga confirmada con `fetch` real: Circular Externa 008/2026 →
  `200`, `application/octet-stream` con `Content-Disposition`, cuerpo con
  magic bytes `%PDF`, 1.28 MB. Mismo mecanismo GET que ya usa
  `core/downloader.py`.
- La celda `Fecha` no siempre está poblada de forma parseable en años
  muy viejos — respaldo: `AAAA-01-01` con aviso vía `on_progress`, sin
  descartar la fila.

## Descubrimiento — sitio 2 (Doctrina y Conceptos, ABCD)

- La colección se abre con un POST a `buscar_integrada.php` con
  `base=juris`, `Opcion=libre`, `coleccion=ac|Doctrina y conceptos|TM_`,
  `Expresion=$` (equivale a la llamada JS
  `BuscarIntegrada("juris","","libre","","ac|Doctrina y conceptos|TM_",…)`).
  La respuesta trae "Mostrando del 1 al 25 de N registros" y un
  formulario `<form name="continuar">` con los campos de sesión + `desde`
  y `pagina` para pedir la siguiente página (POST al mismo endpoint).
- **No hay filtro de fecha en el servidor.** La búsqueda avanzada solo
  ofrece `Título de la norma`, `Temas/Materias`, `Año Norma` (año de la
  norma *citada*, no del concepto), `No. Norma/Sentencia`,
  `No. Expediente/Radicado`. Ninguno sirve para acotar por la fecha del
  concepto.
- **Los registros NO están en orden cronológico**: página 1 ≈ 2021,
  página 70 ≈ 2007, página 138 ≈ 2026 — es orden interno del catálogo
  (MFN/accesión). Dentro de una misma página las fechas tampoco están
  ordenadas. Consecuencia de diseño: **hay que recorrer todas las
  páginas en cada corrida** y filtrar por fecha del lado del cliente.
- Cada registro es un `<table class="registro">` con campos etiquetados:
  `Concepto:` (`2020311455 - 001 del 5 de febrero de 2021` = radicado de
  10 dígitos + consecutivo + fecha en texto español), `Autor
  Corporativo:`, `Título de la norma:` (frase temática + "`/ Concepto
  NNNN-NNN del …`"), `Documento fuente:` (`Conceptos 2021`), `Resumen:`
  (abstract), `Otras formas físicas:`, `Temas/Materias:` (lista de
  descriptores), `Acceso web (URL): Archivo de texto` (enlace
  `loader.php?...&idFile=N`).
- Descarga confirmada con `fetch` real: `200`,
  `application/octet-stream` con `Content-Disposition`
  `filename="{radicado}.docx"` (10 dígitos + `.docx`), magic bytes `PK`
  (DOCX/ZIP), ~52 KB. `core/downloader.py` ya resuelve la extensión
  desde el `Content-Disposition` y el proyecto ya sabe convertir DOCX a
  PDF para la vista previa (`convert_to_pdf_via_libreoffice`).
- Algunos registros no traen la línea `Concepto:` en el formato exacto
  (se observó un caso en ~150 registros de muestra) → respaldo por
  título crudo + `title_unverified`.
- **Radicados repetidos**: existen, raros — en una muestra de ~150
  registros apareció `1998045919` con consecutivos `1` y `4`. Ver
  "Nomenclatura → Conceptos → choque de radicado".

## Alcance (v1)

- **Sitio 1**: los 3 tipos completos (Circulares Externas, Cartas
  Circulares, Resoluciones), más sus **anexos** como documentos
  hermanos.
- **Sitio 2**: **solo** la colección "Doctrina y conceptos" del catálogo
  jurídico. Quedan fuera "Fallos jurisdiccionales" y "Jurisprudencia
  financiera" del mismo catálogo, y los demás catálogos de ABCD.
- El histórico se maneja por rango de fechas como en todas las fuentes
  (no hay "año de corte").
- Todo entra como `review_status = "pending"` (revisión manual). Sin
  `auto_review_status` en el seed.

## Familia técnica: `superfinanciera`

Paquete nuevo `core/scrapers/families/superfinanciera/`:

- `__init__.py` — la clase registrada
  `@register_family("superfinanciera") class ScrapSuperfinanciera(BaseScrapper)`.
  Su `scrap(fini, ffin, q, limit, stop_event, on_progress)` corre
  `normativa.scrap(...)` y luego `conceptos.scrap(...)`, concatena, y
  respeta `limit` / `stop_event` / `on_progress` de forma incremental
  (mismo patrón que `minjusticia` con sus 3 listas).
- `normativa.py` — Circulares Externas, Cartas Circulares, Resoluciones +
  anexos.
- `conceptos.py` — Doctrina y Conceptos (ABCD).

Registro en `core/scrapers/families/__init__.py` (`from . import …,
superfinanciera`). Se usa un paquete y no un archivo plano porque los dos
scrapers no comparten nada y cada uno ronda las 150–200 líneas; el import
explícito del `__init__.py` de familias funciona igual con un paquete.

**Flags de `BaseScrapper`**: se dejan los valores por defecto
(`filters_by_publication_date = False`, `checks_for_republication = True`,
`doc_id_uses_publication_date = True`). En ambos sitios `f_public ==
f_providencia` es la fecha propia e intrínseca del acto/concepto, y la
descarga es un GET directo a un archivo (`loader.php`), apto para el
chequeo barato de republicación.

## Seed

En `core/seed.py`:
- Nueva entrada en `_FAMILIES`: `"superfinanciera"` con display name
  `"Superintendencia Financiera de Colombia"` y una descripción que
  mencione los dos alcances (circulares/cartas circulares/resoluciones +
  doctrina y conceptos).
- `repository.create_source_if_missing(db, family_key="superfinanciera",
  name="Superintendencia Financiera de Colombia", family_params={})`.

## Scraper `normativa`

1. GET a la página índice. Detectar las 3 columnas por el texto de su
   encabezado (`Circulares Externas`, `Cartas Circulares`,
   `Resoluciones`) y, dentro de cada una, los enlaces cuyo texto es un
   año de 4 dígitos → `{tipo: {año: url_absoluta}}`.
2. Para cada `año` en `range(int(fini[:4]), int(ffin[:4]) + 1)` y cada
   uno de los 3 tipos con enlace para ese año: GET la página del año,
   parsear la única `<table>`.
3. Por fila de datos:
   - `numero_raw`: texto de la celda `Número`. `link`: primer `<a href>`
     de esa celda (`loader.php`), `{"url": ..., "method": "GET"}`.
   - `fecha`: `"<Mes> <DD>"` de la celda `Fecha` + el `año` de la página
     → `AAAA-MM-DD` (mapa de meses de `core/fecha_es.py`). Si no parsea →
     `f_public = f"{año}-01-01"` y aviso `on_progress` (no se descarta).
   - Filtro: se conserva solo si `fini <= f_public <= ffin`.
   - `tipo`: `"Circular Externa"` / `"Carta Circular"` / `"Resolución"`.
   - `title`: si `numero_raw` es numérico,
     `f"{sigla}_SF_{int(numero_raw):04d}_{año}"` con `sigla` `C` /
     `CCIR` / `R`. Si no, `title` = descripción/`numero_raw` crudo
     truncado + `title_unverified = True` (y sin anexos, ver abajo).
   - `detalle`: texto de la celda `Descripción` (sin el texto de los
     enlaces `Anexo`). **El número de boletín se ignora.**
   - `f_public = f_providencia = fecha`.
   - `save_path`: `storage_path(source, f_public, tipo,
     f"{safe_title}(extension)")` — el archivo se guarda con el nombre
     canónico (precedente: `minjusticia`).
4. **Anexos** — solo si el documento madre tiene `title` verificado. Por
   cada `<a href>` a `loader.php` dentro de la celda `Descripción`, en
   orden de aparición (`n` = 1, 2, …):
   - `title`: `f"{title_madre}_A{n:02d}"` (ej. `C_SF_0020_2026_A01`).
   - `tipo`: el mismo del documento madre (para que caiga en la misma
     carpeta).
   - `f_public = f_providencia`: los mismos del documento madre.
   - `detalle`: `f"Anexo {n} de {title_madre}"`.
   - `link`: la URL `loader.php` del anexo, método `GET`.
   - `save_path`: `storage_path(source, f_public, tipo,
     f"{title_madre}_A{n:02d}(extension)")`.
5. Un año/tipo cuyo GET falle se registra vía `on_progress` y no aborta
   lo ya recolectado de los demás (patrón de todas las familias).

## Scraper `conceptos`

1. `requests.Session` con `User-Agent: Mozilla/5.0`. POST a
   `https://www.superfinanciera.gov.co/ABCD/superfinanciera/php/buscar_integrada.php`
   con los campos del formulario `bi`: `base=juris`, `cipar=`,
   `Opcion=libre`, `coleccion=ac|Doctrina y conceptos|TM_`,
   `Expresion=$`, `titulo_c=`, `resaltar=`, `submenu=`, `Pft=`,
   `mostrar_exp=`.
2. De la respuesta: total de registros (`"de N registros"`) →
   `paginas = ceil(N / 25)`. Se extrae el `<form name="continuar">` para
   quedarse con sus campos ocultos (llevan el estado de sesión de ABCD).
3. Para `pagina` de 2 a `paginas`: POST al mismo endpoint con los campos
   ocultos del `continuar` de la respuesta anterior, fijando `desde =
   (pagina - 1) * 25 + 1` y `pagina`. Se recorren **todas** las páginas
   en cada corrida (no hay filtro de fecha ni orden cronológico; el corte
   anticipado se descartó por ser inseguro con el orden MFN del
   catálogo). ~138 POST por corrida; runtime estimado 3–5 min.
4. Por `<table class="registro">`:
   - Celda `Concepto:` → regex
     `^\s*(\d{6,})\s*-\s*(\d{1,4})\s+del?\s+(.+?)\s*$` → `radicado`,
     `consecutivo`, `fecha_texto`.
   - `fecha`: `parse_fecha_providencia_es(fecha_texto)` de
     `core/fecha_es.py` (`"5 de febrero de 2021"` → `2021-02-05`).
   - Si la línea `Concepto:` no matchea: `title` = `Título de la norma`
     crudo (truncado), `title_unverified = True`; se intenta hallar una
     fecha en la celda igualmente. Si tampoco hay fecha → se omite el
     registro con aviso `on_progress` (no se puede ubicar en el rango).
   - Filtro: se conserva solo si `fini <= fecha <= ffin`.
   - `tipo`: `"Concepto"`.
   - `detalle`: `Título de la norma` + `" — "` + `Resumen` (omitiendo
     cada parte si está vacía).
   - `link`: `<a>` "Archivo de texto" → URL `loader.php`, método `GET`.
   - `f_public = f_providencia = fecha`.
   - `save_path`: `storage_path(source, fecha, "Concepto",
     f"{safe_title}(extension)")` (la extensión `.docx` la resuelve el
     downloader desde el `Content-Disposition`).
5. Una página cuyo POST falle se reintenta una vez; si vuelve a fallar se
   registra vía `on_progress` y se continúa con las demás (no se pierde
   lo ya recolectado).

## Nomenclatura

Formato general `{SIGLA_DCTO}_SF_{NÚMERO}_{AÑO}` (parametrización dada por
el usuario):

| Tipo | Sigla | Número | Año | Ejemplo |
|---|---|---|---|---|
| Circular Externa | `C` | nº de la tabla, 4 dígitos | año de la página | `C_SF_0020_2026` |
| Carta Circular | `CCIR` | nº de la tabla, 4 dígitos | año de la página | `CCIR_SF_0020_2026` |
| Resolución | `R` | nº de la tabla, 4 dígitos | año de la página | `R_SF_0020_2026` |
| Concepto | `CTO` | 7 dígitos del radicado | 4 dígitos del radicado | `CTO_SF_0019914_2026` |
| Anexo | — | — | — | `{title_madre}_A{nn}` → `C_SF_0020_2026_A01` |

### Conceptos — derivación del número y el año

El "número largo" con el que descarga el documento (ej. `2026019914`) es
el mismo `radicado` de la línea `Concepto:`. Se parte:
`año = radicado[:4]` (`"2026"`), `numero = radicado[4:]` (`"019914"`) →
`numero` se rellena con ceros a la izquierda hasta 7 dígitos
(`"0019914"`) → `CTO_SF_0019914_2026`. Si `radicado[4:]` tuviera más de
7 dígitos (no observado) se deja completo.

### Conceptos — choque de radicado

Decisión del usuario: **incluir el consecutivo solo cuando hay choque**.
Regla concreta y determinista (sin depender del orden de proceso ni de
consultar la base): el `consecutivo` normalizado a entero.
- `consecutivo == 1` → sin sufijo: `CTO_SF_0019914_2026`.
- `consecutivo != 1` → se agrega `_{consecutivo:02d}`:
  `CTO_SF_0045919_1998_04`.

Así el concepto "base" (consecutivo 1) conserva el nombre limpio y
cualquier concepto adicional del mismo radicado (los que hoy chocarían)
queda diferenciado. **Supuesto**: el ejemplo `CTO_SF_0019914_2026`
corresponde a un consecutivo 1; si el equipo de fuentes confirma que no,
se cambia la regla a "detectar el choque dentro del lote de la corrida y
sufijar los que no sean el menor consecutivo".

El `save_path` de Conceptos usa el `title` ya resuelto (con o sin
sufijo), así que dos conceptos del mismo radicado nunca sobrescriben el
mismo archivo en almacenamiento.

### Sin patrón reconocible

`title` = texto crudo (descripción o título temático) truncado a 120
caracteres y saneado, `title_unverified = True`. El worker intentará
recuperar el título del contenido del archivo descargado
(`resolve_unverified_document`, no implementado para esta familia en v1 —
queda como posible mejora).

## Anexos — comportamiento tipo "actuaciones"

Los anexos son **documentos hermanos** (una fila `documents` cada uno),
no adjuntos embebidos — se mantiene la regla "un documento = un archivo"
de todo el pipeline (versionado, preview, revisión, descarga masiva,
sync con MinIO). El comportamiento "N anexos" es **código nuevo en
paralelo** al de "N actuaciones" (que agrupa por título idéntico); acá se
agrupa por la relación `{padre}` ↔ `{padre}_A\d{2}`.

### Helpers (`core/naming.py`)

- `es_anexo_title(title) -> bool`: `bool(re.search(r"_A\d{2}$", title))`.
- `titulo_padre_de_anexo(title) -> str | None`: quita el sufijo `_A\d{2}`.

El nombre canónico de un anexo es su `title` tal cual (no es título de
caso → `construir_nombre` no le agrega fecha; solo `-v{n}` si se
republica). El nombre del documento madre no cambia.

### Listado (`core/db/repository.py`)

En `list_documents`, junto al colapso de "case families", se agrega el
colapso de anexos: una fila cuyo `title` matchea `_A\d{2}$` en la familia
`superfinanciera` se **oculta del listado general** si existe otra fila
con el `title` padre en la misma fuente. (Análogo a `has_newer_sibling`,
pero "tiene padre".) El colapso aplica solo a esta familia y solo a
títulos con forma de anexo; cualquier otro documento queda intacto.

Función nueva `anexo_counts_by_parent_title(db, documents, family_keys)`:
para cada documento madre de `superfinanciera`, cuenta las filas
`{title}_A%` de la misma fuente. Devuelve `{title_padre: n}`.

### API (`api/routers/documents.py`)

- En el listado, para cada documento madre de `superfinanciera` se
  expone `anexo_count` (paralelo a `case_document_count`); `null` si 0.
- Endpoint nuevo `GET /documents/{id}/anexos` → lista los documentos
  anexos (`{title}_A%` de la misma fuente, ordenados por sufijo), cada
  uno con sus propias URLs de preview/descarga (se reutiliza el
  serializador de documento existente). Se prefiere un endpoint dedicado
  sobre reusar el filtro `title_contains` para tener un contrato claro y
  no acoplar el frontend al formato del sufijo.

### Descarga masiva (`core/db/repository.py`)

`_expandir_a_grupos` se extiende: si un id seleccionado es un documento
madre de `superfinanciera`, se agregan los ids de sus anexos
`{title}_A%`. Así, marcar una circular como "útil" y bajarla incluye sus
anexos (mismo criterio que las actuaciones hermanas).

### Revisión

v1: cada anexo entra `pending` como cualquier documento; sin herencia de
`review_status` entre madre y anexos. Queda como posible v2 el análogo
de `heredar_review_status_de_actuaciones_existentes`.

### Frontend

- En la lista de documentos, mostrar un chip "N anexos" en la fila del
  documento madre (junto a / con el mismo tratamiento visual que "N
  actuaciones"), desplegable para ver/descargar cada anexo (consume
  `GET /documents/{id}/anexos`).
- Es el único cambio de frontend; el resto de familias no muestra
  anexos y no se ve afectado.

## Migración

Ninguna de esquema. Los anexos son filas `documents` normales y el
conteo "N anexos" se calcula en la consulta. Solo código nuevo +
`core/seed.py`.

## Pruebas

`tests/families/test_superfinanciera_normativa.py` — fixtures HTML reales
recortados (`responses` mockeando la página índice y una página de año
por tipo):
- Se parsean los 3 tipos; número con relleno a 4 dígitos; fecha armada
  desde `"<Mes> <DD>"` + año de la página; filtro por rango de fechas
  (dentro / fuera); mapeo tipo→sigla.
- Se emiten filas de anexo `_A01`, `_A02` con el `title` del padre y el
  `save_path` correcto; sin anexos cuando el padre es `title_unverified`.
- Número no numérico → `title_unverified`.
- Un año/tipo con GET fallido no tumba el resto.

`tests/families/test_superfinanciera_conceptos.py` — fixtures de páginas
reales del OPAC ABCD:
- Parseo de la línea `Concepto:` (radicado / consecutivo / fecha en
  español); `title = CTO_SF_{7díg}_{año}` con año tomado del prefijo del
  radicado (caso del usuario: `2026019914` → `CTO_SF_0019914_2026`).
- Regla del consecutivo: `1` → sin sufijo; `4` →
  `..._04` (caso real `1998045919`).
- Filtro por rango de fechas (conserva/omite correctamente).
- Bucle de paginación sobre ≥ 2 páginas usando los campos del formulario
  `continuar`.
- Registro sin línea `Concepto:` parseable → `title_unverified`; y se
  omite si además no hay fecha.
- Extensión `.docx` resuelta desde el `Content-Disposition`.

`tests/` de agrupación de anexos:
- `list_documents` oculta las filas `_A%` cuando existe el padre en la
  misma fuente; no toca otras familias.
- `anexo_counts_by_parent_title` devuelve el conteo correcto.
- `expand_document_ids_with_siblings` incluye los anexos al seleccionar
  el documento madre.
- `GET /documents/{id}/anexos` devuelve los anexos ordenados.

Registro/seed:
- `superfinanciera` queda en `FAMILY_REGISTRY` y sembrada como **una
  sola** fuente.

## Frontend — resumen de cambios

Solo el chip "N anexos" + desplegable en la lista de documentos. Sin
cambios en filtros ni en el resto de vistas.
