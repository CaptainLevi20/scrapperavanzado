from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_session
from api.schemas import RunCreate, RunOut, RunSourceOut
from core.db import repository
from worker.tasks import orchestrate_run

router = APIRouter(dependencies=[Depends(require_session)])


@router.post("/runs", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
def post_run(payload: RunCreate, db: Session = Depends(get_db)):
    run = repository.create_run(db, triggered_by="manual", fini=payload.fini, ffin=payload.ffin)
    orchestrate_run.delay(run.id, payload.source_ids)
    return run


@router.get("/runs", response_model=list[RunOut])
def get_runs(
    status_filter: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return repository.list_runs(db, status=status_filter, limit=limit, offset=offset)


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = repository.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run no encontrado")
    return run


@router.get("/runs/{run_id}/sources", response_model=list[RunSourceOut])
def get_run_sources(run_id: int, db: Session = Depends(get_db)):
    return repository.list_run_sources_with_source_names(db, run_id)


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
def post_run_cancel(run_id: int, db: Session = Depends(get_db)):
    run = repository.request_run_cancel(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run no encontrado")
    return run
