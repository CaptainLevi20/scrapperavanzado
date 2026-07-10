from celery.schedules import crontab

from core.db import repository
from core.db.session import SessionLocal
from worker.celery_app import celery_app
from worker.tasks import orchestrate_run


@celery_app.task(name="worker.trigger_scheduled_run")
def trigger_scheduled_run():
    db = SessionLocal()
    try:
        run = repository.create_run(db, triggered_by="scheduled", fini=None, ffin=None)
        run_id = run.id
    finally:
        db.close()
    orchestrate_run.delay(run_id)


celery_app.conf.beat_schedule = {
    "daily-scrape": {
        "task": "worker.trigger_scheduled_run",
        "schedule": crontab(hour=6, minute=0),
    },
}
