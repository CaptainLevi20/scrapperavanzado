from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceFamilyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    display_name: str
    description: Optional[str] = None
    filters_by_publication_date: bool = False


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    family_key: str
    name: str
    family_params: dict
    active: bool


class SourceCreate(BaseModel):
    family_key: str
    name: str
    family_params: dict = {}
    active: bool = True


class SourceUpdate(BaseModel):
    active: Optional[bool] = None
    family_params: Optional[dict] = None


class RunCreate(BaseModel):
    source_ids: Optional[list[int]] = None
    fini: Optional[date] = None
    ffin: Optional[date] = None


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    triggered_by: str
    status: str
    fini: Optional[date] = None
    ffin: Optional[date] = None
    cancel_requested: bool
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime


class RunSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    run_id: int
    source_id: int
    source_name: str
    status: str
    docs_new: int
    docs_updated: int
    docs_errors: int
    error_message: Optional[str] = None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    doc_id: str
    source_id: int
    title: str
    nombre: str
    tipo: Optional[str] = None
    seccion: Optional[str] = None
    especialidad: Optional[str] = None
    magistrado: Optional[str] = None
    detalle: Optional[str] = None
    f_public: Optional[date] = None
    f_providencia: Optional[date] = None
    source_url: Optional[str] = None
    storage_bucket: str
    storage_key: str
    content_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    review_status: str
    reviewed_at: Optional[datetime] = None
    downloaded_at: datetime
    case_document_count: Optional[int] = None
    case_link_id: Optional[int] = None
    case_link_other_source_name: Optional[str] = None


class DocumentReviewUpdate(BaseModel):
    review_status: Literal["pending", "useful", "not_useful"]


class DocumentTitleUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=500)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("El título no puede estar vacío")
        return stripped


class BulkDocumentReviewUpdate(BaseModel):
    document_ids: list[int] = Field(min_length=1)
    review_status: Literal["pending", "useful", "not_useful"]


class BulkDownloadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    document_count: int
    failed_count: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime


class DocumentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    document_id: int
    nombre: str
    file_size_bytes: Optional[int] = None
    content_type: Optional[str] = None
    downloaded_at: datetime
    superseded_at: datetime


class FamilyCount(BaseModel):
    key: str
    display_name: str
    count: int


class TipoCount(BaseModel):
    tipo: str
    count: int


class SourceCount(BaseModel):
    id: int
    name: str
    count: int


class DocumentStatsOut(BaseModel):
    by_family: list[FamilyCount]
    by_tipo: list[TipoCount]
    by_source: list[SourceCount]
    by_month: list[int]
    year: int
    available_years: list[int]


class PaginatedDocuments(BaseModel):
    items: list[DocumentOut]
    total: int
    limit: int
    offset: int


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)
    invite_code: str

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, value: str) -> str:
        # Field(min_length=3) alone would still accept "   " (all whitespace) or
        # let "  ana  " and "ana" register as if they were different usernames.
        stripped = value.strip()
        if len(stripped) < 3:
            raise ValueError("El nombre de usuario debe tener al menos 3 caracteres")
        return stripped


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class AuthResponse(BaseModel):
    token: str
    username: str
    is_admin: bool


class MeResponse(BaseModel):
    username: str
    is_admin: bool


class CaseLinkStageDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    f_public: Optional[date] = None
    f_providencia: Optional[date] = None


class CaseLinkStageOut(BaseModel):
    stage_id: int
    source_id: int
    source_name: str
    radicado: str
    f_public_min: Optional[date] = None
    f_public_max: Optional[date] = None
    documents: list[CaseLinkStageDocumentOut]


class CaseLinkOut(BaseModel):
    id: int
    stages: list[CaseLinkStageOut]


class CaseLinkListItemOut(BaseModel):
    id: int
    source_names: list[str]
    radicados: list[str]
    stage_count: int
    document_count: int
    f_public_min: Optional[date] = None
    f_public_max: Optional[date] = None


class CaseLinkStageRemovalOut(BaseModel):
    dissolved: bool
    case_link_id: Optional[int] = None


class ReorganizeAnalyzeRequest(BaseModel):
    root_path: str


class TipoSummary(BaseModel):
    tipo: str
    total_files: int
    exception_count: int


class ReorganizeException(BaseModel):
    tipo: str
    kind: Literal["missing_entity_folder", "missing_year_folder"]
    current_path: str
    detected_entity: Optional[str] = None
    detected_year: Optional[int] = None
    mtime_year_hint: Optional[int] = None
    proposed_path: Optional[str] = None


class ExtraDepthEntry(BaseModel):
    tipo: str
    current_path: str


class BatchAnalysis(BaseModel):
    root_path: str
    total_files: int
    tipos: list[TipoSummary]
    exceptions: list[ReorganizeException]
    extra_depth: list[ExtraDepthEntry]


class ResolvedMove(BaseModel):
    current_path: str
    target_path: str


class ReorganizeApplyRequest(BaseModel):
    root_path: str
    moves: list[ResolvedMove]


class MoveResult(BaseModel):
    current_path: str
    target_path: str
    moved: bool
    skip_reason: Optional[str] = None


class ApplyResult(BaseModel):
    results: list[MoveResult]
