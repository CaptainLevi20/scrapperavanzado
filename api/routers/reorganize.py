from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.deps import require_admin
from api.schemas import ApplyResult, BatchAnalysis, ReorganizeAnalyzeRequest, ReorganizeApplyRequest
from core.reorganize import analyze_batch, apply_moves

router = APIRouter(dependencies=[Depends(require_admin)])


def _require_directory(root_path: str) -> Path:
    root = Path(root_path)
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="La ruta no existe o no es una carpeta")
    return root


@router.post("/reorganize/analyze", response_model=BatchAnalysis)
def post_reorganize_analyze(payload: ReorganizeAnalyzeRequest):
    return analyze_batch(_require_directory(payload.root_path))


@router.post("/reorganize/apply", response_model=ApplyResult)
def post_reorganize_apply(payload: ReorganizeApplyRequest):
    return apply_moves(_require_directory(payload.root_path), payload.moves)
