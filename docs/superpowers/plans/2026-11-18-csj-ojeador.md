# CSJ → Ojeador Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the `corte_suprema` family to read the Corte Suprema's new Ojeador backend, plus a one-off script that re-keys the CSJ documents already stored so they are not downloaded twice.

**Architecture:** `ScrapCorteSuprema.scrap()` splits `[fini, ffin]` into calendar-month windows and pages through `GET /search/` (100 per page) on `buscadorjurisprudenciabackend.cortesuprema.gov.co`; each result maps to a `RawDocModel` whose link is a plain GET to `/document/descargar?path=<Ubicacion>`. `core/backfill_csj_ojeador.py` finds each stored CSJ document in Ojeador by its code and rewrites only `doc_id`, `source_url`, `f_public`, `f_providencia`.

**Tech Stack:** Python 3, `requests`, `responses` (tests), SQLAlchemy, pytest.

**Spec:** `docs/superpowers/specs/2026-11-18-csj-ojeador-design.md`

## Global Constraints

- Source name stays `CSJ`, family key stays `corte_suprema`; no seed change, no Alembic migration, no change to `core/downloader.py`.
- Backend base: `https://buscadorjurisprudenciabackend.cortesuprema.gov.co`; search `GET /search/`, download `GET /document/descargar?path=<Ubicacion>`. Valid TLS (no `verify=False`).
- `limit` per page = **100** (max accepted); window rule `page * limit ≤ 10000`.
- Search params always: `query_text=""`, `orden="recientes"`, `limit="100"`, `page`, `fechaInicio`, `fechaFin` (`AAAA-MM-DD`).
- `f_public = f_providencia = FechaConsolidacionFirma[:10]`.
- `scheduled_min_lookback_days = 45`; `checks_for_republication = False`; `filters_by_publication_date = False`.
- Title format unchanged ("CSJ = código a secas"): `_codigo_from_titulo` with the existing `_CODIGO_RE` (kept — imported by `core/backfill_csj_titles.py`).
- Buckets: `SCC` / `SCL` / `SCP` by `Sala`; **`SPL`** for `PLENA`. `save_path = storage_path("CSJ", bucket, f"{safe_titulo}(extension)")`.
- Retries: `_MAX_INTENTOS = 3`, `_ESPERA_REINTENTO_SEG = 5`; 5xx / connection error / non-JSON retried, 4xx not retried.
- Default `scrap(limit=...)` = **50000**.
- Backfill script never deletes anything and defaults to simulate; real changes only with `--aplicar`.
- User-facing messages (on_progress, logs, docs) in Spanish, plain language.

## Review Focus

1. `Ubicacion` with spaces, accents, `[ ]`, `.` (e.g. `SALAS/CIVIL/2026/Dr. Fernando Augusto Jiménez Valderrama/11.- Noviembre/Autos/AC7263-2026 [2026-03319-00].docx`) must round-trip into the download URL so the server finds the file → test in Task 2 asserts the exact encoded URL.
2. A `Sala` value outside CIVIL/LABORAL/PENAL/PLENA (or empty) must not crash the run → falls back to the sala named in the `Ubicacion` path, else keeps the raw value as bucket with no especialidad/seccion; test in Task 1.
3. A month with exactly 100 × n results must not request an extra empty page forever / must stop at `page*100 ≥ numFound` → test in Task 2.
4. The 400 "ventana de resultados" on a window that grew past 10 000 mid-run must not abort the other months → test in Task 2.
5. A stored CSJ document whose title carries a version suffix (`AC2794-2026 [2024-00858-00]-v2`) must still be matched by the backfill (strip `-v\d+` before extracting the code) → test in Task 3.

---

### Task 1: Pure mapping helpers

**Files:**
- Modify: `core/scrapers/families/corte_suprema.py`
- Test: `tests/families/test_corte_suprema.py`

**Interfaces:**
- Produces:
  - `_tramos_mensuales(fini: str, ffin: str) -> list[tuple[str, str]]`
  - `_tipo_desde_ojeador(tipo_providencia: str, codigo: str | None) -> str`
  - `_clasificar_sala(item: dict) -> tuple[str | None, str | None, str]` → `(especialidad, seccion, bucket)`
  - `_url_descarga(ubicacion: str) -> str`
  - `_doc_desde_resultado(item: dict) -> RawDocModel` (raises `KeyError` on missing `Ubicacion`/`FechaConsolidacionFirma`)

- [ ] **Step 1: Write failing tests**

```python
def test_tramos_mensuales_recorta_primer_y_ultimo_mes():
    assert _tramos_mensuales("2026-01-15", "2026-03-10") == [
        ("2026-01-15", "2026-01-31"), ("2026-02-01", "2026-02-28"), ("2026-03-01", "2026-03-10")]

def test_tramos_mensuales_un_solo_dia():
    assert _tramos_mensuales("2026-11-18", "2026-11-18") == [("2026-11-18", "2026-11-18")]

@pytest.mark.parametrize("tp, codigo, esperado", [
    ("AUTO", "AC1-2026", "Auto"), ("AUTO TUTELA", "ATP1-2026", "Auto"), ("AUTOHABEAS", "AHP1-2026", "Auto"),
    ("SENTENCIA", "SC1-2026", "Sentencia"), ("SENTENCIA TUTELA", "STP1-2026", "Sentencia"),
    ("CONCEPTO", "CP1-2026", "Concepto"), ("CONCEPTO EXTRADICCION", "CP2-2026", "Concepto"),
    ("OTROS", "SC9-2026", "Sentencia"), ("Otros", None, "Desconocido"), ("", None, "Desconocido")])
def test_tipo_desde_ojeador(tp, codigo, esperado): ...

def test_clasificar_sala_tutela_penal():
    item = {"Sala": "PENAL", "Especialidad": "PENAL", "TipoDeProvidencia": "SENTENCIA TUTELA",
            "Ubicacion": "SALAS/TUTELAS/PENA/2026/Dr. X/Sentencia/STP21139-2026.docx"}
    assert _clasificar_sala(item) == ("Tutela", "Sala de Casación Penal", "SCP")

def test_clasificar_sala_plena():
    item = {"Sala": "PLENA", "Especialidad": "PLENA", "TipoDeProvidencia": "AUTO",
            "Ubicacion": "SALAS/PLENA/2026/Autos/APL6636-2026.docx"}
    assert _clasificar_sala(item) == ("Plena", "Sala Plena", "SPL")

def test_clasificar_sala_civil_y_laboral(): ...  # ("Civil","Sala de Casación Civil","SCC"), ("Laboral",...,"SCL")

def test_clasificar_sala_desconocida_no_rompe():   # Review Focus 2
    item = {"Sala": "", "Especialidad": "", "TipoDeProvidencia": "AUTO", "Ubicacion": "SALAS/LABORAL/2026/x.docx"}
    assert _clasificar_sala(item) == ("Laboral", "Sala de Casación Laboral", "SCL")
    item = {"Sala": "OTRA", "Especialidad": "", "TipoDeProvidencia": "AUTO", "Ubicacion": "raro/x.docx"}
    assert _clasificar_sala(item) == (None, None, "OTRA")

def test_url_descarga_codifica_la_ubicacion():   # Review Focus 1
    u = "SALAS/CIVIL/2026/Dr. Fernando Augusto Jiménez Valderrama/11.- Noviembre/Autos/AC7263-2026 [2026-03319-00].docx"
    assert _url_descarga(u) == (
        "https://buscadorjurisprudenciabackend.cortesuprema.gov.co/document/descargar?path="
        "SALAS%2FCIVIL%2F2026%2FDr.%20Fernando%20Augusto%20Jim%C3%A9nez%20Valderrama%2F11.-%20Noviembre"
        "%2FAutos%2FAC7263-2026%20%5B2026-03319-00%5D.docx")

def test_doc_desde_resultado_completo():
    d = _doc_desde_resultado(_resultado())   # fixture helper: real AC7263-2026 item from the spec
    assert d.title == "AC7263-2026 [2026-03319-00]" and d.title_unverified is False
    assert d.tipo == "Auto" and d.especialidad == "Civil" and d.seccion == "Sala de Casación Civil"
    assert d.f_public == d.f_providencia == "2026-11-06"
    assert d.link == {"url": _url_descarga(_resultado()["Ubicacion"]), "method": "GET"}
    assert d.save_path == "CSJ/SCC/AC7263-2026 [2026-03319-00](extension)"
    assert d.source == "CSJ"

def test_doc_desde_resultado_sin_codigo_marca_titulo_por_verificar():
    d = _doc_desde_resultado(_resultado(Nombre="doc", Numerador=""))
    assert d.title == "doc_2026" and d.title_unverified is True

def test_doc_desde_resultado_usa_numerador_si_nombre_no_calza():
    d = _doc_desde_resultado(_resultado(Nombre="(3)", Numerador="AL12909-2026"))
    assert d.title == "AL12909-2026" and d.title_unverified is False
```

Write `_resultado(**override)` at the top of the test file returning the AC7263-2026 dict from the spec's field table (`id`, `Nombre`, `Numerador`, `CUI`, `FechaConsolidacionFirma`, `Especialidad`, `Sala`, `TipoDeProvidencia`, `ClaseActuacion`, `Ponente`, `Ubicacion`).

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/families/test_corte_suprema.py -k "tramos or tipo_desde or clasificar or url_descarga or doc_desde" -q` → FAIL (ImportError).

- [ ] **Step 3: Implement the five helpers** in `corte_suprema.py`. Notes:
  - `_tipo_desde_ojeador`: upper-case input; `startswith("AUTO")` → Auto, `startswith("SENTENCIA")` → Sentencia, `startswith("CONCEPTO")` → Concepto; else `_tipo_from_titulo(codigo)` if codigo, else `"Desconocido"`.
  - `_clasificar_sala`: sala = `item["Sala"] or item["Especialidad"]`; if empty, take the first of CIVIL/LABORAL/PENAL/PLENA found in `Ubicacion.upper()` (`PENA` counts as PENAL); map `{"CIVIL": ("Civil","Sala de Casación Civil","SCC"), "LABORAL": (...,"SCL"), "PENAL": (...,"SCP"), "PLENA": ("Plena","Sala Plena","SPL")}`; especialidad becomes `"Tutela"` when `"TUTELA" in TipoDeProvidencia.upper()` or `"/TUTELAS/" in Ubicacion.upper()`. Unknown non-empty sala → `(None, None, <sala>)`.
  - `_url_descarga`: `f"{_BASE}/document/descargar?path={quote(ubicacion, safe='')}"`.
  - `_doc_desde_resultado`: título = `_codigo_from_titulo(Nombre)` or `_codigo_from_titulo(Numerador)`; fallback `f"{_INVALID_PATH_CHARS.sub('-', Nombre or 'doc')}_{fecha[:4]}"` with `title_unverified=True`.
  - Add constants `_BASE = "https://buscadorjurisprudenciabackend.cortesuprema.gov.co"`, `_SOURCE = "CSJ"`.

- [ ] **Step 4: Run** the same command → PASS.

- [ ] **Step 5: Commit** `feat(csj): mapeo de resultados del buscador Ojeador`.

---

### Task 2: Rewrite `scrap()` over Ojeador and drop the GraphQL code

**Files:**
- Modify: `core/scrapers/families/corte_suprema.py`
- Test: `tests/families/test_corte_suprema.py` (replace every GraphQL-based test: lines ~16–737 that use `_URL`, `_item`, `_callback_factory`; keep the three `resolve_unverified_document` tests and the registry test)

**Interfaces:**
- Consumes: Task 1 helpers.
- Produces: `ScrapCorteSuprema._consultar_pagina(fini: str, ffin: str, page: int) -> dict` (the parsed JSON); `ScrapCorteSuprema.scrap(fini, ffin, q="", limit=50000, stop_event=None, on_progress=None) -> list[RawDocModel]`.

- [ ] **Step 1: Write failing tests** (all with `@responses.activate`, `_SEARCH = _BASE + "/search/"`, a `_pagina(docs, numFound)` helper building `{"numFound":…, "returned": len(docs), "docs": docs}`):

```python
def test_scrap_pagina_hasta_completar_el_mes():          # 230 → pages 1,2,3 then stop
def test_scrap_para_en_page_por_100_igual_a_numfound():  # Review Focus 3: 200 → exactly 2 calls
def test_scrap_parte_el_rango_en_meses():                # 2026-01-15..2026-03-10 → fechaInicio/fechaFin of 3 calls
def test_scrap_mes_con_mas_de_10000_se_parte_por_dias(): # numFound 12000 on the month → per-day requests
def test_scrap_un_4xx_avisa_y_sigue_con_el_siguiente_mes():  # Review Focus 4: 400 on Jan, Feb still returned
def test_scrap_reintenta_5xx_y_no_json():                # 500, 200-non-JSON, then 200 → docs returned
def test_scrap_se_rinde_tras_3_intentos_y_lo_avisa():
def test_scrap_descarta_fecha_fuera_de_rango_con_aviso():
def test_scrap_deduplica_por_id():
def test_scrap_respeta_limit_y_stop_event():
def test_atributos_de_la_familia():
    assert ScrapCorteSuprema.scheduled_min_lookback_days == 45
    assert ScrapCorteSuprema.checks_for_republication is False
    assert ScrapCorteSuprema.filters_by_publication_date is False
```

Each `responses.add` uses `matchers.query_param_matcher({...})` with the Global Constraints params so the exact query string is pinned.

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/families/test_corte_suprema.py -q` → new tests FAIL.

- [ ] **Step 3: Implement.**
  - `_consultar_pagina`: GET with the fixed params; retry loop as today (5xx / `RequestException` / JSON or missing `docs` → retry after `_ESPERA_REINTENTO_SEG`; 4xx → raise immediately with message `"Error al obtener datos de CSJ: {status} — el sitio pudo haber cambiado su estructura. Informar al equipo de desarrollo."`).
  - `scrap`: for each `(a, b)` in `_tramos_mensuales`: read page 1; if `numFound > 10000`, replace the window by one window per day (if a single day still exceeds 10 000, on_progress `"[CSJ] Aviso: el {día} tiene más de 10.000 providencias; quedó incompleto"` and page only up to 100 pages). Page while `returned == 100 and page*100 < numFound`. Any exception in a window → on_progress `"[CSJ] Error consultando {a}..{b}: {e}"` and continue with the next window. Per item: skip duplicate `id`; build with `_doc_desde_resultado` inside `try/except KeyError` (on_progress and continue); drop if `f_public` outside `[fini, ffin]` with on_progress; stop at `limit` or `stop_event`.
  - Class attrs: `scheduled_min_lookback_days = 45`, keep `checks_for_republication = False`.
  - Delete `_CORTE_SUPREMA_URL`, `_DOWNLOAD_URL`, `_QUERY_TEMPLATE`, `self.tipos`, `_especialidad_from_online_path`, `_seccion_from_online_path`, `_BUCKET_POR_SECCION`, `_bucket_real`, `_COLOMBIA_TZ` and the "ambas URLs apuntan a un mismo servidor" message.

- [ ] **Step 4: Run** `.venv/Scripts/python -m pytest tests/families/test_corte_suprema.py tests/test_backfill_csj_titles.py tests/test_backfill_csj_storage_keys.py -q` → all PASS.

- [ ] **Step 5: Live check (no DB):** with a throwaway script outside the repo, `ScrapCorteSuprema().scrap("2026-10-01", "2026-10-31")` → count equals the site's `numFound` for October (≈1.800), buckets only SCC/SCL/SCP/SPL, `title_unverified` rare. Download 3 links with `requests.get` and confirm `%PDF`.

- [ ] **Step 6: Commit** `feat(csj): la CSJ lee el buscador Ojeador de la Corte`.

---

### Task 3: One-off re-key script for stored CSJ documents

**Files:**
- Create: `core/backfill_csj_ojeador.py`
- Test: `tests/test_backfill_csj_ojeador.py`

**Interfaces:**
- Consumes: `_doc_desde_resultado`, `_codigo_from_titulo`, `_BASE` from Task 1; `compute_doc_id` from `core/utils.py`; `repository`, `Document`, `Source`, `SessionLocal` as in `core/backfill_csj_titles.py`.
- Produces: `buscar_en_ojeador(codigo: str) -> list[dict]`; `elegir_coincidencia(titulo: str, resultados: list[dict]) -> dict | None | str` (`None` = sin coincidencia, `"ambiguo"` = varias); `backfill(db, aplicar: bool = False) -> dict` with keys `actualizados`, `sin_coincidencia`, `ambiguos`, `ya_migrados` (each an int) and `detalle_pendientes: list[str]` (titles); `main()` with argparse flag `--aplicar`.

- [ ] **Step 1: Write failing tests** (DB tests use the `db_session` fixture like `tests/test_backfill_csj_titles.py`; Ojeador mocked with `responses`):

```python
def test_elegir_coincidencia_numerador_exacto(): ...        # 2 results, one Numerador matches → that one
def test_elegir_coincidencia_desempata_por_nombre(): ...     # 2 same Numerador, Nombre == título → that one
def test_elegir_coincidencia_ambigua_devuelve_marca(): ...   # 2 same Numerador, no Nombre match → "ambiguo"
def test_elegir_coincidencia_quita_sufijo_de_version():     # Review Focus 5: "AC2794-2026 [2024-00858-00]-v2"
def test_backfill_simular_no_cambia_nada(db_session): ...    # aplicar=False → doc_id unchanged, actualizados == 1 reported
def test_backfill_aplicar_reescribe_identidad_sin_tocar_archivo(db_session):
    # stored: source_url=".../downloadFile/", doc_id="viejo", f_public="2026-04-30", storage_key="CSJ/SCC/AC2794-2026 [2024-00858-00].pdf"
    # after: doc_id == compute_doc_id(_doc_desde_resultado(hit)), source_url == _url_descarga(hit["Ubicacion"]),
    #        f_public == f_providencia == hit date, title and storage_key unchanged
def test_backfill_sin_codigo_o_sin_resultado_queda_pendiente(db_session): ...
def test_backfill_segunda_corrida_no_cambia_nada(db_session): ...  # ya_migrados == 1
```

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_backfill_csj_ojeador.py -q` → FAIL.

- [ ] **Step 3: Implement** following `core/backfill_csj_titles.py`'s shape (module docstring with "Uso: python -m core.backfill_csj_ojeador [--aplicar]", Spanish). Select CSJ documents (`Source.family_key == "corte_suprema"`) with `source_url == "https://consultaprovidenciasbk.cortesuprema.gov.co/downloadFile/"`; those not matching are counted `ya_migrados`. Strip `-v\d+$` from the title before `_codigo_from_titulo`. Before writing a new `doc_id`, skip (count as `ambiguos`, log) if another document already has it. With `aplicar=True` update the row and `db.commit()` per document; never touch storage. `main()` logs the four counts and the pending titles.

- [ ] **Step 4: Run** the test file plus `tests/test_backfill_csj_titles.py` → PASS.

- [ ] **Step 5: Commit** `feat(csj): script único para reconocer las providencias ya guardadas`.

---

### Task 4: Deployment guide + end-to-end validation

**Files:**
- Modify: `docs/guia-despliegue-sistemas.md:1081-1102` (section "Corte Suprema de Justicia (`corte_suprema`)") and the paragraph at ~501 that cites the 2026 stale index.

- [ ] **Step 1: Rewrite the CSJ section** in plain Spanish: new site (Ojeador), Sala Plena added (`SPL`), daily run looks 45 days back, PDFs only. Add a numbered "Pasos al actualizar (noviembre de 2026)" block:
  1. normal `pull` + `up -d` (no migration);
  2. confirm with RedJurista/BDU/JurIA owners that nothing keys on the internal identifier;
  3. `docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.backfill_csj_ojeador` (simulate) → review pending list;
  4. same with `--aplicar`;
  5. free-space check (PowerShell: `Get-PSDrive C` — needs ~8 GB);
  6. manual CSJ runs one calendar month at a time, 2026-01 → current month, each started after the daily run; measured time per month from Step 3.
  Update the ~501 paragraph to say the Corte moved to Ojeador in November 2026.

- [ ] **Step 2: End-to-end local run** using the `run-iurisync` skill (Docker + API + Celery worker): seed, run CSJ for 2026-10-01..2026-10-31, confirm docs count ≈ October `numFound`, files are PDF and pass the file checks, folders `CSJ/SCC|SCL|SCP|SPL`. Re-run the same month → 0 new downloads. Record minutes per month in the guide (Step 1, item 6).

- [ ] **Step 3: Backfill on local data:** insert two CSJ rows shaped like the old ones (old `source_url`, title `AC2794-2026 [2024-00858-00]`, `STP21139-2026`), run the script simulate then `--aplicar`, confirm both re-keyed, then run CSJ for their months → no duplicates.

- [ ] **Step 4: Run targeted suites** `.venv/Scripts/python -m pytest tests/families/test_corte_suprema.py tests/test_backfill_csj_ojeador.py tests/test_backfill_csj_titles.py tests/test_backfill_csj_storage_keys.py tests/test_seed.py -q` → PASS.

- [ ] **Step 5: Commit** `docs(csj): guía de despliegue para el buscador Ojeador`.
