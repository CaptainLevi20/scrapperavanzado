"""Corrida repetible: borra los documentos (y sus versiones, corridas y
errores asociados) de las fuentes que están desactivadas (Source.active ==
False) — para limpiar los datos que trajeron mientras estaban activas, antes
de que se hayan curado o desarrollado bien. Solo toca fuentes desactivadas:
una fuente activa, y sus documentos, nunca se tocan, sin importar cuál sea.

No borra la fuente misma (la fila en `sources`), solo lo que trajo.

Por seguridad, por defecto NO borra nada — solo muestra qué borraría (modo
"simulación"). Para borrar de verdad hay que pasar --confirm:

    .venv/Scripts/python -m core.purge_inactive_source_documents          # simulación
    .venv/Scripts/python -m core.purge_inactive_source_documents --confirm # borra de verdad

Se puede correr más de una vez sin problema: una fuente ya purgada
simplemente no tiene nada que borrar la próxima vez.
"""
import argparse
import logging

from core.db import repository
from core.db.session import SessionLocal
from core.storage import delete_object

logger = logging.getLogger(__name__)


def purge(db, confirm: bool) -> dict:
    fuentes_inactivas = repository.list_sources(db, active=False, limit=10_000)

    resumen = []
    total_documentos = 0
    total_run_sources = 0
    total_objetos_almacenamiento = 0

    for source in fuentes_inactivas:
        if confirm:
            resultado = repository.purge_documents_for_source(db, source.id)
            for bucket, key in resultado["storage_objects"]:
                try:
                    delete_object(bucket, key)
                except Exception as e:
                    logger.warning("No se pudo borrar el objeto %s/%s: %s", bucket, key, e)
        else:
            # Modo simulación: cuenta sin borrar nada — misma consulta que usa
            # purge_documents_for_source, pero sin la parte que sí borra.
            documentos = repository.list_documents(db, source_id=source.id, limit=1, offset=0)
            resultado = {
                "documents_deleted": documentos[1],  # total, no solo la página de 1
                "run_sources_deleted": 0,
                "storage_objects": [],
            }

        total_documentos += resultado["documents_deleted"]
        total_run_sources += resultado["run_sources_deleted"]
        total_objetos_almacenamiento += len(resultado["storage_objects"])
        resumen.append(
            {
                "source_id": source.id,
                "source_name": source.name,
                "documents_deleted": resultado["documents_deleted"],
            }
        )

    return {
        "modo": "borrado real" if confirm else "simulación (nada se borró)",
        "fuentes_inactivas": len(fuentes_inactivas),
        "documentos": total_documentos,
        "run_sources": total_run_sources,
        "objetos_de_almacenamiento": total_objetos_almacenamiento,
        "detalle_por_fuente": resumen,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Borra de verdad. Sin esta bandera, solo muestra qué se borraría.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        resultado = purge(db, confirm=args.confirm)
        print(f"Modo: {resultado['modo']}")
        print(f"Fuentes desactivadas encontradas: {resultado['fuentes_inactivas']}")
        for fila in resultado["detalle_por_fuente"]:
            print(f"  - [{fila['source_id']}] {fila['source_name']}: {fila['documents_deleted']} documentos")
        print(f"Total documentos: {resultado['documentos']}")
        print(f"Total corridas (run_sources): {resultado['run_sources']}")
        print(f"Total objetos de almacenamiento borrados: {resultado['objetos_de_almacenamiento']}")
        if not args.confirm:
            print("\nNada se borró todavía — corre de nuevo con --confirm para borrar de verdad.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
