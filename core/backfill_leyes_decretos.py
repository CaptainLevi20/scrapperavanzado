"""Corrida única: (1) pasa los títulos de Leyes y Decretos de ministerios ya
guardados del formato con sigla ("L_MA_2277_2022") al código canónico sin
sigla ("L2277022"), y (2) deduplica entre ministerios — la misma norma la
publican varias fuentes; se conserva el archivo más grande y se borran las
copias.

Ver core/naming.py::codigo_ley_decreto y
docs/superpowers/specs/2026-09-03-formato-leyes-decretos-ministerios-design.md.

Uso: .venv/Scripts/python -m core.backfill_leyes_decretos
Idempotente: un título ya migrado no se toca; sin duplicados no borra nada.
"""
import logging
import re

from sqlalchemy import select

from core.db import repository
from core.db.models import Document, Source
from core.db.repository import _MINISTERIO_FAMILIES
from core.db.session import SessionLocal
from core.naming import codigo_ley_decreto, es_codigo_ley_decreto
from core.utils import rekey_filename
from core import storage, storage_sync

logger = logging.getLogger(__name__)

# "<L|D>" + "_" + sigla del ministerio + "_" + número + "_" + año (4 díg).
# "LEST_MI_..." / "DIRECTIVA_..." no matchean: tras L/D debe venir "_".
_VIEJO_RE = re.compile(r"^([LD])_[A-Z]+_(\d+)_(\d{4})$")


def nuevo_titulo_ley_decreto(titulo: str) -> str | None:
    """Devuelve el código canónico si `titulo` es una ley/decreto en el formato
    viejo con sigla; None si ya está migrado o es de otro tipo."""
    match = _VIEJO_RE.match(titulo or "")
    if not match:
        return None
    return codigo_ley_decreto(match.group(1), match.group(2), match.group(3))


def _borrar_objeto(bucket: str, key: str) -> None:
    storage.delete_object(bucket, key)


def _renombrar_familia(db, family_key: str) -> dict:
    documentos = db.scalars(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.family_key == family_key)
    ).all()
    pares = [
        (documento, nuevo)
        for documento in documentos
        if (nuevo := nuevo_titulo_ley_decreto(documento.title)) is not None
    ]

    # Guarda de colisión intra-fuente (mismo patrón que los otros backfills).
    grupos: dict[tuple[str, str], list[tuple[Document, str]]] = {}
    for documento, nuevo in pares:
        nueva_key = rekey_filename(documento.storage_key, nuevo)
        grupos.setdefault((documento.storage_bucket, nueva_key), []).append((documento, nuevo))

    colisiones = 0
    sin_colision: list[tuple[Document, str]] = []
    for (_bucket, nueva_key), grupo in grupos.items():
        if len(grupo) > 1:
            logger.warning(
                "Colisión de clave calculada en %s: los documentos %s calcularían la misma clave %r — se omiten.",
                family_key, [d.id for d, _ in grupo], nueva_key,
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
        storage_sync.reconcile_document(db, documento, family_key, tiene_actuaciones=False)
        storage_sync.reconcile_document_versions(db, documento, family_key, tiene_actuaciones=False)

    return {"renombrados": renombrados, "colisiones_omitidas": colisiones}


def _deduplicar_entre_familias(db) -> int:
    documentos = db.scalars(
        select(Document)
        .join(Source, Source.id == Document.source_id)
        .where(Source.family_key.in_(_MINISTERIO_FAMILIES))
    ).all()

    por_titulo: dict[str, list[Document]] = {}
    for documento in documentos:
        if es_codigo_ley_decreto(documento.title):
            por_titulo.setdefault(documento.title, []).append(documento)

    borrados = 0
    for titulo, grupo in por_titulo.items():
        if len(grupo) <= 1:
            continue
        # Gana el archivo más grande; empate -> id menor; tamaño desconocido pierde.
        ganador = max(grupo, key=lambda d: (d.file_size_bytes or -1, -d.id))
        perdedores = [d.id for d in grupo if d.id != ganador.id]
        objetos = repository.delete_documents_by_id(db, perdedores)
        for bucket, key in objetos:
            try:
                _borrar_objeto(bucket, key)
            except Exception as exc:
                logger.warning("No se pudo borrar el objeto %s de %s: %s", key, titulo, exc)
        borrados += len(perdedores)

    return borrados


def backfill(db) -> dict:
    renombrados = 0
    colisiones_omitidas = 0
    for family_key in sorted(_MINISTERIO_FAMILIES):
        r = _renombrar_familia(db, family_key)
        renombrados += r["renombrados"]
        colisiones_omitidas += r["colisiones_omitidas"]

    duplicados_borrados = _deduplicar_entre_familias(db)

    return {
        "renombrados": renombrados,
        "colisiones_omitidas": colisiones_omitidas,
        "duplicados_borrados": duplicados_borrados,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        resultado = backfill(db)
        logger.info(
            "Backfill leyes/decretos: %s títulos renombrados, %s omitidos por colisión, %s duplicados borrados",
            resultado["renombrados"],
            resultado["colisiones_omitidas"],
            resultado["duplicados_borrados"],
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
