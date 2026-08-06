"""Corrida única: re-resuelve el campo `especialidad` de los documentos de
SAMAI (todos los Tribunales Administrativos y Consejo de Estado) ya
guardados, contra el catálogo de clases de proceso ampliado el 2026-08-04 —
ver `_CLASE_ACRONIMOS` en core/scrapers/families/samai.py. Cuando un
documento se guardó, su clase todavía no estaba en el catálogo y quedó
almacenada tal cual llegó de SAMAI (ej. "PROCESO EJECUTIVO"); ahora que el
catálogo la reconoce, `_especialidad_legible` la resuelve a su forma pulida
("Ejecutivo").

Uso: .venv/Scripts/python -m core.backfill_samai_especialidad
Se puede correr más de una vez sin problema: un documento cuya especialidad
ya está resuelta (o cuya clase sigue sin estar en el catálogo) no se toca.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import Document, Source
from core.db.session import SessionLocal
from core.scrapers.families.samai import _especialidad_legible

logger = logging.getLogger(__name__)


def backfill(db: Session) -> dict:
    documentos = db.scalars(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.family_key == "samai")
    ).all()

    documents_updated = 0
    for documento in documentos:
        if not documento.especialidad:
            continue
        nueva_especialidad = _especialidad_legible(documento.especialidad)
        if nueva_especialidad == documento.especialidad:
            continue
        try:
            repository.update_document_especialidad(db, documento.id, nueva_especialidad)
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
