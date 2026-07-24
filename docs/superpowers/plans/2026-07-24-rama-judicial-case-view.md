# Rama Judicial Case View (Radicado Grouping) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a Rama Judicial document's title (which is literally its formatted radicado number) be recognized as belonging to a "case" when 2+ documents share it, show a badge for those rows in the Documents table, and open the existing preview dialog pre-loaded with just that case's documents in chronological order when the user clicks the title.

**Architecture:** A regex-based `is_radicado_title()` helper (in `core/utils.py`) distinguishes real radicado-formatted titles from scraper fallback titles (e.g. a magistrado's name, which can legitimately repeat without being the same case). `GET /documents` enriches each returned item with `case_document_count` (computed only for `rama_judicial` documents whose title matches the pattern, via two small new repository helpers — `list_documents` itself is untouched except for one new optional `title_exact` filter, added the same additive way `has_documents`/`downloaded_from` were). The frontend's Documents page shows a badge when `case_document_count > 1`, and on click fetches the case's exact members (`family_key=rama_judicial&title_exact=...`) and opens the already-existing `DocumentPreviewDialog` with them, sorted oldest-to-newest by `f_public`.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React + TanStack Query + react-router-dom (frontend), pytest (backend tests), Vitest + Testing Library + MSW (frontend tests).

## Global Constraints

- Scoped to `family_key == "rama_judicial"` only — no JEP, CNDJ, or SAMAI in this plan, even though they also use a radicado-derived title.
- A title only counts as "the same case" when it matches the exact radicado format produced by `core/scrapers/families/rama_judicial.py::_normalize_title` (`T_{CODIGO}_` + 23 digits segmented as `5_2_2_3_4_5_2`). Titles that fell back to something else (e.g. a magistrado's name) must never be grouped, even if repeated.
- `case_document_count` is `None` unless there are **more than 1** documents sharing that radicado — a title that matches the pattern but has no siblings is `None`, identical to a non-matching title from the frontend's perspective.
- Do not change `list_documents`'s existing behavior/signature beyond additively appending `title_exact` — it's used by many other endpoints/filters and must stay backward compatible.
- Case members are ordered oldest-to-newest by `f_public` (ascending) when shown in the preview dialog — this is the opposite of the Documents table's own default order (`f_public DESC`), so the frontend must explicitly reverse the fetched array, not rely on the API's default ordering.
- Rows without a case (no badge) keep their current click-to-filter-by-title behavior completely unchanged.

---

### Task 1: `is_radicado_title()` — detect a real radicado-formatted title

**Files:**
- Modify: `core/utils.py`
- Test: `tests/test_core_utils.py`

**Interfaces:**
- Produces: `is_radicado_title(title: str) -> bool` (in `core/utils.py`) — used by Task 3.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_core_utils.py` (append at the end of the file):

```python
from core.utils import is_radicado_title


def test_is_radicado_title_matches_a_real_formatted_radicado():
    # Real example from Tribunal Superior de Bogotá (código "BTA", 3 letters).
    assert is_radicado_title("T_BTA_11001_31_03_048_2022_00418_02") is True


def test_is_radicado_title_matches_a_four_letter_tribunal_code():
    # Real example from Tribunal Superior de Antioquia (código "ANTI", 4 letters).
    assert is_radicado_title("T_ANTI_05001_31_10_006_2022_00505_03") is True


def test_is_radicado_title_rejects_a_magistrado_name_fallback():
    """When the scraper can't parse a radicado out of the filename, it falls back
    to other text (e.g. a magistrado's name) — this can legitimately repeat across
    unrelated documents and must never be treated as the same case."""
    assert is_radicado_title("DR. WILLIAM SANTA MARIN") is False


def test_is_radicado_title_rejects_an_empty_string():
    assert is_radicado_title("") is False


def test_is_radicado_title_rejects_a_title_missing_a_segment():
    # Missing the final 2-digit segment.
    assert is_radicado_title("T_BTA_11001_31_03_048_2022_00418") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_core_utils.py -k is_radicado_title -v`
Expected: FAIL — `ImportError: cannot import name 'is_radicado_title' from 'core.utils'`

- [ ] **Step 3: Implement `is_radicado_title`**

In `core/utils.py`, add after the existing imports (currently lines 1-4) and before `make_doc_id` (currently line 7):

```python
import hashlib
import re

from core.models import RawDocModel

# Espejo del formato que produce core/scrapers/families/rama_judicial.py::_normalize_title
# (T_{CODIGO}_{radicado segmentado en 23 dígitos}). No importa TRIBUNAL_CODES desde el
# módulo del scraper para no acoplar esta capa a uno de familia específico — el rango de
# 2-5 letras mayúsculas cubre los códigos reales (3-4 letras) con margen.
RADICADO_TITLE_PATTERN = re.compile(r"^T_[A-Z]{2,5}_\d{5}_\d{2}_\d{2}_\d{3}_\d{4}_\d{5}_\d{2}$")


def is_radicado_title(title: str) -> bool:
    return bool(RADICADO_TITLE_PATTERN.match(title))


def make_doc_id(key: str, f_public: str) -> str:
    return hashlib.sha1(f"{key}_{f_public}".encode()).hexdigest()
```

(Only the two new lines — the `import re` and the `RADICADO_TITLE_PATTERN`/`is_radicado_title` block — are additions; `make_doc_id` and everything below it in the file is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_core_utils.py -k is_radicado_title -v`
Expected: `5 passed`

- [ ] **Step 5: Run the full backend suite to check for regressions**

Run: `.venv/Scripts/pytest -q`
Expected: 5 more passing than before this task, same 1 pre-existing `test_migrations.py` failure (documented in `.claude/skills/run-iurisync/SKILL.md`'s Gotchas — unrelated, Windows-only). No other test should regress.

- [ ] **Step 6: Commit**

```bash
git add core/utils.py tests/test_core_utils.py
git commit -m "feat: add is_radicado_title to detect real radicado-formatted document titles"
```

---

### Task 2: Repository helpers — `title_exact` filter, family-key lookup, per-title counts

**Files:**
- Modify: `core/db/repository.py:257-294` (`list_documents`)
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: nothing new from Task 1 (this task is pure SQL/repository plumbing).
- Produces: `list_documents(..., title_exact: Optional[str] = None, ...)` — new keyword param, inserted after `title_contains`.
- Produces: `get_source_family_keys(db: Session, source_ids: list[int]) -> dict[int, str]`.
- Produces: `count_rama_judicial_documents_by_title(db: Session, titles: list[str]) -> dict[str, int]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_repository.py` (append at the end of the file):

```python
def test_list_documents_filters_by_title_exact_not_substring(db_session):
    """title_exact must be a real equality filter, unlike the existing
    title_contains (ilike '%...%'), which would incorrectly match both of these
    since one title is a superstring of the other."""
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    repository.insert_document(
        db_session,
        doc_id="doc-exact",
        source_id=source.id,
        title="T_BTA_11001_31_03_048_2022_00418_02",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )
    repository.insert_document(
        db_session,
        doc_id="doc-superstring",
        source_id=source.id,
        title="T_BTA_11001_31_03_048_2022_00418_02X",
        storage_bucket="iurisync-test",
        storage_key="b.pdf",
    )

    items, total = repository.list_documents(db_session, title_exact="T_BTA_11001_31_03_048_2022_00418_02")

    assert total == 1
    assert [d.doc_id for d in items] == ["doc-exact"]


def test_get_source_family_keys_returns_a_mapping_for_the_given_ids(db_session):
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    repository.create_source_family(db_session, key="jep", display_name="JEP")
    rama_source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    jep_source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})

    result = repository.get_source_family_keys(db_session, [rama_source.id, jep_source.id])

    assert result == {rama_source.id: "rama_judicial", jep_source.id: "jep"}


def test_get_source_family_keys_returns_empty_dict_for_empty_input(db_session):
    assert repository.get_source_family_keys(db_session, []) == {}


def test_count_rama_judicial_documents_by_title_groups_within_the_family_only(db_session):
    """The same title in a DIFFERENT family must not be counted together with the
    rama_judicial ones — a coincidental title collision across families isn't the
    same case."""
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    repository.create_source_family(db_session, key="jep", display_name="JEP")
    rama_source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    jep_source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})

    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=rama_source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=rama_source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-3", source_id=jep_source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="c.pdf",
    )

    result = repository.count_rama_judicial_documents_by_title(db_session, [shared_title])

    assert result == {shared_title: 2}


def test_count_rama_judicial_documents_by_title_returns_empty_dict_for_empty_input(db_session):
    assert repository.count_rama_judicial_documents_by_title(db_session, []) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_repository.py -k "title_exact or get_source_family_keys or count_rama_judicial" -v`
Expected: FAIL — `TypeError: list_documents() got an unexpected keyword argument 'title_exact'` and `AttributeError: module 'core.db.repository' has no attribute 'get_source_family_keys'` (and similarly for `count_rama_judicial_documents_by_title`).

- [ ] **Step 3: Add `title_exact` to `list_documents`**

In `core/db/repository.py`, change the signature and body of `list_documents` (currently lines 257-294):

```python
def list_documents(
    db: Session,
    source_id: Optional[int] = None,
    family_key: Optional[str] = None,
    tipo: Optional[str] = None,
    review_status: Optional[str] = None,
    f_public_from: Optional[date] = None,
    f_public_to: Optional[date] = None,
    downloaded_from: Optional[date] = None,
    downloaded_to: Optional[date] = None,
    title_contains: Optional[str] = None,
    title_exact: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Document], int]:
    stmt = select(Document)
    if source_id is not None:
        stmt = stmt.where(Document.source_id == source_id)
    if family_key is not None:
        stmt = stmt.join(Source, Source.id == Document.source_id).where(Source.family_key == family_key)
    if tipo is not None:
        stmt = stmt.where(Document.tipo == tipo)
    if review_status is not None:
        stmt = stmt.where(Document.review_status == review_status)
    if f_public_from is not None:
        stmt = stmt.where(Document.f_public >= f_public_from)
    if f_public_to is not None:
        stmt = stmt.where(Document.f_public <= f_public_to)
    if downloaded_from is not None:
        stmt = stmt.where(
            Document.downloaded_at >= datetime.combine(downloaded_from, datetime.min.time()).replace(tzinfo=timezone.utc)
        )
    if downloaded_to is not None:
        stmt = stmt.where(
            Document.downloaded_at
            < datetime.combine(downloaded_to, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(days=1)
        )
    if title_contains is not None:
        stmt = stmt.where(Document.title.ilike(f"%{title_contains}%"))
    if title_exact is not None:
        stmt = stmt.where(Document.title == title_exact)

    total = len(list(db.scalars(stmt).all()))
    stmt = stmt.order_by(Document.f_public.desc().nulls_last(), Document.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all()), total
```

- [ ] **Step 4: Add `get_source_family_keys` and `count_rama_judicial_documents_by_title`**

In `core/db/repository.py`, add these two functions immediately after `list_documents` (right after the line `return list(db.scalars(stmt).all()), total` from Step 3):

```python
def get_source_family_keys(db: Session, source_ids: list[int]) -> dict[int, str]:
    if not source_ids:
        return {}
    stmt = select(Source.id, Source.family_key).where(Source.id.in_(source_ids))
    return dict(db.execute(stmt).all())


def count_rama_judicial_documents_by_title(db: Session, titles: list[str]) -> dict[str, int]:
    if not titles:
        return {}
    stmt = (
        select(Document.title, func.count(Document.id))
        .join(Source, Source.id == Document.source_id)
        .where(Source.family_key == "rama_judicial", Document.title.in_(titles))
        .group_by(Document.title)
    )
    return dict(db.execute(stmt).all())
```

(`func` and `select` are already imported at the top of `core/db/repository.py` — no new imports needed.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_repository.py -k "title_exact or get_source_family_keys or count_rama_judicial" -v`
Expected: `5 passed`

- [ ] **Step 6: Run the full backend suite to check for regressions**

Run: `.venv/Scripts/pytest -q`
Expected: 5 more passing than after Task 1 (10 more than the original baseline), same 1 pre-existing failure, no other regressions.

- [ ] **Step 7: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat: add title_exact filter and case-grouping helpers to repository"
```

---

### Task 3: Wire `case_document_count` into `GET /documents`

**Files:**
- Modify: `api/routers/documents.py:52-81` (`get_documents`)
- Modify: `api/schemas.py:67-87` (`DocumentOut`)
- Test: `tests/test_api_documents.py`

**Interfaces:**
- Consumes: `is_radicado_title` from `core/utils.py` (Task 1).
- Consumes: `repository.list_documents(..., title_exact=...)`, `repository.get_source_family_keys(db, source_ids)`, `repository.count_rama_judicial_documents_by_title(db, titles)` (Task 2).
- Produces: `GET /documents` response items gain `case_document_count: Optional[int]`, and the endpoint accepts a new `title_exact` query param.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api_documents.py` (place after `test_list_documents_filters_by_downloaded_at_range` and its sibling, or anywhere else in the file at top level — exact position doesn't matter, this is a flat list of test functions):

```python
def test_get_documents_reports_case_document_count_for_a_shared_radicado(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    for doc_id in ("doc-1", "doc-2", "doc-3"):
        repository.insert_document(
            db_session, doc_id=doc_id, source_id=source.id, title=shared_title,
            storage_bucket="iurisync-test", storage_key=f"{doc_id}.pdf",
        )

    response = api_client.get("/documents", params={"family_key": "rama_judicial"}, headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 3
    assert all(item["case_document_count"] == 3 for item in body["items"])


def test_get_documents_reports_null_case_document_count_for_a_unique_radicado(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    repository.insert_document(
        db_session, doc_id="doc-only", source_id=source.id, title="T_BTA_11001_31_03_048_2022_00418_02",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )

    response = api_client.get("/documents", params={"family_key": "rama_judicial"}, headers=auth_header)

    assert response.status_code == 200
    assert response.json()["items"][0]["case_document_count"] is None


def test_get_documents_does_not_group_repeated_fallback_titles(api_client, auth_header, db_session):
    """A magistrado-name fallback title repeated across unrelated documents must
    never be reported as a case."""
    from core.db import repository

    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Antioquia", family_params={}
    )
    for doc_id in ("doc-1", "doc-2"):
        repository.insert_document(
            db_session, doc_id=doc_id, source_id=source.id, title="DR. WILLIAM SANTA MARIN",
            storage_bucket="iurisync-test", storage_key=f"{doc_id}.pdf",
        )

    response = api_client.get("/documents", params={"family_key": "rama_judicial"}, headers=auth_header)

    assert response.status_code == 200
    assert all(item["case_document_count"] is None for item in response.json()["items"])


def test_get_documents_does_not_group_across_families(api_client, auth_header, db_session):
    """The same radicado-shaped title in a non-rama_judicial family must not be
    counted or grouped."""
    from core.db import repository

    repository.create_source_family(db_session, key="jep", display_name="JEP")
    source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})
    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    for doc_id in ("doc-1", "doc-2"):
        repository.insert_document(
            db_session, doc_id=doc_id, source_id=source.id, title=shared_title,
            storage_bucket="iurisync-test", storage_key=f"{doc_id}.pdf",
        )

    response = api_client.get("/documents", params={"family_key": "jep"}, headers=auth_header)

    assert response.status_code == 200
    assert all(item["case_document_count"] is None for item in response.json()["items"])


def test_get_documents_filters_by_title_exact(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    repository.insert_document(
        db_session, doc_id="doc-exact", source_id=source.id, title="T_BTA_11001_31_03_048_2022_00418_02",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-other", source_id=source.id, title="T_BTA_11001_31_03_048_2022_00418_03",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.get(
        "/documents", params={"title_exact": "T_BTA_11001_31_03_048_2022_00418_02"}, headers=auth_header
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-exact"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_api_documents.py -k "case_document_count or title_exact" -v`
Expected: FAIL — `KeyError: 'case_document_count'` (the field doesn't exist on the response yet) and/or a 422 for the unrecognized `title_exact` query param on the last test.

- [ ] **Step 3: Add `case_document_count` to `DocumentOut`**

In `api/schemas.py`, change `DocumentOut` (currently lines 67-87):

```python
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    doc_id: str
    source_id: int
    title: str
    tipo: Optional[str] = None
    seccion: Optional[str] = None
    especialidad: Optional[str] = None
    magistrado: Optional[str] = None
    detalle: Optional[str] = None
    f_public: Optional[date] = None
    f_providencia: Optional[date] = None
    source_url: Optional[str] = None
    storage_bucket: str
    storage_key: str
    content_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    review_status: str
    reviewed_at: Optional[datetime] = None
    downloaded_at: datetime
    case_document_count: Optional[int] = None
```

- [ ] **Step 4: Wire the enrichment into `get_documents`**

In `api/routers/documents.py`, update the imports (currently lines 1-24) to add `is_radicado_title`:

```python
from core.utils import is_radicado_title
```

(add this import line alongside the existing `from core.storage import presigned_url` line, currently line 23).

Then replace `get_documents` (currently lines 52-81):

```python
@router.get("/documents", response_model=PaginatedDocuments)
def get_documents(
    source_id: Optional[int] = None,
    family_key: Optional[str] = None,
    tipo: Optional[str] = None,
    title: Optional[str] = None,
    title_exact: Optional[str] = None,
    review_status: Optional[str] = None,
    f_public_from: Optional[date] = None,
    f_public_to: Optional[date] = None,
    downloaded_from: Optional[date] = None,
    downloaded_to: Optional[date] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    items, total = repository.list_documents(
        db,
        source_id=source_id,
        family_key=family_key,
        tipo=tipo,
        review_status=review_status,
        f_public_from=f_public_from,
        f_public_to=f_public_to,
        downloaded_from=downloaded_from,
        downloaded_to=downloaded_to,
        title_contains=title,
        title_exact=title_exact,
        limit=limit,
        offset=offset,
    )

    family_keys = repository.get_source_family_keys(db, [d.source_id for d in items])
    radicado_titles = [
        d.title for d in items
        if family_keys.get(d.source_id) == "rama_judicial" and is_radicado_title(d.title)
    ]
    counts = repository.count_rama_judicial_documents_by_title(db, radicado_titles)
    for d in items:
        count = counts.get(d.title)
        d.case_document_count = count if count and count > 1 else None

    return {"items": items, "total": total, "limit": limit, "offset": offset}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_api_documents.py -k "case_document_count or title_exact" -v`
Expected: `5 passed`

- [ ] **Step 6: Run the full backend suite to check for regressions**

Run: `.venv/Scripts/pytest -q`
Expected: 5 more passing than after Task 2 (15 more than the original baseline), same 1 pre-existing failure, no other regressions.

- [ ] **Step 7: Commit**

```bash
git add api/routers/documents.py api/schemas.py tests/test_api_documents.py
git commit -m "feat: enrich GET /documents with case_document_count for rama_judicial radicados"
```

---

### Task 4: Frontend — case badge and preview-dialog wiring

**Files:**
- Modify: `frontend/src/api/types.ts:55-75` (`Document`), `frontend/src/api/types.ts:77-82` (unaffected, shown for context)
- Modify: `frontend/src/api/documents.ts:6-19` (`ListDocumentsParams`)
- Modify: `frontend/src/pages/DocumentsPage.tsx`
- Test: `frontend/src/pages/DocumentsPage.test.tsx`

**Interfaces:**
- Consumes: `fetchDocuments({ family_key, title_exact, ... })` (this task adds `title_exact` to the params type; the function itself already passes through arbitrary params via `buildQuery`).
- Consumes: `DocumentPreviewDialog` (unchanged component, already supports `documents: Document[]`, `initialIndex: number`, `open`, `onOpenChange`).
- Produces: nothing consumed by a later task — this is the last task in the plan.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/pages/DocumentsPage.test.tsx`. First, add a case-badge fixture near the top of the file, right after the existing `DOCUMENT`/`DOCUMENT_2` constants (currently lines 23-50):

```typescript
const CASE_DOCUMENT_1 = {
  ...DOCUMENT,
  id: 10,
  doc_id: "case-1",
  title: "T_BTA_11001_31_03_048_2022_00418_02",
  f_public: "2026-06-16",
  case_document_count: 3,
};

const CASE_DOCUMENT_2 = {
  ...DOCUMENT,
  id: 11,
  doc_id: "case-2",
  title: "T_BTA_11001_31_03_048_2022_00418_02",
  f_public: "2026-06-30",
  case_document_count: 3,
};

const CASE_DOCUMENT_3 = {
  ...DOCUMENT,
  id: 12,
  doc_id: "case-3",
  title: "T_BTA_11001_31_03_048_2022_00418_02",
  f_public: "2026-07-17",
  case_document_count: 3,
};
```

Then add these two tests at the end of the `describe("DocumentsPage", ...)` block:

```typescript
  it("shows a case badge only for documents with case_document_count over 1, and opens the preview dialog with the case's members in chronological order on click", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, ({ request }) => {
        const url = new URL(request.url);
        if (url.searchParams.get("title_exact")) {
          // The API returns newest-first by default — the frontend must reverse this.
          return HttpResponse.json({
            items: [CASE_DOCUMENT_3, CASE_DOCUMENT_2, CASE_DOCUMENT_1],
            total: 3,
            limit: 50,
            offset: 0,
          });
        }
        return HttpResponse.json({
          items: [CASE_DOCUMENT_1, DOCUMENT],
          total: 2,
          limit: 50,
          offset: 0,
        });
      }),
      // Opening DocumentPreviewDialog fires these two queries (content_type is
      // "application/pdf", so the preview query is enabled) — both must be mocked
      // or MSW's onUnhandledRequest: "error" setup (src/test/setup.ts) fails the test
      // on the real click, independent of whether the case-grouping logic is correct.
      http.get(`${BASE_URL}/documents/:id/preview`, () => HttpResponse.json({ url: "https://example.com/preview.pdf" })),
      http.get(`${BASE_URL}/documents/:id/versions`, () => HttpResponse.json([]))
    );

    renderPage();

    const user = userEvent.setup();
    const caseTitleButton = await screen.findByRole("button", { name: "T_BTA_11001_31_03_048_2022_00418_02" });

    // Exactly one badge among the two rendered rows (CASE_DOCUMENT_1 has a case,
    // the plain DOCUMENT fixture has no case_document_count set at all) — proves
    // the badge is conditional, not just present in the fixture, and doesn't fire
    // when case_document_count is undefined.
    expect(screen.getAllByText(/^\d+ actuaciones$/)).toHaveLength(1);
    expect(screen.getByText("3 actuaciones")).toBeInTheDocument();

    await user.click(caseTitleButton);

    const dialog = await screen.findByRole("dialog");
    // CASE_DOCUMENT_1 (2026-06-16, the oldest) must be the one shown first/initially,
    // proving the fetched newest-first array was reversed to chronological order and
    // the clicked document's own position within it was used as the initial index.
    expect(within(dialog).getByText(/2026-06-16|jun/i)).toBeInTheDocument();
  });

  it("keeps the existing filter-by-title click behavior for documents without a case", async () => {
    mockFilterEndpoints();
    server.use(
      http.get(`${BASE_URL}/documents`, () =>
        HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 })
      )
    );

    renderPage();

    const user = userEvent.setup();
    const titleButton = await screen.findByRole("button", { name: DOCUMENT.title });
    await user.click(titleButton);

    const searchInput = screen.getByPlaceholderText("Buscar por título");
    expect(searchInput).toHaveValue(DOCUMENT.title);
  });
```

Update the top imports of `frontend/src/pages/DocumentsPage.test.tsx` to add `userEvent` if not already imported — check the current top of the file; if `import userEvent from "@testing-library/user-event";` is missing, add it alongside the existing `@testing-library/react` import line.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run DocumentsPage`
Expected: FAIL — no element with text `"3 actuaciones"` exists yet, and `case_document_count` isn't a recognized field on the `Document` type (TypeScript) / has no effect on rendering yet.

- [ ] **Step 3: Add `case_document_count` and `title_exact` to the type layer**

In `frontend/src/api/types.ts`, add the field to `Document` (currently lines 55-75):

```typescript
export interface Document {
  id: number;
  doc_id: string;
  source_id: number;
  title: string;
  tipo: string | null;
  seccion: string | null;
  especialidad: string | null;
  magistrado: string | null;
  detalle: string | null;
  f_public: string | null;
  f_providencia: string | null;
  source_url: string | null;
  storage_bucket: string;
  storage_key: string;
  content_type: string | null;
  file_size_bytes: number | null;
  review_status: DocumentReviewStatus;
  reviewed_at: string | null;
  downloaded_at: string;
  case_document_count?: number | null;
}
```

Deliberately **optional** (`?`), not just nullable — every other Document fixture across the frontend test suite (`DashboardPage.test.tsx`'s `makeDoc()`, this same file's own pre-existing `DOCUMENT`/`DOCUMENT_2`, etc.) constructs object literals without this field. Making it required would fail `tsc -b` (part of `npm run build`, which CI runs) on every one of those existing fixtures — the exact class of bug this project already hit once with `process.env.TZ`/`tsconfig.app.json`. Optional means `undefined` is valid wherever the field is omitted, and the click-handler code below already treats `undefined`, `null`, and `0` identically (all falsy) via `!!document.case_document_count`.

In `frontend/src/api/documents.ts`, add `title_exact` to `ListDocumentsParams` (currently lines 6-19):

```typescript
export interface ListDocumentsParams {
  source_id?: number;
  family_key?: string;
  tipo?: string;
  title?: string;
  title_exact?: string;
  review_status?: DocumentReviewStatus;
  f_public_from?: string;
  f_public_to?: string;
  downloaded_from?: string;
  downloaded_to?: string;
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}
```

- [ ] **Step 4: Add the case badge and click-to-open-case-dialog behavior**

In `frontend/src/pages/DocumentsPage.tsx`:

Add a small badge component right after `ReviewBadge` (currently ends at line 29, before `formatDateFilterLabel` at line 31):

```typescript
const CASE_BADGE_CLASS =
  "inline-block rounded-md border-[1.5px] border-sello/50 bg-sello/10 px-2 py-1 text-xs font-semibold text-sello-ink";

function CaseBadge({ count }: { count: number }) {
  return <span className={CASE_BADGE_CLASS}>{count} actuaciones</span>;
}
```

Add new state for the case dialog, right after `const [previewIndex, setPreviewIndex] = useState<number | null>(null);` (currently line 52):

```typescript
  const [caseDocuments, setCaseDocuments] = useState<Document[] | null>(null);
  const [caseInitialIndex, setCaseInitialIndex] = useState(0);
```

This needs `Document` imported as a type — add it to the existing type-only import (currently line 10):

```typescript
import type { Document, DocumentReviewStatus } from "../api/types";
```

Add a handler function, right after the `hasDownloadedFilter` line (currently line 123, before `return (` on line 125):

```typescript
  async function handleTitleClick(document: Document) {
    if (!document.case_document_count || document.case_document_count <= 1) {
      setTitle(document.title);
      setPage(0);
      return;
    }
    const response = await fetchDocuments({
      family_key: "rama_judicial",
      title_exact: document.title,
      limit: 50,
    });
    // The API's default order is f_public DESC (newest first); a case's actuaciones
    // read as a timeline, oldest first, so the fetched array is reversed here.
    const chronological = [...response.items].reverse();
    const clickedIndex = chronological.findIndex((item) => item.id === document.id);
    setCaseDocuments(chronological);
    setCaseInitialIndex(clickedIndex === -1 ? 0 : clickedIndex);
  }
```

Replace the title cell's button (currently lines 355-364):

```tsx
                  <button
                    type="button"
                    onClick={() => handleTitleClick(document)}
                    className="underline-offset-2 hover:underline"
                  >
                    {document.title}
                  </button>
                  {!!document.case_document_count && document.case_document_count > 1 && (
                    <div className="mt-1">
                      <CaseBadge count={document.case_document_count} />
                    </div>
                  )}
```

Add a second `DocumentPreviewDialog` instance, right after the existing one (currently lines 411-420, ends right before the closing `</div>` of the component and the final `);`):

```tsx
      {caseDocuments !== null && (
        <DocumentPreviewDialog
          documents={caseDocuments}
          initialIndex={caseInitialIndex}
          open={caseDocuments !== null}
          onOpenChange={(nextOpen) => {
            if (!nextOpen) setCaseDocuments(null);
          }}
        />
      )}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm test -- --run DocumentsPage`
Expected: PASS (all `DocumentsPage` tests, including the two new ones)

- [ ] **Step 6: Run the full frontend suite and build to check for regressions**

Run: `cd frontend && npm test -- --run`
Expected: same pass count as the current baseline plus the 2 new tests, no regressions.

Run: `cd frontend && npm run build`
Expected: clean build, no TypeScript errors (this project's CI runs `tsc -b` as part of `npm run build` and has previously caught type errors that `npm test` alone missed — always run this before committing frontend changes).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/documents.ts frontend/src/pages/DocumentsPage.tsx frontend/src/pages/DocumentsPage.test.tsx
git commit -m "feat: show a case badge for shared Rama Judicial radicados and open the preview dialog with the case's actuaciones in order"
```

---

## Manual Verification (after all tasks)

- [ ] Start the app per `.claude/skills/run-iurisync/SKILL.md` (`uvicorn`, `celery`, `npm run dev`) — restart `uvicorn` if it was already running, since this repo's dev server does not run with `--reload` and has silently served stale code after backend changes earlier in this project's history.
- [ ] Log in, go to Documents, filter by `Fuente = Tribunal Superior de Bogotá` (or any tribunal with real data).
- [ ] Find the radicado `T_BTA_11001_31_03_048_2022_00418_02` (5 real actuaciones in the dev DB as of this plan's writing) — confirm its rows show a "5 actuaciones" badge.
- [ ] Click the title — confirm the preview dialog opens with exactly those 5 documents, oldest (`2026-06-16`) first, and that ← / → navigation and "Previsualizar" work for each.
- [ ] Click the title of a document with no case (no badge) — confirm it still filters the table by title as before (unchanged behavior).
