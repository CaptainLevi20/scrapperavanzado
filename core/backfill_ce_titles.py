"""Corrida única: complementa el título de los documentos de Consejo de
Estado ya guardados con el número entre paréntesis que a veces aparece junto
al radicado en la primera página del PDF — ver
docs/superpowers/specs/2026-08-03-titulo-consejo-estado-design.md.

Uso: .venv/Scripts/python -m core.backfill_ce_titles
Se puede correr más de una vez sin problema: un documento cuyo título ya
tiene el número entre paréntesis, o cuyo PDF no lo trae, se deja tal cual.

También corre `backfill_quitar_puntos`, que quita el punto de miles (ej.
"(74.369)" -> "(74369)") de los títulos que el `backfill` original ya
complementó antes de que `_numero_extra_desde_texto` empezara a quitarlo —
no vuelve a descargar el PDF, solo corrige el texto ya guardado.
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
# el número ni volver a descargar el PDF innecesariamente. El número no
# siempre es solo dígitos (también aparece como "3104-2023" o "74.604" en
# datos reales — ver core/scrapers/families/samai.py::_numero_extra_desde_texto),
# pero siempre empieza con un dígito, a diferencia de la sigla de clase que
# reemplaza cuando el título aún no está complementado (siempre empieza con
# letra mayúscula) — basta con mirar el primer carácter para distinguir los
# dos casos.
_YA_COMPLEMENTADO_RE = re.compile(r"^[\d-]+\(\d[^)]*\)")

# El número entre paréntesis, cuando trae punto de miles, es siempre
# solo dígitos y puntos (a diferencia del formato número-año como
# "3104-2023", que trae guion y por eso no matchea aquí — no necesita esta
# corrección porque nunca tuvo punto). Ancla el título completo para no tocar
# nada del radicado ni de la sigla que viene después del número.
_NUMERO_CON_PUNTO_RE = re.compile(r"^([\d-]+)\(([\d.]+)\)(.*)$")


def _quitar_punto_del_numero(title: str) -> str | None:
    match = _NUMERO_CON_PUNTO_RE.match(title or "")
    if not match:
        return None
    radicado, numero, resto = match.groups()
    if "." not in numero:
        return None
    return f"{radicado}({numero.replace('.', '')}){resto}"


def backfill_quitar_puntos(db: Session) -> dict:
    documentos = db.scalars(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.name == "Consejo de Estado")
    ).all()

    documents_updated = 0
    for documento in documentos:
        nuevo_titulo = _quitar_punto_del_numero(documento.title)
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
                numero = _numero_extra_desde_texto(texto, radicado)
                if not numero:
                    continue

                nuevo_titulo = _complementar_titulo_con_numero(documento.title, numero)
                repository.update_document_title(db, documento.id, nuevo_titulo)
                documents_updated += 1
            except Exception as e:
                logger.warning("No se pudo procesar el documento %s: %s", documento.id, e)
                db.rollback()
                continue
            finally:
                local_path.unlink(missing_ok=True)

    return {"documents_updated": documents_updated}


def main():
    db = SessionLocal()
    try:
        result = backfill(db)
        print(f"Documentos actualizados (complementados): {result['documents_updated']}")
        result_puntos = backfill_quitar_puntos(db)
        print(f"Documentos actualizados (punto quitado): {result_puntos['documents_updated']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
