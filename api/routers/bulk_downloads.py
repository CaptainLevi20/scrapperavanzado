from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_session
from api.schemas import BulkDownloadOut
from core.config import get_settings
from core.db import repository
from core.storage import presigned_url
from worker.tasks import build_bulk_download_zip

router = APIRouter(dependencies=[Depends(require_session)])


@router.post("/bulk-downloads", response_model=BulkDownloadOut, status_code=status.HTTP_202_ACCEPTED)
def post_bulk_download(db: Session = Depends(get_db)):
    bulk_download = repository.create_bulk_download(db)
    build_bulk_download_zip.delay(bulk_download.id)
    return bulk_download


@router.get("/bulk-downloads", response_model=list[BulkDownloadOut])
def get_bulk_downloads(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return repository.list_bulk_downloads(db, limit=limit, offset=offset)


@router.get("/bulk-downloads/{bulk_download_id}/download")
def get_bulk_download_download(bulk_download_id: int, db: Session = Depends(get_db)):
    bulk_download = repository.get_bulk_download(db, bulk_download_id)
    if bulk_download is None or bulk_download.status != "completed" or not bulk_download.zip_storage_key:
        raise HTTPException(status_code=404, detail="Descarga masiva no disponible")

    # Bulk-download zips always land in the current default bucket (unlike
    # Document rows, which store their own storage_bucket) — fine as long as
    # s3_bucket never changes between when a zip was built and when it's read.
    bucket = get_settings().s3_bucket
    url = presigned_url(
        bucket,
        bulk_download.zip_storage_key,
        response_content_disposition=f'attachment; filename="descarga_masiva_{bulk_download_id}.zip"',
    )
    return {"url": url}
