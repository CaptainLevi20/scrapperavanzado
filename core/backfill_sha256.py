"""Corrida repetible: calcula la huella digital (SHA-256) de los documentos y
versiones archivadas que ya estaban guardados antes de que existiera la huella
(2026-11-05). Los que se descargan desde entonces la traen de una vez.

Lee cada archivo del almacenamiento por trozos (sin cargarlo entero en memoria)
y solo escribe la columna sha256: no cambia ni mueve ningún archivo. Solo toca
filas que aún no tienen huella, así que se puede interrumpir y volver a correr
sin problema: retoma donde quedó.

    python -m core.backfill_sha256 --simular   # cuenta lo que calcularía, sin escribir
    python -m core.backfill_sha256             # calcula y guarda
"""
import argparse
import hashlib
import logging

from sqlalchemy import select

from core.db.models import Document, DocumentVersion
from core.db.session import SessionLocal

logger = logging.getLogger(__name__)

_GUARDAR_CADA = 200


def _huella(trozos) -> str:
    h = hashlib.sha256()
    for trozo in trozos:
        h.update(trozo)
    return h.hexdigest()


def calcular_huellas(db, leer, simular: bool = False) -> dict:
    """`leer(bucket, key)` devuelve un iterable de bytes con el contenido del
    objeto, o lanza FileNotFoundError si no existe. Devuelve cuántas huellas
    calculó (documentos, versiones) y cuántos archivos no encontró."""
    resumen = {"documentos": 0, "versiones": 0, "no_encontrados": 0}
    for modelo, clave in ((Document, "documentos"), (DocumentVersion, "versiones")):
        ids = db.scalars(select(modelo.id).where(modelo.sha256.is_(None)).order_by(modelo.id)).all()
        for i, id_ in enumerate(ids, start=1):
            fila = db.get(modelo, id_)
            try:
                huella = _huella(leer(fila.storage_bucket, fila.storage_key))
            except FileNotFoundError:
                resumen["no_encontrados"] += 1
                logger.warning("No está en el almacenamiento: %s %s (%s)", clave, id_, fila.storage_key)
                continue
            resumen[clave] += 1
            if not simular:
                fila.sha256 = huella
                if i % _GUARDAR_CADA == 0:
                    db.commit()
                    logger.info("%s: %s de %s", clave, i, len(ids))
        if not simular:
            db.commit()
    return resumen


def main() -> None:
    parser = argparse.ArgumentParser(description="Calcula la huella SHA-256 de lo ya guardado.")
    parser.add_argument("--simular", action="store_true", help="no escribe nada; solo cuenta")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from botocore.exceptions import ClientError

    from core.storage import _client

    cliente = _client()

    def leer(bucket, key):
        try:
            cuerpo = cliente.get_object(Bucket=bucket, Key=key)["Body"]
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                raise FileNotFoundError(key) from exc
            raise
        return cuerpo.iter_chunks(1024 * 1024)

    db = SessionLocal()
    try:
        resumen = calcular_huellas(db, leer, simular=args.simular)
    finally:
        db.close()
    modo = "SIMULACIÓN (no se escribió nada)" if args.simular else "Listo"
    logger.info(
        "%s: huellas de %s documentos y %s versiones; %s archivos no encontrados.",
        modo, resumen["documentos"], resumen["versiones"], resumen["no_encontrados"],
    )


if __name__ == "__main__":
    main()
