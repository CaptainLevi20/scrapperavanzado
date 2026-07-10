from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SourceFamilyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    display_name: str
    description: Optional[str] = None


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
    status: str
    docs_new: int
    docs_errors: int
    error_message: Optional[str] = None
