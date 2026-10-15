"""
ESAI Pydantic Schemas for API Requests and Responses
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.components.esai_engine.contracts import (
    RoomRequirementsDTO,
    ValidationResultDTO,
    FloorDTO,
    RoomDTO,
    ProjectPreferencesDTO,
    LengthUnit
)
from app.components.esai_engine.catalog import CatalogAsset
from app.components.esai_engine.rules import ErgonomicRule


class ContextResponse(BaseModel):
    project_id: str
    project_name: str
    unit: LengthUnit
    total_floors: int
    total_rooms: int


class FloorsResponse(BaseModel):
    floors: List[FloorDTO]


class RoomsResponse(BaseModel):
    rooms: List[RoomDTO]


class CatalogListResponse(BaseModel):
    total: int
    items: List[CatalogAsset]


class StandardsListResponse(BaseModel):
    total: int
    rules: List[ErgonomicRule]


class SavedConfigCreateRequest(BaseModel):
    configuration_name: str
    room_ids: List[str]
    settings: Dict[str, Any] = Field(default_factory=dict)


class SavedConfigUpdateRequest(BaseModel):
    configuration_name: Optional[str] = None
    room_ids: Optional[List[str]] = None
    settings: Optional[Dict[str, Any]] = None


class SavedConfigResponse(BaseModel):
    id: str
    project_id: str
    configuration_name: str
    room_ids: List[str]
    settings: Dict[str, Any]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RequirementsSaveResponse(BaseModel):
    id: str
    project_id: str
    room_id: str
    status: str
    validation: ValidationResultDTO
