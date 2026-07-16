import pytest
import responses
from sqlalchemy.orm import sessionmaker

from core.db import repository
from core.models import RawDocModel
from tests.conftest import DummyFamilyScraper, TEST_S3_BUCKET
from worker.celery_app import celery_app
from worker.tasks import scrape_source_task, generate_document_preview_pdf


@responses.activate
def test_scrape_source_task_downloads_new_document_and_marks_run_source_completed(db_session, test_engine, monkeypatch):
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/doc1", "method": "GET"},
            title="Documento 1",
            tipo="Auto",
            f_public="2026-01-01",
        )
    ]
    responses.add(
        responses.GET,
        "https://example.com/doc1",
        body=b"contenido",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )

    # Note: the task's `finally: db.close()` would detach/expire objects held by the test's own
    # db_session if the task reused it directly (observed as a flaky DetachedInstanceError on the
    # `run`/`run_source` objects created above). Per the brief's documented fallback, give the task
    # its own session bound to the same test_engine instead of reusing db_session.
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    scrape_source_task(run_source.id)

    # Re-query via a fresh session rather than db_session: db_session's identity map already
    # holds the run_source object from creation above, and a plain SELECT does not overwrite
    # attributes of an already-identity-mapped, non-expired instance, so it would return the
    # stale "pending" status instead of what the task's (separate) session committed.
    assertion_session = task_session_factory()
    try:
        [refreshed] = repository.list_run_sources(assertion_session, run.id)
        assert refreshed.status == "completed"
        assert refreshed.docs_new == 1
        assert refreshed.docs_errors == 0
    finally:
        assertion_session.close()


@responses.activate
def test_scrape_source_task_uploads_file_with_the_correct_content_type(db_session, test_engine, monkeypatch):
    """Regression test: the uploaded object's Content-Type in storage must match what
    the source actually served (result.content_type), not silently fall back to S3's
    default of binary/octet-stream. A mismatch here breaks the inline previewer: the
    browser renders (or downloads) a blob based on the stored object's own Content-Type
    header, not our documents.content_type DB column — found for real against JEP's
    native-PDF documents, whose preview silently downloaded instead of rendering."""
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/doc2", "method": "GET"},
            title="Documento 2",
            tipo="Auto",
            f_public="2026-01-01",
        )
    ]
    responses.add(
        responses.GET,
        "https://example.com/doc2",
        body=b"contenido pdf",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    scrape_source_task(run_source.id)

    assertion_session = task_session_factory()
    try:
        items, _ = repository.list_documents(assertion_session, source_id=source.id)
        [document] = items
    finally:
        assertion_session.close()

    from core.storage import _client

    head = _client().head_object(Bucket=document.storage_bucket, Key=document.storage_key)
    assert head["ContentType"] == "application/pdf"


def _settings_with_test_bucket():
    from core.config import get_settings

    settings = get_settings()
    settings.s3_bucket = TEST_S3_BUCKET
    return settings


def test_generate_document_preview_pdf_converts_and_saves_the_key(db_session, test_engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from core.db import repository
    from worker.tasks import generate_document_preview_pdf

    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})

    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-2",
        source_id=source.id,
        title="T-200/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-200-26.rtf",
        content_type="application/rtf",
    )

    from core.storage import upload_file
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        rtf_path = Path(tmp) / "T-200-26.rtf"
        rtf_path.write_text("contenido rtf de prueba")
        upload_file(rtf_path, document.storage_key, bucket="iurisync-test")

    class _FakeWordConverter:
        def convert(self, input_path, target_format):
            assert target_format == "pdf"
            output_path = input_path.with_suffix(".pdf")
            output_path.write_bytes(b"%PDF-1.4 contenido convertido")
            return output_path

        def quit(self):
            pass

    monkeypatch.setattr("worker.tasks.WordConverter", _FakeWordConverter)
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    result = generate_document_preview_pdf(document.id)

    assert result == "Corte Constitucional/2026-06-30/Tutela/T-200-26.preview.pdf"

    assertion_session = task_session_factory()
    try:
        refreshed = repository.get_document(assertion_session, document.id)
        assert refreshed.preview_storage_key == "Corte Constitucional/2026-06-30/Tutela/T-200-26.preview.pdf"
    finally:
        assertion_session.close()


def test_generate_document_preview_pdf_is_idempotent_when_already_generated(db_session, test_engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from core.db import repository
    from worker.tasks import generate_document_preview_pdf

    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-3",
        source_id=source.id,
        title="T-201/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-201-26.rtf",
        content_type="application/rtf",
    )
    repository.set_document_preview_key(db_session, document.id, "already/cached.preview.pdf")

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("no debería intentar convertir de nuevo si ya existe preview_storage_key")

    monkeypatch.setattr("worker.tasks.download_file", _fail_if_called)

    result = generate_document_preview_pdf(document.id)

    assert result == "already/cached.preview.pdf"


def test_generate_document_preview_pdf_propagates_conversion_failure_without_saving_a_key(db_session, test_engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from core.db import repository
    from worker.tasks import generate_document_preview_pdf

    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-conversion-fails",
        source_id=source.id,
        title="T-205/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-205-26.rtf",
        content_type="application/rtf",
    )

    from core.storage import upload_file
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        rtf_path = Path(tmp) / "T-205-26.rtf"
        rtf_path.write_text("contenido rtf de prueba")
        upload_file(rtf_path, document.storage_key, bucket="iurisync-test")

    class _FailingWordConverter:
        def convert(self, input_path, target_format):
            raise RuntimeError("Word no pudo convertir el archivo")

        def quit(self):
            pass

    monkeypatch.setattr("worker.tasks.WordConverter", _FailingWordConverter)
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    with pytest.raises(RuntimeError, match="Word no pudo convertir el archivo"):
        generate_document_preview_pdf(document.id)

    assertion_session = task_session_factory()
    try:
        refreshed = repository.get_document(assertion_session, document.id)
        assert refreshed.preview_storage_key is None
    finally:
        assertion_session.close()
