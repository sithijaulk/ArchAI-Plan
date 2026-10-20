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
    ACRES = "acres"
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
    # Provenance of each value. 'ocr' = read from document text, 'image_geometry' = derived from
    # detected line angles + north arrow, 'user' = typed/corrected by the user during verification.
    distance_origin: Optional[str] = Field(default=None, description="ocr | image_geometry | user | fixture")
    bearing_origin: Optional[str] = Field(default=None, description="ocr | image_geometry | user | fixture")
    verification_status: Optional[str] = Field(
        default=None, description="unverified | user_verified | user_corrected | ambiguous"
    )
    flags: List[str] = Field(default_factory=list, description="Machine-readable uncertainty flags")


class ManualSurveyExtractionRequest(BaseModel):
    north_angle: float = Field(default=0.0, ge=0.0, lt=360.0, description="North orientation angle in degrees (image rotation metadata only)")
    reference_edge: Optional[str] = Field(default=None, description="Starting edge id")
    source: SurveySource = Field(default=SurveySource.MANUAL)
    edges: List[SurveyEdgeInput] = Field(..., min_length=3, description="Boundary edges in clockwise sequence")
    # Set only when the user explicitly confirms the boundary table in the verification UI.
    verified_by_user: bool = Field(default=False)
    verified_at: Optional[str] = None
    north_angle_origin: Optional[str] = Field(default=None, description="ocr_arrow | user | default_unknown")
    road_frontage_edge_id: Optional[str] = Field(default=None, description="Edge facing the access road, if identified")
    road_frontage_origin: Optional[str] = Field(default=None, description="ocr_annotation | user | none")
    road_width_m: Optional[float] = Field(default=None, gt=0, description="Road width read from the document (verified by user)")
    road_width_origin: Optional[str] = Field(default=None, description="ocr_annotation | user")


# -------------------------------------------------------------
# 2. Regulatory Context Schema
# -------------------------------------------------------------

class RegulatoryContextInput(BaseModel):
    # Legacy/explicit override. When local authority details are supplied the rules engine
    # resolves the jurisdiction itself (see regulations/rules.py::resolve_jurisdiction).
    jurisdiction_id: Optional[str] = Field(default="sri_lanka_uda_standard", description="Identifier of regulatory jurisdiction")
    province: Optional[str] = None
    district: Optional[str] = None
    local_authority_type: Optional[str] = Field(default=None, description="municipal_council | urban_council | pradeshiya_sabha")
    local_authority_name: Optional[str] = None
    development_zone: Optional[str] = None
    # Not collected from the user any more; populated from verified survey data when available.
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
    notes: Optional[str] = Field(default=None, description="Free-text customer preference for this room")


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

    # Programme summary counts (optional; when supplied they are reconciled with `rooms`)
    bedroom_count: Optional[int] = Field(default=None, ge=0, le=12, description="Total bedrooms incl. master bedrooms")
    master_bedroom_count: Optional[int] = Field(default=None, ge=0, le=12)
    bathroom_count: Optional[int] = Field(default=None, ge=0, le=12, description="Total bathrooms incl. attached")
    kitchen_required: Optional[bool] = None
    living_room_required: Optional[bool] = None
    dining_room_required: Optional[bool] = None
    parking_type: Optional[str] = Field(default=None, description="covered_garage | open_carport")

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
    roof_preference: Optional["RoofPreference"] = Field(default_factory=lambda: RoofPreference())


class RoofType(str, Enum):
    FLAT_SLAB = "flat_slab"
    ACCESSIBLE_ROOFTOP = "accessible_rooftop"
    GABLE = "gable"
    HIP = "hip"
    MONO_PITCH = "mono_pitch"


class RoofPreference(BaseModel):
    roof_type: RoofType = Field(default=RoofType.FLAT_SLAB)
    material: Optional[str] = Field(default="concrete_tile", description="concrete_tile | clay_tile | metal_deck | asphalt_shingle | concrete_slab")
    pitch_angle_deg: float = Field(default=15.0, ge=0.0, le=45.0, description="Pitch angle in degrees (0 for flat)")
    overhang_m: float = Field(default=0.6, ge=0.0, le=1.5, description="Eaves/overhang projection beyond exterior walls in meters")
    parapet_height_m: Optional[float] = Field(default=1.0, ge=0.0, le=1.8, description="Parapet height in meters for flat/accessible roofs")
    rooftop_access: bool = Field(default=False, description="True if stair core extends to roof terrace")
    drainage_preference: str = Field(default="concealed_gutters", description="concealed_gutters | external_downpipes | slope_to_rear")
    notes: Optional[str] = None


class RoofPlane(BaseModel):
    plane_id: str
    polygon: List["Point2D"]
    pitch_deg: float
    slope_azimuth: float
    height_offset_m: float = 0.0


class GeneratedRoofGeometry(BaseModel):
    roof_type: str
    ridge_points: List["Point2D"] = Field(default_factory=list)
    eave_polygon: List["Point2D"] = Field(default_factory=list)
    planes: List[RoofPlane] = Field(default_factory=list)
    max_height_m: float = 1.5
    drainage: str = "concealed_gutters"
    provenance: str = "calculated_geometry"


# -------------------------------------------------------------
# 4. Regulatory Rule Schemas
# -------------------------------------------------------------

class RegulatoryRule(BaseModel):
    rule_id: str
    authority: str
    jurisdiction_id: str
    source_document: str
    source_date: Optional[str] = None
    source_reference: Optional[str] = None
    source_url: Optional[str] = None
    legal_instrument_type: Optional[str] = None
    act_or_regulation_reference: Optional[str] = None
    clause_reference: Optional[str] = None
    table_reference: Optional[str] = None
    page_reference: Optional[str] = None
    official_source_url: Optional[str] = None
    rule_type: str  # setback, ground_coverage, max_height, rear_space, room_dimension, etc.
    conditions: Dict[str, Any] = Field(default_factory=dict)
    affected_edge_type: str  # road_front, rear, side, all
    value: float  # In meters, ratio, sqm
    unit: str = "m"
    effective_date: str
    verification_status: str  # verified, needs_verification, research_test
    version: Optional[str] = None
    last_reviewed: Optional[str] = None
    reviewed_by: Optional[str] = None
    notes: Optional[str] = None


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
    width_m: Optional[float] = None
    length_m: Optional[float] = None
    is_structural_stair: bool = False
    required: Optional[bool] = None
    req_id: Optional[str] = None
    attached_to: Optional[str] = Field(default=None, description="room_id of the room this space is attached to")
    # generated = produced by the layout engine; edited = geometry changed by the user
    geometry_origin: Optional[str] = Field(default=None, description="generated | edited | user_added")


class Opening(BaseModel):
    opening_id: str
    floor_id: str
    kind: str  # door | entrance_door | window
    position: Point2D
    width: float
    wall_start: Point2D
    wall_end: Point2D
    room_ids: List[str] = Field(default_factory=list)


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
    circulation: List[RoomPolygon] = Field(default_factory=list, description="Corridors / landings (not habitable rooms)")
    openings: List[Opening] = Field(default_factory=list)
    unplaced_rooms: List[Dict[str, Any]] = Field(default_factory=list)


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
    # Geometry validity and regulatory verification are reported separately on purpose:
    # a plan can be geometrically valid while its rules are still unverified.
    geometry_status: Optional[str] = Field(default=None, description="valid | invalid")
    regulatory_status: Optional[str] = Field(
        default=None, description="verified | unverified | incomplete | missing | research_test"
    )
    design_checks: Dict[str, Any] = Field(default_factory=dict)


class GabGenRunOutput(BaseModel):
    project_id: str
    project_name: str
    units: str = "meters"
    status: str
    master_json: Dict[str, Any]
    validation: ValidationResult
    warnings: List[str] = Field(default_factory=list)
