"""Corrida única: quita el acrónimo de la clase del título de los documentos
de Consejo de Estado ya guardados — ver
docs/superpowers/specs/2026-08-10-titulo-ce-sin-acronimo-design.md.

Uso: .venv/Scripts/python -m core.backfill_ce_titles_sin_acronimo
Idempotente: un título que ya no tiene acrónimo se deja tal cual, así que se
puede correr más de una vez sin problema.
"""
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import Document, Source
from core.db.session import SessionLocal

logger = logging.getLogger(__name__)

# El título de Consejo de Estado ya guardado puede venir en cuatro formas:
#   {radicado}, {radicado}({número}), {radicado}({ACRÓNIMO}) y
#   {radicado}({número})({ACRÓNIMO}).
# El acrónimo es el último grupo entre paréntesis que empieza con letra
# mayúscula; el número de caso empieza con dígito y se conserva. El grupo 1
# captura todo menos el acrónimo. Cubre el formato con guiones y el crudo de
# 23 dígitos (documentos viejos). Un título de Tribunal Administrativo
# (T_{CÓDIGO}_...) no matchea y se deja intacto.
# Se asume un solo grupo de número antes del acrónimo (igual que SAMAI_CASE_TITLE_PATTERN);
# un título con más de uno no se toca.
_TITULO_CON_ACRONIMO_RE = re.compile(
    r"^(\d{5}-\d{2}-\d{2}-\d{3}-\d{4}-\d{5}-\d{2}(?:\(\d[^)]{0,29}\))?"
    r"|\d{23}(?:\(\d[^)]{0,29}\))?)"
    r"\([A-Z][A-Z0-9]*\)$"
)


def _quitar_acronimo(title: str) -> str | None:
    match = _TITULO_CON_ACRONIMO_RE.match(title or "")
    if not match:
        return None
    return match.group(1)


def backfill(db: Session) -> dict:
    documentos = db.scalars(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.name == "Consejo de Estado")
    ).all()

    documents_updated = 0
    for documento in documentos:
        nuevo_titulo = _quitar_acronimo(documento.title)
        if nuevo_titulo is None:
            continue
        try:
            repository.update_document_title(db, documento.id, nuevo_titulo)
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
        print(f"Documentos actualizados (acrónimo quitado): {result['documents_updated']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
