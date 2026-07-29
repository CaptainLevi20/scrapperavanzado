from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_session
from api.schemas import SourceCreate, SourceFamilyOut, SourceOut, SourceUpdate
from core.db import repository
from core.scrapers import families  # noqa: F401 — ensures FAMILY_REGISTRY is populated
from core.scrapers.registry import FAMILY_REGISTRY

router = APIRouter(dependencies=[Depends(require_session)])


@router.get("/source-families", response_model=list[SourceFamilyOut])
def get_source_families(db: Session = Depends(get_db)):
    return [
        {
            "key": family.key,
            "display_name": family.display_name,
            "description": family.description,
            "filters_by_publication_date": getattr(
                FAMILY_REGISTRY.get(family.key), "filters_by_publication_date", False
            ),
        }
        for family in repository.list_source_families(db)
    ]


@router.get("/sources", response_model=list[SourceOut])
def get_sources(
    id: Optional[int] = None,
    family_key: Optional[str] = None,
    active: Optional[bool] = None,
    has_documents: Optional[bool] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return repository.list_sources(
        db, id=id, family_key=family_key, active=active, has_documents=has_documents, limit=limit, offset=offset
    )


@router.post("/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
def post_source(payload: SourceCreate, db: Session = Depends(get_db)):
    if repository.get_source_family(db, payload.family_key) is None:
        raise HTTPException(status_code=400, detail=f"Familia técnica desconocida: {payload.family_key}")
    return repository.create_source(
        db, family_key=payload.family_key, name=payload.name, family_params=payload.family_params, active=payload.active
    )


@router.patch("/sources/{source_id}", response_model=SourceOut)
def patch_source(source_id: int, payload: SourceUpdate, db: Session = Depends(get_db)):
    source = repository.update_source(db, source_id, active=payload.active, family_params=payload.family_params)
    if source is None:
        raise HTTPException(status_code=404, detail="Fuente no encontrada")
    return source
