"""
ESAI Contracts & Enums
Data models and enumeration types for canonical spatial representation,
client requirements, catalogue entries, and validation results.
Stage 2: Comprehensive multi-level client preference hierarchy, extended asset
categories, lighting, electrical, services, finishes, and style contracts.
"""
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
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
    GUEST_ROOM = "guest_room"
    LIVING_ROOM = "living_room"
    FAMILY_LIVING_AREA = "family_living_area"
    TV_LOBBY = "tv_lobby"
    TV_LOUNGE = "tv_lounge"
    LOUNGE = "lounge"
    DINING_ROOM = "dining_room"
    DINING_AREA = "dining_area"
    KITCHEN = "kitchen"
    PANTRY = "pantry"
    BATHROOM = "bathroom"
    ATTACHED_BATHROOM = "attached_bathroom"
    COMMON_BATHROOM = "common_bathroom"
    TOILET = "toilet"
    STUDY = "study"
    STUDY_OFFICE = "study_office"
    HOME_OFFICE = "home_office"
    UTILITY_ROOM = "utility_room"
    LAUNDRY_ROOM = "laundry_room"
    HALLWAY = "hallway"
    CORRIDOR = "corridor"
    FOYER = "foyer"
    ENTRY = "entry"
    STAIRCASE = "staircase"
    OTHER = "other"
    UNKNOWN = "unknown"



class AssetCategory(str, Enum):
    # Beds
    BED = "bed"
    # Bedroom storage & accessories
    WARDROBE = "wardrobe"
    BEDSIDE_TABLE = "bedside_table"
    DRESSING_TABLE = "dressing_table"
    STUDY_DESK = "study_desk"
    # Living
    SOFA = "sofa"
    ARMCHAIR = "armchair"
    COFFEE_TABLE = "coffee_table"
    TV_CONSOLE = "tv_console"
    MEDIA_WALL = "media_wall"
    SIDE_TABLE = "side_table"
    BOOKSHELF = "bookshelf"
    # Dining
    DINING_TABLE = "dining_table"
    DINING_CHAIR = "dining_chair"
    # Storage
    STORAGE_CABINET = "storage_cabinet"
    # Kitchen
    KITCHEN_COUNTER = "kitchen_counter"
    KITCHEN_ISLAND = "kitchen_island"
    KITCHEN_APPLIANCE = "kitchen_appliance"
    PANTRY_CABINET = "pantry_cabinet"
    # Bathroom
    BASIN = "basin"
    VANITY_UNIT = "vanity_unit"
    COMMODE = "commode"
    SHOWER_ENCLOSURE = "shower_enclosure"
    BATHTUB = "bathtub"
    BATHROOM_MIRROR = "bathroom_mirror"
    TOWEL_RAIL = "towel_rail"
    # Office
    DESK = "desk"
    OFFICE_CHAIR = "office_chair"
    WORKSTATION = "workstation"
    # Lighting
    CEILING_LIGHT = "ceiling_light"
    CHANDELIER = "chandelier"
    PENDANT_LIGHT = "pendant_light"
    WALL_LIGHT = "wall_light"
    FLOOR_LAMP = "floor_lamp"
    TABLE_LAMP = "table_lamp"
    LED_STRIP = "led_strip"
    RECESSED_DOWNLIGHT = "recessed_downlight"
    CEILING_FAN = "ceiling_fan"
    # Electrical / Service
    WALL_SOCKET = "wall_socket"
    USB_CHARGING_POINT = "usb_charging_point"
    TV_DATA_OUTLET = "tv_data_outlet"
    AC_UNIT = "ac_unit"
    WATER_HEATER = "water_heater"
    EXHAUST_FAN = "exhaust_fan"
    # Other
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


class WallDTO(BaseModel):
    id: str
    floor_id: str
    start: Coordinate2D
    end: Coordinate2D
    thickness: float = Field(default=0.225, gt=0.0, description="Wall thickness in meters")
    height: Optional[float] = Field(default=None, gt=0.0, description="Wall height in meters")
    wall_type: str = "interior"  # exterior, interior, party, structural
    related_room_ids: List[str] = Field(default_factory=list)
    orientation: Optional[str] = None


class RoomDTO(BaseModel):
    floor_id: str
    room_id: str
    name: str
    room_type: RoomType
    source_room_type: Optional[str] = None
    is_unsupported_type: bool = False
    polygon: List[Coordinate2D] = Field(..., min_length=3)
    area_sqm: float = Field(..., gt=0.0)
    ceiling_height: Optional[float] = 2.8
    elevation: Optional[float] = 0.0
    doors: List[DoorDTO] = Field(default_factory=list)
    windows: List[WindowDTO] = Field(default_factory=list)
    fixed_obstructions: List[FixedObstructionDTO] = Field(default_factory=list)
    doors_data_available: bool = True
    windows_data_available: bool = True
    missing_upstream_fields: List[str] = Field(default_factory=list)


class FloorDTO(BaseModel):
    floor_id: str
    floor_name: str
    level_index: int = 0
    elevation: float = 0.0
    floor_height: Optional[float] = 3.0
    rooms: List[RoomDTO] = Field(default_factory=list)
    walls: List[WallDTO] = Field(default_factory=list)


class StructuralInputDTO(BaseModel):
    project_id: str
    project_name: str
    unit: LengthUnit = LengthUnit.METERS
    geometry_source: str = "gab_gen"  # gab_gen or vsai_rectifier
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


# ─── Stage 2: Extended Enums ──────────────────────────────────────────────────

class BedType(str, Enum):
    SINGLE = "single"
    TWIN = "twin"
    DOUBLE = "double"
    QUEEN = "queen"
    KING = "king"
    BUNK = "bunk"
    TRIPLE_SLEEPER = "triple_sleeper"


class InteriorStyle(str, Enum):
    MODERN = "modern"
    MINIMALIST = "minimalist"
    SCANDINAVIAN = "scandinavian"
    INDUSTRIAL = "industrial"
    TRADITIONAL = "traditional"
    CONTEMPORARY = "contemporary"
    LUXURY = "luxury"
    RUSTIC = "rustic"
    BOHEMIAN = "bohemian"
    COASTAL = "coastal"


class FinishType(str, Enum):
    PAINT_MATTE = "paint_matte"
    PAINT_SATIN = "paint_satin"
    PAINT_GLOSS = "paint_gloss"
    WALLPAPER = "wallpaper"
    TEXTURED_PLASTER = "textured_plaster"
    CERAMIC_TILE = "ceramic_tile"
    STONE_CLADDING = "stone_cladding"
    WOOD_PANEL = "wood_panel"
    HARDWOOD = "hardwood"
    ENGINEERED_WOOD = "engineered_wood"
    LAMINATE = "laminate"
    CERAMIC_FLOOR_TILE = "ceramic_floor_tile"
    PORCELAIN_TILE = "porcelain_tile"
    MARBLE = "marble"
    VINYL = "vinyl"
    CARPET = "carpet"
    POLISHED_CONCRETE = "polished_concrete"
    PLASTER_SMOOTH = "plaster_smooth"
    POP_DESIGN = "pop_design"
    GYPSUM_BOARD = "gypsum_board"
    WOODEN_CEILING = "wooden_ceiling"
    OPEN_EXPOSED = "open_exposed"
    OTHER = "other"


class LightingType(str, Enum):
    WARM_WHITE = "warm_white"       # ~2700K
    NEUTRAL_WHITE = "neutral_white"  # ~4000K
    COOL_WHITE = "cool_white"        # ~6500K
    RGB = "rgb"
    TUNABLE = "tunable"


class ElectricalOutletType(str, Enum):
    STANDARD_SOCKET = "standard_socket"
    USB_CHARGING = "usb_charging"
    DOUBLE_SOCKET = "double_socket"
    TV_DATA = "tv_data"
    ETHERNET_DATA = "ethernet_data"
    BEDSIDE_CHARGER = "bedside_charger"
    KITCHEN_APPLIANCE = "kitchen_appliance"
    AC_DEDICATED = "ac_dedicated"
    EARTH_LEAKAGE_PROTECTED = "earth_leakage_protected"


class WaterConnectionType(str, Enum):
    HOT_COLD = "hot_cold"
    COLD_ONLY = "cold_only"
    HOT_ONLY = "hot_only"


class AccessibilityProfile(str, Enum):
    STANDARD = "standard"
    WHEELCHAIR_ACCESSIBLE = "wheelchair_accessible"
    ELDERLY_FRIENDLY = "elderly_friendly"
    CHILD_SAFE = "child_safe"


class FurnitureDensity(str, Enum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    LUXURIOUS = "luxurious"


class CirculationPriority(str, Enum):
    COMPACT = "compact"
    STANDARD = "standard"
    SPACIOUS = "spacious"
    ACCESSIBLE = "accessible"


# ─── Stage 2: Lighting & Electrical Models ────────────────────────────────────

class LightingPreferenceItem(BaseModel):
    """A single lighting fixture/zone preference for a room."""
    instance_id: str
    lighting_type: LightingType = LightingType.WARM_WHITE
    category: str = "ceiling_light"  # AssetCategory string value
    quantity: int = Field(default=1, ge=1)
    color_temperature_k: Optional[int] = Field(default=None, ge=2000, le=6500)
    dimmable: bool = False
    preferred_location: Optional[str] = None
    switch_group: Optional[str] = None
    is_required: bool = True
    notes: Optional[str] = None


class ElectricalOutletItem(BaseModel):
    """An electrical socket or outlet requirement in a room."""
    instance_id: str
    outlet_type: ElectricalOutletType = ElectricalOutletType.STANDARD_SOCKET
    quantity: int = Field(default=1, ge=1)
    preferred_wall: Optional[str] = None
    height_from_floor: Optional[float] = Field(default=None, ge=0.0, le=3.0)
    near_asset_instance_id: Optional[str] = None
    is_required: bool = True
    notes: Optional[str] = None


class ServiceProvision(BaseModel):
    """Plumbing, ventilation, AC, and mechanical service provisions."""
    service_type: str  # "plumbing_hot_cold", "drainage", "ac_provision", "exhaust_fan", etc.
    proposed_wall: Optional[str] = None
    notes: Optional[str] = None
    is_required: bool = True


class RoomFinishPreferences(BaseModel):
    """Material and finish selections for a single room."""
    wall_finish: Optional[FinishType] = None
    wall_color: Optional[str] = None
    accent_wall: Optional[bool] = False
    accent_wall_finish: Optional[FinishType] = None
    accent_wall_color: Optional[str] = None
    floor_finish: Optional[FinishType] = None
    floor_color: Optional[str] = None
    ceiling_finish: Optional[FinishType] = None
    ceiling_color: Optional[str] = None
    ceiling_height_m: Optional[float] = Field(default=None, ge=2.4, le=6.0)
    skirting_material: Optional[str] = None
    door_finish: Optional[str] = None
    window_trim_finish: Optional[str] = None
    notes: Optional[str] = None


class RoomStylePreferences(BaseModel):
    """Interior style and aesthetic preferences for a room."""
    interior_style: Optional[InteriorStyle] = None
    color_palette: Optional[List[str]] = Field(default_factory=list)
    material_palette: Optional[List[str]] = Field(default_factory=list)
    decoration_intensity: Optional[str] = None  # "minimal", "moderate", "heavy"
    art_wall_required: Optional[bool] = False
    plants_required: Optional[bool] = False
    curtains: Optional[bool] = True
    curtain_style: Optional[str] = None
    blinds: Optional[bool] = False
    notes: Optional[str] = None


# ─── Stage 2: Room-Type Preference Models ─────────────────────────────────────

class BathroomPreferences(BaseModel):
    """Bathroom-specific fixture and preference model."""
    has_bathtub: bool = False
    bathtub_type: Optional[str] = None
    has_shower: bool = True
    shower_type: Optional[str] = None
    shower_screen_type: Optional[str] = None
    toilet_type: Optional[str] = None
    bidet_required: bool = False
    washbasin_count: int = Field(default=1, ge=0, le=3)
    washbasin_type: Optional[str] = None
    vanity_required: bool = True
    mirror_type: Optional[str] = None
    hot_water_connection: WaterConnectionType = WaterConnectionType.HOT_COLD
    water_heater_type: Optional[str] = None
    exhaust_fan_required: bool = True
    towel_rail_count: int = Field(default=1, ge=0)
    heated_towel_rail: bool = False
    accessories: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class KitchenPreferences(BaseModel):
    """Kitchen-specific fixture and appliance preference model."""
    layout_type: Optional[str] = None
    has_island: bool = False
    island_with_seating: bool = False
    island_seating_count: int = Field(default=0, ge=0)
    countertop_material: Optional[str] = None
    cabinet_material: Optional[str] = None
    cabinet_finish: Optional[str] = None
    sink_type: Optional[str] = None
    sink_material: Optional[str] = None
    tap_style: Optional[str] = None
    hob_type: Optional[str] = None
    hob_burner_count: int = Field(default=4, ge=2, le=6)
    oven_type: Optional[str] = None
    hood_type: Optional[str] = None
    refrigerator_type: Optional[str] = None
    dishwasher_required: bool = False
    washing_machine_in_kitchen: bool = False
    pantry_cabinet_required: bool = True
    breakfast_bar_required: bool = False
    breakfast_bar_stools: int = Field(default=0, ge=0)
    backsplash_material: Optional[str] = None
    plinth_lighting: bool = False
    under_cabinet_lighting: bool = False
    appliances: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class BedroomPreferences(BaseModel):
    """Bedroom-specific furniture and preference model."""
    bed_type: BedType = BedType.DOUBLE
    bed_count: int = Field(default=1, ge=1, le=4)
    headboard_required: bool = True
    headboard_material: Optional[str] = None
    bedside_tables_count: int = Field(default=2, ge=0, le=2)
    wardrobe_type: Optional[str] = None
    wardrobe_wall_count: int = Field(default=1, ge=0, le=4)
    dressing_table_required: bool = False
    study_desk_required: bool = False
    study_chair_required: bool = False
    tv_in_bedroom: bool = False
    tv_bracket_required: bool = False
    tv_wall_location: Optional[str] = None
    bedside_charging_outlets: int = Field(default=2, ge=0)
    mirror_required: bool = False
    seating_required: bool = False
    seating_type: Optional[str] = None
    notes: Optional[str] = None


class LivingRoomPreferences(BaseModel):
    """Living / TV lounge specific furniture and layout preferences."""
    sofa_type: Optional[str] = None
    sofa_count: int = Field(default=1, ge=1)
    armchair_count: int = Field(default=0, ge=0)
    coffee_table_required: bool = True
    coffee_table_shape: Optional[str] = None
    tv_unit_type: Optional[str] = None
    tv_size_inches: Optional[int] = Field(default=None, ge=32, le=100)
    fireplace_required: bool = False
    bookshelf_required: bool = False
    rug_required: bool = True
    ottoman_required: bool = False
    accent_chairs_count: int = Field(default=0, ge=0)
    open_to_dining: bool = False
    viewing_distance_preference: Optional[str] = None
    notes: Optional[str] = None


class DiningPreferences(BaseModel):
    """Dining room specific preferences."""
    table_shape: Optional[str] = None
    seating_count: int = Field(default=4, ge=2, le=16)
    chair_style: Optional[str] = None
    sideboard_required: bool = False
    buffet_cabinet_required: bool = False
    bar_cabinet_required: bool = False
    chandelier_over_table: bool = True
    open_to_kitchen: bool = False
    notes: Optional[str] = None


class OfficePreferences(BaseModel):
    """Home office / study specific preferences."""
    desk_type: Optional[str] = None
    desk_count: int = Field(default=1, ge=1)
    chair_type: Optional[str] = None
    bookcase_required: bool = True
    filing_cabinet_required: bool = False
    monitor_count: int = Field(default=1, ge=1)
    ethernet_outlet_required: bool = True
    daylight_preference: Optional[str] = None
    whiteboard_required: bool = False
    notes: Optional[str] = None


# ─── Stage 2: Multi-Level Preference Hierarchy ────────────────────────────────

class FullRoomPreferencesDTO(BaseModel):
    """
    Complete preferences for a single room.
    Includes furniture, finishes, style, lighting, electrical, services.
    The 'items' list (FurnitureRequirementItem) is preserved for GA consumption.
    Never silently overrides explicit client selections.
    """
    room_id: str
    floor_id: str
    room_type: RoomType

    # Density and Circulation
    furniture_density: FurnitureDensity = FurnitureDensity.STANDARD
    circulation_priority: CirculationPriority = CirculationPriority.STANDARD
    accessibility_profile: AccessibilityProfile = AccessibilityProfile.STANDARD

    # Style & Finishes
    style: Optional[RoomStylePreferences] = None
    finishes: Optional[RoomFinishPreferences] = None

    # Room-type-specific preferences
    bedroom: Optional[BedroomPreferences] = None
    bathroom: Optional[BathroomPreferences] = None
    kitchen: Optional[KitchenPreferences] = None
    living_room: Optional[LivingRoomPreferences] = None
    dining: Optional[DiningPreferences] = None
    office: Optional[OfficePreferences] = None

    # Lighting
    lighting: List[LightingPreferenceItem] = Field(default_factory=list)
    ambient_lighting_type: LightingType = LightingType.WARM_WHITE

    # Electrical / Outlets
    electrical_outlets: List[ElectricalOutletItem] = Field(default_factory=list)

    # Services (plumbing, AC, exhaust)
    service_provisions: List[ServiceProvision] = Field(default_factory=list)

    # Furniture items (GA input)
    items: List[FurnitureRequirementItem] = Field(default_factory=list)

    # Selection control — never silently override
    mandatory_catalog_ids: List[str] = Field(default_factory=list)
    excluded_catalog_ids: List[str] = Field(default_factory=list)
    user_locked_instance_ids: List[str] = Field(default_factory=list)

    notes: Optional[str] = None


class FloorPreferencesDTO(BaseModel):
    """
    Floor-level preferences that override building defaults for all rooms on this floor.
    Per-room FullRoomPreferencesDTO takes final priority.
    """
    floor_id: str
    interior_style: Optional[InteriorStyle] = None
    color_palette: Optional[List[str]] = None
    wall_finish: Optional[FinishType] = None
    floor_finish: Optional[FinishType] = None
    ceiling_finish: Optional[FinishType] = None
    lighting_type: Optional[LightingType] = None
    furniture_density: Optional[FurnitureDensity] = None
    accessibility_profile: Optional[AccessibilityProfile] = None
    notes: Optional[str] = None


class BuildingPreferencesDTO(BaseModel):
    """
    Building-level defaults. Overridden by FloorPreferencesDTO > FullRoomPreferencesDTO.
    Collected once before any GA run begins.
    """
    project_id: str

    # Global defaults
    interior_style: Optional[InteriorStyle] = None
    color_palette: Optional[List[str]] = None
    wall_finish: Optional[FinishType] = None
    floor_finish: Optional[FinishType] = None
    ceiling_finish: Optional[FinishType] = None
    lighting_type: LightingType = LightingType.WARM_WHITE
    furniture_density: FurnitureDensity = FurnitureDensity.STANDARD
    accessibility_profile: AccessibilityProfile = AccessibilityProfile.STANDARD
    preferred_units: LengthUnit = LengthUnit.METERS

    # GA Settings
    requested_alternatives: int = Field(default=3, ge=1, le=10)
    repeatability_seed: Optional[int] = None

    # Floor overrides (keyed by floor_id)
    floor_overrides: Dict[str, Any] = Field(default_factory=dict)

    # Room overrides (keyed by room_id) — highest priority
    room_overrides: Dict[str, Any] = Field(default_factory=dict)

    notes: Optional[str] = None
