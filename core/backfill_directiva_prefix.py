"""Corrida única: cambia el prefijo de las Directivas de ministerios de
"DIRECTIVA_" a "DIR_" en los títulos ya guardados (mineducacion, mininterior,
minvivienda; mindeporte ya usaba "DIR").

Actualiza el título en la base y renombra el archivo (y sus versiones) en el
almacenamiento, reusando core/storage_sync.py. La carpeta de guardado no
cambia.

Uso: .venv/Scripts/python -m core.backfill_directiva_prefix
Idempotente: un título que ya empieza por "DIR_" (o que no empieza por
"DIRECTIVA_") no se toca.
"""
import logging
import re

from sqlalchemy import select

from core.db import repository
from core.db.models import Document, Source
from core.db.repository import _MINISTERIO_FAMILIES
from core.db.session import SessionLocal
from core.utils import rekey_filename
from core import storage_sync

logger = logging.getLogger(__name__)

_VIEJO_RE = re.compile(r"^DIRECTIVA_(.+)$")


def nuevo_titulo_directiva(titulo: str) -> str | None:
    """Devuelve el título con el prefijo "DIR_", o None si `titulo` no empieza
    por "DIRECTIVA_"."""
    match = _VIEJO_RE.match(titulo or "")
    return f"DIR_{match.group(1)}" if match else None


def backfill(db) -> dict:
    documentos = db.scalars(
        select(Document)
        .join(Source, Source.id == Document.source_id)
        .where(Source.family_key.in_(_MINISTERIO_FAMILIES))
    ).all()

    pares = [
        (documento, nuevo)
        for documento in documentos
        if (nuevo := nuevo_titulo_directiva(documento.title)) is not None
    ]

    # Guarda de colisión (mismo patrón que los otros backfills).
    grupos: dict[tuple[str, str], list[tuple[Document, str]]] = {}
    for documento, nuevo in pares:
        nueva_key = rekey_filename(documento.storage_key, nuevo)
        grupos.setdefault((documento.storage_bucket, nueva_key), []).append((documento, nuevo))

    colisiones = 0
    sin_colision: list[tuple[Document, str]] = []
    for (_bucket, nueva_key), grupo in grupos.items():
        if len(grupo) > 1:
            logger.warning(
                "Colisión de clave calculada: los documentos %s calcularían la misma clave %r — se omiten.",
                [d.id for d, _ in grupo], nueva_key,
            )
            colisiones += len(grupo)
            continue
        sin_colision.extend(grupo)

    renombrados = 0
    for documento, nuevo in sin_colision:
        try:
            documento = repository.update_document_title(db, documento.id, nuevo)
            renombrados += 1
        except Exception as exc:
            logger.warning("No se pudo actualizar el título del documento %s: %s", documento.id, exc)
            db.rollback()
            continue
        family_key = db.scalar(select(Source.family_key).where(Source.id == documento.source_id))
        storage_sync.reconcile_document(db, documento, family_key, tiene_actuaciones=False)
        storage_sync.reconcile_document_versions(db, documento, family_key, tiene_actuaciones=False)

    return {"renombrados": renombrados, "colisiones_omitidas": colisiones}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        resultado = backfill(db)
        logger.info(
            "Backfill DIRECTIVA->DIR: %s títulos renombrados, %s omitidos por colisión",
            resultado["renombrados"],
            resultado["colisiones_omitidas"],
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
