from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.deps import get_db, require_session
from api.schemas import RunCreate, RunOut, RunSourceOut
from core.db import repository
from core.run_report import build_run_report_workbook
from worker.tasks import orchestrate_run, retry_failed_run_sources_task

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


@router.get("/runs/{run_id}/report.xlsx")
def get_run_report(run_id: int, db: Session = Depends(get_db)):
    run = repository.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run no encontrado")

    workbook_bytes = build_run_report_workbook(
        repository.list_run_sources_with_source_names(db, run_id),
        repository.list_new_documents_for_run(db, run_id),
        repository.list_updated_documents_for_run(db, run_id),
        repository.list_run_errors_for_run(db, run_id),
    )
    return StreamingResponse(
        iter([workbook_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="informe_run_{run_id}.xlsx"'},
    )


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
def post_run_cancel(run_id: int, db: Session = Depends(get_db)):
    run = repository.request_run_cancel(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run no encontrado")
    return run


@router.post("/runs/{run_id}/retry-failed", response_model=RunOut)
def post_run_retry_failed(run_id: int, db: Session = Depends(get_db)):
    run = repository.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run no encontrado")

    failed_ids = [rs.id for rs in repository.list_run_sources(db, run_id) if rs.status == "failed"]
    if not failed_ids:
        raise HTTPException(status_code=400, detail="No hay fuentes fallidas para reintentar")

    repository.set_run_status(db, run_id, "running")
    retry_failed_run_sources_task.delay(run_id, failed_ids)
    return repository.get_run(db, run_id)
