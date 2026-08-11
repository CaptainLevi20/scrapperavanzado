"""Corrida única: rellena documents.version_no y document_versions.version_no
en lo ya guardado, según el orden real de las versiones (la más antigua = 1;
el documento vigente = k+1). Solo base de datos; no toca archivos."""
import logging

from sqlalchemy import select

from core.db.models import Document, DocumentVersion
from core.db.session import SessionLocal

logger = logging.getLogger(__name__)


def asignar_version_no(db) -> int:
    actualizados = 0
    documentos = db.scalars(select(Document)).all()
    for doc in documentos:
        versiones = db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == doc.id)
            .order_by(DocumentVersion.superseded_at.asc())
        ).all()
        if not versiones:
            doc.version_no = 1
            continue
        for i, v in enumerate(versiones, start=1):
            v.version_no = i
        doc.version_no = len(versiones) + 1
        actualizados += 1
    db.commit()
    return actualizados


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        n = asignar_version_no(db)
        logger.info("version_no asignado; documentos con versiones actualizados: %s", n)
    finally:
        db.close()


if __name__ == "__main__":
    main()
