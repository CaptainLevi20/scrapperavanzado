import responses
from sqlalchemy.orm import sessionmaker

from core.db import repository
from core.models import RawDocModel
from tests.conftest import DummyFamilyScraper, TEST_S3_BUCKET
from worker.celery_app import celery_app
from worker.tasks import scrape_source_task


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


def _settings_with_test_bucket():
    from core.config import get_settings

    settings = get_settings()
    settings.s3_bucket = TEST_S3_BUCKET
    return settings
