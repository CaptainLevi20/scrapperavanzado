"""Corrida única: pobla Document.radicado para los documentos de SAMAI que ya
existen (capturados antes de que el scraper guardara el campo) y genera las
sugerencias de casos relacionados sobre todo ese histórico de una vez — ver
docs/superpowers/specs/2026-07-29-vinculacion-casos-samai-design.md, sección
"Datos existentes (backfill)".

Uso: .venv/Scripts/python -m core.backfill_samai_radicado
Se puede correr más de una vez sin problema: los documentos que ya tienen
radicado se dejan tal cual, y generate_case_link_suggestions no duplica
sugerencias ya existentes.
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import Document, Source
from core.db.session import SessionLocal
from core.utils import is_samai_case_title

_RADICADO_FROM_TITLE = re.compile(r"^(\d+)\(")


def backfill(db: Session) -> dict:
    stmt = (
        select(Document)
        .join(Source, Source.id == Document.source_id)
        .where(Source.family_key == "samai", Document.radicado.is_(None))
    )
    documents_updated = 0
    for document in db.scalars(stmt).all():
        if not is_samai_case_title(document.title):
            continue
        match = _RADICADO_FROM_TITLE.match(document.title)
        if not match:
            continue
        document.radicado = match.group(1)
        documents_updated += 1
    db.commit()

    stmt = (
        select(Document.source_id, Document.radicado)
        .join(Source, Source.id == Document.source_id)
        .where(Source.family_key == "samai", Document.radicado.is_not(None))
        .distinct()
    )
    all_groups = list(db.execute(stmt).all())
    suggestions_created = repository.generate_case_link_suggestions(db, all_groups)

    return {"documents_updated": documents_updated, "suggestions_created": suggestions_created}


def main():
    db = SessionLocal()
    try:
        result = backfill(db)
        print(f"Documentos actualizados: {result['documents_updated']}")
        print(f"Sugerencias nuevas: {result['suggestions_created']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
