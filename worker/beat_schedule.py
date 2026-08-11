from datetime import date, timedelta

from celery.schedules import crontab

from core.config import get_settings
from core.db import repository
from core.db.session import SessionLocal
from worker.celery_app import celery_app
from worker.tasks import orchestrate_run
from worker.storage_sync_tasks import reconcile_all_task  # noqa: F401 — registra la tarea en beat_schedule


@celery_app.task(name="worker.trigger_scheduled_run")
def trigger_scheduled_run():
    # Without an explicit range, create_run(fini=None, ffin=None) falls back
    # (via _default_date_str in worker/tasks.py) to fini == ffin == today, so a
    # source that hasn't published anything yet at 01:00 COT never gets asked
    # about that day again. Use a lookback window instead so today's documents
    # are still picked up on tomorrow's run.
    today = date.today()
    lookback_days = get_settings().scheduled_run_lookback_days
    fini = today - timedelta(days=lookback_days)

    db = SessionLocal()
    try:
        run = repository.create_run(db, triggered_by="scheduled", fini=fini, ffin=today)
        run_id = run.id
    finally:
        db.close()
    orchestrate_run.delay(run_id)


celery_app.conf.beat_schedule = {
    "daily-scrape": {
        "task": "worker.trigger_scheduled_run",
        "schedule": crontab(hour=6, minute=0),
    },
    "nightly-storage-sync": {
        "task": "worker.reconcile_all_task",
        "schedule": crontab(hour=2, minute=0),
    },
}
