from datetime import date, timedelta

from sqlalchemy.orm import sessionmaker

from core.db import repository
from worker import beat_schedule


def test_trigger_scheduled_run_uses_a_lookback_window(db_session, test_engine, monkeypatch):
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr(beat_schedule, "SessionLocal", task_session_factory)

    delayed_run_ids = []
    monkeypatch.setattr(beat_schedule.orchestrate_run, "delay", lambda run_id: delayed_run_ids.append(run_id))

    beat_schedule.trigger_scheduled_run()

    assert len(delayed_run_ids) == 1
    run = repository.get_run(db_session, delayed_run_ids[0])
    today = date.today()
    assert run.ffin == today
    assert run.fini == today - timedelta(days=beat_schedule.get_settings().scheduled_run_lookback_days)
    assert run.fini < run.ffin


def test_trigger_scheduled_run_respects_configured_lookback(db_session, test_engine, monkeypatch):
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr(beat_schedule, "SessionLocal", task_session_factory)
    monkeypatch.setattr(beat_schedule.orchestrate_run, "delay", lambda run_id: None)

    settings = beat_schedule.get_settings()
    monkeypatch.setattr(settings, "scheduled_run_lookback_days", 7)
    monkeypatch.setattr(beat_schedule, "get_settings", lambda: settings)

    beat_schedule.trigger_scheduled_run()

    run = repository.list_runs(db_session, limit=1)[0]
    assert run.fini == date.today() - timedelta(days=7)
