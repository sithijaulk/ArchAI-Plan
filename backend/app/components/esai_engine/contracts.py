"""
ESAI Contracts & Enums
Data models and enumeration types for canonical spatial representation,
client requirements, catalogue entries, and validation results.
"""
from enum import Enum
from typing import Any, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator


class LengthUnit(str, Enum):
    METERS = "m"
    CENTIMETERS = "cm"
    MILLIMETERS = "mm"
    FEET = "ft"
    INCHES = "in"


# Conversion factor to Meters (canonical base unit)
UNIT_TO_METER = {
    LengthUnit.METERS: 1.0,
    LengthUnit.CENTIMETERS: 0.01,
    LengthUnit.MILLIMETERS: 0.001,
    LengthUnit.FEET: 0.3048,
    LengthUnit.INCHES: 0.0254,
}


def convert_to_meters(value: float, unit: LengthUnit | str) -> float:
    """Convert any supported length unit value to canonical meters."""
    if isinstance(unit, str):
        try:
            unit = LengthUnit(unit.lower())
        except ValueError:
            raise ValueError(f"Unsupported measurement unit '{unit}'. Supported: {[u.value for u in LengthUnit]}")
    return round(value * UNIT_TO_METER[unit], 5)


class RoomType(str, Enum):
    MASTER_BEDROOM = "master_bedroom"
    BEDROOM = "bedroom"
    LIVING_ROOM = "living_room"
    DINING_ROOM = "dining_room"
    KITCHEN = "kitchen"
    BATHROOM = "bathroom"
    STUDY = "study"
    HOME_OFFICE = "home_office"
    GUEST_ROOM = "guest_room"
    UTILITY_ROOM = "utility_room"
    LAUNDRY_ROOM = "laundry_room"
    PANTRY = "pantry"
    HALLWAY = "hallway"
    FOYER = "foyer"
    OTHER = "other"


class AssetCategory(str, Enum):
    BED = "bed"
    WARDROBE = "wardrobe"
    BEDSIDE_TABLE = "bedside_table"
    DRESSING_TABLE = "dressing_table"
    SOFA = "sofa"
    ARMCHAIR = "armchair"
    COFFEE_TABLE = "coffee_table"
    TV_CONSOLE = "tv_console"
    SIDE_TABLE = "side_table"
    BOOKSHELF = "bookshelf"
    DINING_TABLE = "dining_table"
    DINING_CHAIR = "dining_chair"
    STORAGE_CABINET = "storage_cabinet"
    KITCHEN_COUNTER = "kitchen_counter"
    KITCHEN_ISLAND = "kitchen_island"
    KITCHEN_APPLIANCE = "kitchen_appliance"
    BASIN = "basin"
    COMMODE = "commode"
    SHOWER_ENCLOSURE = "shower_enclosure"
    BATHTUB = "bathtub"
    DESK = "desk"
    OFFICE_CHAIR = "office_chair"
    WORKSTATION = "workstation"
    OTHER = "other"


class AssetMobility(str, Enum):
    MOVABLE = "movable"
    FIXED = "fixed"
    USER_LOCKED = "user_locked"


class ConstraintPriority(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    CONFIGURABLE = "configurable"


class ClearanceDirection(str, Enum):
    FRONT = "front"
    BACK = "back"
    LEFT = "left"
    RIGHT = "right"
    BOTH_SIDES = "both_sides"
    ALL_SIDES = "all_sides"
    CIRCULATION = "circulation"


class StandardVerificationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    RECOMMENDED = "recommended"


class Coordinate2D(BaseModel):
    x: float
    y: float


class Dimensions3D(BaseModel):
    width: float = Field(..., gt=0, description="Width along local X axis (meters)")
    depth: float = Field(..., gt=0, description="Depth / length along local Y axis (meters)")
    height: float = Field(..., gt=0, description="Height along local Z axis (meters)")


class DoorHinge(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    SLIDING = "sliding"
    DOUBLE = "double"
    UNKNOWN = "unknown"


class DoorOpeningDirection(str, Enum):
    INWARD = "inward"
    OUTWARD = "outward"
    BOTH = "both"
    SLIDING = "sliding"


class DoorDTO(BaseModel):
    id: str
    room_id: str
    start: Coordinate2D
    end: Coordinate2D
    leaf_width: float = Field(..., gt=0, description="Width of the door leaf in meters")
    hinge: DoorHinge = DoorHinge.LEFT
    opening_direction: DoorOpeningDirection = DoorOpeningDirection.INWARD
    swing_angle: float = Field(default=90.0, ge=0.0, le=180.0)
    protected_depth: Optional[float] = Field(default=None, description="Clearance zone depth in front of door")


class WindowDTO(BaseModel):
    id: str
    room_id: str
    start: Coordinate2D
    end: Coordinate2D
    length: float = Field(..., gt=0, description="Window opening length in meters")
    sill_height: Optional[float] = Field(default=0.9, ge=0.0, description="Sill height in meters")
    height: Optional[float] = Field(default=1.2, ge=0.0, description="Window height in meters")
    opening_type: str = "sliding"  # sliding, casement, fixed
    protected_access_depth: Optional[float] = Field(default=0.6, ge=0.0, description="Ergonomic access clearance")


class FixedObstructionDTO(BaseModel):
    id: str
    name: str
    polygon: List[Coordinate2D]
    height: Optional[float] = None
    category: str = "structural"  # column, pipe_duct, built_in_counter, sanitary_fixture


class RoomDTO(BaseModel):
    floor_id: str
    room_id: str
    name: str
    room_type: RoomType
    polygon: List[Coordinate2D] = Field(..., min_length=3)
    area_sqm: float = Field(..., gt=0.0)
    ceiling_height: Optional[float] = 2.8
    elevation: Optional[float] = 0.0
    doors: List[DoorDTO] = Field(default_factory=list)
    windows: List[WindowDTO] = Field(default_factory=list)
    fixed_obstructions: List[FixedObstructionDTO] = Field(default_factory=list)


class FloorDTO(BaseModel):
    floor_id: str
    floor_name: str
    level_index: int = 0
    elevation: float = 0.0
    rooms: List[RoomDTO] = Field(default_factory=list)


class StructuralInputDTO(BaseModel):
    project_id: str
    project_name: str
    unit: LengthUnit = LengthUnit.METERS
    floors: List[FloorDTO] = Field(default_factory=list)


# Client Requirements Models
class FurnitureRequirementItem(BaseModel):
    instance_id: str = Field(..., description="Unique ID for this furniture requirement instance in the room")
    catalog_id: str = Field(..., description="Referenced catalog asset ID")
    category: AssetCategory
    variant_name: Optional[str] = None
    quantity: int = Field(default=1, ge=1)
    is_required: bool = Field(default=True, description="True = mandatory, False = optional decoration")
    priority: ConstraintPriority = ConstraintPriority.HARD
    custom_dimensions: Optional[Dimensions3D] = None
    allowed_rotations: List[int] = Field(default_factory=lambda: [0, 90, 180, 270])
    preferred_walls: List[str] = Field(default_factory=list)  # "north", "south", "east", "west"
    preferred_orientation: Optional[int] = None
    preferred_functional_relations: List[str] = Field(default_factory=list)
    keep_clear_zones: List[dict] = Field(default_factory=list)
    user_locked: bool = False
    locked_position: Optional[Coordinate2D] = None
    locked_rotation: Optional[int] = None
    material_preference: Optional[str] = None
    color_finish: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("allowed_rotations")
    @classmethod
    def validate_rotations(cls, v: List[int]) -> List[int]:
        valid = {0, 90, 180, 270}
        for r in v:
            if r not in valid:
                raise ValueError(f"Invalid rotation {r}. Allowed: 0, 90, 180, 270.")
        return sorted(list(set(v)))


class RoomRequirementsDTO(BaseModel):
    room_id: str
    floor_id: str
    room_type: RoomType
    furniture_density: str = "standard"  # minimal, standard, luxurious
    circulation_priority: str = "standard"  # standard, spacious, compact, accessible
    accessibility_profile: Optional[str] = None  # standard, wheelchair_accessible, elderly_friendly
    items: List[FurnitureRequirementItem] = Field(default_factory=list)
    notes: Optional[str] = None


class ProjectPreferencesDTO(BaseModel):
    project_id: str
    preferred_units: LengthUnit = LengthUnit.METERS
    density_preference: str = "standard"
    accessibility_profile: str = "standard"
    visual_style: Optional[str] = None  # modern, minimalist, scandinavian, industrial, traditional
    color_palette: Optional[List[str]] = None
    flooring_finish: Optional[str] = None
    wall_finish: Optional[str] = None
    requested_alternatives: int = Field(default=3, ge=1, le=10)
    repeatability_seed: Optional[int] = None


class ValidationMessage(BaseModel):
    code: str
    path: str
    room_id: Optional[str] = None
    asset_id: Optional[str] = None
    message: str
    severity: str = "error"  # error, warning, info


class ValidationResultDTO(BaseModel):
    valid: bool
    errors: List[ValidationMessage] = Field(default_factory=list)
    warnings: List[ValidationMessage] = Field(default_factory=list)
    info: List[ValidationMessage] = Field(default_factory=list)
