from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db, require_session
from api.schemas import (
    CaseGroupOut,
    CaseLinkListItemOut,
    CaseLinkOut,
    CaseLinkStageDocumentOut,
    CaseLinkStageOut,
    CaseLinkSuggestionOut,
    ManualCaseLinkCreate,
)
from core.db import repository

router = APIRouter(dependencies=[Depends(require_session)])


def _case_group_out(db: Session, source_id: int, radicado: str) -> CaseGroupOut:
    source = repository.get_source(db, source_id)
    summary = repository.case_group_summary(db, source_id, radicado)
    return CaseGroupOut(
        source_id=source_id,
        source_name=source.name if source else "Fuente eliminada",
        radicado=radicado,
        **summary,
    )


def _case_link_out(db: Session, case_link_id: int) -> CaseLinkOut:
    stages = repository.list_case_link_stages(db, case_link_id)
    stage_outs = []
    for stage in stages:
        source = repository.get_source(db, stage.source_id)
        summary = repository.case_group_summary(db, stage.source_id, stage.radicado)
        documents = repository.list_documents_by_source_and_radicado(db, stage.source_id, stage.radicado)
        stage_outs.append(
            CaseLinkStageOut(
                stage_id=stage.id,
                source_id=stage.source_id,
                source_name=source.name if source else "Fuente eliminada",
                radicado=stage.radicado,
                f_public_min=summary["f_public_min"],
                f_public_max=summary["f_public_max"],
                documents=[CaseLinkStageDocumentOut.model_validate(d) for d in documents],
            )
        )
    return CaseLinkOut(id=case_link_id, stages=stage_outs)


@router.get("/case-link-suggestions", response_model=list[CaseLinkSuggestionOut])
def list_pending_case_link_suggestions(db: Session = Depends(get_db)):
    suggestions = repository.list_pending_case_link_suggestions(db)
    return [
        CaseLinkSuggestionOut(
            id=s.id,
            matched_digits=s.matched_digits,
            status=s.status,
            created_at=s.created_at,
            case_a=_case_group_out(db, s.source_id_a, s.radicado_a),
            case_b=_case_group_out(db, s.source_id_b, s.radicado_b),
        )
        for s in suggestions
    ]


@router.post("/case-link-suggestions/{suggestion_id}/confirm", response_model=CaseLinkOut)
def confirm_case_link_suggestion(suggestion_id: int, db: Session = Depends(get_db)):
    case_link = repository.confirm_case_link_suggestion(db, suggestion_id)
    if case_link is None:
        raise HTTPException(status_code=404, detail="Sugerencia no encontrada o ya resuelta")
    return _case_link_out(db, case_link.id)


@router.post("/case-link-suggestions/{suggestion_id}/dismiss")
def dismiss_case_link_suggestion(suggestion_id: int, db: Session = Depends(get_db)):
    suggestion = repository.dismiss_case_link_suggestion(db, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Sugerencia no encontrada o ya resuelta")
    return {"status": suggestion.status}


@router.post("/case-links", response_model=CaseLinkOut)
def create_manual_case_link(payload: ManualCaseLinkCreate, db: Session = Depends(get_db)):
    if (payload.source_id_a, payload.radicado_a) == (payload.source_id_b, payload.radicado_b):
        raise HTTPException(status_code=400, detail="No se puede vincular un caso consigo mismo")

    source_a = repository.get_source(db, payload.source_id_a)
    source_b = repository.get_source(db, payload.source_id_b)
    if source_a is None or source_a.family_key != "samai" or source_b is None or source_b.family_key != "samai":
        raise HTTPException(
            status_code=400, detail="Las dos fuentes deben existir y pertenecer a la familia samai"
        )

    case_link = repository.create_manual_case_link(
        db, payload.source_id_a, payload.radicado_a, payload.source_id_b, payload.radicado_b
    )
    return _case_link_out(db, case_link.id)


@router.get("/case-links/{case_link_id}", response_model=CaseLinkOut)
def get_case_link(case_link_id: int, db: Session = Depends(get_db)):
    if repository.get_case_link(db, case_link_id) is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    return _case_link_out(db, case_link_id)


@router.get("/case-links", response_model=list[CaseLinkListItemOut])
def list_case_links(db: Session = Depends(get_db)):
    return [CaseLinkListItemOut(**item) for item in repository.list_case_links_with_summary(db)]


@router.delete("/case-links/{case_link_id}/stages/{stage_id}")
def remove_case_link_stage(case_link_id: int, stage_id: int, db: Session = Depends(get_db)):
    result = repository.separate_case_link_stage(db, case_link_id, stage_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Etapa no encontrada en este expediente")
    return result
