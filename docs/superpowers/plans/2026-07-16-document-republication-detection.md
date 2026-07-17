# Detección de republicación de documentos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a run re-scrapes a document that already exists (same `doc_id`), instead of always skipping it, compare its remote file size against what's stored — if it changed (the source republished it with added content), download the new version, archive the old one without losing it, and reset its review status.

**Architecture:** A cheap `HEAD` request checks `Content-Length` against the stored `file_size_bytes` for documents whose family opts in (`checks_for_republication`). A mismatch (or an inconclusive `HEAD`) triggers a real download; if the downloaded file's actual size differs, the old file's location is archived into a new `document_versions` table (by reference — it is never re-uploaded or moved) and the `documents` row is updated to point at the newly uploaded file under a distinct storage key.

**Tech Stack:** Same as the rest of the backend (FastAPI + SQLAlchemy + Alembic + Celery + `requests`) and frontend (React + TanStack Query). No new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-16-document-republication-detection-design.md` — follow it exactly.
- Applies to exactly 8 families with a direct GET download URL: `constitucional`, `jep`, `adr`, `adres`, `ane`, `anh`, `cndj`, `rama_judicial`. `corte_suprema` and `samai` explicitly opt out (`checks_for_republication = False`) — their download mechanisms (POST body, JWT-indirect) have no cheap direct URL to `HEAD`.
- The verification happens automatically inside the existing run flow (`scrape_source_task`) — no new scheduled job, no new manual trigger endpoint.
- The old file is **never re-uploaded, moved, or deleted** — the archived `document_versions` row simply keeps pointing at the bucket/key the file already lives at. Only the newly downloaded file gets uploaded, under a **distinct** storage key so it never overwrites the archived one.
- When a document is replaced, `review_status` resets to `"pending"` and `reviewed_at` to `NULL`.
- A document whose real downloaded size turns out to match the stored size after all (the `HEAD` was inconclusive but nothing actually changed) is discarded without creating a version or touching the document row.
- Backend tests hit a real local Postgres (via `db_session`/`test_engine`) and use the `responses` library to mock HTTP (matching `tests/test_downloader.py` and `tests/test_tasks.py` conventions) — no bare unittest.mock of `requests`.

---

## Task 1: `DocumentVersion` model, migration, and repository functions

**Files:**
- Modify: `core/db/models.py` (add `DocumentVersion` class after `Document`; add `docs_updated` to `RunSource`)
- Create: `alembic/versions/<generated>_add_document_versions.py`
- Modify: `core/db/repository.py` (add functions after `insert_document`; import `DocumentVersion`)
- Test: `tests/test_repository.py`

**Interfaces:**
- Produces (consumed by Task 4 and Task 5):
  - `core.db.models.DocumentVersion` — columns `id`, `document_id`, `storage_bucket`, `storage_key`, `content_type`, `file_extension`, `file_size_bytes`, `converted_format`, `source_url`, `downloaded_at`, `superseded_at`.
  - `RunSource.docs_updated` (Integer, default 0).
  - `repository.get_document_by_doc_id(db: Session, doc_id: str) -> Optional[Document]`
  - `repository.archive_and_replace_document(db: Session, document_id: int, **new_fields) -> Document`
  - `repository.list_document_versions(db: Session, document_id: int) -> list[DocumentVersion]`
  - `repository.get_document_version(db: Session, version_id: int) -> Optional[DocumentVersion]`

- [ ] **Step 1: Add the `DocumentVersion` model and the `docs_updated` column**

In `core/db/models.py`, add `docs_updated` to the existing `RunSource` class:

```python
class RunSource(Base):
    __tablename__ = "run_sources"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    status = Column(String, nullable=False, default="pending")
    docs_new = Column(Integer, nullable=False, default=0)
    docs_updated = Column(Integer, nullable=False, default=0)
    docs_errors = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
```

Add `DocumentVersion` immediately after the `Document` class:

```python
class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    storage_bucket = Column(String, nullable=False)
    storage_key = Column(Text, nullable=False)
    content_type = Column(String, nullable=True)
    file_extension = Column(String, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    converted_format = Column(String, nullable=True)
    source_url = Column(Text, nullable=True)
    downloaded_at = Column(DateTime(timezone=True), nullable=False)
    superseded_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
```

- [ ] **Step 2: Write the failing repository tests**

Add to `tests/test_repository.py`:

```python
def test_get_document_by_doc_id_returns_none_when_missing(db_session):
    assert repository.get_document_by_doc_id(db_session, "does-not-exist") is None


def test_archive_and_replace_document_snapshots_old_file_and_updates_with_new(db_session):
    from datetime import datetime, timezone

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    original_downloaded_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    document = repository.insert_document(
        db_session,
        doc_id="doc-republished",
        source_id=source.id,
        title="A. 829/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-01/Auto/A.829-26.rtf",
        content_type="application/rtf",
        file_size_bytes=76245,
        source_url="https://www.corteconstitucional.gov.co/sentencias/Autos/2026/A829-26.rtf",
        review_status="useful",
        downloaded_at=original_downloaded_at,
    )
    assert repository.get_document_by_doc_id(db_session, "doc-republished").id == document.id

    updated = repository.archive_and_replace_document(
        db_session,
        document.id,
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-01/Auto/A.829-26-republicado-20260716T120000.rtf",
        content_type="application/rtf",
        file_extension=".rtf",
        file_size_bytes=98000,
        converted_format=None,
    )

    assert updated.storage_key == "Corte Constitucional/2026-06-01/Auto/A.829-26-republicado-20260716T120000.rtf"
    assert updated.file_size_bytes == 98000
    assert updated.review_status == "pending"
    assert updated.reviewed_at is None

    [version] = repository.list_document_versions(db_session, document.id)
    assert version.storage_key == "Corte Constitucional/2026-06-01/Auto/A.829-26.rtf"
    assert version.file_size_bytes == 76245
    assert version.downloaded_at == original_downloaded_at


def test_list_document_versions_orders_most_recently_superseded_first(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-multi-version",
        source_id=source.id,
        title="A. 900/26",
        storage_bucket="iurisync-test",
        storage_key="v1.rtf",
        file_size_bytes=100,
    )
    repository.archive_and_replace_document(
        db_session, document.id, storage_bucket="iurisync-test", storage_key="v2.rtf", file_size_bytes=200
    )
    repository.archive_and_replace_document(
        db_session, document.id, storage_bucket="iurisync-test", storage_key="v3.rtf", file_size_bytes=300
    )

    versions = repository.list_document_versions(db_session, document.id)

    assert [v.storage_key for v in versions] == ["v2.rtf", "v1.rtf"]
    assert repository.get_document_version(db_session, versions[0].id).id == versions[0].id
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_repository.py -k "doc_by_doc_id or archive_and_replace or list_document_versions" -v`
Expected: FAIL — `AttributeError: module 'core.db.repository' has no attribute 'get_document_by_doc_id'`

- [ ] **Step 4: Generate the Alembic migration**

Run: `.venv/Scripts/alembic revision -m "add document versions"`

Open the generated file (`down_revision` should already point at `465c6f3e4a45`, the current head) and replace the body:

```python
def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('run_sources', sa.Column('docs_updated', sa.Integer(), nullable=False, server_default='0'))
    op.create_table(
        'document_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('storage_bucket', sa.String(), nullable=False),
        sa.Column('storage_key', sa.Text(), nullable=False),
        sa.Column('content_type', sa.String(), nullable=True),
        sa.Column('file_extension', sa.String(), nullable=True),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('converted_format', sa.String(), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('downloaded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('document_versions')
    op.drop_column('run_sources', 'docs_updated')
```

- [ ] **Step 5: Add the repository functions**

In `core/db/repository.py`, update the model import at the top:

```python
from core.db.models import BulkDownload, Document, DocumentVersion, Run, RunError, RunSource, Source, SourceFamily, User, UserSession
```

Add these functions right after `insert_document` (before `list_distinct_document_tipos`):

```python
def get_document_by_doc_id(db: Session, doc_id: str) -> Optional[Document]:
    return db.scalars(select(Document).where(Document.doc_id == doc_id)).first()


def archive_and_replace_document(db: Session, document_id: int, **new_fields) -> Document:
    document = db.get(Document, document_id)
    version = DocumentVersion(
        document_id=document.id,
        storage_bucket=document.storage_bucket,
        storage_key=document.storage_key,
        content_type=document.content_type,
        file_extension=document.file_extension,
        file_size_bytes=document.file_size_bytes,
        converted_format=document.converted_format,
        source_url=document.source_url,
        downloaded_at=document.downloaded_at,
    )
    db.add(version)
    for key, value in new_fields.items():
        setattr(document, key, value)
    document.review_status = "pending"
    document.reviewed_at = None
    db.commit()
    db.refresh(document)
    return document


def list_document_versions(db: Session, document_id: int) -> list[DocumentVersion]:
    stmt = (
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.superseded_at.desc())
    )
    return list(db.scalars(stmt).all())


def get_document_version(db: Session, version_id: int) -> Optional[DocumentVersion]:
    return db.get(DocumentVersion, version_id)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_repository.py -v`
Expected: all PASS, including the three new tests.

- [ ] **Step 7: Commit**

```bash
git add core/db/models.py core/db/repository.py alembic/versions/*_add_document_versions.py tests/test_repository.py
git commit -m "feat: add DocumentVersion model and repository functions"
```

---

## Task 2: `check_remote_content_length` helper

**Files:**
- Modify: `core/downloader.py` (add `Optional` import, add the function near the top-level helpers)
- Test: `tests/test_downloader.py`

**Interfaces:**
- Produces (consumed by Task 4): `core.downloader.check_remote_content_length(url: str, timeout: int = 15) -> Optional[int]`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_downloader.py` (near the top, after the imports and `_doc` helper, or anywhere in the file — it's a standalone function, not a `Downloader` method):

```python
from core.downloader import check_remote_content_length


@responses.activate
def test_check_remote_content_length_returns_the_header_value():
    responses.add(responses.HEAD, "https://example.com/file.rtf", headers={"Content-Length": "76245"}, status=200)

    assert check_remote_content_length("https://example.com/file.rtf") == 76245


@responses.activate
def test_check_remote_content_length_returns_none_when_header_is_missing():
    responses.add(responses.HEAD, "https://example.com/file.rtf", status=200)

    assert check_remote_content_length("https://example.com/file.rtf") is None


@responses.activate
def test_check_remote_content_length_returns_none_on_non_200_status():
    responses.add(responses.HEAD, "https://example.com/file.rtf", status=404)

    assert check_remote_content_length("https://example.com/file.rtf") is None


@responses.activate
def test_check_remote_content_length_returns_none_on_request_exception():
    def _callback(request):
        raise requests.exceptions.ConnectionError("conexión rechazada")

    responses.add_callback(responses.HEAD, "https://example.com/file.rtf", callback=_callback)

    assert check_remote_content_length("https://example.com/file.rtf") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_downloader.py -k check_remote_content_length -v`
Expected: FAIL — `ImportError: cannot import name 'check_remote_content_length' from 'core.downloader'`

- [ ] **Step 3: Implement the function**

In `core/downloader.py`, add `Optional` to the typing import:

```python
from typing import Optional
```

(add this import line near the top, alongside the existing `from dataclasses import dataclass` / `from pathlib import Path` lines)

Add the function right after the module-level constants (`_WORD_FORMATS`, `_SOFFICE_FALLBACK_PATHS`), before `_find_soffice`:

```python
def check_remote_content_length(url: str, timeout: int = 15) -> Optional[int]:
    """HEAD barato para saber si el archivo remoto cambió de tamaño sin descargarlo
    completo. Devuelve None si el servidor no expone Content-Length, responde con un
    status distinto de 200, o la petición falla — el llamador debe entonces caer a
    descargar y comparar el tamaño real."""
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    except requests.exceptions.RequestException:
        return None
    if response.status_code != 200:
        return None
    content_length = response.headers.get("Content-Length")
    return int(content_length) if content_length is not None else None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_downloader.py -v`
Expected: all PASS, including the four new tests.

- [ ] **Step 5: Commit**

```bash
git add core/downloader.py tests/test_downloader.py
git commit -m "feat: add check_remote_content_length helper"
```

---

## Task 3: `checks_for_republication` flag

**Files:**
- Modify: `core/scrapers/base.py`
- Modify: `core/scrapers/families/corte_suprema.py`
- Modify: `core/scrapers/families/samai.py`
- Test: `tests/families/test_corte_suprema.py`, `tests/families/test_samai.py`

**Interfaces:**
- Produces (consumed by Task 4): `BaseScrapper.checks_for_republication: bool` (default `True`), overridden to `False` on `ScrapCorteSuprema` and `ScrapTribunales`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/families/test_corte_suprema.py`:

```python
def test_corte_suprema_does_not_check_for_republication():
    # CSJ's download is a POST to a shared endpoint (no direct file URL), so there's
    # nothing cheap to HEAD — republication checking is out of scope for this family.
    assert ScrapCorteSuprema().checks_for_republication is False
```

Add to `tests/families/test_samai.py` (`ScrapTribunales` is already imported at the top of this file, via `from core.scrapers.families.samai import ScrapTribunales, SAMAI_CORPS`; its constructor takes `(corp_code: str, corp_name: str)`):

```python
def test_samai_does_not_check_for_republication():
    # SAMAI's download goes through an indirect JWT hop (no direct file URL), so
    # there's nothing cheap to HEAD — republication checking is out of scope.
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    assert scraper.checks_for_republication is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/families/test_corte_suprema.py tests/families/test_samai.py -k republication -v`
Expected: FAIL — `AttributeError: 'ScrapCorteSuprema' object has no attribute 'checks_for_republication'`

- [ ] **Step 3: Add the flag**

In `core/scrapers/base.py`, add alongside `filters_by_publication_date`:

```python
class BaseScrapper:
    source = None

    # Whether fini/ffin (the run's requested date range) are matched against the
    # document's publication date (f_public) rather than its providencia date
    # (f_providencia). Most sources' own search APIs only support filtering by
    # providencia date, so that's the default; a family overrides this only when
    # it can genuinely filter (or, like JEP, precisely re-filter client-side)
    # by publication date instead.
    filters_by_publication_date = False

    # Whether a document that already exists (same doc_id) should still be
    # re-checked for a republication (the source replaced the same file at the
    # same URL with a bigger/different one) via a cheap HEAD request. True by
    # default since most families expose a direct GET file URL; a family opts
    # out when its download mechanism has no cheap direct URL to check (e.g. a
    # shared POST endpoint, or an indirect JWT hop).
    checks_for_republication = True

    def scrap(self, fini, ffin, q="", limit=100, stop_event=None, on_progress=None):
        raise NotImplementedError("Subclasses must implement this method.")
```

In `core/scrapers/families/corte_suprema.py`, inside `ScrapCorteSuprema` (after the class line, alongside `__init__`):

```python
@register_family("corte_suprema")
class ScrapCorteSuprema(BaseScrapper):
    # CSJ's download is a POST to a shared endpoint with a body param, not a direct
    # file URL — there's nothing cheap to HEAD, so republication checking is out of
    # scope for this family (see tests/families/test_corte_suprema.py).
    checks_for_republication = False

    def __init__(self):
        ...
```

In `core/scrapers/families/samai.py`, inside `ScrapTribunales`:

```python
@register_family("samai")
class ScrapTribunales(BaseScrapper):
    source = "Tribunales Administrativos"
    # SAMAI's download goes through an indirect JWT hop, not a direct file URL —
    # there's nothing cheap to HEAD, so republication checking is out of scope for
    # this family (see tests/families/test_samai.py).
    checks_for_republication = False

    def __init__(self, corp_code: str, corp_name: str):
        ...
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/families/test_corte_suprema.py tests/families/test_samai.py -v`
Expected: all PASS.

Run the full families test suite to confirm no regression: `.venv/Scripts/pytest tests/families/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/base.py core/scrapers/families/corte_suprema.py core/scrapers/families/samai.py tests/families/test_corte_suprema.py tests/families/test_samai.py
git commit -m "feat: add checks_for_republication flag, opt out CSJ and SAMAI"
```

---

## Task 4: `scrape_source_task` — detect and apply republications

**Files:**
- Modify: `worker/tasks.py`
- Test: `tests/test_tasks.py`

**Interfaces:**
- Consumes: `repository.get_document_by_doc_id`, `repository.archive_and_replace_document` (Task 1); `core.downloader.check_remote_content_length` (Task 2); `scraper.checks_for_republication` (Task 3).
- Produces: `worker.tasks._versioned_replacement_key(original_key: str) -> str` (module-private, but Task 4's own tests exercise it indirectly through `scrape_source_task`); `scrape_source_task` now also passes `docs_updated` to `set_run_source_status`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_tasks.py`, near the other `scrape_source_task` tests:

```python
@responses.activate
def test_scrape_source_task_replaces_a_republished_document_and_archives_the_old_one(db_session, test_engine, monkeypatch):
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    existing_doc = repository.insert_document(
        db_session,
        doc_id="56fdae9f954347fcfb9cbdd8d9c98acfbe36ce66",
        source_id=source.id,
        title="Documento 1",
        storage_bucket="iurisync-test",
        storage_key="old-key.pdf",
        content_type="application/pdf",
        file_size_bytes=9,  # tamaño de "contenido" (el body del test original)
        source_url="https://example.com/doc1",
        review_status="useful",
    )

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/doc1", "method": "GET"},
            title="Documento 1",
            tipo="Auto",
            f_public="2026-01-01",
        )
    ]
    # "56fdae9f954347fcfb9cbdd8d9c98acfbe36ce66" es make_doc_id("https://example.com/doc1", "2026-01-01")
    # (verificado directamente), el mismo valor que produce compute_doc_id(doc) para
    # este RawDocModel — por eso existing_doc puede insertarse con ese doc_id fijo de
    # antemano y el bucle de scrape_source_task lo reconoce como el mismo documento.
    responses.add(responses.HEAD, "https://example.com/doc1", headers={"Content-Length": "20"}, status=200)
    responses.add(
        responses.GET,
        "https://example.com/doc1",
        body=b"contenido mas largo!",  # 20 bytes, distinto de los 9 originales
        headers={"Content-Type": "application/pdf"},
        status=200,
    )

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    scrape_source_task(run_source.id)

    assertion_session = task_session_factory()
    try:
        [refreshed_source] = repository.list_run_sources(assertion_session, run.id)
        assert refreshed_source.status == "completed"
        assert refreshed_source.docs_new == 0
        assert refreshed_source.docs_updated == 1
        assert refreshed_source.docs_errors == 0

        updated_document = repository.get_document(assertion_session, existing_doc.id)
        assert updated_document.file_size_bytes == 20
        assert updated_document.storage_key != "old-key.pdf"
        assert updated_document.review_status == "pending"
        assert updated_document.reviewed_at is None

        [version] = repository.list_document_versions(assertion_session, existing_doc.id)
        assert version.storage_key == "old-key.pdf"
        assert version.file_size_bytes == 9
    finally:
        assertion_session.close()


@responses.activate
def test_scrape_source_task_skips_unchanged_existing_document_without_downloading(db_session, test_engine, monkeypatch):
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    repository.insert_document(
        db_session,
        doc_id="56fdae9f954347fcfb9cbdd8d9c98acfbe36ce66",
        source_id=source.id,
        title="Documento 1",
        storage_bucket="iurisync-test",
        storage_key="old-key.pdf",
        content_type="application/pdf",
        file_size_bytes=9,
        source_url="https://example.com/doc1",
    )

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/doc1", "method": "GET"},
            title="Documento 1",
            tipo="Auto",
            f_public="2026-01-01",
        )
    ]
    responses.add(responses.HEAD, "https://example.com/doc1", headers={"Content-Length": "9"}, status=200)
    # Deliberadamente NO se registra ningún mock de GET para esta URL — si el código
    # intentara descargar de todos modos, `responses` haría fallar la petición y el
    # test lo detectaría como error, no como "saltado silenciosamente".

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    scrape_source_task(run_source.id)

    assertion_session = task_session_factory()
    try:
        [refreshed_source] = repository.list_run_sources(assertion_session, run.id)
        assert refreshed_source.docs_new == 0
        assert refreshed_source.docs_updated == 0
        assert refreshed_source.docs_errors == 0
    finally:
        assertion_session.close()


@responses.activate
def test_scrape_source_task_never_head_checks_a_family_that_opts_out(db_session, test_engine, monkeypatch):
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    repository.insert_document(
        db_session,
        doc_id="56fdae9f954347fcfb9cbdd8d9c98acfbe36ce66",
        source_id=source.id,
        title="Documento 1",
        storage_bucket="iurisync-test",
        storage_key="old-key.pdf",
        content_type="application/pdf",
        file_size_bytes=9,
        source_url="https://example.com/doc1",
    )

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/doc1", "method": "GET"},
            title="Documento 1",
            tipo="Auto",
            f_public="2026-01-01",
        )
    ]
    # No se registra NINGÚN mock (ni HEAD ni GET) — si el código llegara a llamar a
    # cualquiera de los dos, `responses` lo haría fallar, probando que un existing
    # document se salta por completo cuando la familia no verifica republicaciones.
    DummyFamilyScraper.checks_for_republication = False
    try:
        task_session_factory = sessionmaker(bind=test_engine, future=True)
        monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
        monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

        scrape_source_task(run_source.id)

        assertion_session = task_session_factory()
        try:
            [refreshed_source] = repository.list_run_sources(assertion_session, run.id)
            assert refreshed_source.docs_new == 0
            assert refreshed_source.docs_updated == 0
        finally:
            assertion_session.close()
    finally:
        DummyFamilyScraper.checks_for_republication = True  # restore the class-level default for later tests
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_tasks.py -k "replaces_a_republished or skips_unchanged_existing or never_head_checks" -v`
Expected: FAIL — `AttributeError` (no `docs_updated` on the returned object yet) or a `TypeError`/mismatch, since `scrape_source_task` doesn't do any of this yet.

- [ ] **Step 3: Implement the change in `worker/tasks.py`**

Add the import:

```python
from core.downloader import Downloader, check_remote_content_length, convert_to_pdf_via_libreoffice
```

Add this helper function right after `_download_and_upload_one` (before `@celery_app.task(name="worker.scrape_source_task"...)`):

```python
def _versioned_replacement_key(original_key: str) -> str:
    """Builds a distinct storage key for a re-downloaded (republished) document, so
    the new upload never overwrites the original object — a DocumentVersion row
    keeps pointing at that original key as the archived version's location."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    posix_key = PurePosixPath(original_key)
    if posix_key.suffix:
        return str(posix_key.with_name(f"{posix_key.stem}-republicado-{timestamp}{posix_key.suffix}"))
    return f"{original_key}-republicado-{timestamp}"
```

Modify `_download_and_upload_one` to accept an optional key override:

```python
def _download_and_upload_one(doc, tmp_path: Path, override_storage_key: str | None = None):
    """Runs in a worker thread: download, convert, and upload a single document.
    Returns (payload, error) — payload is the dict of fields insert_document needs
    beyond doc_id/source_id/run_source_id, or None if an error occurred. Owns its
    own Downloader (and therefore its own WordConverter/Word COM instance) so
    concurrent threads never share Word state. `override_storage_key`, when given,
    is used instead of the freshly-computed key — this is how a republication
    replacement lands under a distinct key instead of the original document's."""
    downloader = Downloader()
    try:
        result = downloader.download(doc, tmp_path)
        upload_key = override_storage_key or result.storage_key
        bucket, storage_key = upload_file(result.local_path, upload_key, content_type=result.content_type)

        return {
            "storage_bucket": bucket,
            "storage_key": storage_key,
            "content_type": result.content_type,
            "file_extension": Path(storage_key).suffix,
            "file_size_bytes": result.file_size_bytes,
            "converted_format": result.converted_format,
        }, None
    except Exception as exc:
        return None, exc
    finally:
        downloader.close()
```

Replace the entire body of `scrape_source_task` from the `docs_new = 0` line through the `repository.set_run_source_status(...)` call (i.e. everything inside the outer `try` after `docs = scraper.scrap(...)` succeeded) with:

```python
        docs_new = 0
        docs_updated = 0
        docs_errors = 0
        with tempfile.TemporaryDirectory(prefix=f"run_source_{run_source_id}_") as tmp_dir:
            tmp_path = Path(tmp_dir)

            pending = []  # (doc_id, doc) -> brand new documents
            replace_candidates = []  # (existing_document, doc_id, doc) -> possible republication
            for doc in docs:
                if repository.is_cancel_requested(db, run.id):
                    break
                doc_id = compute_doc_id(doc)
                existing = repository.get_document_by_doc_id(db, doc_id)
                if existing is None:
                    pending.append((doc_id, doc))
                    continue
                if not scraper.checks_for_republication:
                    continue
                remote_size = check_remote_content_length(doc.link.get("url"))
                if remote_size is not None and remote_size == existing.file_size_bytes:
                    continue
                replace_candidates.append((existing, doc_id, doc))

            with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOCUMENT_DOWNLOADS) as executor:
                new_futures = {
                    executor.submit(_download_and_upload_one, doc, tmp_path): ("new", doc_id, doc)
                    for doc_id, doc in pending
                }
                replace_futures = {
                    executor.submit(
                        _download_and_upload_one, doc, tmp_path, _versioned_replacement_key(existing.storage_key)
                    ): ("replace", existing, doc_id, doc)
                    for existing, doc_id, doc in replace_candidates
                }
                all_futures = {**new_futures, **replace_futures}

                for future in as_completed(all_futures):
                    entry = all_futures[future]
                    kind = entry[0]
                    doc = entry[-1]
                    payload, exc = future.result()

                    if exc is not None:
                        if isinstance(exc, FileNotFoundError):
                            logger.info("Documento no disponible aún: %s", exc)
                            continue
                        docs_errors += 1
                        repository.add_run_error(
                            db, run_source_id, str(exc), context={"title": doc.title, "url": doc.link.get("url")}
                        )
                        continue

                    if kind == "new":
                        _, doc_id, doc = entry
                        repository.insert_document(
                            db,
                            doc_id=doc_id,
                            source_id=source.id,
                            run_source_id=run_source_id,
                            title=doc.title,
                            tipo=doc.tipo,
                            seccion=doc.seccion,
                            especialidad=doc.especialidad,
                            magistrado=doc.magistrado,
                            detalle=doc.detalle,
                            f_public=_parse_date(doc.f_public),
                            f_providencia=_parse_date(doc.f_providencia),
                            source_url=doc.link.get("url"),
                            **payload,
                        )
                        docs_new += 1
                    else:
                        _, existing, doc_id, doc = entry
                        if payload["file_size_bytes"] == existing.file_size_bytes:
                            continue  # el HEAD no fue concluyente pero el tamaño real no cambió
                        repository.archive_and_replace_document(db, existing.id, **payload)
                        docs_updated += 1

        repository.set_run_source_status(
            db,
            run_source_id,
            "completed",
            docs_new=docs_new,
            docs_updated=docs_updated,
            docs_errors=docs_errors,
            finished_at=datetime.now(timezone.utc),
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_tasks.py -v`
Expected: all PASS, including the three new tests. Pay particular attention to `test_scrape_source_task_skips_unchanged_existing_document_without_downloading` — if it fails with an `responses.exceptions.ConnectionError`-style error rather than an assertion failure, that means the code tried to download when it shouldn't have; re-check the `remote_size == existing.file_size_bytes` short-circuit.

Run the full backend suite once: `.venv/Scripts/pytest -q`
Expected: same pass count as before plus 3, with only the pre-existing unrelated `test_migrations.py` failure.

- [ ] **Step 5: Commit**

```bash
git add worker/tasks.py tests/test_tasks.py
git commit -m "feat: detect and apply document republications in scrape_source_task"
```

---

## Task 5: API — `DocumentVersionOut`, `docs_updated`, and the versions endpoints

**Files:**
- Modify: `api/schemas.py`
- Modify: `api/routers/documents.py`
- Test: `tests/test_api_documents.py`, `tests/test_api_runs.py`

**Interfaces:**
- Consumes: `repository.list_document_versions`, `repository.get_document_version`, `repository.get_document` (Task 1); `core.storage.presigned_url` (existing).
- Produces (consumed by Task 6): `GET /documents/{document_id}/versions`, `GET /documents/{document_id}/versions/{version_id}/download`. `RunSourceOut.docs_updated`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api_documents.py`:

```python
def test_get_document_versions_lists_most_recently_superseded_first(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session, doc_id="doc-v", source_id=source.id, title="A. 1/26",
        storage_bucket="iurisync-test", storage_key="v1.rtf", file_size_bytes=100,
    )
    repository.archive_and_replace_document(
        db_session, document.id, storage_bucket="iurisync-test", storage_key="v2.rtf", file_size_bytes=200
    )
    repository.archive_and_replace_document(
        db_session, document.id, storage_bucket="iurisync-test", storage_key="v3.rtf", file_size_bytes=300
    )

    response = api_client.get(f"/documents/{document.id}/versions", headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    assert [v["file_size_bytes"] for v in body] == [200, 100]


def test_get_document_versions_returns_empty_list_for_a_document_with_no_history(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session, doc_id="doc-no-versions", source_id=source.id, title="A. 2/26",
        storage_bucket="iurisync-test", storage_key="only.rtf", file_size_bytes=50,
    )

    response = api_client.get(f"/documents/{document.id}/versions", headers=auth_header)

    assert response.status_code == 200
    assert response.json() == []


def test_get_document_version_download_returns_404_for_a_version_of_another_document(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document_a = repository.insert_document(
        db_session, doc_id="doc-a", source_id=source.id, title="A", storage_bucket="iurisync-test",
        storage_key="a.rtf", file_size_bytes=10,
    )
    document_b = repository.insert_document(
        db_session, doc_id="doc-b", source_id=source.id, title="B", storage_bucket="iurisync-test",
        storage_key="b.rtf", file_size_bytes=10,
    )
    repository.archive_and_replace_document(
        db_session, document_b.id, storage_bucket="iurisync-test", storage_key="b-v2.rtf", file_size_bytes=20
    )
    [version_of_b] = repository.list_document_versions(db_session, document_b.id)

    response = api_client.get(f"/documents/{document_a.id}/versions/{version_of_b.id}/download", headers=auth_header)

    assert response.status_code == 404


def test_get_document_version_download_returns_signed_url(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session, doc_id="doc-download-version", source_id=source.id, title="A. 3/26",
        storage_bucket="iurisync-test", storage_key="v1.rtf", file_size_bytes=10,
    )
    repository.archive_and_replace_document(
        db_session, document.id, storage_bucket="iurisync-test", storage_key="v2.rtf", file_size_bytes=20
    )
    [version] = repository.list_document_versions(db_session, document.id)

    response = api_client.get(f"/documents/{document.id}/versions/{version.id}/download", headers=auth_header)

    assert response.status_code == 200
    assert "url" in response.json()
```

Add to `tests/test_api_runs.py`:

```python
def test_get_run_sources_reports_docs_updated(api_client, auth_header, monkeypatch, db_session):
    from core.db import repository

    monkeypatch.setattr("api.routers.runs.orchestrate_run.delay", lambda *a, **k: None)
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)
    repository.set_run_source_status(db_session, run_source.id, "completed", docs_new=1, docs_updated=3, docs_errors=0)

    response = api_client.get(f"/runs/{run.id}/sources", headers=auth_header)

    assert response.status_code == 200
    assert response.json()[0]["docs_updated"] == 3
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_api_documents.py -k "versions" tests/test_api_runs.py -k "docs_updated" -v`
Expected: FAIL — `404 Not Found` for the versions endpoints (not registered yet), `KeyError: 'docs_updated'` for the runs test.

- [ ] **Step 3: Add the schema fields**

In `api/schemas.py`, add `docs_updated` to `RunSourceOut`:

```python
class RunSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    run_id: int
    source_id: int
    status: str
    docs_new: int
    docs_updated: int
    docs_errors: int
    error_message: Optional[str] = None
```

Add `DocumentVersionOut` right after `BulkDownloadOut`:

```python
class DocumentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    document_id: int
    file_size_bytes: Optional[int] = None
    content_type: Optional[str] = None
    downloaded_at: datetime
    superseded_at: datetime
```

- [ ] **Step 4: Add the endpoints**

In `api/routers/documents.py`, update the schema import:

```python
from api.schemas import (
    BulkDocumentReviewUpdate,
    DocumentOut,
    DocumentReviewUpdate,
    DocumentStatsOut,
    DocumentVersionOut,
    PaginatedDocuments,
)
```

Add these two endpoints right after `get_document` (before `patch_bulk_document_review_status`):

```python
@router.get("/documents/{document_id}/versions", response_model=list[DocumentVersionOut])
def get_document_versions(document_id: int, db: Session = Depends(get_db)):
    return repository.list_document_versions(db, document_id)


@router.get("/documents/{document_id}/versions/{version_id}/download")
def download_document_version(document_id: int, version_id: int, db: Session = Depends(get_db)):
    version = repository.get_document_version(db, version_id)
    if version is None or version.document_id != document_id:
        raise HTTPException(status_code=404, detail="Versión no encontrada")
    url = presigned_url(version.storage_bucket, version.storage_key)
    return {"url": url}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_api_documents.py tests/test_api_runs.py -v`
Expected: all PASS.

Run the full backend suite once: `.venv/Scripts/pytest -q`
Expected: same pass count as before plus 5, only the pre-existing unrelated `test_migrations.py` failure.

- [ ] **Step 6: Commit**

```bash
git add api/schemas.py api/routers/documents.py tests/test_api_documents.py tests/test_api_runs.py
git commit -m "feat: add document version history endpoints and docs_updated to RunSourceOut"
```

---

## Task 6: Frontend API client — versions

**Files:**
- Modify: `frontend/src/api/documents.ts`
- Modify: `frontend/src/api/types.ts`
- Test: `frontend/src/api/documents.test.ts`

**Interfaces:**
- Produces (consumed by Task 7):
  - `DocumentVersion` type in `types.ts`: `{ id: number; document_id: number; file_size_bytes: number | null; content_type: string | null; downloaded_at: string; superseded_at: string }`
  - `fetchDocumentVersions(documentId: number): Promise<DocumentVersion[]>`
  - `fetchDocumentVersionUrl(documentId: number, versionId: number): Promise<string>`

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/api/documents.test.ts` (check the file's existing imports/`BASE_URL` const first and reuse them):

```ts
describe("fetchDocumentVersions", () => {
  it("gets the version list for a document", async () => {
    const versions = [
      { id: 1, document_id: 5, file_size_bytes: 100, content_type: "application/rtf", downloaded_at: "2026-06-01T00:00:00Z", superseded_at: "2026-07-01T00:00:00Z" },
    ];
    server.use(http.get(`${BASE_URL}/documents/5/versions`, () => HttpResponse.json(versions)));

    const result = await fetchDocumentVersions(5);

    expect(result).toEqual(versions);
  });
});

describe("fetchDocumentVersionUrl", () => {
  it("returns the presigned url for a version", async () => {
    server.use(
      http.get(`${BASE_URL}/documents/5/versions/1/download`, () =>
        HttpResponse.json({ url: "https://signed.example.com/versions/1.rtf" })
      )
    );

    const result = await fetchDocumentVersionUrl(5, 1);

    expect(result).toBe("https://signed.example.com/versions/1.rtf");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npm test -- --run src/api/documents.test.ts`
Expected: FAIL — `fetchDocumentVersions is not defined` / `fetchDocumentVersionUrl is not defined`.

- [ ] **Step 3: Implement**

In `frontend/src/api/types.ts`, add:

```ts
export interface DocumentVersion {
  id: number;
  document_id: number;
  file_size_bytes: number | null;
  content_type: string | null;
  downloaded_at: string;
  superseded_at: string;
}
```

In `frontend/src/api/documents.ts`, update the type import:

```ts
import type { Document, DocumentReviewStatus, DocumentStats, DocumentVersion, PaginatedDocuments } from "./types";
```

Add these functions right after `fetchDocument`:

```ts
export function fetchDocumentVersions(documentId: number): Promise<DocumentVersion[]> {
  return apiFetch<DocumentVersion[]>(`/documents/${documentId}/versions`);
}

export function fetchDocumentVersionUrl(documentId: number, versionId: number): Promise<string> {
  return apiFetch<{ url: string }>(`/documents/${documentId}/versions/${versionId}/download`).then((data) => data.url);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `frontend/`): `npm test -- --run src/api/documents.test.ts`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/documents.ts frontend/src/api/documents.test.ts
git commit -m "feat: add document version history API client"
```

---

## Task 7: `DocumentPreviewDialog` — version history UI

**Files:**
- Modify: `frontend/src/components/DocumentPreviewDialog.tsx`
- Test: `frontend/src/components/DocumentPreviewDialog.test.tsx`

**Interfaces:**
- Consumes: `fetchDocumentVersions`, `fetchDocumentVersionUrl` (Task 6); `downloadFromUrl` (existing); `formatDateTime`, `formatBytes` (existing, `lib/formatters.ts`).

- [ ] **Step 1: Write the failing tests**

In `frontend/src/components/DocumentPreviewDialog.test.tsx`, add `within` to the existing `@testing-library/react` import:

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
```

Then add to the same file:

```tsx
it("does not show a version history section when the document has no prior versions", async () => {
  const documents = [makeDocument({ id: 20, title: "Sin historial" })];
  mockPreviewUrl(20);
  server.use(http.get(`${BASE_URL}/documents/20/versions`, () => HttpResponse.json([])));

  renderDialog(documents, 0);

  await screen.findByTitle("Vista previa de Sin historial");
  expect(screen.queryByText(/versiones anteriores/i)).not.toBeInTheDocument();
});

it("shows the version history with a working download button", async () => {
  const documents = [makeDocument({ id: 21, title: "Con historial" })];
  mockPreviewUrl(21);
  server.use(
    http.get(`${BASE_URL}/documents/21/versions`, () =>
      HttpResponse.json([
        { id: 1, document_id: 21, file_size_bytes: 76245, content_type: "application/rtf", downloaded_at: "2026-06-01T00:00:00Z", superseded_at: "2026-07-01T00:00:00Z" },
      ])
    ),
    http.get(`${BASE_URL}/documents/21/versions/1/download`, () =>
      HttpResponse.json({ url: "https://signed.example.com/versions/1.rtf" })
    ),
    http.get("https://signed.example.com/versions/1.rtf", () => new HttpResponse(new Blob(["contenido viejo"])))
  );
  const clickSpy = vi.fn();
  const originalCreateElement = document.createElement.bind(document);
  const createElementSpy = vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
    const element = originalCreateElement(tag);
    if (tag === "a") element.click = clickSpy;
    return element;
  });
  const user = userEvent.setup();

  renderDialog(documents, 0);
  await screen.findByTitle("Vista previa de Con historial");

  // Scoped with within(): the default makeDocument() content_type is "application/pdf",
  // so the header already renders its own "Descargar PDF" button — a bare
  // screen.getByRole("button", { name: /descargar/i }) would match both that one and
  // the version row's "Descargar" button and throw for multiple matches.
  const versionsHeading = await screen.findByText(/1 versi.n anterior/i);
  const versionsSection = versionsHeading.closest("div") as HTMLElement;
  await user.click(within(versionsSection).getByRole("button", { name: /descargar/i }));

  await waitFor(() => expect(clickSpy).toHaveBeenCalledOnce());
  createElementSpy.mockRestore();
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npm test -- --run src/components/DocumentPreviewDialog.test.tsx`
Expected: the two new tests FAIL (no version section rendered at all yet); all pre-existing tests in this file still PASS.

- [ ] **Step 3: Implement**

In `frontend/src/components/DocumentPreviewDialog.tsx`, update the imports:

```tsx
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download } from "lucide-react";
import {
  buildDownloadFilename,
  buildPreviewDownloadFilename,
  downloadDocumentFile,
  downloadFromUrl,
  fetchDocumentPreviewUrl,
  fetchDocumentVersionUrl,
  fetchDocumentVersions,
  updateDocumentReviewStatus,
} from "../api/documents";
import type { Document, DocumentReviewStatus } from "../api/types";
import { formatBytes, formatDate, formatDateTime } from "../lib/formatters";
import { ErrorBanner } from "./ErrorBanner";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "./ui/dialog";
```

Add a `versionsQuery` right after `previewUrlQuery`:

```tsx
  const versionsQuery = useQuery({
    queryKey: ["document-versions", currentDocument?.id],
    queryFn: () => fetchDocumentVersions(currentDocument!.id),
    enabled: open && !!currentDocument,
  });
```

Add a handler near `handleDownloadPdf`:

```tsx
  async function handleDownloadVersion(versionId: number) {
    try {
      setDownloadError(null);
      const url = await fetchDocumentVersionUrl(currentDocument.id, versionId);
      await downloadFromUrl(url, `${currentDocument.title}-version-${versionId}.rtf`);
    } catch {
      setDownloadError("Error al descargar la versión anterior");
    }
  }
```

Add the version-history section right after the closing `</div>` of the previewable content area (`isPreviewable ? (...) : (...)`) and before the `{markError && ...}` block:

```tsx
        {(versionsQuery.data?.length ?? 0) > 0 && (
          <div className="rounded-md border border-border bg-secondary/40 p-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase">
              {versionsQuery.data!.length} {versionsQuery.data!.length === 1 ? "versión anterior" : "versiones anteriores"}
            </p>
            <ul className="mt-2 space-y-1.5">
              {versionsQuery.data!.map((version) => (
                <li key={version.id} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-muted-foreground">
                    Reemplazada el {formatDateTime(version.superseded_at)} · {formatBytes(version.file_size_bytes)}
                  </span>
                  <Button variant="outline" size="sm" onClick={() => handleDownloadVersion(version.id)}>
                    <Download className="size-3.5" aria-hidden="true" />
                    Descargar
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `frontend/`): `npm test -- --run src/components/DocumentPreviewDialog.test.tsx`
Expected: all PASS, including the two new tests and every pre-existing one.

Run the full frontend suite once: `npm test -- --run`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DocumentPreviewDialog.tsx frontend/src/components/DocumentPreviewDialog.test.tsx
git commit -m "feat: show version history in the document preview dialog"
```

---

## Task 8: `RunDetailPage` — "Actualizados" column

**Files:**
- Modify: `frontend/src/pages/RunDetailPage.tsx`
- Test: `frontend/src/pages/RunDetailPage.test.tsx`

**Interfaces:**
- Consumes: `RunSource.docs_updated` (already flows through `fetchRunSources`, typed via `frontend/src/api/types.ts`'s `RunSource` interface — that interface needs `docs_updated: number` added too, since it's a plain data type, not something Task 6 touched).

- [ ] **Step 1: Add `docs_updated` to the `RunSource` type and the test fixture**

In `frontend/src/api/types.ts`, find the `RunSource` interface and add the field:

```ts
export interface RunSource {
  id: number;
  run_id: number;
  source_id: number;
  status: RunSourceStatus;
  docs_new: number;
  docs_updated: number;
  docs_errors: number;
  error_message: string | null;
}
```

In `frontend/src/pages/RunDetailPage.test.tsx`, add `docs_updated: 0` to the `RUN_SOURCE` fixture:

```ts
const RUN_SOURCE = { id: 1, run_id: 1, source_id: 5, status: "failed", docs_new: 2, docs_updated: 0, docs_errors: 1, error_message: "timeout" };
```

- [ ] **Step 2: Write the failing test**

Add to `frontend/src/pages/RunDetailPage.test.tsx`:

```tsx
it("shows the Actualizados column with docs_updated", async () => {
  server.use(
    http.get(`${BASE_URL}/runs/1`, () => HttpResponse.json(RUN)),
    http.get(`${BASE_URL}/runs/1/sources`, () => HttpResponse.json([{ ...RUN_SOURCE, docs_updated: 4 }]))
  );

  renderPage();

  await screen.findByText("Run #1");
  expect(screen.getByText("4")).toBeInTheDocument();
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run (from `frontend/`): `npm test -- --run src/pages/RunDetailPage.test.tsx`
Expected: FAIL — no element with text "4" (the column doesn't exist yet).

- [ ] **Step 4: Add the column**

In `frontend/src/pages/RunDetailPage.tsx`, add a header cell after "Docs nuevos":

```tsx
                <th className={TH}>Docs nuevos</th>
                <th className={TH}>Actualizados</th>
                <th className={TH}>Docs con error</th>
```

Add the matching body cell after the `docs_new` cell:

```tsx
                  <td className={TD_MONO}>{runSource.docs_new}</td>
                  <td className={TD_MONO}>{runSource.docs_updated}</td>
                  <td className={TD_MONO}>{runSource.docs_errors}</td>
```

- [ ] **Step 5: Run the tests to verify they pass**

Run (from `frontend/`): `npm test -- --run src/pages/RunDetailPage.test.tsx`
Expected: all PASS, including every pre-existing test in this file (the new column must not break the "renders the run header and its sources table" test, which already asserts on the literal text "2" — that assertion still finds `docs_new`'s "2" regardless of the new column's presence).

Run the full frontend suite once: `npm test -- --run`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/pages/RunDetailPage.tsx frontend/src/pages/RunDetailPage.test.tsx
git commit -m "feat: show docs_updated in the run detail sources table"
```

---

## Final check

- [ ] Run the complete backend suite: `.venv/Scripts/pytest -q` — expect the same pre-existing `test_migrations.py` failure and otherwise all green.
- [ ] Run the complete frontend suite (from `frontend/`): `npm test -- --run` — expect all green.
- [ ] Manually verify end-to-end: pick a real Corte Constitucional document already in the database, temporarily change its stored `file_size_bytes` in the DB to a different value (simulating "the source changed"), then run a scrape for a date range that includes it — confirm the run completes with `docs_updated: 1`, the document's `storage_key`/`file_size_bytes` now reflect a freshly downloaded file, its `review_status` is back to `"pending"`, and the previous version is visible (with a working download) in the preview dialog's version history.
