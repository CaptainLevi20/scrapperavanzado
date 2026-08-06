"""Corrida única: pobla Document.radicado para los documentos de SAMAI que ya
existen (capturados antes de que el scraper guardara el campo) y arma los
expedientes de casos relacionados sobre todo ese histórico de una vez — ver
docs/superpowers/specs/2026-07-29-vinculacion-casos-samai-design.md, sección
"Datos existentes (backfill)".

Uso: .venv/Scripts/python -m core.backfill_samai_radicado
Se puede correr más de una vez sin problema: los documentos que ya tienen
radicado se dejan tal cual, y assemble_case_links no duplica expedientes ya
armados.
"""
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import Document, Source
from core.db.session import SessionLocal

# Formatos reales de título SAMAI (ver core/scrapers/families/samai.py::
# _normalizar_titulo y _complementar_titulo_con_numero):
#   - Consejo de Estado, con guiones: "25000-23-37-000-2021-00423-01(NRD)",
#     a veces con un grupo complementario extra:
#     "66001-23-33-000-2017-00141-01(3104-2023)(NRD)"
#   - Tribunal Administrativo, con prefijo T_{CODIGO}_ y SIN paréntesis:
#     "T_CUND_25001233300020260001200"
# En los tres casos, lo que sigue al prefijo opcional y hasta el primer "("
# (o hasta el final si no hay paréntesis) son los dígitos/guiones/guiones
# bajos del radicado; quitamos todo lo que no sea dígito y solo aceptamos el
# resultado si tiene exactamente 23 dígitos (longitud de un radicado
# colombiano válido). Esto además rechaza naturalmente títulos que no son de
# un caso (ej. "DR. WILLIAM SANTA MARIN", que no tiene dígitos) sin necesitar
# is_samai_case_title como filtro aparte.
_TITLE_PREFIX = re.compile(r"^(?:T_[A-Z]+_)?([\d\-_]+)")
_RADICADO_LENGTH = 23


def _radicado_from_title(title: str) -> Optional[str]:
    match = _TITLE_PREFIX.match(title)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return digits if len(digits) == _RADICADO_LENGTH else None


def backfill(db: Session) -> dict:
    stmt = (
        select(Document)
        .join(Source, Source.id == Document.source_id)
        .where(Source.family_key == "samai", Document.radicado.is_(None))
    )
    documents_updated = 0
    for document in db.scalars(stmt).all():
        radicado = _radicado_from_title(document.title)
        if radicado is None:
            continue
        document.radicado = radicado
        documents_updated += 1
    db.commit()

    stmt = (
        select(Document.source_id, Document.radicado)
        .join(Source, Source.id == Document.source_id)
        .where(Source.family_key == "samai", Document.radicado.is_not(None))
        .distinct()
    )
    all_groups = list(db.execute(stmt).all())
    case_links_assembled = repository.assemble_case_links(db, all_groups)

    return {"documents_updated": documents_updated, "case_links_assembled": case_links_assembled}


def main():
    db = SessionLocal()
    try:
        result = backfill(db)
        print(f"Documentos actualizados: {result['documents_updated']}")
        print(f"Cruces vinculados: {result['case_links_assembled']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
