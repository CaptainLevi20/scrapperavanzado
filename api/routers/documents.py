import logging
import re
from datetime import date
from typing import Optional

from celery.exceptions import TimeoutError as CeleryTimeoutError
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from api.deps import get_db, require_session
from api.schemas import (
    BulkDocumentReviewUpdate,
    DocumentOut,
    DocumentReviewUpdate,
    DocumentStatsOut,
    DocumentTitleUpdate,
    DocumentVersionOut,
    PaginatedDocuments,
)
from core.db import repository
from core.db.models import Document
from core.storage import presigned_url
from core.utils import is_radicado_title, is_samai_case_title
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

_INVALID_FILENAME_CHARS = re.compile(r'[/\\\x00-\x1f]')


def _preview_content_disposition(document: Document) -> str:
    # The preview is always a PDF regardless of what format the main download
    # (storage_key) is in — this is what lets the presigned URL carry a filename
    # hint that the browser's OWN pdf viewer chrome (not just our UI) picks up for
    # its native download button, without us proxying the bytes through a Blob
    # (which would have thrown this filename information away).
    safe_title = _INVALID_FILENAME_CHARS.sub("-", document.title)
    return f'inline; filename="{safe_title}.pdf"'


@router.get("/documents", response_model=PaginatedDocuments)
def get_documents(
    source_id: Optional[int] = None,
    family_key: Optional[str] = None,
    tipo: Optional[str] = None,
    seccion: Optional[str] = None,
    especialidad: Optional[str] = None,
    magistrado: Optional[str] = None,
    title: Optional[str] = None,
    title_exact: Optional[str] = None,
    review_status: Optional[str] = None,
    f_public_from: Optional[date] = None,
    f_public_to: Optional[date] = None,
    downloaded_from: Optional[date] = None,
    downloaded_to: Optional[date] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = repository.list_documents(
        db,
        source_id=source_id,
        family_key=family_key,
        tipo=tipo,
        seccion=seccion,
        especialidad=especialidad,
        magistrado=magistrado,
        review_status=review_status,
        f_public_from=f_public_from,
        f_public_to=f_public_to,
        downloaded_from=downloaded_from,
        downloaded_to=downloaded_to,
        title_contains=title,
        title_exact=title_exact,
        collapse_case_families=title_exact is None,
        limit=limit,
        offset=offset,
    )

    # Families whose title identifies the case (not one specific actuación) —
    # each has its own title format, so its own check for "does this title
    # actually look like a case title" before it's eligible for grouping.
    # "samai" checks both formats: Consejo de Estado titles look like
    # is_samai_case_title, while Tribunal Administrativo titles mirror
    # rama_judicial's format instead (see core/scrapers/families/samai.py).
    _CASE_TITLE_CHECKS = {
        "rama_judicial": is_radicado_title,
        "samai": lambda title: is_samai_case_title(title) or is_radicado_title(title),
    }
    family_keys = repository.get_source_family_keys(db, [d.source_id for d in items])
    counts: dict[str, int] = {}
    for family_key_, is_case_title in _CASE_TITLE_CHECKS.items():
        titles = [
            d.title for d in items
            if family_keys.get(d.source_id) == family_key_ and is_case_title(d.title)
        ]
        counts.update(repository.count_documents_by_title_within_family(db, titles, family_key_))
    for d in items:
        count = counts.get(d.title)
        d.case_document_count = count if count and count > 1 else None

    case_link_status = repository.get_case_link_status_for_documents(db, [d.id for d in items])
    for d in items:
        info = case_link_status.get(d.id)
        if info:
            d.case_link_id = info["case_link_id"]
            d.case_link_other_source_name = info["other_source_name"]

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/documents/tipos", response_model=list[str])
def get_document_tipos(source_id: Optional[int] = None, db: Session = Depends(get_db)):
    return repository.list_distinct_document_tipos(db, source_id=source_id)


@router.get("/documents/secciones", response_model=list[str])
def get_document_secciones(
    source_id: Optional[int] = None, tipo: Optional[str] = None, db: Session = Depends(get_db)
):
    return repository.list_distinct_document_secciones(db, source_id=source_id, tipo=tipo)


@router.get("/documents/especialidades", response_model=list[str])
def get_document_especialidades(
    source_id: Optional[int] = None,
    tipo: Optional[str] = None,
    seccion: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return repository.list_distinct_document_especialidades(
        db, source_id=source_id, tipo=tipo, seccion=seccion
    )


@router.get("/documents/magistrados", response_model=list[str])
def get_document_magistrados(
    source_id: Optional[int] = None,
    tipo: Optional[str] = None,
    seccion: Optional[str] = None,
    especialidad: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return repository.list_distinct_document_magistrados(
        db, source_id=source_id, tipo=tipo, seccion=seccion, especialidad=especialidad
    )


@router.get("/documents/stats", response_model=DocumentStatsOut)
def get_document_stats(
    year: Optional[int] = None, month: Optional[int] = Query(None, ge=1, le=12), db: Session = Depends(get_db)
):
    display_name_by_key = {family.key: family.display_name for family in repository.list_source_families(db)}
    by_family = [
        {"key": key, "display_name": display_name_by_key.get(key, key), "count": count}
        for key, count in repository.count_documents_by_family(db)
    ]
    by_tipo = [{"tipo": tipo, "count": count} for tipo, count in repository.count_documents_by_tipo(db)]

    available_years = repository.list_document_years(db)
    effective_year = year if year is not None else (available_years[0] if available_years else date.today().year)
    by_month = repository.count_documents_by_month(db, effective_year)

    by_source = [
        {"id": source_id, "name": name, "count": count}
        for source_id, name, count in repository.count_documents_by_source(
            db, year=effective_year if month is not None else None, month=month
        )
    ]

    return {
        "by_family": by_family,
        "by_tipo": by_tipo,
        "by_source": by_source,
        "by_month": by_month,
        "year": effective_year,
        "available_years": available_years,
    }


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    document = repository.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    info = repository.get_case_link_status_for_documents(db, [document.id]).get(document.id)
    if info:
        document.case_link_id = info["case_link_id"]
        document.case_link_other_source_name = info["other_source_name"]

    return document


@router.get("/documents/{document_id}/versions", response_model=list[DocumentVersionOut])
def get_document_versions(document_id: int, db: Session = Depends(get_db)):
    if repository.get_document(db, document_id) is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return repository.list_document_versions(db, document_id)


@router.get("/documents/{document_id}/versions/{version_id}/download")
def download_document_version(document_id: int, version_id: int, db: Session = Depends(get_db)):
    version = repository.get_document_version(db, version_id)
    if version is None or version.document_id != document_id:
        raise HTTPException(status_code=404, detail="Versión no encontrada")
    url = presigned_url(version.storage_bucket, version.storage_key)
    return {"url": url}


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


@router.patch("/documents/{document_id}/title", response_model=DocumentOut)
def patch_document_title(document_id: int, payload: DocumentTitleUpdate, db: Session = Depends(get_db)):
    document = repository.update_document_title(db, document_id, payload.title)
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

    disposition = _preview_content_disposition(document)

    # A pre-set preview_storage_key takes priority over content_type-based branching:
    # for sources whose native format is already PDF (e.g. JEP) but are stored as RTF
    # for download, this points at the untouched original PDF captured at scrape time —
    # re-deriving a preview from the stored RTF would instead reconstruct it from a
    # PDF-import round-trip, which can silently drop visible body text.
    if document.preview_storage_key:
        url = presigned_url(document.storage_bucket, document.preview_storage_key, response_content_disposition=disposition)
        return {"url": url}

    if document.content_type == "application/pdf":
        url = presigned_url(document.storage_bucket, document.storage_key, response_content_disposition=disposition)
        return {"url": url}

    if document.content_type not in CONVERTIBLE_CONTENT_TYPES:
        raise HTTPException(status_code=404, detail="Vista previa no disponible para este tipo de archivo")

    try:
        preview_key = generate_document_preview_pdf.delay(document_id).get(timeout=PREVIEW_TASK_TIMEOUT_SECONDS)
    except CeleryTimeoutError:
        raise HTTPException(
            status_code=504, detail="La vista previa está tardando más de lo esperado, intenta de nuevo"
        )
    except Exception:
        logger.exception("Falló la generación de la vista previa para el documento %s", document_id)
        raise HTTPException(status_code=502, detail="No se pudo generar la vista previa")

    url = presigned_url(document.storage_bucket, preview_key, response_content_disposition=disposition)
    return {"url": url}
