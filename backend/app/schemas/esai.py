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


# ─── Phase 2 Schemas ─────────────────────────────────────────────────────────

class BuildingPreferencesResponse(BaseModel):
    id: Optional[str] = None
    project_id: str
    preferences: Dict[str, Any]
    geometry_fingerprint: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class FloorPreferencesResponse(BaseModel):
    id: Optional[str] = None
    project_id: str
    floor_id: str
    preferences: Optional[Dict[str, Any]] = None


class RoomPreferenceRecord(BaseModel):
    id: str
    project_id: str
    floor_id: str
    room_id: str
    room_type: str
    preferences: Dict[str, Any]
    specific_assets: List[Dict[str, Any]] = Field(default_factory=list)
    custom_constraints: List[Dict[str, Any]] = Field(default_factory=list)
    preference_revision: int
    is_orphaned: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class EffectivePreferencesResponse(BaseModel):
    room_id: str
    floor_id: str
    room_type: str
    effective_preferences: Dict[str, Any]
    sources: Dict[str, str]
    overridden_keys: List[str]
    inherited_keys: List[str]
    specific_assets: List[Dict[str, Any]] = Field(default_factory=list)
    custom_constraints: List[Dict[str, Any]] = Field(default_factory=list)


class OrphanDetectionResponse(BaseModel):
    scanned_count: int
    orphaned_count: int
    orphaned_room_ids: List[str]
    details: List[Dict[str, Any]]


class RoomContextDTO(BaseModel):
    room_id: str
    name: str
    room_type: str
    area_sqm: float
    preference_saved: bool
    preference_revision: Optional[int] = None
    is_orphaned: bool = False


class FloorContextDTO(BaseModel):
    floor_id: str
    floor_name: str
    level_index: int
    rooms: List[RoomContextDTO]


class InteriorContextResponse(BaseModel):
    project_id: str
    project_name: str
    floors: List[FloorContextDTO]
    total_floors: int
    total_rooms: int
    configured_rooms: int
    geometry_staleness: Dict[str, Any]

