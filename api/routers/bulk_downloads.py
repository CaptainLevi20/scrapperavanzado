import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_session
from api.schemas import BulkDownloadDeletionOut, BulkDownloadOut
from core.config import get_settings
from core.db import repository
from core.storage import delete_object, presigned_url
from worker.tasks import build_bulk_download_zip

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_session)])


@router.post("/bulk-downloads", response_model=BulkDownloadOut, status_code=status.HTTP_202_ACCEPTED)
def post_bulk_download(db: Session = Depends(get_db)):
    bulk_download = repository.create_bulk_download(db)
    build_bulk_download_zip.delay(bulk_download.id)
    return bulk_download


@router.get("/bulk-downloads", response_model=list[BulkDownloadOut])
def get_bulk_downloads(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    return repository.list_bulk_downloads(db, limit=limit, offset=offset)


@router.get("/bulk-downloads/{bulk_download_id}/download")
def get_bulk_download_download(bulk_download_id: int, db: Session = Depends(get_db)):
    bulk_download = repository.get_bulk_download(db, bulk_download_id)
    if bulk_download is None or bulk_download.status != "completed" or not bulk_download.zip_storage_key:
        raise HTTPException(status_code=404, detail="Descarga masiva no disponible")

    # storage_bucket is the bucket the zip actually landed in at the time it was
    # built — recorded so this keeps working even if s3_bucket is reconfigured
    # later. Falls back to the current default only for rows written before this
    # column existed, which have no bucket of their own recorded.
    bucket = bulk_download.storage_bucket or get_settings().s3_bucket
    url = presigned_url(
        bucket,
        bulk_download.zip_storage_key,
        response_content_disposition=f'attachment; filename="descarga_masiva_{bulk_download_id}.zip"',
    )
    return {"url": url}


@router.delete("/bulk-downloads/{bulk_download_id}", response_model=BulkDownloadDeletionOut)
def delete_bulk_download(bulk_download_id: int, db: Session = Depends(get_db)):
    result = repository.delete_bulk_download(db, bulk_download_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Descarga masiva no encontrada")

    # El ZIP en MinIO es un efecto externo, aparte de la base de datos — si esto
    # falla, los documentos ya quedaron liberados y el lote ya no existe (lo que
    # más le importa al usuario); solo queda un ZIP huérfano en el almacenamiento,
    # no un registro roto. Mismo criterio que core/purge_inactive_source_documents.py.
    if result["zip_storage_key"]:
        bucket = result["storage_bucket"] or get_settings().s3_bucket
        try:
            delete_object(bucket, result["zip_storage_key"])
        except Exception as exc:
            logger.warning("No se pudo borrar el ZIP %s/%s: %s", bucket, result["zip_storage_key"], exc)

    return {"documents_freed": result["documents_freed"]}
