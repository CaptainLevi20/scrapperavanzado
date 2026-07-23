# Rama Judicial Title Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize `RawDocModel.title` for Rama Judicial tribunal-superior documents from the heterogeneous raw filename (e.g. `11001310302020220015001_DraGonzalezAutoAdmiteRecurso`) into a fixed format `T_{CODIGO}_{radicado segmentado}` (e.g. `T_BTA_11001_31_03_020_2022_00150_01`) whenever the filename starts with the 23-digit radicado.

**Architecture:** A new module-level dict `TRIBUNAL_CODES` (dept_code → 3-4 letter code, all 33 entries) and a new pure function `_normalize_title(name_no_ext, dept_code)` in `core/scrapers/families/rama_judicial.py`, following the same segmentation convention as `_format_radicado` in `core/scrapers/families/cndj.py` but joined with `_` instead of `-`. `scrap()` calls this function when building each `RawDocModel`'s `title`.

**Tech Stack:** Python, `re` (already imported in the file), `pytest` + `responses` for tests (same pattern already used in `tests/families/test_rama_judicial.py`).

## Global Constraints

- Trigger condition is **exactly 23 digits followed by `_`** at the start of the raw filename (regex `^\d{23}_`) — do NOT require "Dr"/"Dra" after it; real data has 3 documents (of 726 with a 23-digit prefix) where that's missing or has a stray space, and the rule must still fire for those.
- Rule applies only to the 33 tribunal-superior sources (those with a non-empty `dept_code` present in `TRIBUNAL_CODES`). The 6 Juzgado sources (`dept_code=""`) are never touched — their titles stay exactly as today.
- If the filename doesn't match the trigger condition, or `dept_code` isn't in `TRIBUNAL_CODES`, `title` stays exactly as it is today (the raw filename minus extension) — never guess or partially transform.
- Everything after the 23-digit radicado in the original filename (judge name, action) is discarded — not stored anywhere.
- `save_path`/folder-building logic is unchanged by this plan — it already uses `doc_name` (sanitized `name_no_ext`), not `title`.
- `TRIBUNAL_CODES` must have exactly one entry per `SUPERIORES_DEPTS` key (33 total), using this exact mapping (dept_code → code):
  `05→ANTI, 08→ATLA, 11→BTA, 13→BOLI, 15→BOYA, 17→CALD, 18→CAQU, 19→CAUC, 20→CESA, 23→CORD, 25→CUND, 27→CHOC, 41→HUIL, 44→GUAJ, 47→MAGD, 50→META, 52→NARI, 54→NSAN, 63→QUIN, 66→RISA, 68→SANT, 70→SUCR, 73→TOLI, 76→VALL, 81→ARAU, 85→CASA, 86→PUTU, 88→SAND, 91→AMAZ, 94→GUAI, 95→GUAV, 97→VAUP, 99→VICH`

---

### Task 1: `TRIBUNAL_CODES` table + `_normalize_title` + wire into `scrap()`

**Files:**
- Modify: `core/scrapers/families/rama_judicial.py`
- Test: `tests/families/test_rama_judicial.py`

**Interfaces:**
- Consumes: `SUPERIORES_DEPTS` (already defined in this file, `core/scrapers/families/rama_judicial.py:27`).
- Produces: `TRIBUNAL_CODES: dict[str, str]` (module-level), `_normalize_title(name_no_ext: str, dept_code: str) -> str` (module-level function) — both importable from `core.scrapers.families.rama_judicial` for tests.

- [ ] **Step 1: Write the failing test for `TRIBUNAL_CODES` completeness**

Add to `tests/families/test_rama_judicial.py`, near the top-level imports, add `TRIBUNAL_CODES` and `_normalize_title` to the existing import block:

```python
from core.scrapers.families.rama_judicial import (
    JUZGADOS_ENTIDADES,
    SUPERIORES_DEPTS,
    TRIBUNAL_CODES,
    ScrapRamaJudicial,
    _normalize_title,
)
```

Then add this test function (anywhere after the existing `test_superiores_depts_and_juzgados_entidades_counts` function):

```python
def test_tribunal_codes_has_one_entry_per_superiores_dept():
    assert set(TRIBUNAL_CODES.keys()) == set(SUPERIORES_DEPTS.keys())
    assert TRIBUNAL_CODES["11"] == "BTA"
    assert TRIBUNAL_CODES["76"] == "VALL"
    assert TRIBUNAL_CODES["54"] == "NSAN"
    assert TRIBUNAL_CODES["68"] == "SANT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/families/test_rama_judicial.py::test_tribunal_codes_has_one_entry_per_superiores_dept -v`
Expected: FAIL with `ImportError: cannot import name 'TRIBUNAL_CODES'` (the import at the top of the test file fails because neither `TRIBUNAL_CODES` nor `_normalize_title` exist yet).

- [ ] **Step 3: Add `TRIBUNAL_CODES` to the implementation**

In `core/scrapers/families/rama_judicial.py`, immediately after the `JUZGADOS_ENTIDADES` dict (after line 71, before the blank lines preceding `def _get_with_retries`), add:

```python
# Código de 3-4 letras por tribunal, usado por _normalize_title para el
# prefijo "T_{CODIGO}_" del título normalizado. Dictado directamente por el
# usuario para cada uno de los 33 tribunales — no se deriva automáticamente
# del nombre (ver docs/superpowers/specs/2026-07-23-rama-judicial-title-normalization-design.md).
TRIBUNAL_CODES = {
    "05": "ANTI",
    "08": "ATLA",
    "11": "BTA",
    "13": "BOLI",
    "15": "BOYA",
    "17": "CALD",
    "18": "CAQU",
    "19": "CAUC",
    "20": "CESA",
    "23": "CORD",
    "25": "CUND",
    "27": "CHOC",
    "41": "HUIL",
    "44": "GUAJ",
    "47": "MAGD",
    "50": "META",
    "52": "NARI",
    "54": "NSAN",
    "63": "QUIN",
    "66": "RISA",
    "68": "SANT",
    "70": "SUCR",
    "73": "TOLI",
    "76": "VALL",
    "81": "ARAU",
    "85": "CASA",
    "86": "PUTU",
    "88": "SAND",
    "91": "AMAZ",
    "94": "GUAI",
    "95": "GUAV",
    "97": "VAUP",
    "99": "VICH",
}
```

This step alone does not make the test pass yet — `_normalize_title` still doesn't exist, so the import at the top of the test file still fails. Continue to Step 4 before re-running.

- [ ] **Step 4: Write the failing tests for `_normalize_title`**

Add these test functions to `tests/families/test_rama_judicial.py`, after the `test_tribunal_codes_has_one_entry_per_superiores_dept` test added in Step 1:

```python
def test_normalize_title_builds_prefix_from_23_digit_radicado():
    assert _normalize_title("11001310302020220015001_DraGonzalezAutoAdmiteRecurso", "11") == (
        "T_BTA_11001_31_03_020_2022_00150_01"
    )


def test_normalize_title_ignores_everything_after_the_radicado():
    # el juez y la acción se descartan por completo, no se guardan en ningún lado
    assert _normalize_title("11001310302020220015001_ AnythingElseHere123", "11") == (
        "T_BTA_11001_31_03_020_2022_00150_01"
    )


def test_normalize_title_tolerates_missing_dr_prefix():
    # caso real: el despacho subió el archivo sin "Dr"/"Dra" — la condición de
    # disparo es solo el prefijo de 23 dígitos, no depende de "Dr"/"Dra"
    assert _normalize_title("11001310303320170034203_ValenzuelaSentenciaSegundaInstancia", "11") == (
        "T_BTA_11001_31_03_033_2017_00342_03"
    )


def test_normalize_title_leaves_person_name_titles_unchanged():
    original = "033-2025-00417-01 PAOLA ANDREA NARANJO QUINTANA"
    assert _normalize_title(original, "11") == original


def test_normalize_title_leaves_generic_estado_titles_unchanged():
    original = "ESTADO E-0109 DEL 26 DE JUNIO DE 2026"
    assert _normalize_title(original, "11") == original


def test_normalize_title_leaves_titles_unchanged_when_dept_code_has_no_tribunal_code():
    # Juzgados no tienen dept_code (family_params usa dept_code="", ver core/seed.py)
    original = "11001310302020220015001_DraGonzalezAutoAdmiteRecurso"
    assert _normalize_title(original, "") == original


def test_normalize_title_leaves_titles_unchanged_when_digit_prefix_is_not_23_long():
    original = "1234567890123456789012_DraGonzalezAutoAdmiteRecurso"  # 22 dígitos, no 23
    assert _normalize_title(original, "11") == original
```

Note on Step 4's third test (`test_normalize_title_tolerates_missing_dr_prefix`): the expected value `11001_31_03_033_2017_00342_03` was computed and verified directly (`n[0:5]_n[5:7]_n[7:9]_n[9:12]_n[12:16]_n[16:21]_n[21:23]` applied to `11001310303320170034203`) — copy it verbatim, don't recompute it by hand.

- [ ] **Step 5: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/families/test_rama_judicial.py -v -k "normalize_title or tribunal_codes"`
Expected: FAIL — `AttributeError`/`ImportError` since `_normalize_title` doesn't exist yet (the module-level import at the top of the test file raises before any test body runs).

- [ ] **Step 6: Implement `_normalize_title`**

In `core/scrapers/families/rama_judicial.py`, add this function directly after the `TRIBUNAL_CODES` dict added in Step 3 (and before `def _get_with_retries`):

```python
_RADICADO_PREFIX = re.compile(r"^(\d{23})_")


def _normalize_title(name_no_ext: str, dept_code: str) -> str:
    """Reemplaza el nombre de archivo crudo por "T_{CODIGO}_{radicado segmentado}"
    cuando empieza con el radicado completo (23 dígitos) y el tribunal tiene un
    código conocido. El resto del nombre original (juez, acción) se descarta.
    Si no calza (nombre de persona, aviso genérico "ESTADO...", tribunal sin
    código, o el prefijo no tiene exactamente 23 dígitos), se deja tal cual."""
    codigo = TRIBUNAL_CODES.get(dept_code)
    if codigo is None:
        return name_no_ext

    match = _RADICADO_PREFIX.match(name_no_ext)
    if not match:
        return name_no_ext

    n = match.group(1)
    radicado_segmentado = f"{n[0:5]}_{n[5:7]}_{n[7:9]}_{n[9:12]}_{n[12:16]}_{n[16:21]}_{n[21:23]}"
    return f"T_{codigo}_{radicado_segmentado}"
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/families/test_rama_judicial.py -v -k "normalize_title or tribunal_codes"`
Expected: 8 passed (1 from Step 1 + 7 from Step 4).

- [ ] **Step 8: Write the failing end-to-end test wiring `_normalize_title` into `scrap()`**

Add this test to `tests/families/test_rama_judicial.py`, after `test_scrap_builds_docs_from_listing_and_detail`:

```python
@responses.activate
def test_scrap_normalizes_title_for_documents_with_a_23_digit_radicado(monkeypatch):
    responses.add(
        responses.GET,
        "https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio",
        body=_LISTING_HTML,
        status=200,
    )

    scraper = ScrapRamaJudicial(dept_code="11", dept_name="Tribunal Superior de Bogotá", entidad_id="22")
    monkeypatch.setattr(scraper, "_get_instance_id", lambda session, headers: "XYZ")
    monkeypatch.setattr(
        scraper,
        "_fetch_detail",
        lambda headers, url: [
            (
                "11001310302020220015001_DraGonzalezAutoAdmiteRecurso.pdf",
                _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=abc-999",
                "abc-999",
            )
        ],
    )

    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].title == "T_BTA_11001_31_03_020_2022_00150_01"


@responses.activate
def test_scrap_does_not_normalize_title_for_a_source_without_a_tribunal_code(monkeypatch):
    responses.add(
        responses.GET,
        "https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio",
        body=_LISTING_HTML,
        status=200,
    )

    # dept_code="" es como se instancia un Juzgado (ver core/seed.py) — no tiene
    # código de tribunal, así que el título nunca se normaliza.
    scraper = ScrapRamaJudicial(dept_code="", dept_name="Juzgado de Circuito", entidad_id="31")
    monkeypatch.setattr(scraper, "_get_instance_id", lambda session, headers: "XYZ")
    monkeypatch.setattr(
        scraper,
        "_fetch_detail",
        lambda headers, url: [
            (
                "11001310302020220015001_DraGonzalezAutoAdmiteRecurso.pdf",
                _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=abc-999",
                "abc-999",
            )
        ],
    )

    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].title == "11001310302020220015001_DraGonzalezAutoAdmiteRecurso"
```

- [ ] **Step 9: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/families/test_rama_judicial.py -v -k "test_scrap_normalizes_title_for_documents_with_a_23_digit_radicado or test_scrap_does_not_normalize_title_for_a_source_without_a_tribunal_code"`
Expected: FAIL — both assert `docs[0].title == ...` against the normalized/unnormalized form, but `scrap()` still sets `title=name_no_ext` unconditionally (line 322 today), so `test_scrap_normalizes_title_for_documents_with_a_23_digit_radicado` fails (`title` would be `"11001310302020220015001_DraGonzalezAutoAdmiteRecurso"`, not the expected `"T_BTA_..."`). The second test (`does_not_normalize`) passes already since nothing changed yet for it — confirm both ran, and confirm the first fails for exactly this reason before moving on.

- [ ] **Step 10: Wire `_normalize_title` into `scrap()`**

In `core/scrapers/families/rama_judicial.py`, modify the `RawDocModel` construction inside `scrap()` (currently at line 322):

```python
                        docs.append(RawDocModel(
                            source=self.source,
                            link={"url": download_url, "method": "GET", "body": {"path": file_uuid}},
                            title=name_no_ext,
                            tipo=tipo,
                            especialidad=especialidad_raw,
                            seccion=despacho_raw,
                            f_public=fecha_p,
                            save_path=save_path,
                        ))
```

to:

```python
                        docs.append(RawDocModel(
                            source=self.source,
                            link={"url": download_url, "method": "GET", "body": {"path": file_uuid}},
                            title=_normalize_title(name_no_ext, self._dept_code),
                            tipo=tipo,
                            especialidad=especialidad_raw,
                            seccion=despacho_raw,
                            f_public=fecha_p,
                            save_path=save_path,
                        ))
```

Note `save_path` above it is unchanged — it still uses `doc_name` (the sanitized `name_no_ext`), not the normalized title. This is intentional per the spec: this change only affects the `title` metadata field.

- [ ] **Step 11: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/families/test_rama_judicial.py -v`
Expected: all tests in the file pass (the two from Step 8 plus every pre-existing test in this file, since nothing else in `scrap()` changed).

- [ ] **Step 12: Run the full backend test suite**

Run: `.venv\Scripts\pytest -v`
Expected: all pass except the pre-existing, unrelated failure `tests/test_migrations.py::test_alembic_upgrade_head_creates_all_tables` (documented Windows-shell-only issue, see `.claude/skills/run-iurisync/SKILL.md` Gotchas).

- [ ] **Step 13: Commit**

```bash
git add core/scrapers/families/rama_judicial.py tests/families/test_rama_judicial.py
git commit -m "$(cat <<'EOF'
feat: normalize Rama Judicial titles to T_{CODIGO}_{radicado} format

Per docs/superpowers/specs/2026-07-23-rama-judicial-title-normalization-design.md:
when a tribunal-superior document's raw filename starts with its 23-digit
radicado, the title becomes T_{CODIGO}_{radicado segmentado con "_"} (e.g.
T_BTA_11001_31_03_020_2022_00150_01), discarding the judge/action suffix
entirely. Titles that don't match this pattern, or sources without a
tribunal code (Juzgados), are left unchanged.
EOF
)"
```
