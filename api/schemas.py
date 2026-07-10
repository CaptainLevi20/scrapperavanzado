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
