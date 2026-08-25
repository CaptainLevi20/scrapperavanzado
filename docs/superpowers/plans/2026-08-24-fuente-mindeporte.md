# Fuente Ministerio del Deporte (mindeporte) — Plan de implementación

**Goal:** Agregar una familia de scraper nueva `mindeporte` que recolecte
Resoluciones, Decretos, Leyes, Acuerdos, Conpes, Directivas y Circulares
desde el sitio de transparencia de `mindeporte.gov.co`, conectada al
registro, al seed y al pipeline existente igual que cualquier otra familia.

**Architecture:** Un archivo `core/scrapers/families/mindeporte.py` con una
clase `ScrapMinDeporte(BaseScrapper)` registrada bajo
`@register_family("mindeporte")`. Un solo extractor de bloque
(`_extraer_articulos`) reusado por las 7 categorías. Resoluciones se navega
por año (`.../resoluciones/{año}?page=N`, solo años dentro de
`[fini.year, ffin.year]`); las otras 6 categorías son un único listado
descendente por fecha (`.../normograma/{categoria}?page=N`) donde la
paginación se corta en el primer item con fecha anterior a `fini`. Una
entrada `Source` se agrega a `core/seed.py` (`family_params={}`), sin
cambios de frontend.

**Tech Stack:** Python, `requests`, `beautifulsoup4`, `pytest`, `responses`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-24-fuente-mindeporte-design.md` —
  cada regla abajo viene de ahí, incluido el descubrimiento completo del
  sitio.
- Sin protección anti-robots — confirmado con `curl` plano contra listado y
  PDFs.
- Rama: `feat/fuente-mindeporte`, creada directo desde `master`.
- Alcance v1 (decisión explícita del usuario): Resoluciones, Decretos,
  Leyes, Acuerdos, Conpes, Directivas y Circulares (con parseo dedicado).
  Fuera: Procesos Judiciales (títulos sin patrón), Manuales (página de
  texto libre), normativa-covid-19 (vacía), políticas de privacidad (no es
  normatividad).
- Título: `{LETRA}_MDEPORTE_{numero:04d}_{año}` (decisión explícita del
  usuario, consistente con `madr`/`mincit`/`minambiente`/`mininterior`);
  `CONPES` y `DIR` como literales, `C` para ambos tipos de Circular. Un
  documento sin fecha parseable en el título se descarta (no se guarda con
  fecha inventada); sin número pero con fecha, fallback a título crudo +
  `title_unverified=True`.
- Fecha del acto = fecha extraída del título (`f_providencia`), nunca el
  timestamp de "publicación en el sitio" (verificado sistemáticamente
  posterior, nunca la fecha real) — `filters_by_publication_date` y
  `doc_id_uses_publication_date` se dejan en su default.
- Necesita un quinto nivel de fecha además de la cascada de 4 niveles de
  `madr`: día+mes+año **sin conector "de/del" entre mes y año** (visto en
  una Circular real: `"15 de noviembre 2024"`).

---

### Task 1: Extracción de un item del listado — done

**Files:** `core/scrapers/families/mindeporte.py`,
`tests/families/test_mindeporte.py`

`_extraer_articulos` parsea cada `<article>`: título
(`p.text-base.font-semibold`), detalle (`p.mt-1.text-sm...`, opcional —
ausente en Circulares, limpiado con `_limpiar_detalle` para la mezcla real
de comilla recta de apertura y comilla tipográfica de cierre pegada antes
del punto), enlace (primer `<a href>` en `ul.list-disc`), número (`\d+`,
primer run de dígitos del título) y fecha (resto tras el número, cascada
de 5 niveles). Descarta el item si falta el enlace o si no hay fecha
parseable.

- [x] Cascada de fecha de `madr.py` (`_FECHA_PATTERN`/`_resto_tras_numero`/
  `_parse_fecha`) copiada dentro de `mindeporte.py`, con el quinto nivel
  agregado (día+mes+año sin conector "de/del" antes del año).
- [x] `_extraer_articulos(html, tipo, letra, fini, ffin, source,
  on_progress)` → `List[RawDocModel]`.
- [x] 21 pruebas: parseo del bloque real (título, detalle, enlace), los 5
  niveles de fecha, número para las 7 categorías (incluidas Directivas con
  sus dos prefijos y Circulares con y sin fecha en el título), descarte
  cuando no hay fecha parseable, filtro por rango `fini`/`ffin`, sin
  enlace de descarga.

### Task 2: Paginación — normograma (flat) y resoluciones (por año) — done

**Files:** `core/scrapers/families/mindeporte.py`

- [x] Paginación genérica (`_paginar`): pide `?page=N` mientras la página
  traiga `rel="next"`; corta en cuanto un item con fecha parseable en la
  página es anterior a `fini` (orden descendente confirmado).
- [x] Resoluciones: pide primero la página raíz para descubrir los años
  enlazados (`_anos_enlazados`); filtra a los años dentro de
  `[fini.year, ffin.year]`; pagina cada año con la misma lógica genérica.
- [x] `scrap()` recorre las 7 categorías (Resoluciones con navegación por
  año, las otras 6 planas), agregando resultados y respetando
  `stop_event`/`limit`.
- [x] 6 pruebas: corte de paginación por fecha fuera de rango, selección
  de años en rango para Resoluciones, continúa con lo demás si una
  categoría falla, `stop_event`, detección de `rel="next"`.

### Task 3: Seed wiring — done

**Files:** `core/seed.py`, `core/scrapers/families/__init__.py`,
`tests/test_seed.py`

- [x] Agregado `mindeporte` a `_FAMILIES` y
  `create_source_if_missing(db, family_key="mindeporte",
  name="Ministerio del Deporte", family_params={})`.
- [x] Agregado el import en `core/scrapers/families/__init__.py`.
- [x] `tests/test_seed.py` actualizado (17 familias, 82 fuentes en vez de
  81, grupo de "fuente única" de 13 a 14).

### Task 4: Full verification

- [x] `pytest tests/families/test_mindeporte.py -v` — 31 pruebas, todas en
  verde.
- [x] `pytest tests/test_seed.py` — 3 pruebas, todas en verde.
- [x] `pytest` (suite completa) — 925 passed, 1 failed (la falla
  preexistente ya documentada de `test_migrations.py` en esta máquina
  Windows, no relacionada).
- [x] Sanity check manual contra el sitio real (no mockeado): rango
  2025-07-01 a 2025-08-24 devolvió 9 documentos reales (6 Resoluciones, 1
  Decreto, 2 Leyes) con número, fecha y enlace de PDF correctos, y
  descartó silenciosamente las 3 Circulares sin fecha reconocible del
  mismo rango de fechas del sitio. El PDF de la primera Resolución
  descargó genuino (`application/pdf`, 559 KB) con el mismo
  `User-Agent: Mozilla/5.0` que ya usa `core/downloader.py` — sin sesión
  ni referer especial.
