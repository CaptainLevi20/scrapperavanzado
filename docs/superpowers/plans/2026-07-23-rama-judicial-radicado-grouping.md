# Rama Judicial Detalle Extraction and Radicado Grouping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate `RawDocModel.detalle` with a readable action description (judge name stripped, CamelCase split into words) for Rama Judicial documents whose filename starts with the 23-digit radicado, and make the Documents page's title cell clickable so a click filters the table to only documents sharing that exact title (a de-facto "same radicado" view), reusing the existing title search filter.

**Architecture:** Backend: a new pure function `_extract_detalle` in `core/scrapers/families/rama_judicial.py`, wired into `scrap()` the same way `_normalize_title` already is. Frontend: the existing title `<td>` in `DocumentsPage.tsx` becomes a clickable button that calls the existing `setTitle`/`setPage` state setters with the row's exact title. No schema, API, or ordering changes in either part — `detalle` is already a column/schema/type field end-to-end (`core/db/models.py:108`, `api/schemas.py:77`, `frontend/src/api/types.ts:64`), and the title filter already performs a substring (`ilike`) search server-side.

**Tech Stack:** Backend: Python, `re`, `pytest` (same patterns as `tests/families/test_rama_judicial.py`). Frontend: React, `vitest` + `@testing-library/react` + `msw` (same patterns as `frontend/src/pages/DocumentsPage.test.tsx`).

## Global Constraints

- `_extract_detalle` uses the exact same trigger condition as `_normalize_title`: filename starts with `^\d{23}_` (23 digits then underscore). If it doesn't match, return `None` — same as `_normalize_title` returns the filename unchanged when it doesn't match.
- When the text after the radicado starts with `Dr` or `Dra` followed by a capitalized word (the judge's surname), that whole `Dr{Surname}`/`Dra{Surname}` portion is discarded — it must never appear in `detalle`.
- Whatever remains (or the whole suffix, if there was no `Dr`/`Dra` prefix — this happens in real data) is split into space-separated words: insert a space before every uppercase letter that immediately follows a lowercase letter, and treat `_` as a word separator too (replace with space).
- No spelling correction, no filling in missing words — pass typos and irregularities through exactly as the source has them.
- `detalle` stays `None` whenever the filename doesn't match the 23-digit trigger (person-name titles, generic "ESTADO..." notices) — identical scope to `_normalize_title`.
- The frontend click-to-filter behavior must reuse the existing `title` state/`setTitle`/`setPage` (`frontend/src/pages/DocumentsPage.tsx`) and the existing `fetchDocuments({ title, ... })` call — no new API endpoint, no new query param.
- Do not implement nested/expandable visual grouping in the table — out of scope per the design doc, explicitly replaced by the click-to-filter approach.

---

### Task 1: `_extract_detalle` in the scraper

**Files:**
- Modify: `core/scrapers/families/rama_judicial.py`
- Test: `tests/families/test_rama_judicial.py`

**Interfaces:**
- Consumes: nothing new (uses the same `name_no_ext` string already passed to `_normalize_title` inside `scrap()`).
- Produces: `_extract_detalle(name_no_ext: str) -> Optional[str]` (module-level function, importable from `core.scrapers.families.rama_judicial`).

- [ ] **Step 1: Write the failing tests**

Add `Optional` to the `typing` import at the top of `core/scrapers/families/rama_judicial.py` (currently `from typing import List` at line 3) — change it to:

```python
from typing import List, Optional
```

Add `_extract_detalle` to the import block at the top of `tests/families/test_rama_judicial.py`:

```python
from core.scrapers.families.rama_judicial import (
    JUZGADOS_ENTIDADES,
    SUPERIORES_DEPTS,
    TRIBUNAL_CODES,
    ScrapRamaJudicial,
    _extract_detalle,
    _normalize_title,
)
```

Then add these test functions anywhere after the existing `_normalize_title` tests:

```python
def test_extract_detalle_strips_judge_prefix_and_splits_camel_case():
    assert _extract_detalle("11001310302020220015001_DraGonzalezAutoAdmiteRecurso") == (
        "Auto Admite Recurso"
    )


def test_extract_detalle_splits_the_whole_suffix_when_there_is_no_judge_prefix():
    # caso real: el despacho subió el archivo sin "Dr"/"Dra" antes del apellido
    assert _extract_detalle("11001310303320170034203_ValenzuelaSentenciaSegundaInstancia") == (
        "Valenzuela Sentencia Segunda Instancia"
    )


def test_extract_detalle_treats_underscore_as_a_word_boundary():
    assert _extract_detalle("11001310301620170055608_DrAtshanAutoOrdenaRemitir_Cumplase") == (
        "Auto Ordena Remitir Cumplase"
    )


def test_extract_detalle_tolerates_a_stray_space_after_the_radicado():
    # caso real: espacio extra antes de "Dr"
    assert _extract_detalle("11001310300220230031101_ DrZamudioAutoResuelevApelacion") == (
        "Auto Resuelev Apelacion"
    )


def test_extract_detalle_returns_none_for_person_name_titles():
    assert _extract_detalle("033-2025-00417-01 PAOLA ANDREA NARANJO QUINTANA") is None


def test_extract_detalle_returns_none_for_generic_estado_titles():
    assert _extract_detalle("ESTADO E-0109 DEL 26 DE JUNIO DE 2026") is None


def test_extract_detalle_returns_none_when_digit_prefix_is_not_23_long():
    assert _extract_detalle("1234567890123456789012_DraGonzalezAutoAdmiteRecurso") is None  # 22 dígitos
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/families/test_rama_judicial.py -v -k extract_detalle`
Expected: FAIL with `ImportError: cannot import name '_extract_detalle'` (the import at the top of the test file fails before any test body runs).

- [ ] **Step 3: Implement `_extract_detalle`**

In `core/scrapers/families/rama_judicial.py`, add this directly after `_normalize_title` (which itself was added after `TRIBUNAL_CODES` in the previous plan):

```python
_JUEZ_PREFIX = re.compile(r"^\s*(Dr|Dra)[A-ZÁÉÍÓÚÑ][a-záéíóúñ]*")
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-záéíóúñ])(?=[A-ZÁÉÍÓÚÑ])")


def _extract_detalle(name_no_ext: str) -> Optional[str]:
    """Extrae una descripción legible de la acción (sin el juez) cuando el
    nombre de archivo empieza con el radicado completo (23 dígitos). El
    apellido del juez (prefijo "Dr"/"Dra") se descarta por completo; el resto
    se separa en palabras por límites de CamelCase y guiones bajos. Si no hay
    prefijo "Dr"/"Dra" (pasa en datos reales), se separa el resto completo tal
    cual. Devuelve None cuando el nombre no calza con el patrón de radicado."""
    match = _RADICADO_PREFIX.match(name_no_ext)
    if not match:
        return None

    resto = name_no_ext[match.end():]
    resto = _JUEZ_PREFIX.sub("", resto, count=1)
    resto = resto.replace("_", " ")
    return _CAMEL_CASE_BOUNDARY.sub(" ", resto).strip()
```

This reuses `_RADICADO_PREFIX` (the compiled regex `^(\d{23})_`, already defined for `_normalize_title` in the previous plan) to find where the radicado ends.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/families/test_rama_judicial.py -v -k extract_detalle`
Expected: 7 passed.

- [ ] **Step 5: Write the failing end-to-end test wiring `_extract_detalle` into `scrap()`**

Add this test to `tests/families/test_rama_judicial.py`, after `test_scrap_normalizes_title_for_documents_with_a_23_digit_radicado` (added by the previous plan):

```python
@responses.activate
def test_scrap_populates_detalle_for_documents_with_a_23_digit_radicado(monkeypatch):
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
    assert docs[0].detalle == "Auto Admite Recurso"


@responses.activate
def test_scrap_leaves_detalle_none_for_a_non_matching_title(monkeypatch):
    responses.add(
        responses.GET,
        "https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio",
        body=_LISTING_HTML,
        status=200,
    )

    scraper = ScrapRamaJudicial(dept_code="05", dept_name="Tribunal Superior de Antioquia", entidad_id="22")
    monkeypatch.setattr(scraper, "_get_instance_id", lambda session, headers: "XYZ")
    monkeypatch.setattr(
        scraper,
        "_fetch_detail",
        lambda headers, url: [("Auto_2024.pdf", _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=abc-123", "abc-123")],
    )

    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].detalle is None
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/families/test_rama_judicial.py -v -k "test_scrap_populates_detalle_for_documents_with_a_23_digit_radicado or test_scrap_leaves_detalle_none_for_a_non_matching_title"`
Expected: `test_scrap_populates_detalle_for_documents_with_a_23_digit_radicado` FAILS (`docs[0].detalle` is `None` today, `scrap()` never passes `detalle=` to `RawDocModel` at all). `test_scrap_leaves_detalle_none_for_a_non_matching_title` passes already (nothing to fix for that path) — confirm both ran and confirm the first fails for exactly this reason.

- [ ] **Step 7: Wire `_extract_detalle` into `scrap()`**

In `core/scrapers/families/rama_judicial.py`, find the `RawDocModel` construction inside `scrap()` (added to by the previous plan — it currently has `title=_normalize_title(name_no_ext, self._dept_code)`):

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

Add a `detalle=` line:

```python
                        docs.append(RawDocModel(
                            source=self.source,
                            link={"url": download_url, "method": "GET", "body": {"path": file_uuid}},
                            title=_normalize_title(name_no_ext, self._dept_code),
                            tipo=tipo,
                            especialidad=especialidad_raw,
                            seccion=despacho_raw,
                            f_public=fecha_p,
                            detalle=_extract_detalle(name_no_ext),
                            save_path=save_path,
                        ))
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/families/test_rama_judicial.py -v`
Expected: all tests in the file pass (21 total: 12 pre-existing from the previous two plans + 9 new from this task).

- [ ] **Step 9: Run the full backend test suite**

Run: `.venv\Scripts\pytest -v`
Expected: all pass except the pre-existing, unrelated failure `tests/test_migrations.py::test_alembic_upgrade_head_creates_all_tables`.

- [ ] **Step 10: Commit**

```bash
git add core/scrapers/families/rama_judicial.py tests/families/test_rama_judicial.py
git commit -m "$(cat <<'EOF'
feat: extract readable action detail for Rama Judicial documents

Per docs/superpowers/specs/2026-07-23-rama-judicial-radicado-grouping-design.md:
when a tribunal-superior document's filename starts with its 23-digit
radicado, detalle is now populated with the action description (judge name
stripped, CamelCase split into words), e.g. "Auto Admite Recurso". Titles
that don't match the radicado pattern leave detalle as None, same as today.
EOF
)"
```

---

### Task 2: Clickable title cell in the Documents page

**Files:**
- Modify: `frontend/src/pages/DocumentsPage.tsx`
- Test: `frontend/src/pages/DocumentsPage.test.tsx`

**Interfaces:**
- Consumes: existing `title`/`setTitle` state (`frontend/src/pages/DocumentsPage.tsx:39`), existing `page`/`setPage` state, existing `document.title` field (already typed as `string` on `Document` in `frontend/src/api/types.ts`).
- Produces: no new exported interface — this is a self-contained UI behavior change within `DocumentsPage`.

- [ ] **Step 1: Write the failing test**

Add this test to `frontend/src/pages/DocumentsPage.test.tsx`, after the existing `"refetches with the source filter applied"` test (around line 267 today):

```tsx
  it("clicking a document's title filters the table to that exact title", async () => {
    mockFilterEndpoints();
    let lastUrl = "";
    server.use(
      http.get(`${BASE_URL}/documents`, ({ request }) => {
        lastUrl = request.url;
        return HttpResponse.json({ items: [DOCUMENT, DOCUMENT_2], total: 2, limit: 50, offset: 0 });
      })
    );
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Sentencia C-001-26");
    await user.click(screen.getByText("Sentencia C-001-26"));

    await waitFor(() =>
      expect(lastUrl).toContain(`title=${encodeURIComponent("Sentencia C-001-26")}`)
    );
    expect(screen.getByPlaceholderText("Buscar por título")).toHaveValue("Sentencia C-001-26");
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run -t "clicking a document's title filters"`
Expected: FAIL — the title cell today (`frontend/src/pages/DocumentsPage.tsx:286`) is a plain `<td>` with no click handler, so `user.click(...)` on the text does nothing and `lastUrl` never picks up a `title=` param; `waitFor` times out.

- [ ] **Step 3: Make the title cell clickable**

In `frontend/src/pages/DocumentsPage.tsx`, find the title cell inside the table body (currently):

```tsx
                <td className={`${TD} font-medium whitespace-nowrap text-foreground`} title={document.detalle ?? undefined}>
                  {document.title}
                </td>
```

Replace it with:

```tsx
                <td className={`${TD} font-medium whitespace-nowrap text-foreground`} title={document.detalle ?? undefined}>
                  <button
                    type="button"
                    onClick={() => {
                      setTitle(document.title);
                      setPage(0);
                    }}
                    className="underline-offset-2 hover:underline"
                  >
                    {document.title}
                  </button>
                </td>
```

`setTitle` and `setPage` are already in scope — they're the same state setters the "Buscar por título" input and the other filters already use (`frontend/src/pages/DocumentsPage.tsx:39` and `:46`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run -t "clicking a document's title filters"`
Expected: PASS.

- [ ] **Step 5: Run the full frontend test suite**

Run: `cd frontend && npm test -- --run`
Expected: all tests pass (including every other pre-existing `DocumentsPage.test.tsx` test — the only change is wrapping the title text in a `<button>`, which doesn't change what text is rendered or how other assertions locate it via `getByText`).

- [ ] **Step 6: Run the TypeScript build check**

Run: `cd frontend && npx tsc -b`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/DocumentsPage.tsx frontend/src/pages/DocumentsPage.test.tsx
git commit -m "$(cat <<'EOF'
feat: make document title clickable to filter by exact title

Per docs/superpowers/specs/2026-07-23-rama-judicial-radicado-grouping-design.md:
clicking a document's title in the Documents table now fills the existing
title search filter with that exact title and resets to page 0 — a
zero-schema-change way to see every document sharing a Rama Judicial
radicado (title collisions are otherwise invisible across pages, since the
table is ordered by publication date, not title).
EOF
)"
```
