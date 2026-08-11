import logging
from typing import Optional

from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import Document
from core.naming import nombre_documento
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
