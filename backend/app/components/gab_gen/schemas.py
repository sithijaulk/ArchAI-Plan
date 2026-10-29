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


class SurveyVerificationStatus(str, Enum):
    UPLOADED = "uploaded"
    PREPROCESSING = "preprocessing"
    EXTRACTED_UNVERIFIED = "extracted_unverified"
    REQUIRES_USER_CORRECTION = "requires_user_correction"
    GEOMETRY_INVALID = "geometry_invalid"
    USER_VERIFIED = "user_verified"
    READY_FOR_GENERATION = "ready_for_generation"
    PROCESSING_FAILED = "processing_failed"


class GeoreferenceStatus(str, Enum):
    LOCAL_P0_ONLY = "local_p0_only"
    APPROXIMATE_ESTIMATE = "approximate_estimate"
    VERIFIED_CRS = "verified_crs"
    UNKNOWN = "unknown"


class ManualSurveyExtractionRequest(BaseModel):
    north_angle: float = Field(default=0.0, ge=0.0, lt=360.0, description="North orientation angle in degrees (image rotation metadata only)")
    reference_edge: Optional[str] = Field(default=None, description="Starting edge id")
    source: SurveySource = Field(default=SurveySource.MANUAL)
    edges: List[SurveyEdgeInput] = Field(..., min_length=3, description="Boundary edges in clockwise sequence")
    # Set only when the user explicitly confirms the boundary table in the verification UI.
    verified_by_user: bool = Field(default=False)
    verified_at: Optional[str] = None
    verification_status: SurveyVerificationStatus = Field(
        default=SurveyVerificationStatus.EXTRACTED_UNVERIFIED,
        description="Explicit lifecycle status: uploaded, extracted_unverified, requires_user_correction, user_verified, etc."
    )
    north_angle_origin: Optional[str] = Field(default=None, description="ocr_arrow | user | default_unknown")
    drawing_scale: Optional[str] = Field(default=None, description="e.g. 1:100, 1:200, 1:500")
    drawing_scale_origin: Optional[str] = Field(default=None, description="ocr_text | user | unknown")
    road_frontage_edge_id: Optional[str] = Field(default=None, description="Edge facing the access road, if identified")
    road_frontage_origin: Optional[str] = Field(default=None, description="ocr_annotation | user | none")
    road_width_m: Optional[float] = Field(default=None, gt=0, description="Road width read from the document (verified by user)")
    road_width_origin: Optional[str] = Field(default=None, description="ocr_annotation | user")
    selected_page_number: int = Field(default=1, ge=1, description="Selected 1-based page index from PDF or document")
    total_pages: int = Field(default=1, ge=1, description="Total pages in the uploaded document")
    georeference_status: GeoreferenceStatus = Field(
        default=GeoreferenceStatus.LOCAL_P0_ONLY,
        description="Whether geometry is in canonical local P0 coordinates or verified real-world CRS"
    )
    crs_identifier: Optional[str] = Field(default=None, description="e.g. EPSG:5235 (SLD99 / Sri Lanka Grid 1999) if verified")


class ComplianceStatus(str, Enum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    REQUIRES_REGULATORY_VERIFICATION = "requires_regulatory_verification"
    CONFLICT_REQUIRES_REVIEW = "conflict_requires_review"
    NOT_APPLICABLE = "not_applicable"


class ApplicabilityStatus(str, Enum):
    APPLICABLE_VERIFIED = "applicable_verified"
    NOT_APPLICABLE_VERIFIED = "not_applicable_verified"
    REQUIRES_REGULATORY_VERIFICATION = "requires_regulatory_verification"
    CONFLICT_REQUIRES_REVIEW = "conflict_requires_review"


class SiteRestrictionType(str, Enum):
    FLOOD_PRONE = "flood_prone"
    WETLAND = "wetland"
    PADDY_LAND = "paddy_land"
    ROAD_RESERVATION = "road_reservation"
    CANAL_RESERVATION = "canal_reservation"
    COASTAL_RESTRICTION = "coastal_restriction"
    ENVIRONMENTAL_SENSITIVE = "environmental_sensitive"


class SiteRestrictionCheck(BaseModel):
    restriction_type: SiteRestrictionType
    checked: bool = False
    intersected: Optional[bool] = None
    dataset_name: Optional[str] = None
    dataset_version: Optional[str] = None
    crs: Optional[str] = None
    buffer_required_m: Optional[float] = None
    legal_source_id: Optional[str] = None
    verification_status: str = "unverified"  # verified, unverified, not_checked
    notes: Optional[str] = None


class RegulatoryResolutionOutput(BaseModel):
    authority_id: Optional[str] = None
    authority_name: Optional[str] = None
    authority_type: Optional[str] = None
    district: Optional[str] = None
    province: Optional[str] = "Western"
    authority_verification_status: str = "unverified"  # verified, unverified, provisional
    planning_jurisdiction_id: str
    uda_declared_area: bool = True
    uda_jurisdiction_status: str = "verified"  # verified, requires_regulatory_verification
    development_zone: Optional[str] = None
    zone_verification_status: str = "unverified"  # verified, requires_regulatory_verification
    applicability_status: ApplicabilityStatus = ApplicabilityStatus.REQUIRES_REGULATORY_VERIFICATION
    governing_sources: List[str] = Field(default_factory=list)
    applicable_rule_ids: List[str] = Field(default_factory=list)
    unresolved_requirements: List[str] = Field(default_factory=list)
    disclaimers: List[str] = Field(default_factory=list)


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
    authority_id: Optional[str] = Field(default=None, description="Stable canonical authority ID, e.g. LK-11-CMC")
    development_zone: Optional[str] = None
    zone_confirmed: bool = Field(default=False, description="Whether zone was verified against official gazetted zoning map")
    # Not collected from the user any more; populated from verified survey data when available.
    road_width: Optional[float] = None
    road_category: Optional[str] = None
    site_restrictions: List[SiteRestrictionCheck] = Field(default_factory=list)


# -------------------------------------------------------------
# 3. Client Residential Requirements Schemas
# -------------------------------------------------------------

class FloorAssignmentType(str, Enum):
    REQUIRED_FLOOR = "required_floor"
    PREFERRED_FLOOR = "preferred_floor"
    ANY_FLOOR = "any_floor"


class AdjacencyRelationshipType(str, Enum):
    DIRECT_ACCESS = "direct_access"
    SHARED_BOUNDARY = "shared_boundary"
    NEAR = "near"
    PREFER_NEAR = "prefer_near"
    PREFER_SEPARATE = "prefer_separate"
    MUST_NOT_DIRECTLY_CONNECT = "must_not_directly_connect"


class RoomAdjacencyRequirement(BaseModel):
    adjacency_id: str = Field(..., description="Unique identifier for adjacency constraint")
    source_room_id: str = Field(..., description="Stable ID of source room requirement")
    target_room_id: str = Field(..., description="Stable ID of target room requirement")
    relationship: AdjacencyRelationshipType = Field(default=AdjacencyRelationshipType.PREFER_NEAR)
    priority: RoomPriority = Field(default=RoomPriority.HIGH)
    is_hard_constraint: bool = Field(default=False, description="True if mandatory (fails generation if unmet)")
    maximum_route_distance_m: Optional[float] = Field(default=None, gt=0, description="Max acceptable door-to-door or route distance in meters")
    notes: Optional[str] = None


class PreferenceEvaluationStatus(str, Enum):
    SATISFIED = "satisfied"
    NOT_SATISFIED = "not_satisfied"
    PARTIALLY_SATISFIED = "partially_satisfied"
    NOT_EVALUABLE = "not_evaluable"
    NOT_APPLICABLE = "not_applicable"


class PreferenceEvaluationResult(BaseModel):
    preference_id: str
    category: str = "adjacency"  # adjacency | floor | dimension | entrance | orientation | parking | staircase | window | roof
    status: PreferenceEvaluationStatus = PreferenceEvaluationStatus.NOT_EVALUABLE
    is_hard_constraint: bool = False
    evidence: Dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""


class RoomRequirement(BaseModel):
    id: str = Field(..., description="Unique identifier for requirement entry")
    type: str = Field(..., description="Room type e.g. living_room, master_bedroom, kitchen")
    quantity: int = Field(default=1, ge=1, le=10)
    required: bool = Field(default=True, description="True if mandatory, False if optional")
    preferred_min_area: Optional[float] = Field(default=None, gt=0, description="Minimum preferred area in sqm")
    preferred_area_sqm: Optional[float] = Field(default=None, gt=0, description="Target/preferred area in sqm")
    minimum_width_m: Optional[float] = Field(default=None, gt=0, description="Minimum clear width in meters")
    preferred_width_m: Optional[float] = Field(default=None, gt=0, description="Preferred width in meters")
    preferred_length_m: Optional[float] = Field(default=None, gt=0, description="Preferred length in meters")
    floor_preference: Union[int, str] = Field(default="auto", description="'auto' or integer floor index (0, 1, 2, 3)")
    floor_assignment_type: FloorAssignmentType = Field(default=FloorAssignmentType.PREFERRED_FLOOR)
    priority: RoomPriority = Field(default=RoomPriority.HIGH)
    custom_name: Optional[str] = Field(default=None)
    window_orientation_preference: Optional[str] = Field(default=None, description="e.g. north, south, east, west, exterior_wall")
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

    # Architectural Adjacency Constraints & Preferences
    adjacencies: List[RoomAdjacencyRequirement] = Field(default_factory=list)

    # Orientation & Entrance Preferences
    preferred_entrance_orientation: Optional[str] = Field(default=None, description="north | south | east | west | road_frontage")
    preferred_entrance_edge_id: Optional[str] = Field(default=None, description="Edge ID preferred for main entrance door")
    building_orientation_preference: Optional[str] = Field(default=None, description="north_facing | road_facing")

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


class DoorDefinition(BaseModel):
    door_id: str
    floor_id: str
    connected_space_ids: List[str] = Field(default_factory=list)
    wall_id: Optional[str] = None
    position: Point2D
    width_m: float = 0.90
    swing_direction: Optional[str] = None
    verification_status: str = "GEOMETRY_VERIFIED"
    is_external_entrance: bool = False


class WindowDefinition(BaseModel):
    window_id: str
    floor_id: str
    room_id: str
    wall_id: Optional[str] = None
    position: Point2D
    width_m: float = 1.20
    height_m: Optional[float] = 1.20
    orientation: Optional[str] = None
    is_exterior: bool = True
    verification_status: str = "GEOMETRY_VERIFIED"


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    NOT_EVALUABLE = "NOT_EVALUABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CheckSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class CheckDimension(str, Enum):
    GEOMETRIC_VALIDITY = "GEOMETRIC_VALIDITY"
    FUNCTIONAL_ACCESSIBILITY = "FUNCTIONAL_ACCESSIBILITY"
    USER_REQUIREMENTS = "USER_REQUIREMENTS"
    REGULATORY_COMPLIANCE = "REGULATORY_COMPLIANCE"
    DESIGN_QUALITY = "DESIGN_QUALITY"


class ArchitecturalCheckResult(BaseModel):
    check_id: str
    dimension: CheckDimension
    status: CheckStatus
    severity: CheckSeverity = CheckSeverity.ERROR
    affected_room_ids: List[str] = Field(default_factory=list)
    affected_floor_ids: List[str] = Field(default_factory=list)
    measured_value: Optional[float] = None
    required_value: Optional[float] = None
    unit: Optional[str] = None
    source_rule_id: Optional[str] = None
    message: str
    geometry_reference: Optional[Dict[str, Any]] = None


class IndependentValidationReport(BaseModel):
    validation_schema_version: str = "1.0.0"
    validator_version: str = "1.0.0"
    candidate_id: Optional[str] = None
    overall_status: str = "VALID_WITH_VERIFIED_CONSTRAINTS"  # VALID_WITH_VERIFIED_CONSTRAINTS | VALID_WITH_REGULATORY_UNCERTAINTY | INVALID | REQUIRES_REVIEW
    checks: List[ArchitecturalCheckResult] = Field(default_factory=list)
    geometric_validity: bool = True
    circulation_validity: bool = True
    door_validity: bool = True
    staircase_validity: bool = True
    window_validity: bool = True
    parking_validity: bool = True
    requirements_validity: bool = True
    regulatory_validity: bool = True
    summary: Dict[str, int] = Field(default_factory=dict)
    isolated_room_ids: List[str] = Field(default_factory=list)
    overlapping_pairs: List[Dict[str, Any]] = Field(default_factory=list)
    unreachable_rooms: List[str] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return (
            self.geometric_validity
            and self.circulation_validity
            and self.door_validity
            and self.staircase_validity
            and self.requirements_validity
            and self.overall_status != "INVALID"
        )



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
    doors: List[DoorDefinition] = Field(default_factory=list)
    windows: List[WindowDefinition] = Field(default_factory=list)
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
    compliance_verdict: ComplianceStatus = Field(
        default=ComplianceStatus.REQUIRES_REGULATORY_VERIFICATION,
        description="Strict multi-state compliance: compliant, non_compliant, requires_regulatory_verification, conflict_requires_review, not_applicable"
    )
    unresolved_requirements: List[str] = Field(default_factory=list)
    conflicting_requirements: List[str] = Field(default_factory=list)
    site_restriction_summary: List[Dict[str, Any]] = Field(default_factory=list)
    regulatory_resolution: Optional[RegulatoryResolutionOutput] = None
    design_checks: Dict[str, Any] = Field(default_factory=dict)
    preference_evaluations: List[PreferenceEvaluationResult] = Field(
        default_factory=list,
        description="Deterministic post-generation preference evaluation results"
    )
    validation_report: Optional[IndependentValidationReport] = Field(
        default=None,
        description="Exhaustive independent architectural feasibility and validation report"
    )



class CandidateFeasibilityStatus(str, Enum):
    FEASIBLE_VERIFIED_CONSTRAINTS = "FEASIBLE_VERIFIED_CONSTRAINTS"
    FEASIBLE_WITH_REGULATORY_UNCERTAINTY = "FEASIBLE_WITH_REGULATORY_UNCERTAINTY"
    INFEASIBLE = "INFEASIBLE"
    GENERATION_FAILED = "GENERATION_FAILED"


class CandidateRejectionReason(BaseModel):
    code: str
    requirement_id: Optional[str] = None
    message: str


class NumericalFeatureVector(BaseModel):
    feature_schema_version: str = "1.0.0"
    total_usable_room_area_sqm: float = 0.0
    building_footprint_area_sqm: float = 0.0
    area_utilization_ratio: float = 0.0
    circulation_area_sqm: float = 0.0
    circulation_ratio: float = 0.0
    mandatory_room_satisfaction_ratio: float = 0.0
    preferred_room_size_satisfaction_ratio: float = 0.0
    adjacency_satisfaction_ratio: float = 0.0
    average_room_aspect_ratio: float = 1.0
    room_dimension_penalty: float = 0.0
    staircase_area_ratio: float = 0.0
    floor_distribution_balance: float = 1.0
    parking_satisfaction: float = 1.0
    exterior_wall_access_ratio: float = 1.0
    window_feasibility_ratio: float = 1.0
    compactness_ratio: float = 1.0


class HeuristicScoreBreakdown(BaseModel):
    space_utilization: float = 0.0
    circulation_efficiency: float = 0.0
    room_suitability: float = 0.0
    adjacency_satisfaction: float = 0.0
    preference_satisfaction: float = 0.0
    staircase_efficiency: float = 0.0
    compactness: float = 0.0


class CandidateGenerationConfig(BaseModel):
    requested_candidate_count: int = Field(default=3, ge=1, le=10)
    max_generation_attempts: int = Field(default=20, ge=1, le=100)
    deterministic_seed: int = Field(default=42)
    minimum_layout_diversity: float = Field(default=0.10, ge=0.0, le=1.0)
    ranking_method: str = "heuristic_v1"


class FloorPlanCandidate(BaseModel):
    candidate_id: str
    candidate_fingerprint: str
    display_name: str
    rank: int = 1
    heuristic_score: float = 0.0
    score_breakdown: HeuristicScoreBreakdown = Field(default_factory=HeuristicScoreBreakdown)
    feasibility_status: CandidateFeasibilityStatus = CandidateFeasibilityStatus.FEASIBLE_VERIFIED_CONSTRAINTS
    rejection_reasons: List[CandidateRejectionReason] = Field(default_factory=list)
    strategy_name: str = "default_proportional"
    footprint_variant: str = "conformal_offset"
    building_footprint_polygon: List[Point2D] = Field(default_factory=list)
    building_footprint_area_sqm: float = 0.0
    floors: List[FloorPlanDefinition] = Field(default_factory=list)
    roof_geometry: Optional[GeneratedRoofGeometry] = None
    validation: ValidationResult
    preference_evaluations: List[PreferenceEvaluationResult] = Field(default_factory=list)
    features: NumericalFeatureVector = Field(default_factory=NumericalFeatureVector)
    unmet_preferences: List[str] = Field(default_factory=list)
    regulatory_verification_status: str = "verified"


class GabGenRunOutput(BaseModel):
    project_id: str
    project_name: str
    units: str = "meters"
    status: str
    master_json: Dict[str, Any]
    validation: ValidationResult
    warnings: List[str] = Field(default_factory=list)
    candidates: List[FloorPlanCandidate] = Field(default_factory=list)
    selected_candidate_id: Optional[str] = None

