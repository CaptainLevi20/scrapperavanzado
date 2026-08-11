"""Corrida única: sincroniza storage_key en `documents` y `document_versions`
con el nombre canónico vigente de cada uno — ver core/storage_sync.py y
docs/superpowers/specs/2026-08-11-sincronizar-nombre-archivo-minio-design.md.
Se puede correr más de una vez sin problema: lo que ya coincide no se toca.

Uso: .venv/Scripts/python -m core.backfill_storage_key_sync
"""
import logging

from sqlalchemy.orm import Session

from core.db.session import SessionLocal
from core.storage import rename_object  # noqa: F401 — reexportado para que los tests lo puedan parchear aquí
from core.storage_sync import reconcile_all

logger = logging.getLogger(__name__)


def run_backfill(db: Session) -> dict:
    return reconcile_all(db)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        resultado = run_backfill(db)
        mensaje = (
            f"Documentos renombrados: {resultado['documentos_renombrados']}, "
            f"versiones renombradas: {resultado['versiones_renombradas']}"
        )
        logger.info(mensaje)
        print(mensaje)
    finally:
        db.close()


if __name__ == "__main__":
    main()
