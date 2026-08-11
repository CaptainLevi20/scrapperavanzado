import logging
from typing import Optional

from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import Document
from core.naming import nombre_documento, nombre_version
from core.storage import rename_object
from core.utils import rekey_filename

logger = logging.getLogger(__name__)


def reconcile_document(db: Session, document: Document, family_key: Optional[str], tiene_actuaciones: bool) -> bool:
    """Renombra en MinIO el archivo de `document` si su storage_key actual no
    coincide con su nombre canónico vigente. Devuelve True solo si el
    renombrado se ejecutó con éxito y storage_key quedó actualizado en la
    base — una falla se registra en el log y no propaga (ver Global
    Constraints del plan: nunca bloquea al llamador)."""
    nombre_esperado = nombre_documento(document, family_key, tiene_actuaciones)
    nueva_key = rekey_filename(document.storage_key, nombre_esperado)
    if nueva_key == document.storage_key:
        return False
    try:
        rename_object(document.storage_bucket, document.storage_key, nueva_key)
        # Ambas operaciones (MinIO + DB) en el mismo try — si la DB falla después
        # de que MinIO ya renombró, aceptamos la inconsistencia temporal.
        repository.update_document_storage_key(db, document.id, nueva_key)
    except Exception as exc:
        logger.warning("No se pudo renombrar el documento %s en MinIO: %s", document.id, exc)
        return False
    return True


def reconcile_document_versions(db: Session, document: Document, family_key: Optional[str], tiene_actuaciones: bool) -> int:
    """Igual que reconcile_document, pero para cada versión archivada de
    `document`. Devuelve cuántas se renombraron con éxito."""
    renombradas = 0
    for version in repository.list_document_versions(db, document.id):
        nombre_esperado = nombre_version(document, version, family_key, tiene_actuaciones)
        nueva_key = rekey_filename(version.storage_key, nombre_esperado)
        if nueva_key == version.storage_key:
            continue
        try:
            rename_object(version.storage_bucket, version.storage_key, nueva_key)
            # Ambas operaciones (MinIO + DB) en el mismo try — si la DB falla después
            # de que MinIO ya renombró, aceptamos la inconsistencia temporal.
            repository.update_document_version_storage_key(db, version.id, nueva_key)
        except Exception as exc:
            logger.warning("No se pudo renombrar la versión %s en MinIO: %s", version.id, exc)
            continue
        renombradas += 1
    return renombradas


def reconcile_title_group(db: Session, family_key: str, title: str) -> dict:
    """Recalcula si el grupo de documentos con este título dentro de esta
    familia tiene más de una actuación (misma señal que case_document_count)
    y reconcilia a cada uno (y sus versiones archivadas) con esa decisión.
    Se dispara cuando llega una actuación nueva, para corregir también a los
    'hermanos' existentes que nadie tocó directamente."""
    documentos = repository.list_documents_by_title_within_family(db, family_key, title)
    tiene_actuaciones = len(documentos) > 1
    documentos_renombrados = 0
    versiones_renombradas = 0
    for documento in documentos:
        if reconcile_document(db, documento, family_key, tiene_actuaciones):
            documentos_renombrados += 1
        versiones_renombradas += reconcile_document_versions(db, documento, family_key, tiene_actuaciones)
    return {"documentos_renombrados": documentos_renombrados, "versiones_renombradas": versiones_renombradas}
