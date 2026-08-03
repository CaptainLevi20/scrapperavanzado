"""Corrida única: complementa el título de los documentos de Consejo de
Estado ya guardados con el número entre paréntesis que a veces aparece junto
al radicado en la primera página del PDF — ver
docs/superpowers/specs/2026-08-03-titulo-consejo-estado-design.md.

Uso: .venv/Scripts/python -m core.backfill_ce_titles
Se puede correr más de una vez sin problema: un documento cuyo título ya
tiene el número entre paréntesis, o cuyo PDF no lo trae, se deja tal cual.
"""
import logging
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import Document, Source
from core.db.session import SessionLocal
from core.scrapers.families.samai import (
    _TITULO_CE_RE,
    _complementar_titulo_con_numero,
    _extraer_texto_primera_pagina,
    _numero_extra_desde_texto,
)
from core.storage import download_file

logger = logging.getLogger(__name__)

# Un título ya complementado trae el número justo después del radicado —
# "{radicado}({número})..." — si el título ya tiene esa forma no hay nada
# que hacer, lo que permite correr este backfill más de una vez sin duplicar
# el número ni volver a descargar el PDF innecesariamente.
_YA_COMPLEMENTADO_RE = re.compile(r"^[\d-]+\(\d+\)")


def backfill(db: Session) -> dict:
    documentos = db.scalars(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.name == "Consejo de Estado")
    ).all()

    documents_updated = 0
    with TemporaryDirectory() as tmp_dir:
        for documento in documentos:
            if _YA_COMPLEMENTADO_RE.match(documento.title):
                continue
            match = _TITULO_CE_RE.match(documento.title)
            if not match:
                continue
            radicado = match.group(1)

            local_path = Path(tmp_dir) / f"{documento.id}.pdf"
            try:
                download_file(documento.storage_bucket, documento.storage_key, local_path)
                texto = _extraer_texto_primera_pagina(local_path)
            except Exception as e:
                logger.warning("No se pudo leer el documento %s: %s", documento.id, e)
                continue
            finally:
                local_path.unlink(missing_ok=True)

            numero = _numero_extra_desde_texto(texto, radicado)
            if not numero:
                continue

            nuevo_titulo = _complementar_titulo_con_numero(documento.title, numero)
            repository.update_document_title(db, documento.id, nuevo_titulo)
            documents_updated += 1

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
