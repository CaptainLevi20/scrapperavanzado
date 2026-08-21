from sqlalchemy.orm import sessionmaker

from core.db import repository
from tests.conftest import DummyFamilyScraper
from core.models import RawDocModel
from worker.celery_app import celery_app
from worker.tasks import orchestrate_run, retry_failed_run_sources_task


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


def test_orchestrate_run_marks_the_run_as_failed_when_a_source_fails(db_session, test_engine, monkeypatch):
    """Regression test: a run used to be reported as 'completed' even when one of
    its sources errored out — the dashboard showed everything green while
    documents silently went missing. The run itself must now surface 'failed'."""
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})

    def _raise(self, fini, ffin, **kwargs):
        raise RuntimeError("el sitio remoto respondió con un error")

    monkeypatch.setattr(DummyFamilyScraper, "scrap", _raise)

    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)

    orchestrate_run(run.id, source_ids=[source.id])

    run_sources = repository.list_run_sources(db_session, run.id)
    assert len(run_sources) == 1
    assert run_sources[0].status == "failed"

    assertion_session = task_session_factory()
    try:
        refreshed_run = repository.get_run(assertion_session, run.id)
        assert refreshed_run.status == "failed"
        assert refreshed_run.finished_at is not None
    finally:
        assertion_session.close()


def test_orchestrate_run_marks_the_run_as_cancelled_when_cancel_was_requested(db_session, test_engine, monkeypatch):
    """Regression test: a cancelled run used to just report 'completed' like
    nothing happened — there was no 'cancelled' outcome at all. Once the user
    requests cancellation, the finished run must say so, regardless of what
    individual sources managed to do before stopping."""
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    DummyFamilyScraper.docs_to_return = []

    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    repository.request_run_cancel(db_session, run.id)

    orchestrate_run(run.id, source_ids=[source.id])

    run_sources = repository.list_run_sources(db_session, run.id)
    assert len(run_sources) == 1
    assert run_sources[0].status == "cancelled"

    assertion_session = task_session_factory()
    try:
        refreshed_run = repository.get_run(assertion_session, run.id)
        assert refreshed_run.status == "cancelled"
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


def test_retry_failed_run_sources_task_reruns_only_the_given_sources_and_recomputes_the_run_status(
    db_session, test_engine, monkeypatch
):
    """Un run con una fuente completada y otra fallida (estado 'failed', el
    mismo que dejaría la lógica de tres estados de _finalize_run) — al
    reintentar solo la fallida y que esta vez sí funcione, el run debe quedar
    'completed' (no 'completed_with_errors': ya no queda ninguna fuente
    fallida sin reintentar)."""
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    ok_source = repository.create_source(db_session, family_key="test-dummy", name="Ya completada", family_params={})
    retry_source = repository.create_source(db_session, family_key="test-dummy", name="A reintentar", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    ok_run_source = repository.create_run_source(db_session, run_id=run.id, source_id=ok_source.id)
    retry_run_source = repository.create_run_source(db_session, run_id=run.id, source_id=retry_source.id)
    repository.set_run_source_status(db_session, ok_run_source.id, "completed")
    repository.set_run_source_status(db_session, retry_run_source.id, "failed", error_message="boom")
    repository.set_run_status(db_session, run.id, "failed")

    DummyFamilyScraper.docs_to_return = []

    retry_failed_run_sources_task(run.id, [retry_run_source.id])

    assertion_session = task_session_factory()
    try:
        refreshed_ok = repository.get_run_source(assertion_session, ok_run_source.id)
        refreshed_retry = repository.get_run_source(assertion_session, retry_run_source.id)
        # The untouched source was never re-enqueued — still exactly as it was.
        assert refreshed_ok.status == "completed"
        assert refreshed_retry.status == "completed"
        assert refreshed_retry.error_message is None
        assert repository.get_run(assertion_session, run.id).status == "completed"
    finally:
        assertion_session.close()
