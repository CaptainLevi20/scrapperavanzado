# Fuente MinEducación (Ministerio de Educación Nacional) — Plan de implementación

**Goal:** Agregar una familia de scraper nueva `mineducacion` que recolecte
el listado "Últimas publicaciones" de
`https://www.mineducacion.gov.co/portal/Normatividad/` (Resoluciones,
Decretos, Leyes, Circulares, Directivas y Acuerdos), conectada al registro,
al seed y al pipeline existente igual que cualquier otra familia.

**Architecture:** Un archivo nuevo `core/scrapers/families/mineducacion.py`
con una clase `ScrapMineducacion(BaseScrapper)` registrada bajo
`@register_family("mineducacion")`. El listado se recorre un año completo
por petición: `GET
https://www.mineducacion.gov.co/portal/Normatividad/Ultimas-publicaciones;anos-normatividad/{año}/`
(plantilla Newtenberg CMS, sin paginación dentro del año). El sitio no
separa por categoría, así que cada fila se clasifica por la primera palabra
de su propio título; número y fecha se extraen del título con regex (no
hay campo de fecha estructurado, a diferencia de `minvivienda`). Una
entrada `Source` se agrega a `core/seed.py` (`family_params={}`), sin
cambios de frontend.

**Tech Stack:** Python, `requests`, `beautifulsoup4`, `pytest`, `responses`
— mismo stack que `madr.py` (título en texto libre, sin JSON/API propio).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-13-fuente-mineducacion-design.md`
  — cada regla abajo viene de ahí.
- Antes de esta fuente se descartó Ministerio de Defensa Nacional (su único
  enlace de normatividad apunta a un producto de Avance Jurídico,
  `normograma.info/mindef`) a pedido explícito del usuario, sin resolver
  aún cómo tratar ese tipo de fuente — ver spec, sección "Fuentes
  descartadas".
- Alcance: Resolución, Decreto, Ley, Circular, Directiva, Acuerdo —
  clasificados por la primera palabra del título de cada fila (el sitio no
  separa por categoría). "Proyecto de Decreto/Resolución" y cualquier
  documento suelto que no encaje (Guía, Manual, Reglamento Operativo) se
  excluyen a propósito.
- Base URL: `https://www.mineducacion.gov.co`; listado:
  `https://www.mineducacion.gov.co/portal/Normatividad/Ultimas-publicaciones;anos-normatividad/{año}/`,
  un año completo por petición (verificado sin paginación oculta).
- Título: `{LETRA}_MEN_{numero:04d}_{año}` (`R`/`D`/`L`/`C`/`A` para
  Resolución/Decreto/Ley/Circular/Acuerdo, literal `DIRECTIVA` para
  Directiva).
- Sin campo de fecha estructurado en el sitio: `f_public` se llena
  directamente con la fecha real ya parseada del título (mismo criterio que
  `madr.py`), no hay `f_providencia`. `doc_id_uses_publication_date` se
  queda en el default `True` (a diferencia de `minvivienda`/`minambiente`):
  la fecha viene del propio título del documento, no de un timestamp de
  reindexado del CMS que pueda cambiar para el mismo archivo.
  `filters_by_publication_date` se queda en el default `False` (mismo
  criterio que `madr.py`).
- Los enlaces de descarga son relativos al `<base href>` que declara la
  plantilla Newtenberg, **no** a la URL amigable pedida — deben resolverse
  contra ese `<base>`.
- Cada fila puede traer varios adjuntos; se prefiere el primer adjunto en
  formato PDF (no la primera posición a secas — un `.docx` anexo puede
  aparecer antes que el PDF real, ver spec).

---

### Task 1: Clasificación por primera palabra + extracción de número/fecha — done

**Files:** `core/scrapers/families/mineducacion.py`,
`tests/families/test_mineducacion.py`

`_clasificar_tipo(titulo)` mapea la primera palabra del título (case-
insensitive) a `(tipo, letra)`; devuelve `None` para "Proyecto" y cualquier
palabra no reconocida (Guía, Manual, Reglamento...). `_extraer_numero`
toma el primer grupo de dígitos del título completo. `_parse_fecha`
(cascada de 5 niveles en una sola alternancia, mismo criterio que
`madr._FECHA_PATTERN`) cubre: día+mes con nombre completo, mes completo sin
día, fecha numérica `DD-M-AAAA`, mes abreviado en mayúsculas sin "de", y
solo año.

- [x] Implementado y probado con unidad (los 6 tipos reconocidos, exclusión
  de Proyecto/Guía/Manual/Reglamento, los 5 niveles de fecha + casos límite
  de fecha calendario imposible y case-insensitive).

### Task 2: Selección de adjunto + resolución contra `<base href>` — done

**Files:** `core/scrapers/families/mineducacion.py`

`_elegir_adjunto(figuras)`: primer `div.figure.bajardoc` cuyo `href`
termina en `.pdf`, en orden de documento (fallback al primero si ninguno es
PDF). `_extraer_anio` parsea el `<base href>` de la plantilla Newtenberg
con BeautifulSoup y lo usa como base de `urljoin` para cada enlace de
adjunto, en vez de la URL de la petición.

- [x] Implementado y probado (un `.docx` anexo que aparece antes que el PDF
  real no se elige; resolución de enlaces contra el `<base>`, no contra la
  URL amigable pedida).

### Task 3: Orquestación `scrap()` por año — done

**Files:** `core/scrapers/families/mineducacion.py`,
`core/scrapers/families/__init__.py`

Un `GET` por cada año entre `fini[:4]` y `ffin[:4]` (inclusive); sin
paginación dentro del año (confirmado que cada página trae el año completo
sin truncar, contra el propio contador del sitio). Un año cuyo `GET` falle
no descarta lo ya recolectado — se registra vía `on_progress` y se continúa
con el siguiente año. `mineducacion` agregado al import de
`core/scrapers/families/__init__.py`.

- [x] Implementado y probado (límite respetado, `stop_event` respetado
  entre años, año que falla no descarta los demás, filtro por rango de
  fechas).

### Task 4: Seed wiring — done

**Files:** `core/seed.py`, `tests/test_seed.py`

Agregado `"mineducacion"` a `_FAMILIES` y un
`create_source_if_missing(..., family_key="mineducacion", family_params={})`,
siguiendo el patrón de las entradas `madr`/`mincit`/`minvivienda`. Conteos
hardcodeados en `tests/test_seed.py` actualizados (12→13 familias, y el
grupo de "fuente única" de 9→10).

- [x] Implementado.

### Task 5: Full verification

- [x] `pytest tests/families/test_mineducacion.py -v` — 48 pruebas, todas
  en verde.
- [x] `pytest` (suite completa) — 795 passed, 1 falla preexistente no
  relacionada (`test_migrations.py::test_alembic_upgrade_head_creates_all_tables`,
  `WinError 2` por PATH en esta máquina Windows — la misma falla ya conocida
  de las fuentes anteriores).
- [x] Sanity check manual contra el sitio real (no mockeado): corrido
  contra 2025-2026 (41 documentos) y contra 2020-2026 (250 documentos).
  Confirmó: títulos con el formato esperado en las 4 categorías con volumen
  (Resolución, Decreto, Circular, Directiva), enlaces resueltos vía
  `<base href>` que descargan correctamente, y un único aviso de fila
  omitida (`"CIRCULAR 002 - Útiles Escolares"`, sin fecha reconocible en el
  título — el caso límite ya documentado en la spec). Encontró además un
  hallazgo real del sitio (no un bug del scraper): 14 títulos duplicados en
  el rango 2020-2026 corresponden a dos artículos distintos del CMS con la
  misma norma re-subida bajo un `aid`/URL de PDF diferente — cada uno recibe
  su propio `doc_id` porque la identidad se basa en la URL de descarga, no
  en el título. Ver spec para el detalle completo.
