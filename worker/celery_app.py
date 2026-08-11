from celery import Celery

from core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "iurisync",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker.tasks", "worker.beat_schedule", "worker.storage_sync_tasks"],
)
celery_app.conf.update(timezone="UTC", enable_utc=True)
