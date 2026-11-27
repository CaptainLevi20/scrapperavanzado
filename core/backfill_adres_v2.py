"""Corrida única (noviembre 2026): reconoce en el sitio nuevo de la ADRES
(Next.js + Payload, agosto de 2026) los documentos `adres` que ya estaban
guardados con el scraper v1, para que la v2 no los baje otra vez como
documentos nuevos.

Con el sitio nuevo la URL de todos los archivos cambió
(`/normativa/ResolucionesADRES/<archivo>` → `/api/media/file/<archivo>`) y con
ella el `doc_id` (sha1 de URL + fecha). El nombre del archivo y la fecha se
conservaron. Este script recorre el listado nuevo con el scraper v2, busca
cada documento guardado por nombre de archivo (y, si hace falta desempatar,
por fecha) y le pone la identidad y el título de la v2: `doc_id`,
`source_url`, `title`, `tipo`, `f_public`, `f_providencia` y `detalle`.
Después renombra el archivo en el almacenamiento (y sus versiones
archivadas) con core/storage_sync.py. Conserva marcas de revisión,
historial y descargas masivas. No baja ni borra nada; lo que no encuentra
no se toca.

Diseño: docs/superpowers/specs/2026-11-23-fuente-adres-design.md (opción A).

Uso (simula por defecto, no cambia nada):
    python -m core.backfill_adres_v2
    python -m core.backfill_adres_v2 --aplicar

Se puede correr más de una vez: lo ya migrado no se vuelve a tocar.
"""
import argparse
import logging
from datetime import date
from typing import Optional, Union
from urllib.parse import unquote, urlparse

from sqlalchemy import select

from core import storage_sync
from core.db.models import Document, Source
from core.db.session import SessionLocal
from core.models import RawDocModel
from core.scrapers.families.adres import ScrapADRES
from core.utils import compute_doc_id

logger = logging.getLogger(__name__)

_FAMILY_KEY = "adres"
_PREFIJO_NUEVO = "/api/media/file/"
_AMBIGUO = "ambiguo"


def clave_archivo(url: Optional[str]) -> str:
    """Nombre del archivo de una URL, sin codificar y en minúsculas, para
    comparar la ruta vieja con la nueva ("Resoluci%C3%B3n%20137.pdf" y
    "Resolución 137.pdf" son el mismo)."""
    ruta = urlparse(url or "").path
    return unquote(ruta.rsplit("/", 1)[-1]).strip().lower()


def ya_migrado(source_url: Optional[str]) -> bool:
    return urlparse(source_url or "").path.startswith(_PREFIJO_NUEVO)


def indice_del_sitio(docs: list[RawDocModel]) -> dict[str, list[RawDocModel]]:
    indice: dict[str, list[RawDocModel]] = {}
    for doc in docs:
        indice.setdefault(clave_archivo(doc.link["url"]), []).append(doc)
    return indice


def elegir_coincidencia(source_url: Optional[str], f_public: Optional[date], indice: dict) -> Union[RawDocModel, None, str]:
    """El documento del listado nuevo que corresponde al guardado: el del
    mismo nombre de archivo; si hay varios, el de la misma fecha. None = no
    está; "ambiguo" = varios sin forma de elegir. Con un solo candidato no se
    exige la fecha: la v2 corrige la de 4 resoluciones cuyo año no cuadra con
    el del nombre (ver el diseño), y el nombre del archivo ya es único."""
    candidatos = indice.get(clave_archivo(source_url)) or []
    if len(candidatos) > 1:
        fecha = f_public.isoformat() if f_public else None
        candidatos = [c for c in candidatos if c.f_public == fecha]
        if len(candidatos) != 1:
            return _AMBIGUO
    return candidatos[0] if candidatos else None


def documentos_del_sitio(scraper=None) -> list[RawDocModel]:
    scraper = scraper or ScrapADRES()
    avisos = []
    docs = scraper.scrap("1900-01-01", "2100-12-31", on_progress=avisos.append)
    errores = [a for a in avisos if "Error" in a]
    if errores:
        # Sin el listado completo, lo que falte quedaría "sin coincidencia"
        # y sería bajado otra vez como nuevo: mejor no seguir.
        raise RuntimeError("El listado de la ADRES no se leyó completo: " + " | ".join(errores))
    return docs


def backfill(db, docs_sitio: list[RawDocModel], aplicar: bool = False) -> dict:
    indice = indice_del_sitio(docs_sitio)
    documentos = db.scalars(
        select(Document)
        .join(Source, Source.id == Document.source_id)
        .where(Source.family_key == _FAMILY_KEY)
        .order_by(Document.id)
    ).all()

    resultado = {
        "actualizados": 0, "sin_coincidencia": 0, "ambiguos": 0, "ya_migrados": 0,
        "archivos_renombrados": 0, "versiones_renombradas": 0, "detalle_pendientes": [],
    }
    asignados: set[str] = set()
    for documento in documentos:
        if ya_migrado(documento.source_url):
            resultado["ya_migrados"] += 1
            continue

        elegido = elegir_coincidencia(documento.source_url, documento.f_public, indice)
        if elegido is None:
            resultado["sin_coincidencia"] += 1
            resultado["detalle_pendientes"].append(f"{documento.title} (sin coincidencia)")
            continue
        nuevo_doc_id = compute_doc_id(elegido) if elegido != _AMBIGUO else None
        if (
            nuevo_doc_id is None
            or nuevo_doc_id in asignados
            or db.scalar(select(Document.id).where(Document.doc_id == nuevo_doc_id, Document.id != documento.id)) is not None
        ):
            # Varias candidatas, dos guardados que van al mismo documento
            # nuevo (p. ej. el duplicado 12758/2023 que la v2 junta), o ya hay
            # otro documento con esa identidad: no se toca.
            resultado["ambiguos"] += 1
            resultado["detalle_pendientes"].append(f"{documento.title} (ambiguo o ya existe)")
            continue
        asignados.add(nuevo_doc_id)

        resultado["actualizados"] += 1
        if not aplicar:
            logger.info("[simulación] %r -> %r (%s)", documento.title, elegido.title, elegido.f_public)
            continue

        fecha = date.fromisoformat(elegido.f_public)
        documento.doc_id = nuevo_doc_id
        documento.source_url = elegido.link["url"]
        documento.title = elegido.title
        documento.tipo = elegido.tipo
        documento.f_public = fecha
        documento.f_providencia = date.fromisoformat(elegido.f_providencia) if elegido.f_providencia else fecha
        documento.detalle = elegido.detalle
        db.commit()
        db.refresh(documento)
        if storage_sync.reconcile_document(db, documento, _FAMILY_KEY, tiene_actuaciones=False):
            resultado["archivos_renombrados"] += 1
        resultado["versiones_renombradas"] += storage_sync.reconcile_document_versions(
            db, documento, _FAMILY_KEY, tiene_actuaciones=False
        )

    return resultado


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--aplicar", action="store_true", help="hacer los cambios (sin esto sólo simula)")
    args = parser.parse_args()

    docs_sitio = documentos_del_sitio()
    db = SessionLocal()
    try:
        r = backfill(db, docs_sitio, aplicar=args.aplicar)
        modo = "APLICADO" if args.aplicar else "SIMULACIÓN (no se cambió nada; usa --aplicar)"
        logger.info(
            "ADRES v2 [%s]: %s reconocidos, %s sin coincidencia, %s ambiguos, %s ya migrados; "
            "%s archivos y %s versiones renombrados",
            modo, r["actualizados"], r["sin_coincidencia"], r["ambiguos"], r["ya_migrados"],
            r["archivos_renombrados"], r["versiones_renombradas"],
        )
        for pendiente in r["detalle_pendientes"]:
            logger.info("  pendiente: %s", pendiente)
    finally:
        db.close()


if __name__ == "__main__":
    main()
