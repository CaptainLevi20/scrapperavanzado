"""Corrida única (noviembre 2026): reconoce en el buscador nuevo de la Corte
Suprema (Ojeador) las providencias de la CSJ que ya estaban guardadas con el
buscador viejo, para que la corrida de recuperación no las baje otra vez.

El scraper nuevo identifica cada providencia por su enlace de descarga en
Ojeador; las guardadas tienen el `doc_id` calculado con la ruta del buscador
viejo, así que el worker no las reconocería y las bajaría de nuevo con
sufijo "-v2". Este script busca cada una por su código ("AC2794-2026") y, si
la encuentra sin ambigüedad, actualiza SOLO su identidad: `doc_id`,
`source_url`, `f_public` y `f_providencia` (pasan de la fecha de carga del
buscador viejo a la fecha de firma). El archivo, el título y la carpeta no se
tocan. No borra nada.

Uso (simula por defecto, no cambia nada):
    python -m core.backfill_csj_ojeador
    python -m core.backfill_csj_ojeador --aplicar

Se puede correr más de una vez: lo ya reconocido no se vuelve a tocar.
"""
import argparse
import logging
import re
from datetime import date
from typing import Optional, Union

import requests
from sqlalchemy import select

from core.db.models import Document, Source
from core.db.session import SessionLocal
from core.scrapers.families.corte_suprema import _BASE, _codigo_from_titulo, _doc_desde_resultado
from core.utils import compute_doc_id

logger = logging.getLogger(__name__)

_FAMILY_KEY = "corte_suprema"
# El worker guarda sólo link["url"]; con el buscador viejo todas las
# providencias de la CSJ compartían esta misma URL de descarga (POST).
_URL_VIEJA = "https://consultaprovidenciasbk.cortesuprema.gov.co/downloadFile/"
_SUFIJO_VERSION = re.compile(r"-v\d+$")
_AMBIGUO = "ambiguo"


def buscar_en_ojeador(codigo: str) -> list[dict]:
    response = requests.get(
        f"{_BASE}/search/", params={"query_text": codigo, "limit": "20", "page": "1"}, timeout=60
    )
    response.raise_for_status()
    return response.json().get("docs") or []


def _codigo(titulo: str) -> Optional[str]:
    return _codigo_from_titulo(_SUFIJO_VERSION.sub("", (titulo or "").strip()))


def elegir_coincidencia(titulo: str, resultados: list[dict]) -> Union[dict, None, str]:
    """El resultado de Ojeador que corresponde a `titulo`: el de Numerador
    exacto; si hay varios, el de Nombre igual al título. None = no hay;
    "ambiguo" = varios sin forma de elegir. (No se compara la fecha: lo
    guardado tiene la fecha de carga del buscador viejo, no la de firma.)"""
    codigo = _codigo(titulo)
    if not codigo:
        return None
    sin_version = _SUFIJO_VERSION.sub("", titulo.strip())
    numerador = codigo.split()[0].split("(")[0].upper()
    candidatos = [r for r in resultados if (r.get("Numerador") or "").strip().upper() == numerador]
    if len(candidatos) > 1:
        candidatos = [r for r in candidatos if (r.get("Nombre") or "").strip() == sin_version]
        if len(candidatos) != 1:
            return _AMBIGUO
    return candidatos[0] if candidatos else None


def backfill(db, aplicar: bool = False) -> dict:
    documentos = db.scalars(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.family_key == _FAMILY_KEY)
    ).all()

    resultado = {"actualizados": 0, "sin_coincidencia": 0, "ambiguos": 0, "ya_migrados": 0, "detalle_pendientes": []}
    for documento in documentos:
        if documento.source_url != _URL_VIEJA:
            resultado["ya_migrados"] += 1
            continue

        codigo = _codigo(documento.title)
        try:
            hits = buscar_en_ojeador(codigo.split()[0]) if codigo else []
        except Exception as e:
            logger.warning("No se pudo buscar %s en Ojeador: %s", documento.title, e)
            hits = []
        elegido = elegir_coincidencia(documento.title, hits)

        if elegido is None:
            resultado["sin_coincidencia"] += 1
            resultado["detalle_pendientes"].append(documento.title)
            continue

        nuevo = _doc_desde_resultado(elegido) if elegido != _AMBIGUO else None
        nuevo_doc_id = compute_doc_id(nuevo) if nuevo else None
        if nuevo is None or db.scalar(select(Document.id).where(Document.doc_id == nuevo_doc_id)) is not None:
            # Varias candidatas, o ya hay otro documento con esa identidad
            # (p. ej. una corrida nueva lo bajó antes del script): no se toca.
            resultado["ambiguos"] += 1
            resultado["detalle_pendientes"].append(documento.title)
            continue

        resultado["actualizados"] += 1
        if aplicar:
            fecha = date.fromisoformat(nuevo.f_public)
            documento.doc_id = nuevo_doc_id
            documento.source_url = nuevo.link["url"]
            documento.f_public = fecha
            documento.f_providencia = fecha
            db.commit()

    return resultado


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--aplicar", action="store_true", help="hacer los cambios (sin esto sólo simula)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        r = backfill(db, aplicar=args.aplicar)
        modo = "APLICADO" if args.aplicar else "SIMULACIÓN (no se cambió nada; usa --aplicar)"
        logger.info(
            "CSJ → Ojeador [%s]: %s reconocidas, %s sin coincidencia, %s ambiguas, %s ya migradas",
            modo, r["actualizados"], r["sin_coincidencia"], r["ambiguos"], r["ya_migrados"],
        )
        for titulo in r["detalle_pendientes"]:
            logger.info("  pendiente: %s", titulo)
    finally:
        db.close()


if __name__ == "__main__":
    main()
