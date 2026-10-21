"""
Vastu Shastra Spatial Analysis & Engineering Rule Engine.

This module implements the finalized VSAI Rectifier Vastu Shastra rules:
1. Brahmasthan Exact Center-Point Check (vsai.brahmasthan.exact_center)
2. Dwara Sthana Door-Combination Analysis (vsai.dwara_sthana.combination)
3. Main Entrance Direction Analysis (vsai.main_entrance.direction)
4. Room Direction Analysis (vsai.room.direction)

Designed for Stage 1 Master JSON validation, spatial compliance analysis,
violation reporting, and actionable remedial recommendations.
"""

from __future__ import annotations

import json
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Enums and Constants
# ==============================================================================

class VastuSector(str, Enum):
    """Padavinyasa directional sectors and central core."""
    NORTH = "NORTH"
    NORTH_EAST = "NORTH_EAST"
    EAST = "EAST"
    SOUTH_EAST = "SOUTH_EAST"
    SOUTH = "SOUTH"
    SOUTH_WEST = "SOUTH_WEST"
    WEST = "WEST"
    NORTH_WEST = "NORTH_WEST"
    CENTER = "CENTER"
    CENTER_BRAHMASTHAN = "CENTER_BRAHMASTHAN"
    SOUTH_OF_SOUTH_EAST = "SOUTH_OF_SOUTH_EAST"
    WEST_OF_NORTH_WEST = "WEST_OF_NORTH_WEST"
    GLOBAL = "GLOBAL"


# Legacy constant aliases for backward compatibility
SECTOR_NORTH = VastuSector.NORTH.value
SECTOR_NORTH_EAST = VastuSector.NORTH_EAST.value
SECTOR_EAST = VastuSector.EAST.value
SECTOR_SOUTH_EAST = VastuSector.SOUTH_EAST.value
SECTOR_SOUTH = VastuSector.SOUTH.value
SECTOR_SOUTH_WEST = VastuSector.SOUTH_WEST.value
SECTOR_WEST = VastuSector.WEST.value
SECTOR_NORTH_WEST = VastuSector.NORTH_WEST.value
SECTOR_CENTER = VastuSector.CENTER.value

SECTOR_DISPLAY_NAMES: Dict[str, str] = {
    SECTOR_NORTH: "North (Uttara / Kubera)",
    SECTOR_NORTH_EAST: "North-East (Ishanya / Shiva)",
    SECTOR_EAST: "East (Purva / Indra)",
    SECTOR_SOUTH_EAST: "South-East (Agneya / Agni)",
    SECTOR_SOUTH: "South (Dakshina / Yama)",
    SECTOR_SOUTH_WEST: "South-West (Nairutya / Nirrithi)",
    SECTOR_WEST: "West (Pashchima / Varuna)",
    SECTOR_NORTH_WEST: "North-West (Vayavya / Vayu)",
    SECTOR_CENTER: "Brahmasthan (Center / Brahma Core)",
    VastuSector.CENTER_BRAHMASTHAN.value: "Brahmasthan (Center / Brahma Core)",
    VastuSector.SOUTH_OF_SOUTH_EAST.value: "South of South-East (SSE)",
    VastuSector.WEST_OF_NORTH_WEST.value: "West of North-West (WNW)",
    VastuSector.GLOBAL.value: "Global Structure",
}

ORIENTATION_OFFSETS: Dict[str, int] = {
    "north": 0,
    "north-east": 45,
    "northeast": 45,
    "east": 90,
    "south-east": 135,
    "southeast": 135,
    "south": 180,
    "south-west": 225,
    "southwest": 225,
    "west": 270,
    "north-west": 315,
    "northwest": 315,
}

CLOCKWISE_SECTORS: Sequence[str] = (
    SECTOR_NORTH,
    SECTOR_NORTH_EAST,
    SECTOR_EAST,
    SECTOR_SOUTH_EAST,
    SECTOR_SOUTH,
    SECTOR_SOUTH_WEST,
    SECTOR_WEST,
    SECTOR_NORTH_WEST,
)

CARDINAL_DIRECTIONS: Sequence[str] = (
    SECTOR_EAST,
    SECTOR_SOUTH,
    SECTOR_WEST,
    SECTOR_NORTH,
)

DEFAULT_CENTER_TOLERANCE: float = 0.05

# 16 Dwara Sthana combinations mapped by frozenset of cardinal directions
DWARA_STHANA_COMBINATIONS: Dict[FrozenSet[str], Tuple[str, str, str]] = {
    frozenset(): ("Dhruva", "VERY_GOOD", "Wealth, grain and prosperity"),
    frozenset([SECTOR_EAST]): ("Dhanya", "GOOD", "Good harvest and grain resources"),
    frozenset([SECTOR_SOUTH]): ("Jaya", "GOOD", "Victory in activities"),
    frozenset([SECTOR_EAST, SECTOR_SOUTH]): ("Nanda", "BAD", "Harm/misfortune to women (traditional claim)"),
    frozenset([SECTOR_WEST]): ("Khara", "BAD", "Loss of property and wealth (traditional claim)"),
    frozenset([SECTOR_EAST, SECTOR_WEST]): ("Kanta", "GOOD", "Happiness and progress for children/grandchildren"),
    frozenset([SECTOR_SOUTH, SECTOR_WEST]): ("Manorama", "GOOD", "Beauty, peace and happiness in the home"),
    frozenset([SECTOR_EAST, SECTOR_SOUTH, SECTOR_WEST]): ("Sumukha", "GOOD", "Resources and comfort"),
    frozenset([SECTOR_NORTH]): ("Durmukha", "BAD", "Misfortune (traditional claim)"),
    frozenset([SECTOR_EAST, SECTOR_NORTH]): ("Ugra", "BAD", "Distress for the family (traditional claim)"),
    frozenset([SECTOR_NORTH, SECTOR_SOUTH]): ("Ripuda", "BAD", "Fear and adversity from enemies (traditional claim)"),
    frozenset([SECTOR_EAST, SECTOR_NORTH, SECTOR_SOUTH]): ("Vittada", "GOOD", "Wealth and money"),
    frozenset([SECTOR_NORTH, SECTOR_WEST]): ("Kshaya/Nasha", "BAD", "Destruction and decline (traditional claim)"),
    frozenset([SECTOR_EAST, SECTOR_NORTH, SECTOR_WEST]): ("Akranda", "BAD", "Sorrow and tears (traditional claim)"),
    frozenset([SECTOR_NORTH, SECTOR_SOUTH, SECTOR_WEST]): ("Vipula", "GOOD", "Abundant resources and reputation"),
    frozenset([SECTOR_EAST, SECTOR_NORTH, SECTOR_SOUTH, SECTOR_WEST]): ("Vijaya", "VERY_GOOD", "Great wealth and happiness"),
}

POSITIVE_ENTRANCE_ZONES: Set[str] = {
    SECTOR_NORTH,
    SECTOR_NORTH_EAST,
    SECTOR_EAST,
    VastuSector.SOUTH_OF_SOUTH_EAST.value,
    VastuSector.WEST_OF_NORTH_WEST.value,
}


# ==============================================================================
# 2. Domain Data Structures
# ==============================================================================

@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned bounding box."""
    min_x: float
    max_x: float
    min_y: float
    max_y: float

    @property
    def width(self) -> float:
        return max(0.0, self.max_x - self.min_x)

    @property
    def height(self) -> float:
        return max(0.0, self.max_y - self.min_y)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> Tuple[float, float]:
        """Calculates exact midpoint (min_x + W/2, min_y + H/2)."""
        return (self.min_x + self.width / 2.0, self.min_y + self.height / 2.0)

    def overlaps(self, other: BoundingBox) -> bool:
        return not (
            self.max_x < other.min_x
            or self.min_x > other.max_x
            or self.max_y < other.min_y
            or self.min_y > other.max_y
        )

    def contains_point(self, px: float, py: float, tolerance: float = 0.0) -> bool:
        return (
            (self.min_x - tolerance) <= px <= (self.max_x + tolerance)
            and (self.min_y - tolerance) <= py <= (self.max_y + tolerance)
        )

    def to_dict(self, area_sqft: Optional[float] = None) -> Dict[str, float]:
        return {
            "min_x": round(self.min_x, 2),
            "max_x": round(self.max_x, 2),
            "min_y": round(self.min_y, 2),
            "max_y": round(self.max_y, 2),
            "width": round(self.width, 2),
            "height": round(self.height, 2),
            "area_sqft": round(area_sqft if area_sqft is not None else self.area, 2),
        }


@dataclass
class SpatialObject:
    """Generic spatial element representation for geometric collision tests."""
    id: str
    name: str
    object_type: str
    polygon: List[List[float]] = field(default_factory=list)
    line_segment: Optional[Tuple[Tuple[float, float], Tuple[float, float]]] = None
    bounds: Optional[BoundingBox] = None


@dataclass
class RoomEntity:
    """Represents a room in the floor plan with its spatial characteristics."""
    id: str
    name: str
    room_type: str
    polygon: List[List[float]]
    centroid: Tuple[float, float]
    bounds: BoundingBox
    sector: str = SECTOR_CENTER
    overlaps_brahmasthan_core: bool = False
    occupies_exact_center: bool = False

    @property
    def sector_display(self) -> str:
        return SECTOR_DISPLAY_NAMES.get(self.sector, self.sector)

    def to_sector_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.room_type,
            "sector": self.sector,
            "sector_display": self.sector_display,
            "centroid": [round(self.centroid[0], 2), round(self.centroid[1], 2)],
            "polygon": self.polygon,
            "overlaps_brahmasthan": self.overlaps_brahmasthan_core,
            "occupies_exact_center": self.occupies_exact_center,
        }


@dataclass
class DoorEntity:
    """Represents a door element for Dwara Sthana and Entrance analysis."""
    id: str
    name: str
    door_type: str
    polygon: List[List[float]]
    centroid: Tuple[float, float]
    bounds: BoundingBox
    sector: str = SECTOR_CENTER
    cardinal_direction: str = SECTOR_EAST
    is_main_entrance: bool = False
    designated_subsector: Optional[str] = None


@dataclass
class VastuRule:
    """Strongly typed rule definition compatible with both legacy and new specifications."""
    rule_id: str
    category: str
    name: str
    weight: int = 25
    severity: str = "HIGH"
    center_formula: Optional[Dict[str, str]] = None
    condition: str = ""
    dhruva_condition: str = ""
    combinations: List[Dict[str, Any]] = field(default_factory=list)
    positive_zones: List[Dict[str, Any]] = field(default_factory=list)
    room_guidance: List[Dict[str, Any]] = field(default_factory=list)
    target_room_types: List[str] = field(default_factory=list)
    preferred_sectors: List[str] = field(default_factory=list)
    tolerated_sectors: List[str] = field(default_factory=list)
    forbidden_sectors: List[str] = field(default_factory=list)
    good_description: str = ""
    defect_description: str = ""
    remedy: str = ""
    notes: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VastuRule:
        rule_id = data.get("rule_id", "")
        category = data.get("category", "")
        # Assign standard default weights (25 each for the 4 core rules)
        weight = data.get("weight") or 25
        return cls(
            rule_id=rule_id,
            category=category,
            name=data.get("name", rule_id),
            weight=weight,
            severity=data.get("severity", "HIGH"),
            center_formula=data.get("center_formula"),
            condition=data.get("condition", ""),
            dhruva_condition=data.get("dhruva_condition", ""),
            combinations=data.get("combinations", []),
            positive_zones=data.get("positive_zones", []),
            room_guidance=data.get("room_guidance", []),
            target_room_types=[t.lower() for t in data.get("target_room_types", [])],
            preferred_sectors=data.get("preferred_sectors", []),
            tolerated_sectors=data.get("tolerated_sectors", []),
            forbidden_sectors=data.get("forbidden_sectors", []),
            good_description=data.get("good_description", ""),
            defect_description=data.get("defect_description", ""),
            remedy=data.get("remedy", ""),
            notes=data.get("notes", []),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "category": self.category,
            "name": self.name,
            "weight": self.weight,
            "severity": self.severity,
            "condition": self.condition,
            "notes": self.notes,
        }


@dataclass
class EvaluationContext:
    """Pre-processed spatial context passed to rule evaluators."""
    master_json: Dict[str, Any]
    overall_bounds: BoundingBox
    total_area_sqft: float
    orientation: str
    exact_center: Tuple[float, float]
    numerical_tolerance: float
    rooms: List[RoomEntity]
    room_dict: Dict[str, RoomEntity]
    doors: List[DoorEntity]
    walls: List[SpatialObject]
    columns: List[SpatialObject]
    staircases: List[SpatialObject]
    all_spatial_objects: List[SpatialObject]


@dataclass
class EvaluationResult:
    """Output produced by evaluating a single rule."""
    earned_weight: int
    good_aspects: List[Dict[str, Any]] = field(default_factory=list)
    defects: List[Dict[str, Any]] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


# ==============================================================================
# 3. Geometry and Spatial Grid Services
# ==============================================================================

class GeometryService:
    """Pure geometric calculation utility."""

    @staticmethod
    def _is_valid_point(pt: Any) -> bool:
        return (
            isinstance(pt, (list, tuple))
            and len(pt) == 2
            and isinstance(pt[0], (int, float))
            and isinstance(pt[1], (int, float))
            and not isinstance(pt[0], bool)
            and not isinstance(pt[1], bool)
            and math.isfinite(pt[0])
            and math.isfinite(pt[1])
        )

    @classmethod
    def calculate_centroid(cls, polygon: Sequence[Sequence[float]]) -> Tuple[float, float]:
        valid_pts = [p for p in polygon if cls._is_valid_point(p)]
        if not valid_pts:
            return (0.0, 0.0)
        n = len(valid_pts)
        cx = sum(p[0] for p in valid_pts) / n
        cy = sum(p[1] for p in valid_pts) / n
        return (cx, cy)

    @classmethod
    def calculate_bounds(cls, polygon: Sequence[Sequence[float]]) -> BoundingBox:
        valid_pts = [p for p in polygon if cls._is_valid_point(p)]
        if not valid_pts:
            return BoundingBox(0.0, 0.0, 0.0, 0.0)
        xs = [p[0] for p in valid_pts]
        ys = [p[1] for p in valid_pts]
        return BoundingBox(min(xs), max(xs), min(ys), max(ys))

    @classmethod
    def calculate_collective_bounds(cls, polygons: Sequence[Sequence[Sequence[float]]]) -> BoundingBox:
        all_points = [pt for poly in polygons if poly for pt in poly if cls._is_valid_point(pt)]
        if not all_points:
            return BoundingBox(0.0, 0.0, 0.0, 0.0)
        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]
        return BoundingBox(min(xs), max(xs), min(ys), max(ys))

    @staticmethod
    def point_to_segment_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        """Calculates Euclidean distance from point (px, py) to line segment (x1, y1)-(x2, y2)."""
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px - x1, py - y1)
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy
        return math.hypot(px - closest_x, py - closest_y)

    @classmethod
    def is_point_in_polygon(cls, px: float, py: float, polygon: Sequence[Sequence[float]], tolerance: float = 0.05) -> bool:
        """
        Ray-casting point-in-polygon check with boundary edge distance tolerance.
        Returns True if (px, py) is strictly inside or within tolerance of any edge.
        """
        if not polygon or len(polygon) < 3:
            return False

        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        # Quick rejection via bounding box
        if px < min_x - tolerance or px > max_x + tolerance or py < min_y - tolerance or py > max_y + tolerance:
            return False

        inside = False
        n = len(polygon)
        for i in range(n):
            j = (i + 1) % n
            x1, y1 = polygon[i][0], polygon[i][1]
            x2, y2 = polygon[j][0], polygon[j][1]

            # Check edge distance
            if cls.point_to_segment_distance(px, py, x1, y1, x2, y2) <= tolerance:
                return True

            # Standard ray casting
            if ((y1 > py) != (y2 > py)) and (px < (x2 - x1) * (py - y1) / (y2 - y1) + x1):
                inside = not inside

        return inside


class PadavinyasaGrid:
    """
    Implements the classical 3x3 Padavinyasa mandala partition and cardinal door mapping.
    Maps coordinates to compass sectors accounting for orientation.
    """

    BASE_GRID: Dict[Tuple[int, int], str] = {
        (0, 0): SECTOR_SOUTH_WEST,
        (1, 0): SECTOR_SOUTH,
        (2, 0): SECTOR_SOUTH_EAST,
        (0, 1): SECTOR_WEST,
        (1, 1): SECTOR_CENTER,
        (2, 1): SECTOR_EAST,
        (0, 2): SECTOR_NORTH_WEST,
        (1, 2): SECTOR_NORTH,
        (2, 2): SECTOR_NORTH_EAST,
    }

    def __init__(self, bounds: BoundingBox, orientation_str: str = "north"):
        self.bounds = bounds
        self.orientation_str = orientation_str.strip().lower()
        self.offset_deg = ORIENTATION_OFFSETS.get(self.orientation_str, 0)
        self.exact_center = bounds.center

    @property
    def brahmasthan_bounds(self) -> BoundingBox:
        """Central 1/9th core zone of the site."""
        b_min_x = self.bounds.min_x + (self.bounds.width / 3.0)
        b_max_x = self.bounds.min_x + (2.0 * self.bounds.width / 3.0)
        b_min_y = self.bounds.min_y + (self.bounds.height / 3.0)
        b_max_y = self.bounds.min_y + (2.0 * self.bounds.height / 3.0)
        return BoundingBox(b_min_x, b_max_x, b_min_y, b_max_y)

    def determine_sector(self, cx: float, cy: float) -> str:
        """Determines Padavinyasa 3x3 sector for coordinate [cx, cy]."""
        if self.bounds.width <= 0 or self.bounds.height <= 0:
            return SECTOR_CENTER

        rx = (cx - self.bounds.min_x) / self.bounds.width
        ry = (cy - self.bounds.min_y) / self.bounds.height

        col = 0 if rx < (1.0 / 3.0) else (1 if rx < (2.0 / 3.0) else 2)
        row = 0 if ry < (1.0 / 3.0) else (1 if ry < (2.0 / 3.0) else 2)

        base_sector = self.BASE_GRID.get((col, row), SECTOR_CENTER)
        if base_sector == SECTOR_CENTER or self.offset_deg == 0:
            return base_sector

        try:
            idx = CLOCKWISE_SECTORS.index(base_sector)
            steps = round(self.offset_deg / 45.0)
            new_idx = (idx + steps) % 8
            return CLOCKWISE_SECTORS[new_idx]
        except (ValueError, IndexError):
            return base_sector

    def determine_cardinal_direction(self, cx: float, cy: float) -> str:
        """
        Determines the closest cardinal direction (EAST, SOUTH, WEST, NORTH)
        for an element (such as a door) taking boundary edges and orientation into account.
        """
        # Vector from center to element
        vx = cx - self.exact_center[0]
        vy = cy - self.exact_center[1]

        # Rotate vector to canonical North-up orientation
        rad = math.radians(-self.offset_deg)
        rot_x = vx * math.cos(rad) - vy * math.sin(rad)
        rot_y = vx * math.sin(rad) + vy * math.cos(rad)

        angle = math.degrees(math.atan2(rot_y, rot_x))  # -180 to 180

        # Boundary edge proximity check
        dist_east = abs(self.bounds.max_x - cx)
        dist_west = abs(cx - self.bounds.min_x)
        dist_north = abs(self.bounds.max_y - cy)
        dist_south = abs(cy - self.bounds.min_y)
        min_dist = min(dist_east, dist_west, dist_north, dist_south)

        # If clearly on an outer boundary wall (within 15% margin of perimeter)
        perimeter_margin = min(self.bounds.width, self.bounds.height) * 0.15
        if min_dist <= perimeter_margin:
            # Re-orient boundary according to orientation offset
            edges = [
                (dist_east, SECTOR_EAST),
                (dist_north, SECTOR_NORTH),
                (dist_west, SECTOR_WEST),
                (dist_south, SECTOR_SOUTH),
            ]
            edges.sort(key=lambda item: item[0])
            closest_edge_sector = edges[0][1]

            if self.offset_deg == 0:
                return closest_edge_sector
            try:
                cardinal_order = [SECTOR_NORTH, SECTOR_EAST, SECTOR_SOUTH, SECTOR_WEST]
                c_idx = cardinal_order.index(closest_edge_sector)
                steps = round(self.offset_deg / 90.0)
                return cardinal_order[(c_idx + steps) % 4]
            except ValueError:
                pass

        # Angle-based quadrant classification
        if -45.0 <= angle <= 45.0:
            return SECTOR_EAST
        if 45.0 < angle < 135.0:
            return SECTOR_NORTH
        if -135.0 < angle < -45.0:
            return SECTOR_SOUTH
        return SECTOR_WEST


# ==============================================================================
# 4. Strategy Pattern: Rule Evaluators
# ==============================================================================

class BaseRuleEvaluator(ABC):
    """Abstract strategy interface for Vastu rule evaluators."""

    @abstractmethod
    def evaluate(self, rule: VastuRule, context: EvaluationContext) -> EvaluationResult:
        pass


class BrahmasthanExactCenterEvaluator(BaseRuleEvaluator):
    """
    Rule 1: Brahmasthan Exact Center-Point Check (vsai.brahmasthan.exact_center).
    Pass condition: No represented spatial object (room, wall, door, column, pillar, staircase)
    occupies or intersects the exact plan center point (W / 2, H / 2).
    Checks ONLY the exact center point, NOT the entire 1/9th center cell.
    """

    def evaluate(self, rule: VastuRule, context: EvaluationContext) -> EvaluationResult:
        cx, cy = context.exact_center
        tol = context.numerical_tolerance

        obstructing_objects: List[SpatialObject] = []

        for obj in context.all_spatial_objects:
            # 1. Polygon collision check
            if obj.polygon and len(obj.polygon) >= 3:
                if GeometryService.is_point_in_polygon(cx, cy, obj.polygon, tolerance=tol):
                    obstructing_objects.append(obj)
                    continue

            # 2. Line segment check (walls / doors without full polygons)
            if obj.line_segment:
                (x1, y1), (x2, y2) = obj.line_segment
                if GeometryService.point_to_segment_distance(cx, cy, x1, y1, x2, y2) <= tol:
                    obstructing_objects.append(obj)
                    continue

            # 3. Bounding box check for point-like objects (e.g. columns without polygon)
            if obj.bounds and obj.bounds.contains_point(cx, cy, tolerance=tol):
                obstructing_objects.append(obj)

        if not obstructing_objects:
            # Passed: Exact center point is completely unobstructed
            return EvaluationResult(
                earned_weight=rule.weight,
                good_aspects=[{
                    "rule_id": rule.rule_id,
                    "title": "Brahmasthan Exact Center Point is Open & Clear",
                    "room_id": None,
                    "room_name": "Brahmasthan Center",
                    "sector": SECTOR_CENTER,
                    "sector_display": SECTOR_DISPLAY_NAMES[SECTOR_CENTER],
                    "polygon": None,
                    "description": (
                        f"The exact Brahmasthan center point ({cx:.2f}, {cy:.2f}) is completely "
                        f"clear and unobstructed by any walls, columns, pillars, stairs, or rooms "
                        f"(tested with {tol}m numerical tolerance)."
                    ),
                    "points_earned": rule.weight,
                }],
                details={
                    "status": "PASS",
                    "exact_center": [round(cx, 2), round(cy, 2)],
                    "tolerance": tol,
                    "obstructing_objects_count": 0,
                    "obstructing_objects": [],
                },
            )

        # Failed: One or more objects occupy or intersect the exact center point
        names = ", ".join(f"{o.object_type.title()} '{o.name}'" for o in obstructing_objects)
        defect_msg = (
            f"The exact Brahmasthan center point ({cx:.2f}, {cy:.2f}) is occupied or intersected "
            f"by {len(obstructing_objects)} represented spatial object(s): {names}."
        )
        remedy = (
            "Ensure the exact plan center point (Brahmasthan core) is left completely free and open. "
            "Relocate load-bearing walls, structural columns, pillars, staircases, and enclosed partitions "
            "away from the center coordinate."
        )

        return EvaluationResult(
            earned_weight=0,
            defects=[{
                "rule_id": rule.rule_id,
                "title": "Brahmasthan Exact Center Point Obstructed",
                "severity": "CRITICAL",
                "room_id": None,
                "room_name": names,
                "sector": SECTOR_CENTER,
                "sector_display": SECTOR_DISPLAY_NAMES[SECTOR_CENTER],
                "polygon": None,
                "description": defect_msg,
                "remedy": remedy,
                "points_deducted": rule.weight,
            }],
            details={
                "status": "FAIL",
                "exact_center": [round(cx, 2), round(cy, 2)],
                "tolerance": tol,
                "obstructing_objects_count": len(obstructing_objects),
                "obstructing_objects": [{"id": o.id, "name": o.name, "type": o.object_type} for o in obstructing_objects],
            },
        )


class DwaraSthanaCombinationEvaluator(BaseRuleEvaluator):
    """
    Rule 2: Dwara Sthana Door-Combination Analysis (vsai.dwara_sthana.combination).
    Analyzes the combination of cardinal door directions (EAST, SOUTH, WEST, NORTH).
    Dhruva condition: Classifies combination as Dhruva ONLY when there are no doors anywhere in the house.
    """

    def evaluate(self, rule: VastuRule, context: EvaluationContext) -> EvaluationResult:
        doors = context.doors

        # Dhruva condition: Classify combination ONLY when there are NO doors anywhere in the house
        if not doors:
            house_type, classification, traditional_result = DWARA_STHANA_COMBINATIONS[frozenset()]
            return EvaluationResult(
                earned_weight=rule.weight,
                good_aspects=[{
                    "rule_id": rule.rule_id,
                    "title": f"Dwara Sthana: {house_type} Combination ({classification})",
                    "room_id": None,
                    "room_name": "Doors",
                    "sector": SECTOR_CENTER,
                    "sector_display": "Global House Doors",
                    "polygon": None,
                    "description": (
                        f"House has no door representations detected. Traditional Dwara Sthana classification: "
                        f"{house_type} ({classification}) — {traditional_result}."
                    ),
                    "points_earned": rule.weight,
                }],
                details={
                    "house_type": house_type,
                    "classification": classification,
                    "directions": [],
                    "traditional_result": traditional_result,
                    "doors_count": 0,
                },
            )

        # Doors exist: Determine distinct cardinal directions present
        present_directions: Set[str] = set()
        door_details: List[Dict[str, Any]] = []

        for d in doors:
            cardinal = d.cardinal_direction
            if cardinal in CARDINAL_DIRECTIONS:
                present_directions.add(cardinal)
            door_details.append({
                "id": d.id,
                "name": d.name,
                "cardinal_direction": cardinal,
                "sector": d.sector,
                "is_main_entrance": d.is_main_entrance,
            })

        combo_key = frozenset(present_directions)
        combo_info = DWARA_STHANA_COMBINATIONS.get(combo_key)

        if not combo_info:
            # Fallback if directions set somehow misses key
            house_type = "Unknown"
            classification = "GOOD"
            traditional_result = "Mixed directional doors"
        else:
            house_type, classification, traditional_result = combo_info

        directions_list = sorted(list(present_directions))
        directions_str = ", ".join(directions_list) if directions_list else "None"

        if classification in ("VERY_GOOD", "GOOD"):
            earned = rule.weight if classification == "VERY_GOOD" else round(rule.weight * 0.85)
            return EvaluationResult(
                earned_weight=earned,
                good_aspects=[{
                    "rule_id": rule.rule_id,
                    "title": f"Dwara Sthana: {house_type} Combination ({classification})",
                    "room_id": None,
                    "room_name": f"Doors ({directions_str})",
                    "sector": directions_list[0] if directions_list else SECTOR_CENTER,
                    "sector_display": f"Cardinal Facings: {directions_str}",
                    "polygon": None,
                    "description": (
                        f"Dwara Sthana classification: {house_type} ({classification}). "
                        f"Traditional attribution: {traditional_result}. "
                        f"Doors present in {len(directions_list)} direction(s): {directions_str}."
                    ),
                    "points_earned": earned,
                }],
                details={
                    "house_type": house_type,
                    "classification": classification,
                    "directions": directions_list,
                    "traditional_result": traditional_result,
                    "doors_count": len(doors),
                    "door_details": door_details,
                },
            )

        # Classification is BAD: Generate Defect
        defect_msg = (
            f"Dwara Sthana door configuration is classified as {house_type} ({classification}). "
            f"Traditional attribution: {traditional_result}. "
            f"Current doors face {directions_str}."
        )
        remedy = (
            "Rebalance door placements to favor auspicious combinations such as Dhanya (East), "
            "Jaya (South), Kanta (East & West), Manorama (South & West), Sumukha (East, South & West), "
            "or Vijaya (All 4 cardinal directions)."
        )

        return EvaluationResult(
            earned_weight=round(rule.weight * 0.2),
            defects=[{
                "rule_id": rule.rule_id,
                "title": f"Dwara Sthana Defect: {house_type} Combination ({classification})",
                "severity": "HIGH",
                "room_id": None,
                "room_name": f"Doors ({directions_str})",
                "sector": directions_list[0] if directions_list else SECTOR_CENTER,
                "sector_display": f"Cardinal Facings: {directions_str}",
                "polygon": None,
                "description": defect_msg,
                "remedy": remedy,
                "points_deducted": rule.weight,
            }],
            details={
                "house_type": house_type,
                "classification": classification,
                "directions": directions_list,
                "traditional_result": traditional_result,
                "doors_count": len(doors),
                "door_details": door_details,
            },
        )


class MainEntranceDirectionEvaluator(BaseRuleEvaluator):
    """
    Rule 3: Main Entrance Direction Analysis (vsai.main_entrance.direction).
    Identifies the primary entrance and verifies placement in positive suitable zones:
    NORTH, NORTH_EAST, EAST, SOUTH_OF_SOUTH_EAST, WEST_OF_NORTH_WEST.
    Does not guess boundaries for South of Southeast or West of Northwest unless explicitly designated.
    """

    def evaluate(self, rule: VastuRule, context: EvaluationContext) -> EvaluationResult:
        doors = context.doors

        # 1. Identify Main Entrance
        main_door = next((d for d in doors if d.is_main_entrance), None)

        if not main_door and doors:
            # Fallback candidate identification
            main_door = doors[0]

        if not main_door:
            # No doors present in floor plan
            return EvaluationResult(
                earned_weight=round(rule.weight * 0.6),
                good_aspects=[{
                    "rule_id": rule.rule_id,
                    "title": "Main Entrance: Pending Designation",
                    "room_id": None,
                    "room_name": "Main Entrance",
                    "sector": SECTOR_NORTH,
                    "sector_display": "Entrance Sector Pending",
                    "polygon": None,
                    "description": (
                        "No doors are represented in the floor plan to evaluate main entrance direction. "
                        "Stage 1 analysis requires explicit door representations."
                    ),
                    "points_earned": round(rule.weight * 0.6),
                }],
                details={"identified": False, "reason": "No door representations present."},
            )

        # Check positive zones
        sector = main_door.sector
        subsector = main_door.designated_subsector

        is_positive = (
            sector in (SECTOR_NORTH, SECTOR_NORTH_EAST, SECTOR_EAST)
            or subsector in (VastuSector.SOUTH_OF_SOUTH_EAST.value, VastuSector.WEST_OF_NORTH_WEST.value)
        )

        sector_name = SECTOR_DISPLAY_NAMES.get(subsector or sector, sector)

        if is_positive:
            return EvaluationResult(
                earned_weight=rule.weight,
                good_aspects=[{
                    "rule_id": rule.rule_id,
                    "title": f"Main Entrance in Auspicious Direction ({sector_name})",
                    "room_id": main_door.id,
                    "room_name": main_door.name,
                    "sector": sector,
                    "sector_display": sector_name,
                    "polygon": main_door.polygon,
                    "description": (
                        f"The main entrance '{main_door.name}' is auspiciously positioned in the "
                        f"{sector_name} sector (POSITIVE_SUITABLE), optimizing cosmic energy flow."
                    ),
                    "points_earned": rule.weight,
                }],
                details={
                    "identified": True,
                    "door_id": main_door.id,
                    "door_name": main_door.name,
                    "sector": sector,
                    "classification": "POSITIVE_SUITABLE",
                },
            )

        # Inauspicious entrance zone
        defect_msg = (
            f"The main entrance '{main_door.name}' is positioned in {sector_name}. "
            "Vastu Shastra guidelines designate North, North-East, East, South of South-East, "
            "or West of North-West as positive suitable entrance zones."
        )
        remedy = (
            "Relocate the primary entrance door towards North, North-East (Ishanya), or East (Indra) "
            "to enhance auspicious ingress of prana and prosperity."
        )

        return EvaluationResult(
            earned_weight=round(rule.weight * 0.2),
            defects=[{
                "rule_id": rule.rule_id,
                "title": f"Main Entrance in Inauspicious Direction ({sector_name})",
                "severity": "HIGH",
                "room_id": main_door.id,
                "room_name": main_door.name,
                "sector": sector,
                "sector_display": sector_name,
                "polygon": main_door.polygon,
                "description": defect_msg,
                "remedy": remedy,
                "points_deducted": rule.weight,
            }],
            details={
                "identified": True,
                "door_id": main_door.id,
                "door_name": main_door.name,
                "sector": sector,
                "classification": "UNSUITABLE",
            },
        )


class RoomDirectionEvaluator(BaseRuleEvaluator):
    """
    Rule 4: Room Direction Analysis (vsai.room.direction).
    Evaluates individual room placement against directional preferences, alternatives,
    and avoid_as_stated constraints. Does not convert alternatives into forbidden directions.
    """

    # Room type aliases matching standard floor plan identifiers
    ROOM_TYPE_MAPPINGS: Dict[str, str] = {
        "living": "living_room",
        "living_room": "living_room",
        "hall": "living_room",
        "drawing_room": "living_room",
        "sitting": "living_room",
        "family_room": "living_room",
        "kitchen": "kitchen",
        "cooking": "kitchen",
        "pantry": "kitchen",
        "master_bedroom": "master_bedroom",
        "master_bed": "master_bedroom",
        "primary_bedroom": "master_bedroom",
        "childrens_bedroom": "childrens_bedroom",
        "children_bedroom": "childrens_bedroom",
        "kids_bedroom": "childrens_bedroom",
        "kids_room": "childrens_bedroom",
        "child_bed": "childrens_bedroom",
        "parents_bedroom": "parents_grandparents_bedroom",
        "grandparents_bedroom": "parents_grandparents_bedroom",
        "parents_grandparents_bedroom": "parents_grandparents_bedroom",
        "elders_bedroom": "parents_grandparents_bedroom",
        "guest_bedroom": "guest_bedroom",
        "guest_room": "guest_bedroom",
        "guest_bed": "guest_bedroom",
        "bedroom": "general_bedroom",
        "bed": "general_bedroom",
        "pooja": "pooja_room",
        "pooja_room": "pooja_room",
        "prayer": "pooja_room",
        "shrine": "pooja_room",
        "altar": "pooja_room",
        "mandir": "pooja_room",
        "bath_area": "bath_area",
        "bathing": "bath_area",
        "shower": "bath_area",
        "bath": "bath_area",
        "toilet": "toilet_washroom",
        "toilet_washroom": "toilet_washroom",
        "washroom": "toilet_washroom",
        "wc": "toilet_washroom",
        "powder_room": "toilet_washroom",
        "bathroom": "toilet_washroom",
        "restroom": "toilet_washroom",
        "store": "store_room",
        "store_room": "store_room",
        "storage": "store_room",
        "station_room": "store_room",
        "staircase": "staircase",
        "stairs": "staircase",
        "stair": "staircase",
    }

    # Consolidated guidance from finalized JSON specification
    STANDARDIZED_GUIDANCE: Dict[str, Dict[str, Any]] = {
        "living_room": {
            "name": "Living Room",
            "preferred": [SECTOR_NORTH_WEST, SECTOR_NORTH, SECTOR_NORTH_EAST, SECTOR_EAST],
            "alternatives": [SECTOR_WEST, SECTOR_SOUTH_EAST],
            "avoid": [SECTOR_SOUTH_WEST],
            "remedy": "Align living seating towards North or East during conversations.",
        },
        "kitchen": {
            "name": "Kitchen",
            "preferred": [SECTOR_SOUTH_EAST],
            "alternatives": [SECTOR_NORTH_WEST],
            "avoid": [SECTOR_NORTH_EAST, SECTOR_SOUTH_WEST, SECTOR_CENTER],
            "remedy": "Relocate cooking stove towards South-East (Agneya) or North-West (Vayavya).",
        },
        "master_bedroom": {
            "name": "Master Bedroom",
            "preferred": [SECTOR_SOUTH_WEST],
            "alternatives": [SECTOR_SOUTH, SECTOR_WEST],
            "avoid": [SECTOR_NORTH_EAST, SECTOR_CENTER, SECTOR_NORTH],
            "remedy": "Ensure master bedroom is grounded in South-West (Nairutya) for authority and stability.",
        },
        "childrens_bedroom": {
            "name": "Children's Bedroom",
            "preferred": [SECTOR_SOUTH, SECTOR_WEST],
            "alternatives": [SECTOR_SOUTH_EAST, SECTOR_NORTH_WEST],
            "avoid": [SECTOR_SOUTH_WEST, SECTOR_CENTER],
            "remedy": "Place study desk facing East or North inside the bedroom.",
        },
        "parents_grandparents_bedroom": {
            "name": "Parents/Grandparents Bedroom",
            "preferred": [SECTOR_NORTH, SECTOR_EAST],
            "alternatives": [SECTOR_NORTH_EAST, SECTOR_NORTH_WEST],
            "avoid": [SECTOR_SOUTH_WEST],
            "remedy": "Situate elders' sleeping area in serene North or East quadrants.",
        },
        "guest_bedroom": {
            "name": "Guest Bedroom",
            "preferred": [SECTOR_NORTH_WEST],
            "alternatives": [SECTOR_WEST, SECTOR_NORTH],
            "avoid": [SECTOR_SOUTH_WEST],
            "remedy": "Position guest accommodation in North-West (Vayu zone) for harmonious stays.",
        },
        "general_bedroom": {
            "name": "Bedroom",
            "preferred": [SECTOR_SOUTH_WEST, SECTOR_SOUTH, SECTOR_WEST, SECTOR_NORTH_WEST],
            "alternatives": [SECTOR_NORTH],
            "avoid": [SECTOR_NORTH_EAST, SECTOR_CENTER],
            "remedy": "Orient sleeping head direction towards South or East.",
        },
        "pooja_room": {
            "name": "Pooja Room",
            "preferred": [SECTOR_NORTH_EAST],
            "alternatives": [SECTOR_NORTH, SECTOR_EAST],
            "avoid": [SECTOR_SOUTH_WEST, SECTOR_SOUTH, SECTOR_SOUTH_EAST, SECTOR_CENTER],
            "remedy": "Relocate prayer altar to North-East (Ishanya) or align deities facing East/North.",
        },
        "bath_area": {
            "name": "Bathing Area",
            "preferred": [SECTOR_NORTH, SECTOR_EAST],
            "alternatives": [SECTOR_NORTH_WEST],
            "avoid": [SECTOR_SOUTH_WEST, SECTOR_CENTER],
            "remedy": "Ensure drainage drains naturally towards North or North-East.",
        },
        "toilet_washroom": {
            "name": "Toilet / Washroom",
            "preferred": [SECTOR_WEST, SECTOR_NORTH_WEST],
            "alternatives": [SECTOR_SOUTH],
            "avoid": [SECTOR_NORTH_EAST, SECTOR_CENTER, VastuSector.CENTER_BRAHMASTHAN.value],
            "remedy": (
                "Relocate toilet fixtures away from North-East and central Brahmasthan to West or North-West. "
                "Never share common walls between a toilet and a Pooja room."
            ),
        },
        "store_room": {
            "name": "Store Room",
            "preferred": [SECTOR_SOUTH, SECTOR_WEST],
            "alternatives": [SECTOR_SOUTH_WEST],
            "avoid": [SECTOR_NORTH_EAST, SECTOR_CENTER],
            "remedy": "Heavy storage should be positioned in heavier South or West sectors.",
        },
        "staircase": {
            "name": "Staircase",
            "preferred": [SECTOR_SOUTH, SECTOR_WEST],
            "alternatives": [SECTOR_SOUTH_WEST, SECTOR_NORTH_WEST],
            "avoid": [SECTOR_NORTH_EAST, SECTOR_CENTER, VastuSector.CENTER_BRAHMASTHAN.value],
            "remedy": "Build staircases clockwise and keep them out of the sacred central Brahmasthan.",
        },
    }

    def evaluate(self, rule: VastuRule, context: EvaluationContext) -> EvaluationResult:
        rooms = context.rooms
        if not rooms:
            return EvaluationResult(earned_weight=rule.weight)

        good_aspects: List[Dict[str, Any]] = []
        defects: List[Dict[str, Any]] = []

        total_points_available = rule.weight
        points_per_room = total_points_available / len(rooms)
        earned_sum = 0.0

        for r in rooms:
            mapped_key = self.ROOM_TYPE_MAPPINGS.get(r.room_type, "living_room")
            guidance = self.STANDARDIZED_GUIDANCE.get(mapped_key, self.STANDARDIZED_GUIDANCE["living_room"])

            sector = r.sector
            sector_name = r.sector_display
            preferred = guidance["preferred"]
            alternatives = guidance.get("alternatives", [])
            avoid = guidance.get("avoid", [])

            if sector in preferred:
                # Primary preferred sector -> 100% compliant
                earned_sum += points_per_room
                good_aspects.append({
                    "rule_id": rule.rule_id,
                    "title": f"{r.name} - Auspicious Sector ({sector_name})",
                    "room_id": r.id,
                    "room_name": r.name,
                    "sector": sector,
                    "sector_display": sector_name,
                    "polygon": r.polygon,
                    "description": (
                        f"{r.name} is ideally positioned in {sector_name}, "
                        f"which is the primary auspicious sector for {guidance['name']} in Vastu Shastra."
                    ),
                    "points_earned": round(points_per_room, 1),
                })
            elif sector in alternatives:
                # Alternative listed sector -> 85% compliant (per rule note: alternatives are not defects)
                earned_sum += points_per_room * 0.85
                good_aspects.append({
                    "rule_id": rule.rule_id,
                    "title": f"{r.name} - Acceptable Alternative ({sector_name})",
                    "room_id": r.id,
                    "room_name": r.name,
                    "sector": sector,
                    "sector_display": sector_name,
                    "polygon": r.polygon,
                    "description": (
                        f"{r.name} is located in {sector_name}, which is listed as an acceptable "
                        f"secondary alternative for {guidance['name']}."
                    ),
                    "points_earned": round(points_per_room * 0.85, 1),
                })
            elif sector in avoid:
                # Explicitly avoided zone -> Critical defect
                defect_msg = (
                    f"{r.name} is located in {sector_name}. Vastu Shastra explicitly states that "
                    f"{guidance['name']} must AVOID {', '.join(avoid)}."
                )
                defects.append({
                    "rule_id": rule.rule_id,
                    "title": f"{r.name} in Prohibited Zone ({sector_name})",
                    "severity": "CRITICAL",
                    "room_id": r.id,
                    "room_name": r.name,
                    "sector": sector,
                    "sector_display": sector_name,
                    "polygon": r.polygon,
                    "description": defect_msg,
                    "remedy": guidance["remedy"],
                    "points_deducted": round(points_per_room, 1),
                })
            else:
                # Unlisted direction -> Secondary non-critical defect
                earned_sum += points_per_room * 0.4
                defect_msg = (
                    f"{r.name} is located in {sector_name}. Recommended preferred directions are "
                    f"{', '.join(preferred)}."
                )
                defects.append({
                    "rule_id": rule.rule_id,
                    "title": f"{r.name} Sub-Optimal Placement ({sector_name})",
                    "severity": "MEDIUM",
                    "room_id": r.id,
                    "room_name": r.name,
                    "sector": sector,
                    "sector_display": sector_name,
                    "polygon": r.polygon,
                    "description": defect_msg,
                    "remedy": guidance["remedy"],
                    "points_deducted": round(points_per_room * 0.6, 1),
                })

        return EvaluationResult(
            earned_weight=round(earned_sum),
            good_aspects=good_aspects,
            defects=defects,
            details={"evaluated_rooms_count": len(rooms)},
        )


class StructuralSpanEvaluator(BaseRuleEvaluator):
    """Fallback evaluator for structural spans when requested."""

    def evaluate(self, rule: VastuRule, context: EvaluationContext) -> EvaluationResult:
        col_count = len(context.columns)
        if context.total_area_sqft > 1500 and 0 < col_count <= 4:
            return EvaluationResult(
                earned_weight=0,
                defects=[{
                    "rule_id": rule.rule_id,
                    "title": "Inadequate Structural Column Grid",
                    "severity": "HIGH",
                    "room_id": None,
                    "room_name": "Columns / Span",
                    "sector": VastuSector.GLOBAL.value,
                    "sector_display": "Global Structure",
                    "polygon": None,
                    "description": f"Area is {context.total_area_sqft:.0f} sqft with only {col_count} columns.",
                    "remedy": "Add structural columns to maintain safe spans under 16-20 ft.",
                    "points_deducted": rule.weight,
                }],
            )
        return EvaluationResult(earned_weight=rule.weight)


class EvaluatorRegistry:
    """Registry mapping rule categories and rule IDs to their dedicated evaluators."""

    def __init__(self) -> None:
        self.exact_center_evaluator = BrahmasthanExactCenterEvaluator()
        self.door_combo_evaluator = DwaraSthanaCombinationEvaluator()
        self.main_entrance_evaluator = MainEntranceDirectionEvaluator()
        self.room_evaluator = RoomDirectionEvaluator()
        self.structural_evaluator = StructuralSpanEvaluator()

    def get_evaluator(self, rule: VastuRule) -> BaseRuleEvaluator:
        rid = rule.rule_id.lower()
        cat = rule.category.lower()

        if "exact_center" in rid or cat == "brahmasthan":
            return self.exact_center_evaluator
        if "dwara" in rid or cat == "door_combination":
            return self.door_combo_evaluator
        if "entrance" in rid or cat == "main_entrance":
            return self.main_entrance_evaluator
        if "room" in rid or cat == "room_placement":
            return self.room_evaluator
        if cat == "structural":
            return self.structural_evaluator

        # Default fallback
        return self.room_evaluator


# ==============================================================================
# 5. Rule Repository with Caching
# ==============================================================================

class RuleRepository:
    """Loads and caches Vastu rules from finalized JSON specification."""

    PRIMARY_RULES_PATH = Path(__file__).parent / "VSAI_Rectifier_Finalized_Vastu_Rules.json"
    FALLBACK_RULES_PATH = Path(__file__).parent / "vastu_rules.json"

    @classmethod
    @lru_cache(maxsize=1)
    def load_cached_raw_rules(cls) -> List[Dict[str, Any]]:
        target_path = cls.PRIMARY_RULES_PATH if cls.PRIMARY_RULES_PATH.exists() else cls.FALLBACK_RULES_PATH
        if not target_path.exists():
            logger.warning(f"Vastu rules file not found at {target_path}, returning empty rules")
            return []
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("rules", [])
        except Exception as ex:
            logger.error(f"Failed to load vastu rules from {target_path}: {ex}")
            return []

    @classmethod
    def load_rules(cls) -> List[VastuRule]:
        raw = cls.load_cached_raw_rules()
        return [VastuRule.from_dict(r) for r in raw]


# ==============================================================================
# 6. Scoring and Grade Calculator
# ==============================================================================

class VastuScorer:
    """Calculates final score (0-100) and letter grades."""

    @staticmethod
    def calculate_score(earned_weight: int, total_weight: int) -> int:
        if total_weight <= 0:
            return 80
        score = int(round((earned_weight / total_weight) * 100))
        return max(0, min(100, score))

    @staticmethod
    def get_grade(score: int) -> Tuple[str, str]:
        if score >= 90:
            return "A+", "Excellent Vastu Harmony: Space aligns with universal cosmic principles."
        if score >= 75:
            return "A", "Good Compliance: Solid Vastu layout with minimal non-critical adjustments."
        if score >= 55:
            return "B", "Moderate Vastu Harmony: Key elemental or directional rectifications needed."
        if score >= 35:
            return "C", "Significant Vastu Defects: Critical zones (e.g. Brahmasthan or Toilet) need relocation."
        return "D", "Major Non-Compliance: Fundamental spatial redesign recommended."


# ==============================================================================
# 7. Orchestrator Engine
# ==============================================================================

class VastuEngine:
    """Main engine coordinating spatial pre-processing, rule execution, and report formulation."""

    def __init__(self, registry: Optional[EvaluatorRegistry] = None) -> None:
        self.registry = registry or EvaluatorRegistry()

    def create_context(
        self,
        master_json: Dict[str, Any],
        tolerance: float = DEFAULT_CENTER_TOLERANCE,
    ) -> EvaluationContext:
        floor_plan = master_json.get("floor_plan", {})
        land_info = master_json.get("land_info", {})
        # Resolve orientation from land_info or spatial_metadata (e.g. north_direction: "top")
        raw_orient = (
            land_info.get("orientation")
            or floor_plan.get("orientation")
            or master_json.get("orientation")
            or master_json.get("north_direction")
        )
        if not raw_orient and isinstance(floor_plan.get("spatial_metadata"), dict):
            nd = str(floor_plan["spatial_metadata"].get("north_direction", "")).lower().strip()
            if nd in ("top", "up"):
                raw_orient = "North"
            elif nd in ("right",):
                raw_orient = "East"
            elif nd in ("bottom", "down"):
                raw_orient = "South"
            elif nd in ("left",):
                raw_orient = "West"
        orientation = raw_orient or "North"

        raw_rooms = floor_plan.get("rooms", [])
        raw_doors = floor_plan.get("doors", [])
        raw_walls = floor_plan.get("walls", [])
        raw_structural = floor_plan.get("structural_elements", [])

        # 1. Collective Bounding Box
        all_polys = [r.get("polygon", []) for r in raw_rooms if isinstance(r.get("polygon"), list)]
        boundary_pts = land_info.get("boundary_points")
        if boundary_pts and isinstance(boundary_pts, list):
            all_polys.append(boundary_pts)
        footprint_poly = master_json.get("buildable_footprint", {}).get("polygon")
        if footprint_poly and isinstance(footprint_poly, list):
            all_polys.append(footprint_poly)
        site_bounds = GeometryService.calculate_collective_bounds(all_polys)

        total_area = land_info.get("area_sqft") or round(site_bounds.area)
        grid = PadavinyasaGrid(site_bounds, orientation)
        exact_center = grid.exact_center
        brahmasthan_bounds = grid.brahmasthan_bounds

        # 2. Extract Room Entities
        room_entities: List[RoomEntity] = []
        for r in raw_rooms:
            rid = str(r.get("id"))
            rname = r.get("name") or r.get("type") or rid
            rtype = str(r.get("type") or rname).strip().lower()
            poly = r.get("polygon", [])
            if not poly or len(poly) < 3:
                continue

            cx, cy = GeometryService.calculate_centroid(poly)
            rbounds = GeometryService.calculate_bounds(poly)
            sector = grid.determine_sector(cx, cy)
            overlaps_core = rbounds.overlaps(brahmasthan_bounds)
            occupies_center = GeometryService.is_point_in_polygon(exact_center[0], exact_center[1], poly, tolerance=tolerance)

            room_entities.append(RoomEntity(
                id=rid,
                name=rname,
                room_type=rtype,
                polygon=poly,
                centroid=(cx, cy),
                bounds=rbounds,
                sector=sector,
                overlaps_brahmasthan_core=overlaps_core,
                occupies_exact_center=occupies_center,
            ))

        # 3. Extract Door Entities
        door_entities: List[DoorEntity] = []
        for idx, d in enumerate(raw_doors):
            did = str(d.get("id") or f"door-{idx+1}")
            dname = d.get("name") or f"Door {idx+1}"
            dtype = str(d.get("type") or "standard").strip().lower()

            poly = d.get("polygon", [])
            if poly and len(poly) >= 2:
                dcx, dcy = GeometryService.calculate_centroid(poly)
                dbounds = GeometryService.calculate_bounds(poly)
            elif d.get("position") and isinstance(d["position"], (list, tuple)) and len(d["position"]) == 2:
                dcx, dcy = float(d["position"][0]), float(d["position"][1])
                dbounds = BoundingBox(dcx, dcx, dcy, dcy)
            else:
                dcx, dcy = exact_center
                dbounds = BoundingBox(dcx, dcx, dcy, dcy)

            # Check if designated main entrance
            is_main = bool(
                d.get("is_main_entrance")
                or d.get("is_main")
                or dtype in ("main", "main_entrance", "entrance", "entry")
                or "main" in did.lower()
            )

            # Explicit direction override if supplied (support shorthand "S", "E", "W", "N")
            cardinal = d.get("cardinal_direction") or d.get("direction")
            if isinstance(cardinal, str):
                c_clean = cardinal.upper().strip()
                shorthand_map = {
                    "S": SECTOR_SOUTH,
                    "E": SECTOR_EAST,
                    "W": SECTOR_WEST,
                    "N": SECTOR_NORTH,
                    "SOUTH": SECTOR_SOUTH,
                    "EAST": SECTOR_EAST,
                    "WEST": SECTOR_WEST,
                    "NORTH": SECTOR_NORTH,
                }
                cardinal = shorthand_map.get(c_clean, c_clean)
            if not cardinal or cardinal not in CARDINAL_DIRECTIONS:
                cardinal = grid.determine_cardinal_direction(dcx, dcy)

            sector = grid.determine_sector(dcx, dcy)

            door_entities.append(DoorEntity(
                id=did,
                name=dname,
                door_type=dtype,
                polygon=poly,
                centroid=(dcx, dcy),
                bounds=dbounds,
                sector=sector,
                cardinal_direction=cardinal,
                is_main_entrance=is_main,
                designated_subsector=d.get("subsector"),
            ))

        # 4. Extract All Spatial Objects for Exact-Center Intersection
        all_spatial: List[SpatialObject] = []

        # Rooms
        for rent in room_entities:
            # Exclude open courtyards from being flagged as blocking objects
            if rent.room_type not in ("courtyard", "atrium", "open_to_sky"):
                all_spatial.append(SpatialObject(
                    id=rent.id,
                    name=rent.name,
                    object_type="room",
                    polygon=rent.polygon,
                    bounds=rent.bounds,
                ))

        # Walls
        for idx, w in enumerate(raw_walls):
            wid = str(w.get("id") or f"wall-{idx+1}")
            wname = w.get("name") or f"Wall {idx+1}"
            wpoly = w.get("polygon", [])
            wseg = None
            if not wpoly and w.get("start") and w.get("end"):
                wseg = (
                    (float(w["start"][0]), float(w["start"][1])),
                    (float(w["end"][0]), float(w["end"][1])),
                )
            all_spatial.append(SpatialObject(
                id=wid,
                name=wname,
                object_type="wall",
                polygon=wpoly,
                line_segment=wseg,
                bounds=GeometryService.calculate_bounds(wpoly) if wpoly else None,
            ))

        # Structural Elements (Columns, Pillars, Stairs)
        for idx, s in enumerate(raw_structural):
            sid = str(s.get("id") or f"struct-{idx+1}")
            stype = str(s.get("type") or "column").strip().lower()
            sname = s.get("name") or f"{stype.title()} {idx+1}"
            spoly = s.get("polygon", [])
            all_spatial.append(SpatialObject(
                id=sid,
                name=sname,
                object_type=stype,
                polygon=spoly,
                bounds=GeometryService.calculate_bounds(spoly) if spoly else None,
            ))

        # Doors
        for dent in door_entities:
            all_spatial.append(SpatialObject(
                id=dent.id,
                name=dent.name,
                object_type="door",
                polygon=dent.polygon,
                bounds=dent.bounds,
            ))

        return EvaluationContext(
            master_json=master_json,
            overall_bounds=site_bounds,
            total_area_sqft=float(total_area),
            orientation=orientation,
            exact_center=exact_center,
            numerical_tolerance=tolerance,
            rooms=room_entities,
            room_dict={r.id: r for r in room_entities},
            doors=door_entities,
            walls=[o for o in all_spatial if o.object_type == "wall"],
            columns=[o for o in all_spatial if o.object_type in ("column", "pillar")],
            staircases=[o for o in all_spatial if o.object_type in ("staircase", "stairs")],
            all_spatial_objects=all_spatial,
        )

    def evaluate(
        self,
        master_json: Dict[str, Any],
        rules: Optional[Sequence[VastuRule | Dict[str, Any]]] = None,
        tolerance: float = DEFAULT_CENTER_TOLERANCE,
    ) -> Dict[str, Any]:
        """Runs full VSAI Rectifier Stage 1 Vastu compliance analysis."""
        parsed_rules: List[VastuRule] = []
        if rules is None:
            parsed_rules = RuleRepository.load_rules()
        else:
            for r in rules:
                if isinstance(r, VastuRule):
                    parsed_rules.append(r)
                elif isinstance(r, dict):
                    parsed_rules.append(VastuRule.from_dict(r))

        context = self.create_context(master_json, tolerance=tolerance)

        # Early exit if no valid room geometries exist
        if not context.rooms:
            return {
                "score": 0,
                "grade": "N/A",
                "grade_description": "No floor plan rooms detected to evaluate Vastu compliance.",
                "good_aspects": [],
                "defects": [{
                    "rule_id": "vsai.general.empty",
                    "title": "Missing Room Geometries",
                    "severity": "CRITICAL",
                    "room_id": None,
                    "room_name": "General",
                    "sector": VastuSector.GLOBAL.value,
                    "description": "Floor plan contains no rooms to evaluate spatial compliance.",
                    "remedy": "Upload a Master JSON containing valid room polygons.",
                    "points_deducted": 0,
                }],
                "total_rules_evaluated": 0,
                "passed_rules_count": 0,
                "failed_rules_count": 1,
                "room_sectors": {},
                "brahmasthan": {
                    "status": "UNKNOWN",
                    "exact_center": [round(context.exact_center[0], 2), round(context.exact_center[1], 2)],
                    "tolerance": tolerance,
                    "obstructing_objects": [],
                    "obstructing_rooms": [],
                },
                "dwara_sthana": {
                    "house_type": "Dhruva",
                    "classification": "VERY_GOOD",
                    "directions": [],
                },
                "bounding_box": context.overall_bounds.to_dict(context.total_area_sqft),
            }

        total_weight = 0
        earned_weight = 0
        good_aspects: List[Dict[str, Any]] = []
        defects: List[Dict[str, Any]] = []
        rule_details: Dict[str, Any] = {}

        for rule in parsed_rules:
            total_weight += rule.weight
            evaluator = self.registry.get_evaluator(rule)
            res = evaluator.evaluate(rule, context)
            earned_weight += res.earned_weight
            good_aspects.extend(res.good_aspects)
            defects.extend(res.defects)
            rule_details[rule.rule_id] = res.details

        score = VastuScorer.calculate_score(earned_weight, total_weight)
        grade, grade_desc = VastuScorer.get_grade(score)

        # Extract specific rule findings
        center_details = rule_details.get("vsai.brahmasthan.exact_center", {})
        door_details = rule_details.get("vsai.dwara_sthana.combination", {})
        entrance_details = rule_details.get("vsai.main_entrance.direction", {})

        obstructing_objs = center_details.get("obstructing_objects", [])
        obstructing_room_names = [o["name"] for o in obstructing_objs if o.get("type") == "room"]

        return {
            "score": score,
            "grade": grade,
            "grade_description": grade_desc,
            "good_aspects": good_aspects,
            "defects": defects,
            "total_rules_evaluated": len(parsed_rules),
            "passed_rules_count": len(good_aspects),
            "failed_rules_count": len(defects),
            "room_sectors": {r.id: r.to_sector_dict() for r in context.rooms},
            "brahmasthan": {
                "status": "CLEAR" if center_details.get("status") == "PASS" else "OBSTRUCTED",
                "exact_center": [round(context.exact_center[0], 2), round(context.exact_center[1], 2)],
                "tolerance": tolerance,
                "obstructing_objects": [o.get("name", "") for o in obstructing_objs],
                "obstructing_rooms": obstructing_room_names,
            },
            "dwara_sthana": {
                "house_type": door_details.get("house_type", "Dhruva"),
                "classification": door_details.get("classification", "VERY_GOOD"),
                "directions": door_details.get("directions", []),
                "traditional_result": door_details.get("traditional_result", ""),
            },
            "main_entrance": {
                "identified": entrance_details.get("identified", False),
                "door_id": entrance_details.get("door_id"),
                "sector": entrance_details.get("sector"),
                "classification": entrance_details.get("classification"),
            },
            "bounding_box": context.overall_bounds.to_dict(context.total_area_sqft),
            "rule_details": rule_details,
        }


# ==============================================================================
# 8. Public Backward-Compatible API Surface
# ==============================================================================

_engine_instance = VastuEngine()


def load_vastu_rules() -> List[Dict[str, Any]]:
    """Loads rule definitions from VSAI_Rectifier_Finalized_Vastu_Rules.json (cached)."""
    return RuleRepository.load_cached_raw_rules()


def calculate_polygon_centroid(polygon: List[List[float]]) -> Tuple[float, float]:
    """Calculates polygon centroid [cx, cy]."""
    return GeometryService.calculate_centroid(polygon)


def calculate_polygon_bounds(polygon: List[List[float]]) -> Tuple[float, float, float, float]:
    """Returns (min_x, max_x, min_y, max_y) for a polygon."""
    b = GeometryService.calculate_bounds(polygon)
    return (b.min_x, b.max_x, b.min_y, b.max_y)


def determine_sector_3x3(
    cx: float,
    cy: float,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    orientation_str: str = "north",
) -> str:
    """Divides bounding box into 3x3 Padavinyasa grid and maps coordinate to sector."""
    bounds = BoundingBox(min_x, max_x, min_y, max_y)
    grid = PadavinyasaGrid(bounds, orientation_str)
    return grid.determine_sector(cx, cy)


def evaluate_vastu_shastra(
    master_json: Dict[str, Any],
    rules: Optional[List[Dict[str, Any]]] = None,
    tolerance: float = DEFAULT_CENTER_TOLERANCE,
) -> Dict[str, Any]:
    """Evaluates Master JSON floor plan against finalized Vastu rules."""
    return _engine_instance.evaluate(master_json, rules, tolerance=tolerance)
