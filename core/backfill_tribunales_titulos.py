"""Corrida única: corrige el título de los documentos de Tribunales Superiores
que quedaron con el nombre de archivo crudo de la fuente en vez de
"T_{CODIGO}_{radicado}" — ver core/scrapers/families/rama_judicial.py.

Dos pasos por documento, en este orden:
1. Por el nombre: el radicado completo venía en el nombre pero no al inicio, o
   con guiones/espacios entre sus partes (~24% en producción, octubre 2026).
2. Por el PDF: se lee la primera página del archivo guardado y se toma el
   radicado solo si no hay ambigüedad (mismas reglas que la ingesta diaria,
   _titulo_desde_pdf). Aprovecha la misma lectura para la fecha de providencia.

Las listas de Estados del día (varios procesos en un archivo) y los Juzgados
no se tocan. Los archivos se renombran con core/storage_sync.py, que agrupa
las actuaciones del mismo radicado y no toca nada si dos calcularían el mismo
nombre.

Uso (en el servidor):
  python -m core.backfill_tribunales_titulos --simular   # solo cuenta, no cambia nada
  python -m core.backfill_tribunales_titulos             # aplica
  python -m core.backfill_tribunales_titulos --sin-pdf   # solo el paso 1 (minutos)
Se puede correr más de una vez: un título ya corregido no se vuelve a tocar.
"""
import argparse
import logging
import tempfile
from pathlib import Path

from sqlalchemy import select

from core import storage_sync
from core.db.models import Document, Source
from core.db.session import SessionLocal
from core.fecha_es import parse_fecha_providencia_es
from core.scrapers.families.rama_judicial import (
    _LISTA_DE_ESTADOS,
    TRIBUNAL_CODES,
    _extraer_texto_primera_pagina,
    _normalize_title,
    _titulo_desde_pdf,
)
from core.storage import download_file
from core.utils import is_radicado_title

logger = logging.getLogger(__name__)

_FAMILY_KEY = "rama_judicial"


def _es_pdf(documento: Document) -> bool:
    return (documento.content_type or "").lower() == "application/pdf" or (documento.storage_key or "").lower().endswith(".pdf")


def _titulo_y_fecha_desde_pdf(documento: Document, dept_code: str, carpeta: Path):
    """(título, fecha de providencia) leídos del PDF guardado, o (None, None)."""
    local = carpeta / f"doc_{documento.id}.pdf"
    try:
        download_file(documento.storage_bucket, documento.storage_key, local)
        texto = _extraer_texto_primera_pagina(local)
    except Exception as exc:
        logger.warning("No se pudo leer el PDF del documento %s: %s", documento.id, exc)
        return None, None
    finally:
        local.unlink(missing_ok=True)
    titulo = _titulo_desde_pdf(documento.title, texto, dept_code)
    return titulo, (parse_fecha_providencia_es(texto) if titulo else None)


def backfill(db, leer_pdf: bool = True, simular: bool = False) -> dict:
    filas = db.execute(
        select(Document, Source.family_params)
        .join(Source, Source.id == Document.source_id)
        .where(Source.family_key == _FAMILY_KEY)
    ).all()

    resultado = {"revisados": 0, "por_nombre": 0, "por_pdf": 0, "sin_cambio": 0, "archivos_renombrados": 0}
    titulos_nuevos: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="backfill_tribunales_") as tmp:
        for documento, family_params in filas:
            dept_code = (family_params or {}).get("dept_code", "")
            if dept_code not in TRIBUNAL_CODES or is_radicado_title(documento.title):
                continue
            resultado["revisados"] += 1
            if resultado["revisados"] % 500 == 0:
                logger.info("Revisados %s documentos...", resultado["revisados"])

            nuevo, fecha, via = _normalize_title(documento.title, dept_code), None, "por_nombre"
            if nuevo == documento.title:
                nuevo = None
                # Las listas de Estados nunca se renombran: ni se descargan.
                if leer_pdf and _es_pdf(documento) and not _LISTA_DE_ESTADOS.search(documento.title):
                    nuevo, fecha = _titulo_y_fecha_desde_pdf(documento, dept_code, Path(tmp))
                    via = "por_pdf"
            if nuevo is None:
                resultado["sin_cambio"] += 1
                continue

            resultado[via] += 1
            if simular:
                continue
            documento.title = nuevo
            if fecha is not None and documento.f_providencia is None:
                documento.f_providencia = fecha
            db.commit()
            titulos_nuevos.add(nuevo)

    # Renombra los archivos de cada radicado corregido (y de sus "hermanos" ya
    # existentes con el mismo título), con detección de choques.
    for titulo in sorted(titulos_nuevos):
        renombrados = storage_sync.reconcile_title_group(db, _FAMILY_KEY, titulo)
        resultado["archivos_renombrados"] += renombrados["documentos_renombrados"]
    return resultado


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--simular", action="store_true", help="solo cuenta, no cambia nada")
    parser.add_argument("--sin-pdf", action="store_true", help="solo corrige por el nombre, sin leer los PDFs")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        r = backfill(db, leer_pdf=not args.sin_pdf, simular=args.simular)
        logger.info(
            "%sTribunales Superiores: %s revisados — %s corregidos por el nombre, %s por el PDF, "
            "%s sin cambio; %s archivos renombrados",
            "[SIMULACIÓN, nada se cambió] " if args.simular else "",
            r["revisados"], r["por_nombre"], r["por_pdf"], r["sin_cambio"], r["archivos_renombrados"],
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
