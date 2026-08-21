"""Corrida única: corrige el estado de los runs que quedaron marcados
'failed' cuando en realidad solo algunas de sus fuentes fallaron, no todas.

Antes del 2026-08-21, worker/tasks.py::_finalize_run marcaba el run entero
como 'failed' apenas UNA fuente fallaba, sin importar cuántas otras hubieran
terminado bien — confuso para quien lo veía en la lista (por ejemplo, "1 de
70 fuentes falló" se veía igual de alarmante que "las 70 fallaron"). Ahora
existe un tercer estado, 'completed_with_errors', para el fracaso parcial;
este script reclasifica los runs ya guardados que deberían haber quedado así.

No toca runs 'completed' ni 'cancelled' — el bug solo afectaba a los que ya
terminaron en 'failed'.

Uso: .venv/Scripts/python -m core.backfill_run_status
Se puede correr más de una vez sin problema: un run que ya está bien no se toca.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import Run
from core.db.session import SessionLocal


def backfill(db: Session) -> dict:
    failed_runs = db.scalars(select(Run).where(Run.status == "failed")).all()

    runs_updated = 0
    for run in failed_runs:
        run_sources = repository.list_run_sources(db, run.id)
        if run_sources and any(rs.status != "failed" for rs in run_sources):
            run.status = "completed_with_errors"
            runs_updated += 1

    db.commit()
    return {"runs_updated": runs_updated}


def main():
    db = SessionLocal()
    try:
        result = backfill(db)
        print(f"Runs actualizados: {result['runs_updated']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
