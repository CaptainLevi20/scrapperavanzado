"""Corrida única: renombra, dentro del almacenamiento, el archivo de los
documentos de Corte Suprema (CSJ) cuyo título fue corregido después de la
descarga (ver resolve_unverified_document en
core/scrapers/families/corte_suprema.py) — para los que se descargaron antes
de que worker/tasks.py empezara a reconstruir storage_key a partir del
título ya corregido (ver core.utils.rekey_filename), el archivo guardado
todavía tiene el nombre viejo ("placeholder", el que traía antes de leerse
el PDF), aunque el título en la base de datos ya esté bien.

No vuelve a descargar el PDF: solo renombra el objeto ya guardado
(core.storage.rename_object — copia y borra del lado del servidor, sin pasar
los bytes del archivo por este proceso) y actualiza storage_key en la base
de datos.

Uso: .venv/Scripts/python -m core.backfill_csj_storage_keys
Se puede correr más de una vez sin problema: un documento cuyo storage_key
ya coincide con su título no se toca.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import Document, Source
from core.db.session import SessionLocal
from core.storage import rename_object
from core.utils import rekey_filename

logger = logging.getLogger(__name__)


def backfill(db: Session) -> dict:
    documentos = db.scalars(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.family_key == "corte_suprema")
    ).all()

    documents_updated = 0
    for documento in documentos:
        nuevo_key = rekey_filename(documento.storage_key, documento.title)
        if nuevo_key == documento.storage_key:
            continue
        try:
            rename_object(documento.storage_bucket, documento.storage_key, nuevo_key)
            repository.update_document_storage_key(db, documento.id, nuevo_key)
            documents_updated += 1
        except Exception as e:
            logger.warning("No se pudo renombrar el documento %s: %s", documento.id, e)
            db.rollback()
            continue

    return {"documents_updated": documents_updated}


def main():
    db = SessionLocal()
    try:
        result = backfill(db)
        print(f"Documentos actualizados: {result['documents_updated']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
