"""
Pydantic Schemas for GAB-Gen (Geo-Spatial AI Blueprint Generator)
Standard normalized contracts for survey measurements, client requirements,
regulatory checks, space allocation, and floor plan outputs.
"""
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field


class DistanceUnit(str, Enum):
    METERS = "m"
    FEET = "ft"


class LandExtentUnit(str, Enum):
    PERCHES = "perches"
    SQUARE_FEET = "sqft"
    SQUARE_METERS = "sqm"


class BuildingType(str, Enum):
    RESIDENTIAL_HOUSE = "residential_house"
    RESIDENTIAL_BUILDING = "residential_building"


class EdgeType(str, Enum):
    ROAD_FRONT = "road_front"
    REAR = "rear"
    SIDE = "side"
    SIDE_LEFT = "side_left"
    SIDE_RIGHT = "side_right"
    OTHER = "other"


class SurveySource(str, Enum):
    MANUAL = "manual"
    FIXTURE = "fixture"
    EASYOCR = "easyocr"  # Reserved for Stage 2


class RoomPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# -------------------------------------------------------------
# 1. Survey Measurement Normalized Schemas
# -------------------------------------------------------------

class DistanceValue(BaseModel):
    value: float = Field(..., gt=0, description="Measurement distance value")
    unit: DistanceUnit = Field(default=DistanceUnit.METERS, description="Unit of distance")


class BearingValue(BaseModel):
    raw: str = Field(..., description="Raw bearing string (e.g. '045°30' or 'N 45° E')")
    normalized_degrees: float = Field(..., ge=0, lt=360, description="Azimuth angle clockwise from North (0-360)")


class SurveyEdgeInput(BaseModel):
    edge_id: str = Field(..., description="Unique edge identifier, e.g. 'E01'")
    distance: DistanceValue
    bearing: BearingValue
    edge_type: Optional[EdgeType] = Field(default=EdgeType.SIDE, description="Boundary classification")
    source: SurveySource = Field(default=SurveySource.MANUAL)
    confidence: Optional[float] = Field(default=None, description="OCR confidence (null for Stage 1)")
    source_bbox: Optional[List[int]] = Field(default=None, description="Bounding box if detected (null for Stage 1)")


class ManualSurveyExtractionRequest(BaseModel):
    north_angle: float = Field(default=0.0, ge=0.0, lt=360.0, description="North orientation angle in degrees (image rotation metadata only)")
    reference_edge: Optional[str] = Field(default=None, description="Starting edge id")
    source: SurveySource = Field(default=SurveySource.MANUAL)
    edges: List[SurveyEdgeInput] = Field(..., min_length=3, description="Boundary edges in clockwise sequence")


# -------------------------------------------------------------
# 2. Regulatory Context Schema
# -------------------------------------------------------------

class RegulatoryContextInput(BaseModel):
    jurisdiction_id: str = Field(default="sri_lanka_uda_standard", description="Identifier of regulatory jurisdiction")
    province: Optional[str] = None
    district: Optional[str] = None
    local_authority_type: Optional[str] = None
    local_authority_name: Optional[str] = None
    development_zone: Optional[str] = None
    road_width: Optional[float] = None
    road_category: Optional[str] = None


# -------------------------------------------------------------
# 3. Client Residential Requirements Schemas
# -------------------------------------------------------------

class RoomRequirement(BaseModel):
    id: str = Field(..., description="Unique identifier for requirement entry")
    type: str = Field(..., description="Room type e.g. living_room, master_bedroom, kitchen")
    quantity: int = Field(default=1, ge=1, le=10)
    required: bool = Field(default=True, description="True if mandatory, False if optional")
    preferred_min_area: Optional[float] = Field(default=None, gt=0, description="Minimum preferred area in sqm")
    floor_preference: Union[int, str] = Field(default="auto", description="'auto' or integer floor index (0, 1, 2, 3)")
    priority: RoomPriority = Field(default=RoomPriority.HIGH)
    custom_name: Optional[str] = Field(default=None)


class ClientRequirementsInput(BaseModel):
    # Project & Land Info
    project_name: Optional[str] = None
    description: Optional[str] = None
    declared_land_extent: float = Field(..., gt=0, description="Declared land extent")
    declared_land_unit: LandExtentUnit = Field(default=LandExtentUnit.PERCHES)
    drawing_scale: Optional[str] = Field(default="1:100", description="Drawing scale ratio")
    road_frontage_edge_id: Optional[str] = Field(default=None, description="Edge ID identified as road frontage")
    source_notes: Optional[str] = None

    # Regulatory Context
    regulatory_context: Optional[RegulatoryContextInput] = Field(default_factory=RegulatoryContextInput)

    # Building Profile
    building_type: BuildingType = Field(default=BuildingType.RESIDENTIAL_HOUSE)
    storey_count: int = Field(default=1, ge=1, le=4, description="Number of storeys (1-4)")
    preferred_total_building_area: Optional[float] = Field(default=None, gt=0)
    preferred_ground_coverage: Optional[float] = Field(default=None, gt=0)

    # Room Programme
    rooms: List[RoomRequirement] = Field(default_factory=list)

    # Amenities & Functional Preferences
    occupant_count: Optional[int] = Field(default=4, ge=1)
    open_plan_living_dining: bool = Field(default=False)
    separate_kitchen: bool = Field(default=True)
    bathroom_requirements: Optional[str] = None
    attached_bathroom_count: Optional[int] = Field(default=0, ge=0)
    study_office_requirement: bool = Field(default=False)
    guest_room_requirement: bool = Field(default=False)
    storage_requirement: bool = Field(default=False)
    laundry_utility_requirement: bool = Field(default=False)
    balcony_requirement: bool = Field(default=False)
    parking_capacity: Optional[int] = Field(default=0, ge=0)
    staircase_preference: Optional[str] = Field(default="internal_linear", description="internal_linear, dogleg, etc.")
    additional_notes: Optional[str] = None


# -------------------------------------------------------------
# 4. Regulatory Rule Schemas
# -------------------------------------------------------------

class RegulatoryRule(BaseModel):
    rule_id: str
    authority: str
    jurisdiction_id: str
    source_document: str
    source_date: str
    source_reference: Optional[str] = None
    rule_type: str  # setback, ground_coverage, max_height, rear_space
    conditions: Dict[str, Any] = Field(default_factory=dict)
    affected_edge_type: str  # road_front, rear, side, all
    value: float  # In meters
    unit: str = "m"
    effective_date: str
    verification_status: str  # verified, research_test, needs_verification


# -------------------------------------------------------------
# 5. Geometry & Output Schemas
# -------------------------------------------------------------

class Point2D(BaseModel):
    x: float
    y: float


class WallSegment(BaseModel):
    wall_id: str
    floor_id: str
    start: Point2D
    end: Point2D
    wall_type: str = "exterior"  # exterior, interior, party
    thickness: float = 0.225  # in meters
    related_room_ids: List[str] = Field(default_factory=list)


class RoomPolygon(BaseModel):
    room_id: str
    name: str
    type: str
    floor_id: str
    area: float
    target_area: float
    polygon: List[Point2D]
    center: Point2D
    is_structural_stair: bool = False


class FloorPlanDefinition(BaseModel):
    floor_id: str
    floor_index: int
    name: str
    elevation: float
    floor_height: float = 3.0
    available_area: float
    target_allocated_area: float
    rooms: List[RoomPolygon] = Field(default_factory=list)
    walls: List[WallSegment] = Field(default_factory=list)


class ValidationResult(BaseModel):
    valid: bool
    status: str  # pending, completed, needs_verification, infeasible, failed
    closure_error: Optional[float] = None
    closure_tolerance: Optional[float] = None
    declared_area_sqm: Optional[float] = None
    reconstructed_area_sqm: Optional[float] = None
    area_difference_sqm: Optional[float] = None
    area_difference_percent: Optional[float] = None
    violations: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class GabGenRunOutput(BaseModel):
    project_id: str
    project_name: str
    units: str = "meters"
    status: str
    master_json: Dict[str, Any]
    validation: ValidationResult
    warnings: List[str] = Field(default_factory=list)
