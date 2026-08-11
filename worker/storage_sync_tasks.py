import logging

from core.db import repository
from core.db.session import SessionLocal
from core.storage_sync import reconcile_all, reconcile_document, reconcile_document_versions, reconcile_title_group
from worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="worker.reconcile_title_group_task")
def reconcile_title_group_task(family_key: str, title: str) -> None:
    db = SessionLocal()
    try:
        reconcile_title_group(db, family_key, title)
    finally:
        db.close()


@celery_app.task(name="worker.reconcile_document_task")
def reconcile_document_task(document_id: int) -> None:
    db = SessionLocal()
    try:
        document = repository.get_document(db, document_id)
        if document is None:
            return
        family_key = repository.get_source_family_keys(db, [document.source_id]).get(document.source_id)
        tiene_actuaciones = (
            repository.actuacion_counts_by_title(db, [document], {document.source_id: family_key}).get(document.title, 0) > 1
        )
        reconcile_document(db, document, family_key, tiene_actuaciones)
        reconcile_document_versions(db, document, family_key, tiene_actuaciones)
    finally:
        db.close()


@celery_app.task(name="worker.reconcile_all_task")
def reconcile_all_task() -> None:
    db = SessionLocal()
    try:
        resultado = reconcile_all(db)
        logger.info(
            "Barrido nocturno de sincronización — documentos renombrados: %s, versiones renombradas: %s",
            resultado["documentos_renombrados"], resultado["versiones_renombradas"],
        )
    finally:
        db.close()
