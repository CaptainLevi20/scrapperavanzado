from sqlalchemy.orm import sessionmaker

from core.db import repository
from tests.conftest import DummyFamilyScraper
from core.models import RawDocModel
from worker.celery_app import celery_app
from worker.tasks import orchestrate_run


def test_orchestrate_run_creates_run_sources_and_completes_run(db_session, test_engine, monkeypatch):
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    # Note: the task's `finally: db.close()` would detach/expire objects held by the test's own
    # db_session if the task reused it directly (same DetachedInstanceError pitfall documented in
    # tests/test_tasks.py for scrape_source_task). Give the task its own session bound to the same
    # test_engine instead of reusing db_session.
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    DummyFamilyScraper.docs_to_return = []

    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)

    orchestrate_run(run.id, source_ids=[source.id])

    run_sources = repository.list_run_sources(db_session, run.id)
    assert len(run_sources) == 1
    assert run_sources[0].status == "completed"

    # Re-query via a fresh session rather than db_session: db_session's identity map already
    # holds the `run` object from creation above, and a plain SELECT does not overwrite
    # attributes of an already-identity-mapped, non-expired instance, so it would return the
    # stale "pending" status instead of what the task's (separate) session committed.
    assertion_session = task_session_factory()
    try:
        refreshed_run = repository.get_run(assertion_session, run.id)
        assert refreshed_run.status == "completed"
        assert refreshed_run.finished_at is not None
    finally:
        assertion_session.close()


def test_orchestrate_run_with_no_active_sources_still_completes(db_session, test_engine, monkeypatch):
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)

    orchestrate_run(run.id, source_ids=[999999])

    assertion_session = task_session_factory()
    try:
        refreshed_run = repository.get_run(assertion_session, run.id)
        assert refreshed_run.status == "completed"
    finally:
        assertion_session.close()
