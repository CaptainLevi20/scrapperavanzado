from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from api.deps import get_db, require_api_key
from api.schemas import DocumentOut, DocumentReviewUpdate, PaginatedDocuments
from core.db import repository
from core.storage import presigned_url

router = APIRouter(dependencies=[Depends(require_api_key)])


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


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    document = repository.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return document


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
