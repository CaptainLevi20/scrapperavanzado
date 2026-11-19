import logging

from celery import Celery, signals

from core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "iurisync",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker.tasks", "worker.beat_schedule", "worker.storage_sync_tasks"],
)
celery_app.conf.update(timezone="UTC", enable_utc=True)


@signals.worker_init.connect(weak=False)
def _limpiar_temporales_al_arrancar(**_kwargs) -> None:
    # worker_init corre una sola vez en el proceso principal, antes de que el
    # worker empiece a recibir tareas. Un fallo aquí nunca debe impedir que el
    # worker arranque.
    try:
        from worker.limpieza_temporales import limpiar_temporales_huerfanos

        limpiar_temporales_huerfanos()
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("Falló la limpieza de temporales al arrancar")
