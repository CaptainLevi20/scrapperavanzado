"""Corrida única: pasa el título de los documentos de la Corte Suprema (CSJ)
ya guardados del formato viejo "CSJ_<sala>_<código>_<año>" al nuevo, que es
el código a secas ("AP2260-2025(62924)") — ver
core/scrapers/families/corte_suprema.py.

La sala (SCT/SCL/SCC/SCP) se sigue usando como carpeta de guardado
(CSJ/<sala>/...); solo desaparece del nombre del archivo. El "_<año>" del
final solo se conserva cuando el resto no es un código reconocible (título
de relleno tipo "doc_2024").

Actualiza el título en la base y renombra el archivo (y sus versiones
archivadas) en el almacenamiento, reusando core/storage_sync.py.

Uso: .venv/Scripts/python -m core.backfill_csj_titles
Se puede correr más de una vez sin problema: un título que ya no lleva el
prefijo, o que no tiene la forma esperada, se deja tal cual.
"""
import logging
import re

from sqlalchemy import select

from core.db import repository
from core.db.models import Document, Source
from core.db.session import SessionLocal
from core.scrapers.families.corte_suprema import _CODIGO_RE
from core.utils import rekey_filename
from core import storage_sync

logger = logging.getLogger(__name__)

_FAMILY_KEY = "corte_suprema"

# "CSJ_" + una de las cuatro siglas de sala + "_" + el cuerpo, con un "-v{n}"
# opcional al final. Un título que ya no lleva el prefijo no matchea, así que
# volver a correr el backfill no lo toca.
_PREFIJO_RE = re.compile(r"^CSJ_(?:SCT|SCL|SCC|SCP)_(.+?)(-v\d+)?$")
# Un "_<año>" (4 dígitos) al final del cuerpo.
_ANIO_FINAL_RE = re.compile(r"^(.*)_\d{4}$")


def nuevo_titulo_csj(titulo: str) -> str | None:
    """Devuelve el título en el formato nuevo (código a secas, con el sufijo
    de versión si lo tenía), o None si `titulo` ya está migrado o no tiene la
    forma vieja. El "_<año>" solo se quita si lo que queda es un código
    reconocible; un título de relleno lo conserva."""
    match = _PREFIJO_RE.match(titulo or "")
    if not match:
        return None
    cuerpo, version = match.group(1), match.group(2) or ""
    sin_anio = _ANIO_FINAL_RE.match(cuerpo)
    if sin_anio and _CODIGO_RE.match(sin_anio.group(1)):
        cuerpo = sin_anio.group(1)
    return f"{cuerpo}{version}"


def backfill(db) -> dict:
    documentos = db.scalars(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.family_key == _FAMILY_KEY)
    ).all()

    # Empareja cada documento migrable con su título nuevo.
    pares = [
        (documento, nuevo)
        for documento in documentos
        if (nuevo := nuevo_titulo_csj(documento.title)) is not None
    ]

    # Antes de renombrar nada, detecta colisiones de clave calculada (mismo
    # espíritu que core/storage_sync.py::_grupos_en_colision). Dos documentos
    # CSJ que hoy solo se diferencian por el "_<año>" del final (mismo código
    # de providencia, distinto año de f_public — ambos sobrevivieron al dedup
    # del scraper) normalizan al mismo título nuevo y, como las claves CSJ son
    # CSJ/<sala>/<título>.<ext> sin carpeta de fecha, a la misma clave destino.
    # Renombrar los dos haría que el segundo copy_object sobrescriba el archivo
    # del primero — pérdida silenciosa de datos. Se omiten ambos lados de cada
    # colisión: ni se actualiza el título ni se reconcilia.
    grupos_por_key: dict[tuple[str, str], list[tuple[Document, str]]] = {}
    for documento, nuevo in pares:
        nueva_key = rekey_filename(documento.storage_key, nuevo)
        grupos_por_key.setdefault((documento.storage_bucket, nueva_key), []).append((documento, nuevo))

    colisiones_omitidas = 0
    pares_sin_colision: list[tuple[Document, str]] = []
    for (_bucket, nueva_key), grupo in grupos_por_key.items():
        if len(grupo) > 1:
            logger.warning(
                "Colisión de clave calculada en el backfill CSJ: los documentos %s calcularían "
                "la misma clave %r — se omiten, sin cambios.",
                [documento.id for documento, _ in grupo], nueva_key,
            )
            colisiones_omitidas += len(grupo)
            continue
        pares_sin_colision.extend(grupo)

    documentos_actualizados = 0
    archivos_renombrados = 0
    versiones_renombradas = 0
    for documento, nuevo in pares_sin_colision:
        try:
            documento = repository.update_document_title(db, documento.id, nuevo)
            documentos_actualizados += 1
        except Exception as exc:
            logger.warning("No se pudo actualizar el título del documento %s: %s", documento.id, exc)
            db.rollback()
            continue
        if storage_sync.reconcile_document(db, documento, _FAMILY_KEY, tiene_actuaciones=False):
            archivos_renombrados += 1
        versiones_renombradas += storage_sync.reconcile_document_versions(
            db, documento, _FAMILY_KEY, tiene_actuaciones=False
        )

    return {
        "documentos_actualizados": documentos_actualizados,
        "archivos_renombrados": archivos_renombrados,
        "versiones_renombradas": versiones_renombradas,
        "colisiones_omitidas": colisiones_omitidas,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        resultado = backfill(db)
        logger.info(
            "Backfill CSJ: %s títulos actualizados, %s archivos renombrados, "
            "%s versiones archivadas renombradas, %s documentos omitidos por colisión de clave",
            resultado["documentos_actualizados"],
            resultado["archivos_renombrados"],
            resultado["versiones_renombradas"],
            resultado["colisiones_omitidas"],
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
