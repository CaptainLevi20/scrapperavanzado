from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_session
from api.schemas import MonthlyReportCreate, MonthlyReportOut
from core.config import get_settings
from core.db import repository
from core.storage import presigned_url
from worker.tasks import build_monthly_report

router = APIRouter(dependencies=[Depends(require_session)])


@router.post("/reports", response_model=MonthlyReportOut, status_code=status.HTTP_202_ACCEPTED)
def post_report(payload: MonthlyReportCreate, db: Session = Depends(get_db)):
    period = date(payload.period.year, payload.period.month, 1)
    today = date.today()
    current_period = date(today.year, today.month, 1)
    if period > current_period:
        raise HTTPException(status_code=400, detail="No se puede generar el reporte de un mes futuro.")

    report = repository.create_monthly_report(db, period=period, triggered_by="manual")
    build_monthly_report.delay(report.id)
    return report


@router.get("/reports", response_model=list[MonthlyReportOut])
def get_reports(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    return repository.list_monthly_reports(db, limit=limit, offset=offset)


@router.get("/reports/{report_id}/download")
def get_report_download(report_id: int, db: Session = Depends(get_db)):
    report = repository.get_monthly_report(db, report_id)
    if report is None or report.status != "completed" or not report.storage_key:
        raise HTTPException(status_code=404, detail="Reporte no disponible")

    bucket = report.storage_bucket or get_settings().s3_bucket
    url = presigned_url(
        bucket,
        report.storage_key,
        response_content_disposition=f'attachment; filename="reporte_{report.period:%Y-%m}.pdf"',
    )
    return {"url": url}
