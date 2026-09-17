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


def _fuente_util(db_session, review_status="useful"):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(
        db_session, family_key="constitucional", name="Corte Constitucional", family_params={}
    )
    repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="ST-065-24",
        storage_bucket="iurisync-test", storage_key="k.rtf", review_status=review_status,
    )


def test_trigger_scheduled_bulk_download_creates_and_dispatches_when_there_are_useful_docs(
    db_session, test_engine, monkeypatch
):
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr(beat_schedule, "SessionLocal", task_session_factory)
    dispatched = []
    monkeypatch.setattr(beat_schedule.build_bulk_download_zip, "delay", lambda bd_id: dispatched.append(bd_id))

    _fuente_util(db_session, review_status="useful")

    beat_schedule.trigger_scheduled_bulk_download()

    lotes = repository.list_bulk_downloads(db_session)
    assert len(lotes) == 1
    assert dispatched == [lotes[0].id]


def test_trigger_scheduled_bulk_download_skips_when_no_new_useful_docs(db_session, test_engine, monkeypatch):
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr(beat_schedule, "SessionLocal", task_session_factory)
    dispatched = []
    monkeypatch.setattr(beat_schedule.build_bulk_download_zip, "delay", lambda bd_id: dispatched.append(bd_id))

    _fuente_util(db_session, review_status="pending")  # nada útil sin entregar

    beat_schedule.trigger_scheduled_bulk_download()

    assert dispatched == []
    assert repository.list_bulk_downloads(db_session) == []


def test_beat_schedule_incluye_la_descarga_masiva_diaria():
    entrada = beat_schedule.celery_app.conf.beat_schedule["daily-bulk-download"]
    assert entrada["task"] == "worker.trigger_scheduled_bulk_download"


def test_trigger_monthly_report_creates_the_previous_month_and_dispatches(db_session, test_engine, monkeypatch):
    from datetime import date

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr(beat_schedule, "SessionLocal", task_session_factory)
    monkeypatch.setattr(beat_schedule, "date", type("_FixedDate", (date,), {"today": staticmethod(lambda: date(2026, 9, 1))}))
    dispatched = []
    monkeypatch.setattr(beat_schedule.build_monthly_report, "delay", lambda report_id: dispatched.append(report_id))

    beat_schedule.trigger_monthly_report()

    reports = repository.list_monthly_reports(db_session)
    assert len(reports) == 1
    assert reports[0].period == date(2026, 8, 1)
    assert reports[0].triggered_by == "scheduled"
    assert dispatched == [reports[0].id]


def test_trigger_monthly_report_handles_year_rollover(db_session, test_engine, monkeypatch):
    from datetime import date

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr(beat_schedule, "SessionLocal", task_session_factory)
    monkeypatch.setattr(beat_schedule, "date", type("_FixedDate", (date,), {"today": staticmethod(lambda: date(2026, 1, 1))}))
    monkeypatch.setattr(beat_schedule.build_monthly_report, "delay", lambda report_id: None)

    beat_schedule.trigger_monthly_report()

    reports = repository.list_monthly_reports(db_session)
    assert reports[0].period == date(2025, 12, 1)


def test_beat_schedule_incluye_el_reporte_mensual():
    entrada = beat_schedule.celery_app.conf.beat_schedule["monthly-report"]
    assert entrada["task"] == "worker.trigger_monthly_report"
