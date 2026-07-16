import logging
from typing import Optional

from celery.exceptions import TimeoutError as CeleryTimeoutError
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from api.deps import get_db, require_session
from api.schemas import BulkDocumentReviewUpdate, DocumentOut, DocumentReviewUpdate, PaginatedDocuments
from core.db import repository
from core.storage import presigned_url
from worker.tasks import generate_document_preview_pdf

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_session)])

# Tipos que requieren conversión bajo demanda (application/pdf se maneja aparte,
# como passthrough directo, antes de siquiera consultar este set).
CONVERTIBLE_CONTENT_TYPES = {
    "application/rtf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
PREVIEW_TASK_TIMEOUT_SECONDS = 30


@router.get("/documents", response_model=PaginatedDocuments)
def get_documents(
    source_id: Optional[int] = None,
    family_key: Optional[str] = None,
    tipo: Optional[str] = None,
    title: Optional[str] = None,
    review_status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    items, total = repository.list_documents(
        db,
        source_id=source_id,
        family_key=family_key,
        tipo=tipo,
        review_status=review_status,
        title_contains=title,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/documents/tipos", response_model=list[str])
def get_document_tipos(db: Session = Depends(get_db)):
    return repository.list_distinct_document_tipos(db)


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    document = repository.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return document


@router.patch("/documents/bulk-review")
def patch_bulk_document_review_status(payload: BulkDocumentReviewUpdate, db: Session = Depends(get_db)):
    updated = repository.bulk_update_document_review_status(db, payload.document_ids, payload.review_status)
    return {"updated": updated}


@router.patch("/documents/{document_id}", response_model=DocumentOut)
def patch_document_review_status(document_id: int, payload: DocumentReviewUpdate, db: Session = Depends(get_db)):
    document = repository.update_document_review_status(db, document_id, payload.review_status)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return document


@router.get("/documents/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db)):
    document = repository.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    url = presigned_url(document.storage_bucket, document.storage_key)
    return RedirectResponse(url)


@router.get("/documents/{document_id}/preview")
def preview_document(document_id: int, db: Session = Depends(get_db)):
    document = repository.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    if document.content_type == "application/pdf":
        url = presigned_url(document.storage_bucket, document.storage_key)
        return RedirectResponse(url)

    if document.content_type not in CONVERTIBLE_CONTENT_TYPES:
        raise HTTPException(status_code=404, detail="Vista previa no disponible para este tipo de archivo")

    if document.preview_storage_key:
        url = presigned_url(document.storage_bucket, document.preview_storage_key)
        return RedirectResponse(url)

    try:
        preview_key = generate_document_preview_pdf.delay(document_id).get(timeout=PREVIEW_TASK_TIMEOUT_SECONDS)
    except CeleryTimeoutError:
        raise HTTPException(
            status_code=504, detail="La vista previa está tardando más de lo esperado, intenta de nuevo"
        )
    except Exception:
        logger.exception("Falló la generación de la vista previa para el documento %s", document_id)
        raise HTTPException(status_code=502, detail="No se pudo generar la vista previa")

    url = presigned_url(document.storage_bucket, preview_key)
    return RedirectResponse(url)
