"""Corrida única: pone la fecha real (la de firma, leída del encabezado del
.docx) a los conceptos del ICBF que se guardaron con el 1 de enero de su año, y
cambia su doc_id al nuevo formato (sólo la URL del archivo, sin la fecha) — ver
core/scrapers/families/icbf.py.

Hay que correrlo JUSTO DESPUÉS de actualizar producción y ANTES de la siguiente
corrida diaria: el código nuevo calcula el doc_id sin la fecha, así que sin
este paso no reconocería los conceptos ya guardados y los volvería a bajar,
duplicados.

Por cada concepto del ICBF:
1. doc_id nuevo = sha1 de su URL (lo mismo que compute_doc_id con
   include_publication_date=False). Si otro documento ya tiene ese doc_id, no
   se toca y se avisa.
2. Fecha: se lee el .docx guardado en MinIO con las mismas reglas que la
   ingesta diaria (_fecha_del_encabezado). Si no se encuentra o el encabezado
   es de otro concepto, se deja la fecha que tenía.

El archivo guardado no se mueve: su carpeta sigue diciendo <año>-01-01. Sólo
cambian los datos del documento en la base.

Uso (en el servidor):
  python -m core.backfill_icbf_fechas --simular   # solo cuenta, no cambia nada
  python -m core.backfill_icbf_fechas             # aplica
Se puede correr más de una vez: lo ya corregido no se vuelve a tocar.
"""
import argparse
import hashlib
import logging
import re
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from sqlalchemy import select

from core.db.models import Document, Source
from core.db.session import SessionLocal
from core.scrapers.families.icbf import _fecha_del_encabezado, _texto_inicial_docx
from core.storage import download_file

logger = logging.getLogger(__name__)

_FAMILY_KEY = "icbf"
_TITULO_RE = re.compile(r"^CTO_ICBF_(\d+(?:[A-Z]|-\d+)?)_(\d{4})$")


def doc_id_nuevo(url: str) -> str:
    """Igual que core.utils.compute_doc_id(doc, include_publication_date=False)."""
    return hashlib.sha1(url.encode()).hexdigest()


def _numero_y_anio(titulo: str) -> Tuple[Optional[str], Optional[int]]:
    m = _TITULO_RE.match(titulo or "")
    return (m.group(1), int(m.group(2))) if m else (None, None)


def _fecha_desde_docx(documento: Document, carpeta: Path):
    numero, anio = _numero_y_anio(documento.title)
    if numero is None:
        return None, f"título '{documento.title}' sin número y año legibles"
    local = carpeta / f"doc_{documento.id}.docx"
    try:
        download_file(documento.storage_bucket, documento.storage_key, local)
        texto = _texto_inicial_docx(local.read_bytes())
    except Exception as exc:
        return None, f"no se pudo leer el archivo guardado: {exc}"
    finally:
        local.unlink(missing_ok=True)
    return _fecha_del_encabezado(texto, numero, anio)


def backfill(db, simular: bool = False) -> dict:
    documentos = db.scalars(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.family_key == _FAMILY_KEY)
    ).all()
    resultado = {"revisados": 0, "fecha_corregida": 0, "fecha_sin_cambio": 0, "doc_id_cambiado": 0, "avisos": 0}

    with tempfile.TemporaryDirectory(prefix="backfill_icbf_") as tmp:
        for documento in documentos:
            resultado["revisados"] += 1
            cambios = False

            if documento.source_url:
                nuevo = doc_id_nuevo(documento.source_url)
                if nuevo != documento.doc_id:
                    otro = db.scalars(select(Document.id).where(Document.doc_id == nuevo)).first()
                    if otro is not None:
                        resultado["avisos"] += 1
                        logger.warning("%s: el doc_id nuevo ya lo tiene el documento %s; no se cambia", documento.title, otro)
                    else:
                        resultado["doc_id_cambiado"] += 1
                        if not simular:
                            documento.doc_id = nuevo
                            cambios = True
            else:
                resultado["avisos"] += 1
                logger.warning("%s (id %s) no tiene URL de origen; doc_id sin cambiar", documento.title, documento.id)

            fecha, motivo = _fecha_desde_docx(documento, Path(tmp))
            if fecha is None:
                resultado["fecha_sin_cambio"] += 1
                logger.info("%s: se deja la fecha %s (%s)", documento.title, documento.f_public, motivo)
            elif fecha != documento.f_public or fecha != documento.f_providencia:
                resultado["fecha_corregida"] += 1
                if not simular:
                    documento.f_public = fecha
                    documento.f_providencia = fecha
                    cambios = True
            else:
                resultado["fecha_sin_cambio"] += 1

            if cambios:
                db.commit()
            if resultado["revisados"] % 100 == 0:
                logger.info("Revisados %s conceptos...", resultado["revisados"])
    return resultado


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--simular", action="store_true", help="solo cuenta, no cambia nada")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        r = backfill(db, simular=args.simular)
        logger.info(
            "%sICBF: %s conceptos revisados — %s con fecha corregida, %s con la fecha que tenían; "
            "%s doc_id cambiados; %s avisos",
            "[SIMULACIÓN, nada se cambió] " if args.simular else "",
            r["revisados"], r["fecha_corregida"], r["fecha_sin_cambio"], r["doc_id_cambiado"], r["avisos"],
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
