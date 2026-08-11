import time
from datetime import date

import pytest
import responses
from sqlalchemy.orm import sessionmaker

import worker.tasks as tasks_module
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
def test_scrape_source_task_stores_radicado_from_the_scraped_document(db_session, test_engine, monkeypatch):
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
            radicado="25001233300020260001200",
        )
    ]
    responses.add(
        responses.GET,
        "https://example.com/doc1",
        body=b"contenido",
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
        assert document.radicado == "25001233300020260001200"
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
def test_scrape_source_task_deduplicates_the_same_document_appearing_twice_in_one_scrap(
    db_session, test_engine, monkeypatch
):
    """Regression test: a source listing the same document twice in one
    scrap() pass (pagination overlap, a listing bug on the remote site) used
    to download and upload BOTH occurrences to storage — the DB write was
    protected (on_conflict_do_nothing), but the second upload became a
    permanently orphaned object nobody references, and docs_new counted it as
    a second new document even though only one was ever saved."""
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    duplicated_doc = RawDocModel(
        source="Dummy Source",
        link={"url": "https://example.com/duplicated", "method": "GET"},
        title="Documento duplicado",
        tipo="Auto",
        f_public="2026-01-01",
    )
    DummyFamilyScraper.docs_to_return = [duplicated_doc, duplicated_doc]

    call_count = {"n": 0}

    def _callback(request):
        call_count["n"] += 1
        return (200, {"Content-Type": "application/pdf"}, b"contenido")

    responses.add_callback(responses.GET, "https://example.com/duplicated", callback=_callback)

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    scrape_source_task(run_source.id)

    assert call_count["n"] == 1  # the second occurrence never gets downloaded at all

    assertion_session = task_session_factory()
    try:
        [refreshed] = repository.list_run_sources(assertion_session, run.id)
        assert refreshed.status == "completed"
        assert refreshed.docs_new == 1
        assert refreshed.docs_errors == 0

        _, total = repository.list_documents(assertion_session, source_id=source.id)
        assert total == 1
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
def test_scrape_source_task_matches_existing_document_by_stable_doc_id_ignoring_publication_date(
    db_session, test_engine, monkeypatch
):
    # Rama Judicial-style family: f_public is a listing-occurrence date, not an
    # intrinsic document date, so the source can re-list the same file under a
    # new f_public. doc_id_uses_publication_date=False must still match this
    # against the pre-existing document (by url/body key alone) so it goes
    # through the replace/versioning path instead of being inserted as new.
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    existing_doc = repository.insert_document(
        db_session,
        # sha1("https://example.com/doc1") - compute_doc_id(doc, include_publication_date=False)
        doc_id="99e8f097d9e596cafcea365756719ae6af3e3213",
        source_id=source.id,
        title="Documento 1",
        storage_bucket="iurisync-test",
        storage_key="old-key.pdf",
        content_type="application/pdf",
        file_size_bytes=9,
        source_url="https://example.com/doc1",
        review_status="useful",
    )

    DummyFamilyScraper.doc_id_uses_publication_date = False
    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/doc1", "method": "GET"},
            title="Documento 1",
            tipo="Auto",
            f_public="2026-06-11",  # distinta a la fecha original con la que se insertó existing_doc
        )
    ]
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

    try:
        scrape_source_task(run_source.id)

        assertion_session = task_session_factory()
        try:
            [refreshed_source] = repository.list_run_sources(assertion_session, run.id)
            assert refreshed_source.docs_new == 0
            assert refreshed_source.docs_updated == 1

            updated_document = repository.get_document(assertion_session, existing_doc.id)
            assert updated_document.file_size_bytes == 20
        finally:
            assertion_session.close()
    finally:
        DummyFamilyScraper.doc_id_uses_publication_date = True  # restore the class-level default for later tests


@responses.activate
def test_scrape_source_task_calls_resolve_unverified_document_for_flagged_docs(db_session, test_engine, monkeypatch):
    """Wiring check: a doc scraped with title_unverified=True must have the
    scraper's resolve_unverified_document called on it (with the real,
    downloaded local file) before it's inserted, and the correction it makes
    must land in the stored document — including storage_key, which is resolved
    from the pre-correction title before resolve_unverified_document runs and
    must be rebuilt from the corrected one (see core.utils.rekey_filename), or
    bulk-download ZIPs (which use storage_key, not title, as the entry name)
    would still show the old, uncorrected name."""
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/doc1", "method": "GET"},
            title="doc",
            title_unverified=True,
            tipo="Desconocido",
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

    def _resolve_unverified_document(self, doc, local_path, content_type):
        assert local_path.exists()  # el archivo ya se descargó de verdad para este punto
        doc.title = "recuperado-del-archivo"
        doc.tipo = "Auto"

    monkeypatch.setattr(DummyFamilyScraper, "resolve_unverified_document", _resolve_unverified_document)

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    scrape_source_task(run_source.id)

    assertion_session = task_session_factory()
    try:
        items, _ = repository.list_documents(assertion_session, source_id=source.id)
        [document] = items
        assert document.title == "recuperado-del-archivo"
        assert document.tipo == "Auto"
        assert document.storage_key.endswith("recuperado-del-archivo.pdf")
        assert "doc1" not in document.storage_key
    finally:
        assertion_session.close()


@responses.activate
def test_scrape_source_task_does_not_rekey_storage_when_the_hook_leaves_the_title_unchanged(
    db_session, test_engine, monkeypatch
):
    """Regression test: Rama Judicial's resolve_unverified_document only fills
    doc.f_providencia from the downloaded PDF — it never touches doc.title. If
    scrape_source_task still called rekey_filename unconditionally after the
    hook (as it did before this fix), the descriptive storage_key built from
    save_path would get rewritten to the short canonical radicado title,
    losing the descriptive detail and risking two actuaciones of the same
    radicado colliding on the same storage_key. The rekey must only happen
    when the hook actually changed doc.title (SAMAI/CSJ's placeholder-title
    case), not whenever title_unverified=True."""
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/doc1", "method": "GET"},
            title="T_BTA_11001_31_03_022_2019_00814_02",
            title_unverified=True,
            tipo="Auto",
            f_public="2026-01-01",
            save_path="Dummy/2026-01-01/Auto/DescriptivoLargo(extension)",
        )
    ]
    responses.add(
        responses.GET,
        "https://example.com/doc1",
        body=b"contenido",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )

    def _resolve_unverified_document(self, doc, local_path, content_type):
        # Como Rama Judicial: solo fija f_providencia, NO cambia doc.title.
        doc.f_providencia = "2026-08-10"

    monkeypatch.setattr(DummyFamilyScraper, "resolve_unverified_document", _resolve_unverified_document)

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    scrape_source_task(run_source.id)

    assertion_session = task_session_factory()
    try:
        items, _ = repository.list_documents(assertion_session, source_id=source.id)
        [document] = items
        assert document.storage_key.endswith("DescriptivoLargo.pdf")
        assert "T_BTA" not in document.storage_key
        assert document.f_providencia == date(2026, 8, 10)
    finally:
        assertion_session.close()


@responses.activate
def test_scrape_source_task_applies_auto_review_status_from_family_params_for_new_documents(
    db_session, test_engine, monkeypatch
):
    """A source can declare family_params={"auto_review_status": "useful"} (e.g. the
    sources team confirming everything from Corte Constitucional is useful) so brand
    new documents land already reviewed instead of "pending"."""
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(
        db_session, family_key="test-dummy", name="Dummy Source", family_params={"auto_review_status": "useful"}
    )
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

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    scrape_source_task(run_source.id)

    assertion_session = task_session_factory()
    try:
        items, _ = repository.list_documents(assertion_session, source_id=source.id)
        [document] = items
        assert document.review_status == "useful"
    finally:
        assertion_session.close()


@responses.activate
def test_scrape_source_task_applies_auto_review_status_from_family_params_on_republication(
    db_session, test_engine, monkeypatch
):
    """The same auto_review_status override must also apply when a document is
    replaced due to republication, not just on first insert — otherwise a
    republished Corte Constitucional document would fall back to "pending"."""
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(
        db_session, family_key="test-dummy", name="Dummy Source", family_params={"auto_review_status": "useful"}
    )
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
        file_size_bytes=9,
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
    responses.add(responses.HEAD, "https://example.com/doc1", headers={"Content-Length": "20"}, status=200)
    responses.add(
        responses.GET,
        "https://example.com/doc1",
        body=b"contenido mas largo!",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    scrape_source_task(run_source.id)

    assertion_session = task_session_factory()
    try:
        updated_document = repository.get_document(assertion_session, existing_doc.id)
        assert updated_document.review_status == "useful"
    finally:
        assertion_session.close()


@responses.activate
def test_scrape_source_task_does_not_forward_auto_review_status_to_scraper_constructor(
    db_session, test_engine, monkeypatch
):
    """family_params={"auto_review_status": ...} is orchestration-only metadata
    read directly by scrape_source_task (see the auto_review_status tests above) -
    it must not also be forwarded into resolve_scraper's cls(**params) call. Real
    family scrapers (ScrapConstitucional, Cndj, Jep, ...) take no **kwargs, so any
    orchestration-only key leaking through blows up their __init__ with an
    unexpected keyword argument. StrictFamilyScraper (unlike DummyFamilyScraper)
    reproduces that real constructor shape."""
    from tests.conftest import StrictFamilyScraper

    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-strict", display_name="Strict")
    source = repository.create_source(
        db_session, family_key="test-strict", name="Strict Source", family_params={"auto_review_status": "useful"}
    )
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    StrictFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Strict Source",
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

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    scrape_source_task(run_source.id)

    assertion_session = task_session_factory()
    try:
        [refreshed] = repository.list_run_sources(assertion_session, run.id)
        assert refreshed.status == "completed", refreshed.error_message
        items, _ = repository.list_documents(assertion_session, source_id=source.id)
        [document] = items
        assert document.review_status == "useful"
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


@responses.activate
def test_scrape_source_task_uploads_nothing_when_head_is_inconclusive_but_real_size_is_unchanged(db_session, test_engine, monkeypatch):
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
        file_size_bytes=9,  # tamaño de "contenido"
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
    # El HEAD no trae Content-Length (inconcluso) — dispara la descarga completa de
    # respaldo. El contenido real descargado ("contenido", 9 bytes) resulta ser
    # idéntico al ya guardado, así que no debe subirse nada nuevo ni tocarse el
    # documento ni crearse ninguna versión.
    responses.add(responses.HEAD, "https://example.com/doc1", status=200)  # sin Content-Length
    responses.add(
        responses.GET,
        "https://example.com/doc1",
        body=b"contenido",
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
        assert refreshed_source.docs_new == 0
        assert refreshed_source.docs_updated == 0
        assert refreshed_source.docs_errors == 0

        unchanged_document = repository.get_document(assertion_session, existing_doc.id)
        assert unchanged_document.storage_key == "old-key.pdf"  # nunca se tocó

        assert repository.list_document_versions(assertion_session, existing_doc.id) == []  # no se creó versión
    finally:
        assertion_session.close()


@responses.activate
def test_scrape_source_task_records_a_db_write_failure_as_an_error_and_still_completes(
    db_session, test_engine, monkeypatch
):
    """Regression test: a DB write failing for one document (IntegrityError,
    OperationalError, a dropped connection) used to propagate out of the whole
    task uncaught, skipping the final set_run_source_status call and leaving the
    source stuck 'running' forever. It must instead be recorded like a download
    error, and the rest of the documents must still be processed normally."""
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/db-fail", "method": "GET"},
            title="Documento con fallo de base de datos",
            tipo="Auto",
            f_public="2026-01-01",
        ),
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/db-ok", "method": "GET"},
            title="Documento OK",
            tipo="Auto",
            f_public="2026-01-01",
        ),
    ]
    responses.add(
        responses.GET,
        "https://example.com/db-fail",
        body=b"contenido con fallo",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://example.com/db-ok",
        body=b"contenido ok",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )

    real_insert_document = repository.insert_document_reporting_whether_created

    def _flaky_insert_document(db, **fields):
        if fields["title"] == "Documento con fallo de base de datos":
            raise RuntimeError("conexión con la base de datos perdida")
        return real_insert_document(db, **fields)

    monkeypatch.setattr("worker.tasks.repository.insert_document_reporting_whether_created", _flaky_insert_document)

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

        from sqlalchemy import select

        from core.db.models import RunError

        errors = list(
            assertion_session.scalars(select(RunError).where(RunError.run_source_id == run_source.id))
        )
        assert len(errors) == 1
        assert "conexión con la base de datos perdida" in errors[0].message
    finally:
        assertion_session.close()


@responses.activate
def test_scrape_source_task_marks_the_source_as_failed_instead_of_stuck_running_on_an_unexpected_crash(
    db_session, test_engine, monkeypatch
):
    """Regression test: any unexpected exception while processing documents (not
    just the per-document DB write failures covered above) must still leave the
    source in a terminal state. Simulates a bug elsewhere in the processing loop
    (compute_doc_id raising) — the source must end up 'failed' with an
    error_message, never left stuck at 'running'."""
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/doc-crash", "method": "GET"},
            title="Documento",
            tipo="Auto",
            f_public="2026-01-01",
        )
    ]

    def _raise(*_args, **_kwargs):
        raise RuntimeError("error inesperado calculando doc_id")

    monkeypatch.setattr("worker.tasks.compute_doc_id", _raise)

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    scrape_source_task(run_source.id)

    assertion_session = task_session_factory()
    try:
        [refreshed] = repository.list_run_sources(assertion_session, run.id)
        assert refreshed.status == "failed"
        assert refreshed.status != "running"
        assert "error inesperado calculando doc_id" in refreshed.error_message
        assert refreshed.finished_at is not None
    finally:
        assertion_session.close()


@responses.activate
def test_scrape_source_task_records_a_scraper_reported_error_as_a_run_error(db_session, test_engine, monkeypatch):
    """Regression test: family scrapers already call on_progress(f'... Error ...')
    when they recover from a partial failure (a page, section, or date range that
    broke but didn't abort the whole scrap) — but nothing in production ever
    passed on_progress in, so those messages were generated and immediately lost.
    The source stays 'completed' (the scraper did recover real documents), but
    the error must now show up as a RunError and count toward docs_errors,
    instead of the run looking clean when a chunk of documents is actually
    missing."""
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/partial-ok", "method": "GET"},
            title="Documento recuperado",
            tipo="Auto",
            f_public="2026-01-01",
        )
    ]

    def _scrap_with_a_recovered_error(self, fini, ffin, on_progress=None, **kwargs):
        if on_progress:
            on_progress("[Dummy Source] Procesando…")  # progress message, not an error
            on_progress("[Dummy Source] Error consultando página 2: 503 Service Unavailable")
        return DummyFamilyScraper.docs_to_return

    monkeypatch.setattr(DummyFamilyScraper, "scrap", _scrap_with_a_recovered_error)

    responses.add(
        responses.GET,
        "https://example.com/partial-ok",
        body=b"contenido",
        headers={"Content-Type": "application/pdf"},
        status=200,
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

        from sqlalchemy import select

        from core.db.models import RunError

        errors = list(
            assertion_session.scalars(select(RunError).where(RunError.run_source_id == run_source.id))
        )
        assert len(errors) == 1
        assert "503 Service Unavailable" in errors[0].message
    finally:
        assertion_session.close()


def test_scrape_source_task_does_no_work_when_the_run_was_already_cancelled(db_session, test_engine, monkeypatch):
    """Regression test: a source task that hadn't started yet (still queued
    behind others in the chord) used to do a full scrap() and download run
    even if the whole run had already been cancelled. It must now bail out
    immediately, before touching the scraper at all."""
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)
    repository.request_run_cancel(db_session, run.id)

    scrap_calls = {"count": 0}

    def _scrap_that_should_never_run(self, fini, ffin, **kwargs):
        scrap_calls["count"] += 1
        return []

    monkeypatch.setattr(DummyFamilyScraper, "scrap", _scrap_that_should_never_run)

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)

    scrape_source_task(run_source.id)

    assert scrap_calls["count"] == 0
    assertion_session = task_session_factory()
    try:
        [refreshed] = repository.list_run_sources(assertion_session, run.id)
        assert refreshed.status == "cancelled"
    finally:
        assertion_session.close()


def test_scrape_source_task_marks_cancelled_not_completed_when_cancel_requested_mid_enumeration(
    db_session, test_engine, monkeypatch
):
    """Regression test: cancelling while still enumerating which documents are
    new/republished already stopped the loop (`break`), but the source still
    ended up reported as 'completed' — the cancellation itself left no trace."""
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/never-fetched", "method": "GET"},
            title="Nunca se descarga",
            tipo="Auto",
            f_public="2026-01-01",
        )
    ]

    calls = {"n": 0}
    real_is_cancel_requested = repository.is_cancel_requested

    def _is_cancel_requested(db, run_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return False  # el chequeo inicial, antes de "running"
        return True  # el chequeo dentro del ciclo de enumeración

    monkeypatch.setattr(repository, "is_cancel_requested", _is_cancel_requested)

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)

    scrape_source_task(run_source.id)

    monkeypatch.setattr(repository, "is_cancel_requested", real_is_cancel_requested)
    assertion_session = task_session_factory()
    try:
        [refreshed] = repository.list_run_sources(assertion_session, run.id)
        assert refreshed.status == "cancelled"
        assert refreshed.docs_new == 0

        _, total = repository.list_documents(assertion_session, source_id=source.id)
        assert total == 0  # nunca se llegó a descargar
    finally:
        assertion_session.close()


@responses.activate
def test_scrape_source_task_interrupts_an_in_flight_download_when_cancelled_mid_run(
    db_session, test_engine, monkeypatch
):
    """Regression test: once a document's download actually started, cancelling
    the run used to have zero effect — nothing re-checked cancel_requested until
    the whole thing finished. A cancellation that arrives while a download is
    already in flight must now interrupt it (via stop_event) and the source
    must end up 'cancelled', not 'completed'."""
    celery_app.conf.task_always_eager = True
    monkeypatch.setattr(tasks_module, "CANCEL_POLL_INTERVAL_SECONDS", 0.02)

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/cancel-mid-download", "method": "GET"},
            title="Documento cancelado a mitad de camino",
            tipo="Auto",
            f_public="2026-01-01",
        )
    ]

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    def _slow_callback(request):
        # Cancela el run justo cuando la descarga ya inició — el poller (con
        # intervalo casi cero) debería notarlo durante el sleep de abajo.
        cancel_session = task_session_factory()
        try:
            repository.request_run_cancel(cancel_session, run.id)
        finally:
            cancel_session.close()
        time.sleep(0.3)
        return (200, {"Content-Type": "application/pdf"}, b"contenido que nunca deberia guardarse")

    responses.add_callback(responses.GET, "https://example.com/cancel-mid-download", callback=_slow_callback)

    scrape_source_task(run_source.id)

    assertion_session = task_session_factory()
    try:
        [refreshed] = repository.list_run_sources(assertion_session, run.id)
        assert refreshed.status == "cancelled"
        assert refreshed.docs_new == 0

        _, total = repository.list_documents(assertion_session, source_id=source.id)
        assert total == 0
    finally:
        assertion_session.close()


@responses.activate
def test_scrape_source_task_cancellation_poller_never_touches_the_run_orm_object(
    db_session, test_engine, monkeypatch
):
    """Regression test: the poller thread used to call
    is_cancel_requested(poll_db, run.id) — `run` is an ORM object bound to the
    task's own `db` session, not the poller's `poll_db`. SQLAlchemy expires
    every object on a session after each commit, so `run.id` (an attribute
    access, not a plain value) can trigger a lazy re-query through `db` from
    the poller's own thread — a second thread touching a session the main
    thread may be using at that exact moment, which corrupted its transaction
    state ("session is in 'prepared' state") during a real, high-volume
    Consejo de Estado run. The poller must use a plain int captured once up
    front, so it never dereferences `run` at all.

    The exact race is timing-dependent (needs the main thread's commit and the
    poller's lazy-load to land on the session at the same instant) and isn't
    reliably reproducible against the fast in-memory test DB used here — this
    doesn't fail against the pre-fix code. What it does verify, deterministically,
    is that the fixed code path runs correctly end to end under real concurrent
    load: two documents downloaded in parallel (one fast, whose commit expires
    every object attached to `db` including `run` — exactly what happens
    repeatedly in production; one slow, which cancels the run and sleeps long
    enough for the poller, at a 20ms interval, to notice) without raising, and
    that the poller only ever received a plain int, never the ORM object."""
    celery_app.conf.task_always_eager = True
    monkeypatch.setattr(tasks_module, "CANCEL_POLL_INTERVAL_SECONDS", 0.02)

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)
    run_id = run.id

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/fast", "method": "GET"},
            title="Documento rapido (dispara el commit que expira run)",
            tipo="Auto",
            f_public="2026-01-01",
        ),
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/cancel-mid-download", "method": "GET"},
            title="Documento cancelado mientras run esta expirado",
            tipo="Auto",
            f_public="2026-01-01",
        ),
    ]

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    recorded_run_ids = []
    real_is_cancel_requested = repository.is_cancel_requested

    def _recording_is_cancel_requested(db, passed_run_id):
        recorded_run_ids.append(passed_run_id)
        return real_is_cancel_requested(db, passed_run_id)

    monkeypatch.setattr(repository, "is_cancel_requested", _recording_is_cancel_requested)

    responses.add(
        responses.GET,
        "https://example.com/fast",
        status=200,
        headers={"Content-Type": "application/pdf"},
        body=b"contenido rapido",
    )

    def _slow_callback(request):
        cancel_session = task_session_factory()
        try:
            repository.request_run_cancel(cancel_session, run_id)
        finally:
            cancel_session.close()
        time.sleep(0.3)
        return (200, {"Content-Type": "application/pdf"}, b"contenido que nunca deberia guardarse")

    responses.add_callback(responses.GET, "https://example.com/cancel-mid-download", callback=_slow_callback)

    # Must not raise — the old code could hit InvalidRequestError /
    # DetachedInstanceError from the poller thread lazily reloading `run`
    # (expired by the fast document's commit) through the wrong session.
    scrape_source_task(run_source.id)

    assert recorded_run_ids, "is_cancel_requested was never called"
    assert all(isinstance(rid, int) and rid == run_id for rid in recorded_run_ids)

    assertion_session = task_session_factory()
    try:
        [refreshed] = repository.list_run_sources(assertion_session, run.id)
        assert refreshed.status == "cancelled"
        assert refreshed.docs_new == 1  # only the fast one made it in
    finally:
        assertion_session.close()


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
        # Regression test: the bucket the zip actually landed in used to be
        # discarded entirely (upload_file's return value was never captured),
        # so the API had no choice but to always assume the CURRENT default
        # bucket setting when signing a download URL later.
        assert refreshed.storage_bucket == TEST_S3_BUCKET

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


def test_build_bulk_download_zip_skips_a_document_with_an_unsafe_storage_key(db_session, test_engine, monkeypatch):
    """Regression test: storage_key is joined onto a real local directory
    (downloads_dir / storage_key) and used as the ZIP's arcname. A row whose key
    contains '..' — from an older, pre-sanitization version of the code, or a
    directly-edited row — must be skipped instead of trusted, since either use
    would let it write or read outside the intended directory."""
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
    repository.insert_document(
        db_session, doc_id="doc-unsafe", source_id=source.id, title="Unsafe", review_status="useful",
        storage_bucket=TEST_S3_BUCKET, storage_key="../../etc/passwd",
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


def test_build_bulk_download_zip_frees_each_raw_copy_as_soon_as_its_zipped(db_session, test_engine, monkeypatch):
    """Regression test: before this fix, every downloaded file stayed on disk
    until the whole batch finished and only then got zipped, so disk usage
    peaked at roughly twice the total size (every raw copy plus the zip being
    built). Now each raw copy is deleted right after being added to the zip,
    so at most one extra file's worth of disk should ever be in use at once."""
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

    keys = ["doc1.pdf", "doc2.pdf", "doc3.pdf"]
    with tempfile.TemporaryDirectory() as tmp:
        for key in keys:
            local = Path(tmp) / key
            local.write_bytes(b"x" * 100)
            upload_file(local, f"JEP/2026-06-01/Auto/{key}", bucket=TEST_S3_BUCKET, content_type="application/pdf")
    for i, key in enumerate(keys):
        repository.insert_document(
            db_session, doc_id=f"doc-{i}", source_id=source.id, title=f"Doc {i}", review_status="useful",
            storage_bucket=TEST_S3_BUCKET, storage_key=f"JEP/2026-06-01/Auto/{key}",
        )

    files_present_before_each_download = []
    real_download_file = tasks_module.download_file

    def _spying_download_file(bucket, key, local_path):
        # Cuenta cuántos archivos ya descargados siguen en disco justo antes de
        # bajar el siguiente — si el arreglo funciona, siempre debe ser 0.
        downloads_dir = next(p for p in local_path.parents if p.name == "files")
        files_present_before_each_download.append(sum(1 for p in downloads_dir.rglob("*") if p.is_file()))
        return real_download_file(bucket, key, local_path)

    monkeypatch.setattr(tasks_module, "download_file", _spying_download_file)

    bulk_download = repository.create_bulk_download(db_session)
    build_bulk_download_zip(bulk_download.id)

    assert files_present_before_each_download == [0, 0, 0]

    assertion_session = task_session_factory()
    try:
        refreshed = repository.get_bulk_download(assertion_session, bulk_download.id)
        assert refreshed.status == "completed"
        assert refreshed.document_count == 3
    finally:
        assertion_session.close()


def test_build_bulk_download_zip_fails_early_when_disk_space_is_insufficient(db_session, test_engine, monkeypatch):
    """Regression test: previously there was no check at all — a bulk download
    would just start filling the disk and only fail once it genuinely ran out
    of space mid-way. Now, when every useful document's size is known, it
    fails fast before downloading anything."""
    from collections import namedtuple

    from worker.tasks import build_bulk_download_zip

    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)

    repository.create_source_family(db_session, key="jep", display_name="JEP")
    source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Doc 1", review_status="useful",
        storage_bucket=TEST_S3_BUCKET, storage_key="JEP/2026-06-01/Auto/doc1.pdf", file_size_bytes=10_000_000,
    )

    download_calls = []
    monkeypatch.setattr(tasks_module, "download_file", lambda *a, **k: download_calls.append(a))
    _Usage = namedtuple("usage", ["total", "used", "free"])
    monkeypatch.setattr(tasks_module.shutil, "disk_usage", lambda path: _Usage(total=0, used=0, free=1_000))

    bulk_download = repository.create_bulk_download(db_session)
    build_bulk_download_zip(bulk_download.id)

    assert download_calls == []  # nunca llegó a intentar descargar nada

    assertion_session = task_session_factory()
    try:
        refreshed = repository.get_bulk_download(assertion_session, bulk_download.id)
        assert refreshed.status == "failed"
        assert "espacio suficiente" in refreshed.error_message
    finally:
        assertion_session.close()


def test_build_bulk_download_zip_skips_the_disk_space_check_when_a_document_size_is_unknown(
    db_session, test_engine, monkeypatch
):
    """Documents saved by an older version of the code (or with a directly-edited
    row) may have no recorded file_size_bytes — the safety check can't reliably
    guess a total in that case, so it's skipped entirely rather than blocking a
    bulk download that would otherwise have gone through fine."""
    from collections import namedtuple
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
        for name in ("doc1.pdf", "doc2.pdf"):
            local = Path(tmp) / name
            local.write_bytes(b"contenido")
            upload_file(local, f"JEP/2026-06-01/Auto/{name}", bucket=TEST_S3_BUCKET, content_type="application/pdf")

    repository.insert_document(
        db_session, doc_id="doc-known", source_id=source.id, title="Con tamaño", review_status="useful",
        storage_bucket=TEST_S3_BUCKET, storage_key="JEP/2026-06-01/Auto/doc1.pdf", file_size_bytes=9,
    )
    repository.insert_document(
        db_session, doc_id="doc-unknown", source_id=source.id, title="Sin tamaño", review_status="useful",
        storage_bucket=TEST_S3_BUCKET, storage_key="JEP/2026-06-01/Auto/doc2.pdf",
    )

    _Usage = namedtuple("usage", ["total", "used", "free"])
    monkeypatch.setattr(tasks_module.shutil, "disk_usage", lambda path: _Usage(total=0, used=0, free=1))

    bulk_download = repository.create_bulk_download(db_session)
    build_bulk_download_zip(bulk_download.id)

    assertion_session = task_session_factory()
    try:
        refreshed = repository.get_bulk_download(assertion_session, bulk_download.id)
        assert refreshed.status == "completed"  # el chequeo se saltó, no bloqueó la descarga
        assert refreshed.document_count == 2
    finally:
        assertion_session.close()


def test_finalize_run_triggers_case_link_assembly(db_session, test_engine, monkeypatch):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Tribunal X", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)

    calls = []
    monkeypatch.setattr(
        "worker.tasks.repository.assemble_case_links_for_run",
        lambda db, run_id: calls.append(run_id) or 0,
    )

    tasks_module._finalize_run(run.id)

    assert calls == [run.id]


def test_finalize_run_still_completes_when_assembly_fails(db_session, test_engine, monkeypatch):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Tribunal X", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)

    def _boom(db, run_id):
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr("worker.tasks.repository.assemble_case_links_for_run", _boom)

    tasks_module._finalize_run(run.id)

    assertion_session = task_session_factory()
    assert repository.get_run(assertion_session, run.id).status == "completed"
