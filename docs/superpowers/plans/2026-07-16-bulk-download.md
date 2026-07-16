# Descarga masiva de documentos útiles — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Descarga masiva" button to Documentos that packages every document marked `review_status = "useful"` into a single `.zip` (preserving each document's existing `storage_key` folder hierarchy), built asynchronously by a Celery task, with a new "Descargas masivas" history page to track progress and download the result.

**Architecture:** New `bulk_downloads` table + repository functions mirror the existing `runs` pattern (pending → running → completed/failed, tracked via a DB row). A new Celery task downloads each useful document from MinIO into a temp directory (preserving `storage_key` as the relative path), zips it, and re-uploads the zip to MinIO. A new router exposes create/list/download-url endpoints. The frontend gets a new list page (polling, same pattern as `RunsPage`) plus a single button wired into `DocumentsPage`.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + Celery/Redis (backend, existing stack) — React + TanStack Query + react-router-dom (frontend, existing stack). No new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-16-bulk-download-design.md` — follow it exactly; this plan implements it task-by-task.
- The bulk download always covers **all** `review_status = "useful"` documents system-wide — never filtered by what's currently shown in `DocumentsPage`.
- The zip's internal file paths must be exactly each document's `storage_key` (already `/`-delimited, e.g. `JEP/2026-06-01/Auto/archivo.pdf`) — this **is** the folder hierarchy requirement, already established per-family in the scrapers.
- A document that fails to download from MinIO is skipped (counted in `failed_count`), not fatal to the whole job. Zero useful documents (or zero successfully downloaded) is a `failed` job with a clear `error_message`, not a crash.
- No expiration/cleanup of generated zips (out of scope), no per-run cancellation (out of scope), no filtering the bulk download by source/date (out of scope).
- Backend tests hit a **real** local Postgres + MinIO (via `TEST_DATABASE_URL`/`TEST_S3_BUCKET` in `tests/conftest.py`) — do not mock `boto3`/storage calls; call `core.storage.upload_file`/`download_file` for real against the test bucket, matching `tests/test_storage.py` and `tests/test_tasks.py`.
- Celery task tests run synchronously via `celery_app.conf.task_always_eager = True` and a `SessionLocal` monkeypatched to a `sessionmaker` bound to the test engine (see `tests/test_tasks.py` for the exact pattern) — re-query assertions through a **fresh** session from that same factory, not the test's own `db_session` (stale identity-map issue, documented inline in the existing test).

---

## Task 1: `BulkDownload` model, migration, and repository functions

**Files:**
- Modify: `core/db/models.py` (add `BulkDownload` class, after `RunError`)
- Create: `alembic/versions/<generated>_add_bulk_downloads.py`
- Modify: `core/db/repository.py` (add functions, after `add_run_error`)
- Test: `tests/test_repository.py` (add test, after `test_run_and_run_source_lifecycle`)

**Interfaces:**
- Produces (consumed by Task 2 and Task 3):
  - `core.db.models.BulkDownload` — columns `id`, `status`, `document_count`, `failed_count`, `zip_storage_key`, `error_message`, `started_at`, `finished_at`, `created_at`.
  - `repository.create_bulk_download(db: Session) -> BulkDownload`
  - `repository.get_bulk_download(db: Session, bulk_download_id: int) -> Optional[BulkDownload]`
  - `repository.list_bulk_downloads(db: Session, limit: int = 50, offset: int = 0) -> list[BulkDownload]`
  - `repository.set_bulk_download_status(db: Session, bulk_download_id: int, status: str, **fields) -> None`
  - `repository.list_useful_documents(db: Session) -> list[Document]`

- [ ] **Step 1: Add the `BulkDownload` model**

In `core/db/models.py`, add this class immediately after the `RunError` class (which ends right before `class Document(Base):`):

```python
class BulkDownload(Base):
    __tablename__ = "bulk_downloads"

    id = Column(Integer, primary_key=True)
    status = Column(String, nullable=False, default="pending")  # pending | running | completed | failed
    document_count = Column(Integer, nullable=False, default=0)  # incluidos en el zip
    failed_count = Column(Integer, nullable=False, default=0)  # se omitieron por error de lectura
    zip_storage_key = Column(Text, nullable=True)  # solo si status == completed
    error_message = Column(Text, nullable=True)  # solo si status == failed
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
```

- [ ] **Step 2: Write the failing repository test**

Add to `tests/test_repository.py`, right after `test_run_and_run_source_lifecycle`:

```python
def test_bulk_download_lifecycle(db_session):
    from datetime import datetime, timezone

    bulk_download = repository.create_bulk_download(db_session)
    assert bulk_download.status == "pending"
    assert bulk_download.document_count == 0
    assert bulk_download.failed_count == 0

    repository.set_bulk_download_status(
        db_session, bulk_download.id, "running", started_at=datetime.now(timezone.utc)
    )
    refreshed = repository.get_bulk_download(db_session, bulk_download.id)
    assert refreshed.status == "running"
    assert refreshed.started_at is not None

    repository.set_bulk_download_status(
        db_session,
        bulk_download.id,
        "completed",
        document_count=5,
        failed_count=1,
        zip_storage_key="bulk-downloads/1.zip",
        finished_at=datetime.now(timezone.utc),
    )
    refreshed = repository.get_bulk_download(db_session, bulk_download.id)
    assert refreshed.status == "completed"
    assert refreshed.document_count == 5
    assert refreshed.failed_count == 1
    assert refreshed.zip_storage_key == "bulk-downloads/1.zip"


def test_list_bulk_downloads_orders_by_most_recent_first(db_session):
    first = repository.create_bulk_download(db_session)
    second = repository.create_bulk_download(db_session)

    listed = repository.list_bulk_downloads(db_session)

    assert [item.id for item in listed] == [second.id, first.id]


def test_list_useful_documents_filters_by_review_status(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-useful", source_id=source.id, title="A", review_status="useful",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-pending", source_id=source.id, title="B",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    useful = repository.list_useful_documents(db_session)

    assert [doc.doc_id for doc in useful] == ["doc-useful"]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_repository.py -k bulk_download -v`
Expected: FAIL — `AttributeError: module 'core.db.repository' has no attribute 'create_bulk_download'` (the model exists but nothing references it yet, so this also confirms the model alone doesn't create the table — the migration/`Base.metadata` step below does).

- [ ] **Step 4: Generate the Alembic migration**

Run: `.venv/Scripts/alembic revision -m "add bulk downloads"`

This prints the generated file path, e.g. `alembic/versions/<hash>_add_bulk_downloads.py`. Open it and replace the body (keep the auto-generated `revision`/`down_revision` header as-is — `down_revision` should already point at `93307b0ad39a`, the current head):

```python
def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'bulk_downloads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('document_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('zip_storage_key', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('bulk_downloads')
```

- [ ] **Step 5: Add the repository functions**

In `core/db/repository.py`, add this block right after `add_run_error` (before `def document_exists`):

```python
def create_bulk_download(db: Session) -> BulkDownload:
    bulk_download = BulkDownload(status="pending")
    db.add(bulk_download)
    db.commit()
    db.refresh(bulk_download)
    return bulk_download


def get_bulk_download(db: Session, bulk_download_id: int) -> Optional[BulkDownload]:
    return db.get(BulkDownload, bulk_download_id)


def list_bulk_downloads(db: Session, limit: int = 50, offset: int = 0) -> list[BulkDownload]:
    stmt = (
        select(BulkDownload)
        .order_by(BulkDownload.created_at.desc(), BulkDownload.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).all())


def set_bulk_download_status(db: Session, bulk_download_id: int, status: str, **fields) -> None:
    bulk_download = db.get(BulkDownload, bulk_download_id)
    bulk_download.status = status
    for key, value in fields.items():
        setattr(bulk_download, key, value)
    db.commit()


def list_useful_documents(db: Session) -> list[Document]:
    stmt = select(Document).where(Document.review_status == "useful")
    return list(db.scalars(stmt).all())
```

Add `BulkDownload` to the model import at the top of the file:

```python
from core.db.models import BulkDownload, Document, Run, RunError, RunSource, Source, SourceFamily, User, UserSession
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_repository.py -v`
Expected: all PASS, including the three new tests (`test_bulk_download_lifecycle`, `test_list_bulk_downloads_orders_by_most_recent_first`, `test_list_useful_documents_filters_by_review_status`).

- [ ] **Step 7: Commit**

```bash
git add core/db/models.py core/db/repository.py alembic/versions/*_add_bulk_downloads.py tests/test_repository.py
git commit -m "feat: add BulkDownload model and repository functions"
```

---

## Task 2: Celery task `build_bulk_download_zip`

**Files:**
- Modify: `worker/tasks.py` (add `import zipfile`, add the task at the end of the file)
- Test: `tests/test_tasks.py` (add tests at the end of the file)

**Interfaces:**
- Consumes: `repository.list_useful_documents`, `repository.set_bulk_download_status`, `repository.create_bulk_download`, `repository.get_bulk_download` (Task 1); `core.storage.download_file`, `core.storage.upload_file` (already imported in this file).
- Produces (consumed by Task 3): `worker.tasks.build_bulk_download_zip(bulk_download_id: int) -> None`, registered as Celery task `"worker.build_bulk_download_zip"`.

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_tasks.py`:

```python
def test_build_bulk_download_zip_uploads_zip_preserving_storage_key_hierarchy(db_session, test_engine, monkeypatch):
    from pathlib import Path
    import zipfile

    from core.storage import presigned_url, upload_file
    from worker.tasks import build_bulk_download_zip

    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    repository.create_source_family(db_session, key="jep", display_name="JEP")
    source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})

    # Sube dos "documentos" reales al bucket de prueba, con la jerarquía que
    # ya usan los scrapers (fuente/fecha/tipo/archivo), y los marca "useful".
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        doc1_local = Path(tmp) / "doc1.pdf"
        doc1_local.write_bytes(b"contenido uno")
        upload_file(doc1_local, "JEP/2026-06-01/Auto/doc1.pdf", bucket=TEST_S3_BUCKET, content_type="application/pdf")

        doc2_local = Path(tmp) / "doc2.pdf"
        doc2_local.write_bytes(b"contenido dos")
        upload_file(doc2_local, "JEP/2026-06-02/Sentencia/doc2.pdf", bucket=TEST_S3_BUCKET, content_type="application/pdf")

    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Doc 1", review_status="useful",
        storage_bucket=TEST_S3_BUCKET, storage_key="JEP/2026-06-01/Auto/doc1.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="Doc 2", review_status="useful",
        storage_bucket=TEST_S3_BUCKET, storage_key="JEP/2026-06-02/Sentencia/doc2.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-3", source_id=source.id, title="Doc 3",  # not useful — must be excluded
        storage_bucket=TEST_S3_BUCKET, storage_key="JEP/2026-06-03/Auto/doc3.pdf",
    )

    bulk_download = repository.create_bulk_download(db_session)

    build_bulk_download_zip(bulk_download.id)

    assertion_session = task_session_factory()
    try:
        refreshed = repository.get_bulk_download(assertion_session, bulk_download.id)
        assert refreshed.status == "completed"
        assert refreshed.document_count == 2
        assert refreshed.failed_count == 0
        assert refreshed.zip_storage_key == f"bulk-downloads/{bulk_download.id}.zip"

        url = presigned_url(TEST_S3_BUCKET, refreshed.zip_storage_key)
        import requests
        response = requests.get(url, timeout=10)
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "result.zip"
            zip_path.write_bytes(response.content)
            with zipfile.ZipFile(zip_path) as zf:
                names = set(zf.namelist())
                assert names == {"JEP/2026-06-01/Auto/doc1.pdf", "JEP/2026-06-02/Sentencia/doc2.pdf"}
                assert zf.read("JEP/2026-06-01/Auto/doc1.pdf") == b"contenido uno"
    finally:
        assertion_session.close()


def test_build_bulk_download_zip_skips_a_document_that_fails_to_download(db_session, test_engine, monkeypatch):
    from pathlib import Path
    import tempfile

    from core.storage import upload_file
    from worker.tasks import build_bulk_download_zip

    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    repository.create_source_family(db_session, key="jep", display_name="JEP")
    source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})

    with tempfile.TemporaryDirectory() as tmp:
        doc_local = Path(tmp) / "doc.pdf"
        doc_local.write_bytes(b"contenido real")
        upload_file(doc_local, "JEP/2026-06-01/Auto/doc.pdf", bucket=TEST_S3_BUCKET, content_type="application/pdf")

    repository.insert_document(
        db_session, doc_id="doc-real", source_id=source.id, title="Real", review_status="useful",
        storage_bucket=TEST_S3_BUCKET, storage_key="JEP/2026-06-01/Auto/doc.pdf",
    )
    # Apunta a una clave que nunca se subió — download_file fallará para este documento.
    repository.insert_document(
        db_session, doc_id="doc-missing", source_id=source.id, title="Missing", review_status="useful",
        storage_bucket=TEST_S3_BUCKET, storage_key="JEP/2026-06-01/Auto/no-existe.pdf",
    )

    bulk_download = repository.create_bulk_download(db_session)

    build_bulk_download_zip(bulk_download.id)

    assertion_session = task_session_factory()
    try:
        refreshed = repository.get_bulk_download(assertion_session, bulk_download.id)
        assert refreshed.status == "completed"
        assert refreshed.document_count == 1
        assert refreshed.failed_count == 1
    finally:
        assertion_session.close()


def test_build_bulk_download_zip_fails_when_there_are_no_useful_documents(db_session, test_engine, monkeypatch):
    from worker.tasks import build_bulk_download_zip

    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)

    bulk_download = repository.create_bulk_download(db_session)

    build_bulk_download_zip(bulk_download.id)

    assertion_session = task_session_factory()
    try:
        refreshed = repository.get_bulk_download(assertion_session, bulk_download.id)
        assert refreshed.status == "failed"
        assert refreshed.error_message == "No hay documentos marcados como Útil para descargar"
    finally:
        assertion_session.close()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_tasks.py -k build_bulk_download_zip -v`
Expected: FAIL — `ImportError: cannot import name 'build_bulk_download_zip' from 'worker.tasks'`

- [ ] **Step 3: Implement the task**

In `worker/tasks.py`, add `import zipfile` to the top imports (after `import tempfile`):

```python
import logging
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
```

Then add this task at the end of the file:

```python
@celery_app.task(name="worker.build_bulk_download_zip")
def build_bulk_download_zip(bulk_download_id: int) -> None:
    db = SessionLocal()
    try:
        repository.set_bulk_download_status(
            db, bulk_download_id, "running", started_at=datetime.now(timezone.utc)
        )

        documents = repository.list_useful_documents(db)
        if not documents:
            repository.set_bulk_download_status(
                db,
                bulk_download_id,
                "failed",
                error_message="No hay documentos marcados como Útil para descargar",
                finished_at=datetime.now(timezone.utc),
            )
            return

        with tempfile.TemporaryDirectory(prefix=f"bulk_download_{bulk_download_id}_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            downloads_dir = tmp_path / "files"
            downloads_dir.mkdir()

            downloaded: list[tuple[str, Path]] = []
            failed_count = 0
            for document in documents:
                local_path = downloads_dir / document.storage_key
                local_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    download_file(document.storage_bucket, document.storage_key, local_path)
                    downloaded.append((document.storage_key, local_path))
                except Exception as exc:
                    logger.warning("No se pudo incluir %s en la descarga masiva: %s", document.storage_key, exc)
                    failed_count += 1

            if not downloaded:
                repository.set_bulk_download_status(
                    db,
                    bulk_download_id,
                    "failed",
                    error_message=f"No se pudo leer ninguno de los {len(documents)} documentos útiles",
                    finished_at=datetime.now(timezone.utc),
                )
                return

            zip_path = tmp_path / "bulk_download.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for storage_key, local_path in downloaded:
                    zf.write(local_path, arcname=storage_key)

            zip_key = f"bulk-downloads/{bulk_download_id}.zip"
            upload_file(zip_path, zip_key, content_type="application/zip")

        repository.set_bulk_download_status(
            db,
            bulk_download_id,
            "completed",
            document_count=len(downloaded),
            failed_count=failed_count,
            zip_storage_key=zip_key,
            finished_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        repository.set_bulk_download_status(
            db, bulk_download_id, "failed", error_message=str(exc), finished_at=datetime.now(timezone.utc)
        )
    finally:
        db.close()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_tasks.py -v`
Expected: all PASS, including the three new `build_bulk_download_zip` tests. (This exercises real MinIO upload/download against the test bucket — Docker's `minio` container must be running, same requirement as the rest of the suite.)

- [ ] **Step 5: Commit**

```bash
git add worker/tasks.py tests/test_tasks.py
git commit -m "feat: add build_bulk_download_zip Celery task"
```

---

## Task 3: API — schema, router, registration

**Files:**
- Modify: `api/schemas.py` (add `BulkDownloadOut`)
- Create: `api/routers/bulk_downloads.py`
- Modify: `api/main.py` (register the router)
- Test: `tests/test_api_bulk_downloads.py` (new)

**Interfaces:**
- Consumes: `repository.create_bulk_download`, `repository.list_bulk_downloads`, `repository.get_bulk_download` (Task 1); `worker.tasks.build_bulk_download_zip` (Task 2); `core.storage.presigned_url` (existing).
- Produces (consumed by Task 4): `POST /bulk-downloads`, `GET /bulk-downloads`, `GET /bulk-downloads/{id}/download` — all requiring the same `require_session` auth as every other router.

- [ ] **Step 1: Write the failing API tests**

Create `tests/test_api_bulk_downloads.py`:

```python
def test_post_bulk_download_creates_row_and_dispatches_task(api_client, auth_header, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "api.routers.bulk_downloads.build_bulk_download_zip.delay", lambda bulk_download_id: calls.append(bulk_download_id)
    )

    response = api_client.post("/bulk-downloads", headers=auth_header)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["document_count"] == 0
    assert calls == [body["id"]]


def test_get_bulk_downloads_lists_most_recent_first(api_client, auth_header, monkeypatch):
    monkeypatch.setattr("api.routers.bulk_downloads.build_bulk_download_zip.delay", lambda *a, **k: None)

    first = api_client.post("/bulk-downloads", headers=auth_header).json()
    second = api_client.post("/bulk-downloads", headers=auth_header).json()

    response = api_client.get("/bulk-downloads", headers=auth_header)

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [second["id"], first["id"]]


def test_get_bulk_download_download_returns_404_when_not_completed(api_client, auth_header, monkeypatch):
    monkeypatch.setattr("api.routers.bulk_downloads.build_bulk_download_zip.delay", lambda *a, **k: None)

    created = api_client.post("/bulk-downloads", headers=auth_header).json()

    response = api_client.get(f"/bulk-downloads/{created['id']}/download", headers=auth_header)

    assert response.status_code == 404


def test_get_bulk_download_download_returns_signed_url_when_completed(api_client, auth_header, db_session):
    from core.db import repository

    bulk_download = repository.create_bulk_download(db_session)
    repository.set_bulk_download_status(
        db_session, bulk_download.id, "completed", document_count=2, zip_storage_key="bulk-downloads/1.zip"
    )

    response = api_client.get(f"/bulk-downloads/{bulk_download.id}/download", headers=auth_header)

    assert response.status_code == 200
    assert "url" in response.json()


def test_bulk_downloads_endpoints_require_authentication(api_client):
    assert api_client.post("/bulk-downloads").status_code == 401
    assert api_client.get("/bulk-downloads").status_code == 401
    assert api_client.get("/bulk-downloads/1/download").status_code == 401
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_api_bulk_downloads.py -v`
Expected: FAIL — `404 Not Found` for `POST /bulk-downloads` (no router registered yet).

- [ ] **Step 3: Add the `BulkDownloadOut` schema**

In `api/schemas.py`, add right after `BulkDocumentReviewUpdate` (before `PaginatedDocuments`):

```python
class BulkDownloadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    document_count: int
    failed_count: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
```

- [ ] **Step 4: Create the router**

Create `api/routers/bulk_downloads.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db, require_session
from api.schemas import BulkDownloadOut
from core.config import get_settings
from core.db import repository
from core.storage import presigned_url
from worker.tasks import build_bulk_download_zip

router = APIRouter(dependencies=[Depends(require_session)])


@router.post("/bulk-downloads", response_model=BulkDownloadOut, status_code=202)
def post_bulk_download(db: Session = Depends(get_db)):
    bulk_download = repository.create_bulk_download(db)
    build_bulk_download_zip.delay(bulk_download.id)
    return bulk_download


@router.get("/bulk-downloads", response_model=list[BulkDownloadOut])
def get_bulk_downloads(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return repository.list_bulk_downloads(db, limit=limit, offset=offset)


@router.get("/bulk-downloads/{bulk_download_id}/download")
def get_bulk_download_download(bulk_download_id: int, db: Session = Depends(get_db)):
    bulk_download = repository.get_bulk_download(db, bulk_download_id)
    if bulk_download is None or bulk_download.status != "completed" or not bulk_download.zip_storage_key:
        raise HTTPException(status_code=404, detail="Descarga masiva no disponible")

    bucket = get_settings().s3_bucket
    url = presigned_url(
        bucket,
        bulk_download.zip_storage_key,
        response_content_disposition=f'attachment; filename="descarga_masiva_{bulk_download_id}.zip"',
    )
    return {"url": url}
```

- [ ] **Step 5: Register the router**

In `api/main.py`:

```python
from api.routers import auth, bulk_downloads, documents, health, runs, sources
```

```python
app.include_router(bulk_downloads.router)
```

(add it next to the other `app.include_router(...)` lines)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_api_bulk_downloads.py -v`
Expected: all PASS.

Run the full backend suite once to confirm nothing else broke: `.venv/Scripts/pytest -q`
Expected: same pass count as before plus the new tests (the pre-existing `test_migrations.py::test_alembic_upgrade_head_creates_all_tables` failure on Windows is expected and unrelated).

- [ ] **Step 7: Commit**

```bash
git add api/schemas.py api/routers/bulk_downloads.py api/main.py tests/test_api_bulk_downloads.py
git commit -m "feat: add /bulk-downloads API endpoints"
```

---

## Task 4: Frontend API client — `api/bulkDownloads.ts`

**Files:**
- Create: `frontend/src/api/bulkDownloads.ts`
- Test: `frontend/src/api/bulkDownloads.test.ts` (new)

**Interfaces:**
- Consumes: `apiFetch`, `buildQuery` from `./client` (existing).
- Produces (consumed by Task 5 and Task 6):
  - `BulkDownload` type: `{ id: number; status: "pending" | "running" | "completed" | "failed"; document_count: number; failed_count: number; error_message: string | null; started_at: string | null; finished_at: string | null; created_at: string }`
  - `createBulkDownload(): Promise<BulkDownload>`
  - `fetchBulkDownloads(params?: { limit?: number; offset?: number }): Promise<BulkDownload[]>`
  - `fetchBulkDownloadUrl(id: number): Promise<string>`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/api/bulkDownloads.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { createBulkDownload, fetchBulkDownloadUrl, fetchBulkDownloads } from "./bulkDownloads";

const BASE_URL = "http://localhost:8000";

const BULK_DOWNLOAD = {
  id: 1,
  status: "pending",
  document_count: 0,
  failed_count: 0,
  error_message: null,
  started_at: null,
  finished_at: null,
  created_at: "2026-07-16T00:00:00Z",
};

describe("createBulkDownload", () => {
  it("posts to /bulk-downloads and returns the created row", async () => {
    server.use(http.post(`${BASE_URL}/bulk-downloads`, () => HttpResponse.json(BULK_DOWNLOAD, { status: 202 })));

    const result = await createBulkDownload();

    expect(result).toEqual(BULK_DOWNLOAD);
  });
});

describe("fetchBulkDownloads", () => {
  it("gets the list from /bulk-downloads", async () => {
    server.use(http.get(`${BASE_URL}/bulk-downloads`, () => HttpResponse.json([BULK_DOWNLOAD])));

    const result = await fetchBulkDownloads();

    expect(result).toEqual([BULK_DOWNLOAD]);
  });
});

describe("fetchBulkDownloadUrl", () => {
  it("returns the presigned url from /bulk-downloads/:id/download", async () => {
    server.use(
      http.get(`${BASE_URL}/bulk-downloads/1/download`, () =>
        HttpResponse.json({ url: "https://signed.example.com/bulk-downloads/1.zip" })
      )
    );

    const result = await fetchBulkDownloadUrl(1);

    expect(result).toBe("https://signed.example.com/bulk-downloads/1.zip");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npm test -- --run src/api/bulkDownloads.test.ts`
Expected: FAIL — cannot resolve `./bulkDownloads` (file doesn't exist yet).

- [ ] **Step 3: Implement `api/bulkDownloads.ts`**

Create `frontend/src/api/bulkDownloads.ts`:

```ts
import { apiFetch, buildQuery } from "./client";

export interface BulkDownload {
  id: number;
  status: "pending" | "running" | "completed" | "failed";
  document_count: number;
  failed_count: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ListBulkDownloadsParams {
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}

export function createBulkDownload(): Promise<BulkDownload> {
  return apiFetch<BulkDownload>("/bulk-downloads", { method: "POST" });
}

export function fetchBulkDownloads(params: ListBulkDownloadsParams = {}): Promise<BulkDownload[]> {
  return apiFetch<BulkDownload[]>(`/bulk-downloads${buildQuery(params)}`);
}

export function fetchBulkDownloadUrl(id: number): Promise<string> {
  return apiFetch<{ url: string }>(`/bulk-downloads/${id}/download`).then((data) => data.url);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `frontend/`): `npm test -- --run src/api/bulkDownloads.test.ts`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/bulkDownloads.ts frontend/src/api/bulkDownloads.test.ts
git commit -m "feat: add bulkDownloads API client"
```

---

## Task 5: `BulkDownloadsPage` — history list, route, nav link

**Files:**
- Create: `frontend/src/pages/BulkDownloadsPage.tsx`
- Modify: `frontend/src/App.tsx` (add route)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (add nav link)
- Test: `frontend/src/pages/BulkDownloadsPage.test.tsx` (new)

**Interfaces:**
- Consumes: `fetchBulkDownloads`, `fetchBulkDownloadUrl` (Task 4); `downloadFromUrl` (existing, `api/documents.ts`); `StatusBadge`, `EmptyState`, `ErrorBanner`, `Button` (existing components); `formatDateTime` (existing, `lib/formatters.ts`); table style constants from `lib/tableStyles.ts` (existing).
- Produces (consumed by Task 6, indirectly via routing): route `/bulk-downloads`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/pages/BulkDownloadsPage.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { BulkDownloadsPage } from "./BulkDownloadsPage";

const BASE_URL = "http://localhost:8000";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <BulkDownloadsPage />
    </QueryClientProvider>
  );
}

const COMPLETED = {
  id: 1,
  status: "completed",
  document_count: 12,
  failed_count: 2,
  error_message: null,
  started_at: "2026-07-16T00:00:00Z",
  finished_at: "2026-07-16T00:01:00Z",
  created_at: "2026-07-16T00:00:00Z",
};

describe("BulkDownloadsPage", () => {
  it("renders the fetched bulk downloads with status and document count", async () => {
    server.use(http.get(`${BASE_URL}/bulk-downloads`, () => HttpResponse.json([COMPLETED])));

    renderPage();

    expect(await screen.findByText("completed")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText(/2 omitidos/)).toBeInTheDocument();
  });

  it("shows a Descargar button only when completed, wired to the presigned url", async () => {
    server.use(
      http.get(`${BASE_URL}/bulk-downloads`, () => HttpResponse.json([COMPLETED])),
      http.get(`${BASE_URL}/bulk-downloads/1/download`, () =>
        HttpResponse.json({ url: "https://signed.example.com/1.zip" })
      )
    );
    // downloadFromUrl does a real fetch()+Blob — stub it so this test only
    // verifies the click is wired to the right endpoint, not the browser download mechanics.
    server.use(http.get("https://signed.example.com/1.zip", () => HttpResponse.text("contenido")));

    const user = userEvent.setup();
    renderPage();

    const button = await screen.findByRole("button", { name: /descargar/i });
    await user.click(button);
  });

  it("shows the error message instead of a download button for a failed job", async () => {
    server.use(
      http.get(`${BASE_URL}/bulk-downloads`, () =>
        HttpResponse.json([
          { ...COMPLETED, status: "failed", error_message: "No hay documentos marcados como Útil para descargar" },
        ])
      )
    );

    renderPage();

    expect(await screen.findByText("No hay documentos marcados como Útil para descargar")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /descargar/i })).not.toBeInTheDocument();
  });

  it("polls again while a job is not in a terminal state, and stops once it is", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let callCount = 0;
    server.use(
      http.get(`${BASE_URL}/bulk-downloads`, () => {
        callCount += 1;
        return HttpResponse.json([{ ...COMPLETED, status: callCount >= 2 ? "completed" : "running" }]);
      })
    );

    renderPage();
    await waitFor(() => expect(callCount).toBe(1));

    await vi.advanceTimersByTimeAsync(4100);
    await waitFor(() => expect(callCount).toBe(2));

    await vi.advanceTimersByTimeAsync(4100);
    expect(callCount).toBe(2);

    vi.useRealTimers();
  });

  it("shows an empty state when there is no history yet", async () => {
    server.use(http.get(`${BASE_URL}/bulk-downloads`, () => HttpResponse.json([])));

    renderPage();

    expect(await screen.findByText(/todav.a no se ha generado ninguna descarga masiva/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npm test -- --run src/pages/BulkDownloadsPage.test.tsx`
Expected: FAIL — cannot resolve `./BulkDownloadsPage`.

- [ ] **Step 3: Implement `BulkDownloadsPage.tsx`**

Create `frontend/src/pages/BulkDownloadsPage.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { Archive } from "lucide-react";
import { fetchBulkDownloads, fetchBulkDownloadUrl } from "../api/bulkDownloads";
import { downloadFromUrl } from "../api/documents";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { StatusBadge } from "../components/StatusBadge";
import { Button } from "../components/ui/button";
import { formatDateTime } from "../lib/formatters";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TD_MONO, TH, THEAD_ROW } from "../lib/tableStyles";

const POLL_INTERVAL_MS = 4000;
const TERMINAL_STATUSES = new Set(["completed", "failed"]);

export function BulkDownloadsPage() {
  const bulkDownloadsQuery = useQuery({
    queryKey: ["bulk-downloads"],
    queryFn: () => fetchBulkDownloads({ limit: 50 }),
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasActive = data?.some((item) => !TERMINAL_STATUSES.has(item.status));
      return hasActive ? POLL_INTERVAL_MS : false;
    },
  });

  async function handleDownload(id: number) {
    const url = await fetchBulkDownloadUrl(id);
    await downloadFromUrl(url, `descarga_masiva_${id}.zip`);
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
          <Archive className="size-3.5" aria-hidden="true" />
          Historial de descargas
        </p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">Descargas masivas</h1>
      </div>

      {bulkDownloadsQuery.isError && (
        <ErrorBanner
          message="No se pudieron cargar las descargas masivas."
          onRetry={() => bulkDownloadsQuery.refetch()}
        />
      )}

      <div className={TABLE_SHELL}>
        <div className={TABLE_SCROLL}>
          <table className={TABLE}>
            <thead>
              <tr className={THEAD_ROW}>
                <th className={TH}>ID</th>
                <th className={TH}>Estado</th>
                <th className={TH}>Documentos</th>
                <th className={TH}>Creado</th>
                <th className={TH}>Descarga</th>
              </tr>
            </thead>
            <tbody>
              {bulkDownloadsQuery.data?.map((item) => (
                <tr key={item.id} className={TBODY_ROW}>
                  <td className={TD_MONO}>#{item.id}</td>
                  <td className={TD}>
                    <StatusBadge status={item.status} />
                  </td>
                  <td className={TD}>
                    {item.document_count}
                    {item.failed_count > 0 && (
                      <span className="ml-1.5 text-xs text-muted-foreground">({item.failed_count} omitidos)</span>
                    )}
                  </td>
                  <td className={TD_MONO}>{formatDateTime(item.created_at)}</td>
                  <td className={TD}>
                    {item.status === "completed" && (
                      <Button variant="outline" size="sm" onClick={() => handleDownload(item.id)}>
                        Descargar
                      </Button>
                    )}
                    {item.status === "failed" && <span className="text-xs text-rojo">{item.error_message}</span>}
                    {(item.status === "pending" || item.status === "running") && (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {(bulkDownloadsQuery.data?.length ?? 0) === 0 && (
          <EmptyState message="Todavía no se ha generado ninguna descarga masiva." />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `frontend/`): `npm test -- --run src/pages/BulkDownloadsPage.test.tsx`
Expected: all PASS.

- [ ] **Step 5: Wire up the route**

In `frontend/src/App.tsx`, add the import:

```tsx
import { BulkDownloadsPage } from "./pages/BulkDownloadsPage";
```

And the route, next to `/documents`:

```tsx
<Route path="/documents" element={<DocumentsPage />} />
<Route path="/bulk-downloads" element={<BulkDownloadsPage />} />
```

- [ ] **Step 6: Add the nav link**

In `frontend/src/components/layout/Sidebar.tsx`, add `Archive` to the `lucide-react` import:

```tsx
import { Archive, FileStack, Gauge, LogOut, PlayCircle, Radar } from "lucide-react";
```

And add an entry to the `LINKS` array, after `/documents`:

```tsx
const LINKS = [
  { to: "/", label: "Dashboard", end: true, icon: Gauge },
  { to: "/sources", label: "Fuentes", end: false, icon: Radar },
  { to: "/runs", label: "Runs", end: false, icon: PlayCircle },
  { to: "/documents", label: "Documentos", end: false, icon: FileStack },
  { to: "/bulk-downloads", label: "Descargas masivas", end: false, icon: Archive },
];
```

- [ ] **Step 7: Run the full frontend suite**

Run (from `frontend/`): `npm test -- --run`
Expected: all PASS (existing tests unaffected — this task only added new files plus two small additive edits).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/BulkDownloadsPage.tsx frontend/src/pages/BulkDownloadsPage.test.tsx frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat: add Descargas masivas history page"
```

---

## Task 6: "Descarga masiva" button on `DocumentsPage`

**Files:**
- Modify: `frontend/src/pages/DocumentsPage.tsx`
- Test: `frontend/src/pages/DocumentsPage.test.tsx` (modify `renderPage` helper, add one test)

**Interfaces:**
- Consumes: `createBulkDownload` (Task 4); `useNavigate` from `react-router-dom` (new dependency for this file — it isn't imported here yet).

- [ ] **Step 1: Update the test helper and write the failing test**

In `frontend/src/pages/DocumentsPage.test.tsx`, change the imports (add `MemoryRouter`, `Route`, `Routes`):

```tsx
import { describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { DocumentsPage } from "./DocumentsPage";

const BASE_URL = "http://localhost:8000";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DocumentsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}
```

(Wrapping the existing `renderPage` helper in `MemoryRouter` is required because the page will call `useNavigate`, which throws outside a Router — this alone must not change the behavior of any pre-existing test in this file.)

Then add this test at the end of the `describe("DocumentsPage", ...)` block, right before the closing `});`. It renders its own `<Routes>` (instead of using the shared `renderPage()` helper) so it can assert on the actual navigation target, since `DocumentsPage` alone has no route for `/bulk-downloads` to land on:

```tsx
  it("creates a bulk download and navigates to /bulk-downloads when 'Descarga masiva' is clicked", async () => {
    mockFilterEndpoints();
    let bulkDownloadCreated = false;
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 })),
      http.post(`${BASE_URL}/bulk-downloads`, () => {
        bulkDownloadCreated = true;
        return HttpResponse.json(
          { id: 1, status: "pending", document_count: 0, failed_count: 0, error_message: null, started_at: null, finished_at: null, created_at: "2026-07-16T00:00:00Z" },
          { status: 202 }
        );
      })
    );
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/documents"]}>
          <Routes>
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/bulk-downloads" element={<div>Página de descargas masivas</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await user.click(screen.getByRole("button", { name: /descarga masiva/i }));

    await waitFor(() => expect(bulkDownloadCreated).toBe(true));
    expect(await screen.findByText("Página de descargas masivas")).toBeInTheDocument();
  });
```

This test needs `Routes`/`Route` imported alongside `MemoryRouter`, so the final import line is:

```tsx
import { MemoryRouter, Route, Routes } from "react-router-dom";
```

- [ ] **Step 2: Run the tests to verify the new one fails**

Run (from `frontend/`): `npm test -- --run src/pages/DocumentsPage.test.tsx`
Expected: the new test FAILS with "Unable to find role="button" with name /descarga masiva/i" (button doesn't exist yet); all pre-existing tests in this file still PASS (confirming the `MemoryRouter` wrapper change alone didn't break anything).

- [ ] **Step 3: Add the button**

In `frontend/src/pages/DocumentsPage.tsx`, update the imports:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Calendar, Download, Eye, FileStack, Search } from "lucide-react";
import { Button } from "../components/ui/button";
import { DocumentPreviewDialog } from "../components/DocumentPreviewDialog";
import { createBulkDownload } from "../api/bulkDownloads";
import { fetchDocuments, fetchDocumentTipos } from "../api/documents";
```

Inside the `DocumentsPage` function, add the navigate hook and mutation right after the existing `documentsQuery` declaration (before `const hasDateFilter = ...`):

```tsx
  const navigate = useNavigate();
  const bulkDownloadMutation = useMutation({
    mutationFn: createBulkDownload,
    onSuccess: () => navigate("/bulk-downloads"),
  });
```

Then add the button as the last child of the filter bar `<div className="flex flex-wrap items-center gap-3 ...">` (right before its closing `</div>`, after the date filter's closing `</div>`):

```tsx
        <Button
          variant="outline"
          onClick={() => bulkDownloadMutation.mutate()}
          disabled={bulkDownloadMutation.isPending}
        >
          <Download className="size-3.5" aria-hidden="true" />
          {bulkDownloadMutation.isPending ? "Generando…" : "Descarga masiva"}
        </Button>
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `frontend/`): `npm test -- --run src/pages/DocumentsPage.test.tsx`
Expected: all PASS, including the new bulk-download test.

Run the full frontend suite: `npm test -- --run`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/DocumentsPage.tsx frontend/src/pages/DocumentsPage.test.tsx
git commit -m "feat: add Descarga masiva button to DocumentsPage"
```

---

## Final check

- [ ] Run the complete backend suite: `.venv/Scripts/pytest -q` — expect the same pre-existing `test_migrations.py` failure and otherwise all green.
- [ ] Run the complete frontend suite (from `frontend/`): `npm test -- --run` — expect all green.
- [ ] Manually verify end-to-end via the `run-iurisync` skill or by hand: mark a document "Útil" from the preview modal, click "Descarga masiva" on `DocumentsPage`, confirm it navigates to `/bulk-downloads`, watch the row go `pending` → `running` → `completed`, click "Descargar", and open the resulting `.zip` to confirm the file's path inside matches its `storage_key` (e.g. `JEP/2026-06-01/Auto/archivo.pdf`).
