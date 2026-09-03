"""Corrida única: pasa los títulos ya guardados de la Corte Constitucional
del formato viejo ("ST206_26", "A846_26") al nuevo ("ST-206-26", "A-846-26")
— ver core/scrapers/families/constitucional.py::_normalize_title.

Actualiza el título en la base y renombra el archivo (y sus versiones
archivadas) en el almacenamiento, reusando core/storage_sync.py.

Uso: .venv/Scripts/python -m core.backfill_constitucional_titles
Se puede correr más de una vez sin problema: un documento cuyo título ya
está en el formato nuevo, o que no tiene la forma esperada, se deja tal cual.
"""
import logging
import re

from sqlalchemy import select

from core.db import repository
from core.db.models import Document, Source
from core.db.session import SessionLocal
from core import storage_sync

logger = logging.getLogger(__name__)

_FAMILY_KEY = "constitucional"
_SOURCE_NAME = "Corte Constitucional"

# Formato viejo: prefijo de letras + número + "_" + año, con un "_v{n}"
# opcional al final. El formato nuevo usa "-" en vez de "_" entre esas partes,
# así que un título que ya trae "-" no matchea acá y se deja intacto (esto es
# lo que hace la corrida idempotente).
_TITULO_VIEJO_RE = re.compile(r"^([A-Za-z]+)(\d+)_(\d+)(?:_v(\d+))?$")


def nuevo_titulo_constitucional(titulo: str) -> str | None:
    """Devuelve el título en el formato nuevo, o None si `titulo` ya está
    migrado o no tiene la forma que produce el scraper viejo."""
    match = _TITULO_VIEJO_RE.match(titulo or "")
    if not match:
        return None
    letras, numero, anio, version = match.groups()
    nuevo = f"{letras}-{numero}-{anio}"
    if version:
        nuevo = f"{nuevo}-v{version}"
    return nuevo


def backfill(db) -> dict:
    documentos = db.scalars(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.name == _SOURCE_NAME)
    ).all()

    documentos_actualizados = 0
    archivos_renombrados = 0
    versiones_renombradas = 0
    for documento in documentos:
        nuevo = nuevo_titulo_constitucional(documento.title)
        if nuevo is None:
            continue
        try:
            documento = repository.update_document_title(db, documento.id, nuevo)
            documentos_actualizados += 1
        except Exception as exc:
            logger.warning("No se pudo actualizar el título del documento %s: %s", documento.id, exc)
            db.rollback()
            continue
        if storage_sync.reconcile_document(db, documento, _FAMILY_KEY, tiene_actuaciones=False):
            archivos_renombrados += 1
        versiones_renombradas += storage_sync.reconcile_document_versions(
            db, documento, _FAMILY_KEY, tiene_actuaciones=False
        )

    return {
        "documentos_actualizados": documentos_actualizados,
        "archivos_renombrados": archivos_renombrados,
        "versiones_renombradas": versiones_renombradas,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        resultado = backfill(db)
        logger.info(
            "Backfill Corte Constitucional: %s títulos actualizados, "
            "%s archivos renombrados, %s versiones archivadas renombradas",
            resultado["documentos_actualizados"],
            resultado["archivos_renombrados"],
            resultado["versiones_renombradas"],
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
