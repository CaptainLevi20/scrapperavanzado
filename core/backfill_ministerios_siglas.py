"""Corrida única: cambia la sigla del ministerio dentro del título de los
documentos ya guardados, según el nuevo mapeo — ver los scrapers en
core/scrapers/families/ (madr, mindeporte, mineducacion, minenergia,
mininterior, minjusticia, mintrabajo).

El título tiene la forma "<letra>_<SIGLA>_<número>_<año>" (p. ej.
"D_MADR_0765_2026"); solo cambia el token de la sigla ("D_MADR_..." ->
"D_MA_..."). La carpeta de guardado (Fuente/Fecha/Tipo/) no cambia.

Actualiza el título en la base y renombra el archivo (y sus versiones
archivadas) en el almacenamiento, reusando core/storage_sync.py.

Uso: .venv/Scripts/python -m core.backfill_ministerios_siglas
Se puede correr más de una vez sin problema: un título que ya tiene la sigla
nueva, o que no tiene la forma esperada, se deja tal cual.
"""
import logging
import re

from sqlalchemy import select

from core.db import repository
from core.db.models import Document, Source
from core.db.session import SessionLocal
from core.utils import rekey_filename
from core import storage_sync

logger = logging.getLogger(__name__)

# family_key -> (sigla vieja, sigla nueva). Solo las familias que cambian;
# minambiente (MADS), mincit (MCIT) y minvivienda (MVCT) se quedan igual.
_SIGLAS = {
    "madr": ("MADR", "MA"),
    "mindeporte": ("MDEPORTE", "MDEP"),
    "mineducacion": ("MEN", "ME"),
    "minenergia": ("MINENERGIA", "MME"),
    "mininterior": ("MININT", "MI"),
    "minjusticia": ("MINJUSTICIA", "MJ"),
    "mintrabajo": ("MINTRABAJO", "MTRA"),
}


def nuevo_titulo(titulo: str, sigla_vieja: str, sigla_nueva: str) -> str | None:
    """Reemplaza el token de la sigla en un título "<letra>_<SIGLA>_<resto>".
    Devuelve None si `titulo` ya tiene la sigla nueva o no tiene esa forma."""
    match = re.match(rf"^([A-Za-z]+)_{re.escape(sigla_vieja)}_(.+)$", titulo or "")
    if not match:
        return None
    return f"{match.group(1)}_{sigla_nueva}_{match.group(2)}"


def _backfill_familia(db, family_key: str, sigla_vieja: str, sigla_nueva: str) -> dict:
    documentos = db.scalars(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.family_key == family_key)
    ).all()

    pares = [
        (documento, nuevo)
        for documento in documentos
        if (nuevo := nuevo_titulo(documento.title, sigla_vieja, sigla_nueva)) is not None
    ]

    # Guarda de colisión (mismo espíritu que core/storage_sync.py::_grupos_en_colision
    # y core/backfill_csj_titles.py): si dos documentos calcularan la misma clave
    # destino, renombrar ambos haría que el segundo copy_object sobrescriba el
    # archivo del primero. En la práctica no debería pasar acá — el cambio es un
    # swap 1:1 del token de la sigla y las rutas llevan carpeta de fecha/tipo —
    # pero la guarda es barata y consistente.
    grupos_por_key: dict[tuple[str, str], list[tuple[Document, str]]] = {}
    for documento, nuevo in pares:
        nueva_key = rekey_filename(documento.storage_key, nuevo)
        grupos_por_key.setdefault((documento.storage_bucket, nueva_key), []).append((documento, nuevo))

    colisiones_omitidas = 0
    pares_sin_colision: list[tuple[Document, str]] = []
    for (_bucket, nueva_key), grupo in grupos_por_key.items():
        if len(grupo) > 1:
            logger.warning(
                "Colisión de clave calculada en el backfill de %s: los documentos %s calcularían "
                "la misma clave %r — se omiten, sin cambios.",
                family_key, [documento.id for documento, _ in grupo], nueva_key,
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
        if storage_sync.reconcile_document(db, documento, family_key, tiene_actuaciones=False):
            archivos_renombrados += 1
        versiones_renombradas += storage_sync.reconcile_document_versions(
            db, documento, family_key, tiene_actuaciones=False
        )

    return {
        "documentos_actualizados": documentos_actualizados,
        "archivos_renombrados": archivos_renombrados,
        "versiones_renombradas": versiones_renombradas,
        "colisiones_omitidas": colisiones_omitidas,
    }


def backfill(db) -> dict:
    return {
        family_key: _backfill_familia(db, family_key, sigla_vieja, sigla_nueva)
        for family_key, (sigla_vieja, sigla_nueva) in _SIGLAS.items()
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        resultado = backfill(db)
        for family_key, r in resultado.items():
            logger.info(
                "Backfill %s: %s títulos actualizados, %s archivos renombrados, "
                "%s versiones archivadas renombradas, %s omitidos por colisión",
                family_key,
                r["documentos_actualizados"],
                r["archivos_renombrados"],
                r["versiones_renombradas"],
                r["colisiones_omitidas"],
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
