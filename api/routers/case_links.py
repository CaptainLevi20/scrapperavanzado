from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db, require_session
from api.schemas import (
    CaseLinkListItemOut,
    CaseLinkOut,
    CaseLinkStageDocumentOut,
    CaseLinkStageOut,
)
from core.db import repository

router = APIRouter(dependencies=[Depends(require_session)])


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
