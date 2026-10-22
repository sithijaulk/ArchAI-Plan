"""
Phase 8 Reporting Contracts & DTOs
Defines data structures for professional PDF generation, schedules,
vector drawings, validation summaries, and report configuration options.
Strictly excludes budgets, prices, monetary values, and cost calculations.
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ReportScope(str, Enum):
    BUILDING = "building"
    FLOOR = "floor"
    ROOM = "room"


class ReportMode(str, Enum):
    FINAL = "final"  # Strictly enforces current, valid, non-stale designs
    DRAFT = "draft"  # Permissive mode with prominent watermark and staleness warnings


class ReportSection(str, Enum):
    COVER = "cover"
    PROJECT_OVERVIEW = "project_overview"
    FLOOR_SUMMARY = "floor_summary"
    CLIENT_PREFERENCES = "client_preferences"
    LAYOUT_DRAWINGS = "layout_drawings"
    FURNITURE_SCHEDULE = "furniture_schedule"
    KITCHEN_BATHROOM_SCHEDULE = "kitchen_bathroom_schedule"
    LIGHTING_SCHEDULE = "lighting_schedule"
    ELECTRICAL_SCHEDULE = "electrical_schedule"
    PLUMBING_SCHEDULE = "plumbing_schedule"
    FINISH_SCHEDULE = "finish_schedule"
    ERGONOMIC_VALIDATION = "ergonomic_validation"
    OPTIMIZATION_SUMMARY = "optimization_summary"
    DISCLAIMERS = "disclaimers"


class PdfReportRequest(BaseModel):
    scope: ReportScope = ReportScope.BUILDING
    mode: ReportMode = ReportMode.FINAL
    target_floor_id: Optional[str] = None
    target_room_id: Optional[str] = None
    floor_id: Optional[str] = None
    room_id: Optional[str] = None
    floor_ids: Optional[List[str]] = None
    room_ids: Optional[List[str]] = None
    sections: Optional[List[ReportSection]] = None
    include_2d_drawings: bool = True
    include_3d_views: bool = True
    # Optional client-rendered 3D viewport captures (keyed by room_id -> base64 data URL or structured dict with revision/room metadata)
    view_captures: Optional[Dict[str, Any]] = Field(default_factory=dict)
    viewer_3d_captures: Optional[Dict[str, Any]] = None
    drawing_scale_mode: str = "auto"  # "auto", "1:50", "not_to_scale"
    author_name: Optional[str] = None
    notes: Optional[str] = None


class ReportOptionsResponse(BaseModel):
    available_scopes: List[str]
    available_modes: List[str]
    available_sections: List[str]
    default_sections: List[str]
    supported_scopes: Optional[List[str]] = None
    supported_sections: Optional[List[str]] = None
    available_floors: Optional[List[Dict[str, Any]]] = None
    available_rooms: Optional[List[Dict[str, Any]]] = None
    staleness: Optional[Dict[str, Any]] = None


# ── Schedule Data Transfer Objects ──────────────────────────────────────────

class RoomScheduleItemDTO(BaseModel):
    instance_id: str
    asset_name: str
    catalog_id: str
    category: str
    variant: Optional[str] = None
    quantity: int = 1
    width_m: float
    depth_m: float
    height_m: float
    material: str
    color: str
    placement_mode: str
    is_mandatory: bool
    is_locked: bool
    position_x: float = 0.0
    position_y: float = 0.0
    rotation_deg: float = 0.0
    associated_wall_id: Optional[str] = None


class LightingScheduleItemDTO(BaseModel):
    fixture_id: str
    fixture_type: str
    purpose: str
    installation_mode: str
    position_x: float
    position_y: float
    height_m: float
    control_zone: Optional[str] = None
    is_proposed: bool = True


class ServiceScheduleItemDTO(BaseModel):
    point_id: str
    service_type: str
    purpose: str
    associated_asset_name: Optional[str] = None
    position_x: float
    position_y: float
    height_m: float
    status: str  # "proposed", "existing", "unverified"
    requires_professional_review: bool = True


class PlumbingScheduleItemDTO(BaseModel):
    item_id: str
    fixture_type: str
    hot_water_required: bool
    drainage_type: str
    supply_type: str
    status: str
    requires_professional_review: bool = True


class FinishScheduleItemDTO(BaseModel):
    surface_type: str  # "wall", "floor", "ceiling", "cabinetry", "countertop"
    finish_id: str
    finish_name: str
    material_category: str
    color_or_pattern: str
    coverage_area_sqm: Optional[float] = None


class ValidationReportItemDTO(BaseModel):
    rule_id: str
    rule_description: str
    standard_source: str
    standard_edition: Optional[str] = None
    standard_section: Optional[str] = None
    status: str  # "PASS", "VIOLATION", "NOT_EVALUATED"
    severity: str
    required_clearance_m: Optional[float] = None
    message: str


class OptimizationSummaryDTO(BaseModel):
    algorithm_name: str = "PyGAD Genetic Spatial Optimizer"
    generations: int
    population_size: int
    seed: int
    fitness_score: float
    hard_constraints_passed: bool
    overlap_area_sqm: float
    out_of_bounds_area_sqm: float
    door_violations: int
    window_violations: int
    ergonomic_score: float
    runtime_seconds: Optional[float] = None


class RoomReportDataDTO(BaseModel):
    room_id: str
    room_name: str
    room_type: str
    floor_id: str
    floor_name: str
    area_sqm: float
    ceiling_height_m: float
    polygon: List[List[float]]
    doors: List[Dict[str, Any]] = Field(default_factory=list)
    windows: List[Dict[str, Any]] = Field(default_factory=list)
    perimeter_m: float = 0.0
    net_wall_area_sqm: float = 0.0
    openings_area_sqm: float = 0.0
    design_revision: int
    has_design: bool
    furniture_schedule: List[RoomScheduleItemDTO] = Field(default_factory=list)
    bathroom_schedule: List[RoomScheduleItemDTO] = Field(default_factory=list)
    kitchen_schedule: List[RoomScheduleItemDTO] = Field(default_factory=list)
    lighting_schedule: List[LightingScheduleItemDTO] = Field(default_factory=list)
    service_schedule: List[ServiceScheduleItemDTO] = Field(default_factory=list)
    plumbing_schedule: List[PlumbingScheduleItemDTO] = Field(default_factory=list)
    finish_schedule: List[FinishScheduleItemDTO] = Field(default_factory=list)
    validation_items: List[ValidationReportItemDTO] = Field(default_factory=list)
    optimization_summary: Optional[OptimizationSummaryDTO] = None
    image_capture_base64: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class FloorReportDataDTO(BaseModel):
    floor_id: str
    floor_name: str
    rooms: List[RoomReportDataDTO] = Field(default_factory=list)


class ReportDataDTO(BaseModel):
    project_id: str
    project_name: str
    scope: ReportScope
    mode: ReportMode
    generated_at: str
    design_revision: int
    geometry_revision: int
    preference_revision: int
    geometry_fingerprint: str
    is_stale: bool
    staleness_reasons: List[str] = Field(default_factory=list)
    rooms: List[RoomReportDataDTO] = Field(default_factory=list)
    floors: List[FloorReportDataDTO] = Field(default_factory=list)
    client_preferences: Dict[str, Any] = Field(default_factory=dict)
    author_name: Optional[str] = None
    custom_notes: Optional[str] = None
    general_disclaimers: List[str] = Field(default_factory=list)
    drawing_scale_mode: str = "auto"
    include_2d_drawings: bool = True
    include_3d_views: bool = True

