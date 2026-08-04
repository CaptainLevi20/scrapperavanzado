"""Corrida única: normaliza el campo `tipo` de los documentos de SAMAI (todos
los Tribunales Administrativos y Consejo de Estado) ya guardados — SAMAI no es
consistente con las mayúsculas de la primera palabra de la actuación ("Auto",
"AUTO", "aUTO" aparecen todas para el mismo tipo de documento), y "Autos"
(plural) se fusiona con "Auto" — ver _normalizar_tipo en
core/scrapers/families/samai.py.

Solo actualiza el valor guardado en la base de datos; no toca el archivo ya
almacenado (la carpeta de almacenamiento de un documento ya subido no se
renombra retroactivamente, a diferencia de core/backfill_csj_storage_keys.py).

Uso: .venv/Scripts/python -m core.backfill_samai_tipo
Se puede correr más de una vez sin problema: un documento cuyo tipo ya está
normalizado no se toca.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import Document, Source
from core.db.session import SessionLocal
from core.scrapers.families.samai import _normalizar_tipo

logger = logging.getLogger(__name__)


def backfill(db: Session) -> dict:
    documentos = db.scalars(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.family_key == "samai")
    ).all()

    documents_updated = 0
    for documento in documentos:
        if not documento.tipo:
            continue
        nuevo_tipo = _normalizar_tipo(documento.tipo)
        if nuevo_tipo == documento.tipo:
            continue
        try:
            repository.update_document_tipo(db, documento.id, nuevo_tipo)
            documents_updated += 1
        except Exception as e:
            logger.warning("No se pudo actualizar el documento %s: %s", documento.id, e)
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
