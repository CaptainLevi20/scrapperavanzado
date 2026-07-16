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
def test_scrape_source_task_processes_multiple_documents_concurrently(db_session, test_engine, monkeypatch):
    """Downloading/converting/uploading now happens on a thread pool (see
    MAX_CONCURRENT_DOCUMENT_DOWNLOADS) instead of one document at a time — this
    verifies a batch with a success, a not-yet-published document (soft 404 via
    HTML response), and a hard failure (HTTP 500) are all handled correctly when
    processed concurrently, with the right counts landing in run_source."""
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/multi-ok", "method": "GET"},
            title="Documento OK",
            tipo="Auto",
            f_public="2026-01-01",
        ),
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/multi-not-published", "method": "GET"},
            title="Documento no publicado",
            tipo="Auto",
            f_public="2026-01-01",
        ),
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/multi-error", "method": "GET"},
            title="Documento con error",
            tipo="Auto",
            f_public="2026-01-01",
        ),
    ]
    responses.add(
        responses.GET,
        "https://example.com/multi-ok",
        body=b"contenido ok",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://example.com/multi-not-published",
        body="<!DOCTYPE html><html><body>No disponible</body></html>",
        headers={"Content-Type": "text/html; charset=utf-8"},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://example.com/multi-error",
        body="error interno",
        status=500,
    )

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    scrape_source_task(run_source.id)

    assertion_session = task_session_factory()
    try:
        [refreshed] = repository.list_run_sources(assertion_session, run.id)
        assert refreshed.status == "completed"
        assert refreshed.docs_new == 1
        assert refreshed.docs_errors == 1

        items, total = repository.list_documents(assertion_session, source_id=source.id)
        assert total == 1
        assert items[0].title == "Documento OK"
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

    def _fake_convert_to_pdf(input_path, timeout=180):
        output_path = input_path.with_suffix(".pdf")
        output_path.write_bytes(b"%PDF-1.4 contenido convertido")
        return output_path

    monkeypatch.setattr("worker.tasks.convert_to_pdf_via_libreoffice", _fake_convert_to_pdf)
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

    def _failing_convert_to_pdf(input_path, timeout=180):
        raise RuntimeError("LibreOffice no pudo convertir el archivo")

    monkeypatch.setattr("worker.tasks.convert_to_pdf_via_libreoffice", _failing_convert_to_pdf)
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    with pytest.raises(RuntimeError, match="LibreOffice no pudo convertir el archivo"):
        generate_document_preview_pdf(document.id)

    assertion_session = task_session_factory()
    try:
        refreshed = repository.get_document(assertion_session, document.id)
        assert refreshed.preview_storage_key is None
    finally:
        assertion_session.close()


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


def test_build_bulk_download_zip_fails_when_every_document_fails_to_download(db_session, test_engine, monkeypatch):
    from worker.tasks import build_bulk_download_zip

    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    repository.create_source_family(db_session, key="jep", display_name="JEP")
    source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})

    # Ambos documentos apuntan a claves que nunca se subieron — download_file
    # fallará para los dos, dejando `downloaded` vacío.
    repository.insert_document(
        db_session, doc_id="doc-missing-1", source_id=source.id, title="Missing 1", review_status="useful",
        storage_bucket=TEST_S3_BUCKET, storage_key="JEP/2026-06-01/Auto/no-existe-1.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-missing-2", source_id=source.id, title="Missing 2", review_status="useful",
        storage_bucket=TEST_S3_BUCKET, storage_key="JEP/2026-06-01/Auto/no-existe-2.pdf",
    )

    bulk_download = repository.create_bulk_download(db_session)

    build_bulk_download_zip(bulk_download.id)

    assertion_session = task_session_factory()
    try:
        refreshed = repository.get_bulk_download(assertion_session, bulk_download.id)
        assert refreshed.status == "failed"
        assert refreshed.error_message == "No se pudo leer ninguno de los 2 documentos útiles"
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
