"""Corrida única: pone el título canónico a los documentos de MinCIT que se
guardaron con el texto crudo del sitio porque el número no se reconocía —
"Circular Externa 065 de 1995", "Resolución No. 2649 ...", "Decreto - Ley
444 ...", circulares sin número (C_MCIT_SN_<año>), etc. Ver _parse_numero y
_NUMEROS_FIJOS en core/scrapers/families/mincit.py.

Recorre el sitio completo con el scraper actual para saber el título nuevo de
cada documento (mismo doc_id que usa el worker) y solo toca documentos cuyo
título guardado NO tiene ya la forma canónica: un título que ya estaba bien
nunca se cambia.

Actualiza el título en la base y renombra el archivo (y sus versiones
archivadas) en el almacenamiento, reusando core/storage_sync.py.

Uso: .venv/Scripts/python -m core.backfill_mincit_titulos [--simular]
Con --simular solo cuenta lo que cambiaría, sin tocar nada. Se puede correr
más de una vez sin problema.
"""
import logging
import re
import sys

from sqlalchemy import select

from core import storage_sync
from core.db import repository
from core.db.models import Document, Source
from core.db.session import SessionLocal
from core.naming import es_codigo_ley_decreto
from core.scrapers.families.mincit import ScrapMINCIT
from core.utils import compute_doc_id

logger = logging.getLogger(__name__)

_FAMILY_KEY = "mincit"
_CANONICO_MCIT = re.compile(r"^[A-Z]+_MCIT_\S+_\d{4}(?:_\d+)?$")


def es_titulo_canonico(titulo: str) -> bool:
    return bool(_CANONICO_MCIT.match(titulo or "")) or es_codigo_ley_decreto(titulo or "")


def titulos_del_sitio(scraper=None) -> dict:
    """doc_id -> título calculado por el scraper actual, sobre todo el sitio."""
    scraper = scraper or ScrapMINCIT()
    docs = scraper.scrap("1900-01-01", "2100-12-31")
    return {
        compute_doc_id(doc, include_publication_date=scraper.doc_id_uses_publication_date): doc.title
        for doc in docs
        if not doc.title_unverified
    }


def backfill(db, titulos: dict, simular: bool = False) -> dict:
    documentos = db.scalars(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.family_key == _FAMILY_KEY)
    ).all()

    actualizados = archivos = versiones = 0
    for documento in documentos:
        nuevo = titulos.get(documento.doc_id)
        if nuevo is None or nuevo == documento.title or es_titulo_canonico(documento.title):
            continue
        if simular:
            logger.info("[simulación] %r -> %r", documento.title, nuevo)
            actualizados += 1
            continue
        try:
            documento = repository.update_document_title(db, documento.id, nuevo)
            actualizados += 1
        except Exception as exc:
            logger.warning("No se pudo actualizar el título del documento %s: %s", documento.id, exc)
            db.rollback()
            continue
        if storage_sync.reconcile_document(db, documento, _FAMILY_KEY, tiene_actuaciones=False):
            archivos += 1
        versiones += storage_sync.reconcile_document_versions(db, documento, _FAMILY_KEY, tiene_actuaciones=False)

    return {
        "documentos_actualizados": actualizados,
        "archivos_renombrados": archivos,
        "versiones_renombradas": versiones,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    simular = "--simular" in sys.argv[1:]
    titulos = titulos_del_sitio()
    db = SessionLocal()
    try:
        r = backfill(db, titulos, simular=simular)
        logger.info(
            "Backfill MinCIT%s: %s títulos actualizados, %s archivos renombrados, %s versiones archivadas renombradas",
            " (simulación)" if simular else "",
            r["documentos_actualizados"], r["archivos_renombrados"], r["versiones_renombradas"],
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
