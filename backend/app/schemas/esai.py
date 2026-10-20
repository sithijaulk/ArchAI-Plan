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
    LengthUnit,
    ResolvedRoomDesignInputDTO,
    GeneratedRoomDesignDTO,
    GeneratedBuildingDesignDTO,
    PlacedFixturePointDTO,
    PlacedAssetPersistedDTO,
    PersistedRoomDesignDTO,
    SaveDesignResponseDTO,
    SelectAlternativeResponseDTO,
    DesignStalenessReportDTO,
    DesignStalenessRoomReportDTO,
)
from app.components.esai_engine.catalog import CatalogAsset, FinishAsset
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


# ─── Phase 3 Schemas ─────────────────────────────────────────────────────────

class CatalogCategoriesResponse(BaseModel):
    categories: List[str]


class FinishesListResponse(BaseModel):
    total: int
    finishes: List[FinishAsset]


class StylesCatalogResponse(BaseModel):
    styles: Dict[str, Any]


class FunctionalRelationsResponse(BaseModel):
    total: int
    relations: List[Dict[str, Any]]


class CatalogValidationRequest(BaseModel):
    items: List[Dict[str, Any]]
    room_type: Optional[str] = None


class CatalogValidationResponse(BaseModel):
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    validated_items: List[Dict[str, Any]] = Field(default_factory=list)


class ResolvedDesignInputResponse(BaseModel):
    resolved: ResolvedRoomDesignInputDTO


class RunOptimizationRequest(BaseModel):
    scope: str = Field(default="building", description="Scope of layout generation: 'room', 'floor', or 'building'")
    room_id: Optional[str] = Field(default=None, description="Target room ID if scope is 'room'")
    floor_id: Optional[str] = Field(default=None, description="Target floor ID if scope is 'floor'")
    seed: Optional[int] = Field(default=42, description="Random seed for reproducible evolutionary runs")
    population_size: Optional[int] = Field(default=25, ge=10, le=100)
    generations: Optional[int] = Field(default=20, ge=5, le=100)
    alternatives_count: Optional[int] = Field(default=2, ge=1, le=5)
    auto_save: bool = Field(default=False, description="Whether to automatically persist validated designs into Master JSON")
    expected_revision: Optional[int] = None
    expected_design_revision: Optional[int] = None


class RunOptimizationResponse(BaseModel):
    result: GeneratedBuildingDesignDTO
    persistence: Optional[SaveDesignResponseDTO] = None


class BaselineBenchmarkRequest(BaseModel):
    room_id: str
    floor_id: Optional[str] = None
    eval_budget: int = Field(default=250, ge=50, le=2000)
    seed: int = Field(default=42)


class BaselineBenchmarkResponse(BaseModel):
    report: Dict[str, Any]


# ─── Phase 5: Master JSON Persistence & Selective Regeneration Schemas ─────────

class SaveDesignRequest(BaseModel):
    building_design: Optional[GeneratedBuildingDesignDTO] = None
    room_design: Optional[GeneratedRoomDesignDTO] = None
    scope: str = Field(default="building", description="Scope of layout being saved: 'room', 'floor', or 'building'")
    target_room_id: Optional[str] = None
    target_floor_id: Optional[str] = None
    expected_design_revision: Optional[int] = None


class SaveDesignResponse(BaseModel):
    success: bool
    project_id: str
    design_revision: int
    saved_rooms_count: int
    saved_room_ids: List[str]
    timestamp: str
    details: Dict[str, Any] = Field(default_factory=dict)


class RegenerateScopeRequest(BaseModel):
    scope: str = Field(default="room", description="Regeneration scope: 'room', 'floor', or 'building'")
    room_id: Optional[str] = Field(default=None, description="Target room ID if scope is 'room'")
    floor_id: Optional[str] = Field(default=None, description="Target floor ID if scope is 'floor'")
    seed: Optional[int] = Field(default=42, description="Random seed")
    population_size: Optional[int] = Field(default=20, ge=10, le=100)
    generations: Optional[int] = Field(default=15, ge=5, le=100)
    alternatives_count: Optional[int] = Field(default=2, ge=1, le=5)
    auto_save: bool = Field(default=True, description="Whether to immediately commit validated layout into Master JSON")
    expected_design_revision: Optional[int] = None


class RegenerateScopeResponse(BaseModel):
    generation: GeneratedBuildingDesignDTO
    persistence: Optional[SaveDesignResponseDTO] = None
    scope: str
    auto_saved: bool


class SelectAlternativeRequest(BaseModel):
    alternative_id: str
    expected_design_revision: Optional[int] = None


class SelectAlternativeResponse(BaseModel):
    success: bool
    project_id: str
    room_id: str
    active_alternative_id: str
    design_revision: int
    updated_at: str


class DesignStalenessResponse(BaseModel):
    report: DesignStalenessReportDTO


class SavedDesignsResponse(BaseModel):
    project_id: str
    design_revision: int
    schema_version: str
    geometry_fingerprint: Optional[str] = None
    geometry_source: Optional[str] = None
    total_saved_rooms: int
    rooms: Dict[str, Any]
    revisions: List[Dict[str, Any]] = Field(default_factory=list)


# ─── Phase 6: 3D Scene Visualization Schema ───────────────────────────────────

class SceneDataResponse(BaseModel):
    project_id: str
    project_name: str
    unit: str = "m"
    geometry_revision: int
    design_revision: int
    geometry_fingerprint: Optional[str] = None
    floors: List[FloorDTO]
    saved_designs: Dict[str, Any]
    staleness: Dict[str, Any]


# ─── Phase 7: Interactive Editing, Validation & Locking Schemas ───────────────

class ValidationDiagnosticDTO(BaseModel):
    code: str
    severity: str = "error"  # "error", "warning", "info"
    instance_id: Optional[str] = None
    room_id: Optional[str] = None
    rule_id: Optional[str] = None
    message: str
    suggested_correction: Optional[str] = None


class RoomEditValidateRequest(BaseModel):
    room_id: str
    floor_id: Optional[str] = None
    expected_design_revision: Optional[int] = None
    furniture: List[PlacedAssetPersistedDTO] = Field(default_factory=list)
    cabinetry: List[PlacedAssetPersistedDTO] = Field(default_factory=list)
    appliances: List[PlacedAssetPersistedDTO] = Field(default_factory=list)
    sanitary_fixtures: List[PlacedAssetPersistedDTO] = Field(default_factory=list)
    decorations: List[PlacedAssetPersistedDTO] = Field(default_factory=list)
    lighting: List[PlacedFixturePointDTO] = Field(default_factory=list)
    electrical_points: List[PlacedFixturePointDTO] = Field(default_factory=list)
    plumbing_requirements: List[PlacedFixturePointDTO] = Field(default_factory=list)
    service_requirements: List[Dict[str, Any]] = Field(default_factory=list)
    wall_finishes: Dict[str, Any] = Field(default_factory=dict)
    floor_finishes: Dict[str, Any] = Field(default_factory=dict)
    ceiling_finishes: Dict[str, Any] = Field(default_factory=dict)
    wall_finish: Optional[str] = None
    wall_color: Optional[str] = None
    floor_finish: Optional[str] = None
    ceiling_finish: Optional[str] = None


class RoomEditValidateResponse(BaseModel):
    is_valid: bool
    hard_constraints_passed: bool
    diagnostics: List[ValidationDiagnosticDTO] = Field(default_factory=list)
    overlap_area_sqm: float = 0.0
    out_of_bounds_area_sqm: float = 0.0
    door_violation_count: int = 0
    window_violation_count: int = 0
    ergonomic_score: float = 1.0


class SaveRoomEditRequest(RoomEditValidateRequest):
    expected_design_revision: Optional[int] = None


class SaveRoomEditResponse(BaseModel):
    success: bool
    project_id: str
    room_id: str
    design_revision: int
    updated_at: str
    saved_design: Dict[str, Any]


class LockAssetRequest(BaseModel):
    instance_id: str
    is_locked: bool = True
    lock_type: Optional[str] = "all"  # "position", "rotation", "all"
    expected_design_revision: Optional[int] = None


class LockAssetResponse(BaseModel):
    success: bool
    project_id: str
    room_id: str
    instance_id: str
    is_locked: bool
    design_revision: int
    updated_at: str


class RegenerateUnlockedRequest(BaseModel):
    expected_design_revision: Optional[int] = None
    seed: Optional[int] = 42
    population_size: Optional[int] = 20
    generations: Optional[int] = 15
    auto_save: bool = True


class RegenerateUnlockedResponse(BaseModel):
    success: bool
    project_id: str
    room_id: str
    design_revision: int
    saved_design: Optional[Dict[str, Any]] = None
    diagnostics: List[str] = Field(default_factory=list)
