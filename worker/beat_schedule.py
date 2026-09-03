import logging
from datetime import date, timedelta

from celery.schedules import crontab

from core.config import get_settings
from core.db import repository
from core.db.session import SessionLocal
from worker.celery_app import celery_app
from worker.tasks import build_bulk_download_zip, orchestrate_run
from worker.storage_sync_tasks import reconcile_all_task  # noqa: F401 — registra la tarea en beat_schedule

logger = logging.getLogger(__name__)


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


@celery_app.task(name="worker.trigger_scheduled_bulk_download")
def trigger_scheduled_bulk_download():
    """Genera una descarga masiva con todo lo marcado 'útil' que aún no se haya
    entregado en un lote anterior (list_useful_documents ya excluye lo
    entregado). Corre después del scrape diario, así que cada día empaqueta
    solo lo nuevo. Si no hay nada útil sin entregar, no crea el lote."""
    db = SessionLocal()
    try:
        if not repository.list_useful_documents(db):
            logger.info("Descarga masiva programada: no hay documentos útiles sin entregar, se omite.")
            return
        bulk_download_id = repository.create_bulk_download(db).id
    finally:
        db.close()
    build_bulk_download_zip.delay(bulk_download_id)


celery_app.conf.beat_schedule = {
    "daily-scrape": {
        "task": "worker.trigger_scheduled_run",
        "schedule": crontab(hour=6, minute=0),
    },
    "daily-bulk-download": {
        "task": "worker.trigger_scheduled_bulk_download",
        # Después del scrape de las 6:00, con margen para que termine.
        "schedule": crontab(hour=8, minute=0),
    },
    "nightly-storage-sync": {
        "task": "worker.reconcile_all_task",
        "schedule": crontab(hour=2, minute=0),
    },
}
