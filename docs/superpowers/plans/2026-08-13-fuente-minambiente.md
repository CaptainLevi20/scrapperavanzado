# Fuente MinAmbiente (Ministerio de Ambiente y Desarrollo Sostenible) Implementation Plan

**Goal:** Add a new scraper family `minambiente` that scrapes Resoluciones, Leyes, Decretos, Autos, Conpes and Conceptos from `https://www.minambiente.gov.co/normativa/`, wired into the registry, the seed data, and the existing worker/frontend pipeline exactly like every other family.

**Architecture:** One new file `core/scrapers/families/minambiente.py` with a `ScrapMinAmbiente(BaseScrapper)` class registered under `@register_family("minambiente")`. It fetches each category with a single `POST` to the site's own AJAX endpoint (`admin-ajax.php`, `action=normativa_paginacion-load-posts-2`, `area1={termID}`) — confirmed the `page` parameter is a no-op and every category returns its full history in one response. Resoluciones/Leyes/Decretos/Autos/Conpes are parsed from `div.box-docgd` blocks with a date/number cascade copied from `madr.py`'s proven approach; Conceptos is parsed separately from an HTML table embedded inside the description of each year's entry (the top-level link there is a CSV index, not a real document). One `Source` row is added to `core/seed.py` (`family_params={}`), no frontend changes needed.

**Tech Stack:** Python, `requests`, `beautifulsoup4`, `pytest`, `responses` (with `matchers.urlencoded_params_matcher`, since every category shares one URL and is only distinguished by POST body) — same stack `madr.py`/`mincit.py` already use.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-13-fuente-minambiente-design.md` — every rule below (scope, date handling, title format) traces back to it.
- Scope is exactly 6 categories: `Resoluciones`, `Leyes`, `Decretos`, `Autos`, `Conpes`, `Conceptos`. `Agenda Regulatoria`, `Circulares`, `Boletín Legal` and `Boletín Legal Decretos` are explicitly out of scope (see spec for why each was excluded).
- Base URL: `https://www.minambiente.gov.co`; AJAX endpoint: `https://www.minambiente.gov.co/wp-admin/admin-ajax.php`.
- Title format: `{LETRA}_MADS_{numero:04d}_{año}` (`R`/`D`/`L`/`A` for Resolución/Decreto/Ley/Auto, literal `CONPES` for Conpes), `CONCEPTO_MADS_{rad_salida}` for Conceptos.
- Both `f_public` (required by `RawDocModel`) and `f_providencia` (optional) are set for the 5 "normas" categories; `fini`/`ffin` filter against `f_providencia`, not `f_public` — the site's `Publicado:` field was verified to drift on CMS reindex and is not reliable for filtering or identity. `filters_by_publication_date` stays at the `BaseScrapper` default (`False`). `doc_id_uses_publication_date` is explicitly set to `False` for this same reason (same pattern as `rama_judicial`/`samai`).

---

### Task 1: Date/number parsing and title-normalization helpers — done

**Files:** `core/scrapers/families/minambiente.py`, `tests/families/test_minambiente.py`

Ported `madr.py`'s `_resto_tras_numero` + 4-level `_FECHA_PATTERN` cascade (día+mes+año / mes+día+año invertido / mes+año / solo año) unchanged in shape, since the real title formats observed on MinAmbiente match MADR's exactly. Added two more parsers specific to this site: `_parse_publicado` (fixed `"Publicado: {mes} {día}, {año}"` format) and `_parse_fecha_concepto` (`dd/mm/yyyy` from the Conceptos table). Number extraction uses `re.search(r"\d+", título)` (first digit run) rather than `mincit`'s `^\S+\s+(\d+)`, because real titles have noise before the type word (`"Actualizada – Res 0953 del 03 de Septiembre de 2021"`).

- [x] `_resto_tras_numero`, `_normalize_title`, `_parse_fecha`, `_parse_publicado`, `_parse_fecha_concepto` implemented with unit tests covering all cascade levels, the noisy-prefix case, and the calendar-invalid-date fallback.

### Task 2: `_extraer_normas` (Resoluciones/Leyes/Decretos/Autos/Conpes) — done

**Files:** `core/scrapers/families/minambiente.py`, `tests/families/test_minambiente.py`

Iterates `div.box-docgd`, pulls the download link + title from `a.documento-normativa`, `detalle` from `p.descripcion-archivo`, `f_public` from the `Publicado:` span (falling back to `f_providencia` when the span is missing, since `f_public` is a required field), and `f_providencia` + número from the title via Task 1's cascade. Filters `fini`/`ffin` against `f_providencia`. Falls back to `title_unverified=True` with the raw site title when no number or no date is parseable, matching `madr`/`mincit`.

- [x] Implemented and unit-tested (canonical title, providencia-not-publicado filtering, noisy-prefix number, year-only fallback, Conpes literal, missing-Publicado fallback).

### Task 3: `_extraer_conceptos` — done

**Files:** `core/scrapers/families/minambiente.py`, `tests/families/test_minambiente.py`

Separate parser: iterates `div.box-docgd` (one per year with real content — empty years are `display:none` placeholders with no table, skipped naturally), finds the embedded `<table>`, and reads each row's `Fecha` (dd/mm/yyyy → `f_providencia`, duplicated into `f_public` since Conceptos has only one real date), `Rad. Salida` (→ title `CONCEPTO_MADS_{rad_salida}`), `Tema` (→ `detalle`), and the `Descarga` column's link (→ actual document URL — the top-level `a.documento-normativa` for the year is a CSV index and is intentionally never used as a document link here).

- [x] Implemented and unit-tested (table parsing, CSV link ignored, empty-year placeholder produces no documents, invalid calendar date in a row is skipped without crashing the rest of the table).

### Task 4: `scrap()` orchestration + registry wiring — done

**Files:** `core/scrapers/families/minambiente.py`, `core/scrapers/families/__init__.py`

`scrap()` POSTs once per category (5 "normas" categories + Conceptos), calling `_extraer_normas`/`_extraer_conceptos` and continuing past any category whose request fails (logged via `on_progress`, matching `adr.py`/`madr.py`). `minambiente` added to the family import line in `core/scrapers/families/__init__.py` so `@register_family` actually runs at app startup.

- [x] Implemented and unit-tested (aggregation across categories, a failing category doesn't drop the rest, `limit` respected, `filters_by_publication_date`/`doc_id_uses_publication_date` flags asserted, registry membership asserted).

### Task 5: Seed wiring — done

**Files:** `core/seed.py`

Added `"minambiente"` to `_FAMILIES` and a `create_source_if_missing(..., family_key="minambiente", family_params={})` call, following the exact pattern of the `madr`/`mincit` entries right above it.

- [x] Implemented.

### Task 6: Full verification

- [x] `pytest tests/families/test_minambiente.py -v` — 32 tests, all PASS.
- [ ] `pytest` (full suite) — run once more after this doc lands, to confirm no regressions in `tests/test_seed.py`/`tests/test_api_sources.py` (which assert on family/source counts and will need their expected counts bumped by one family + one source, same as Task 4 did for `madr` in the MADR plan).
- [ ] Manual sanity check against the live site (not mocked): run `ScrapMinAmbiente().scrap(fini=..., ffin=..., limit=5, on_progress=print)` and confirm real documents come back with clean, non-`title_unverified` titles in the expected shape.
