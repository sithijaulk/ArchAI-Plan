"""
ESAI Geometry Constraint Evaluator
Computational geometry analysis using Shapely for polygon containment,
footprint collisions, door swings, window access, and circulation connectivity.
"""
import math
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from shapely.geometry import box, LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union
from shapely.affinity import rotate, translate

from ..contracts import (
    DoorDTO,
    DoorOpeningDirection,
    FixedObstructionDTO,
    WindowDTO,
)
from .chromosome import PlacedAssetDTO


class GeometryEvaluationResult(BaseModel):
    is_valid: bool = True
    violations: List[str] = Field(default_factory=list)
    overlap_area_sqm: float = 0.0
    out_of_bounds_area_sqm: float = 0.0
    door_violation_count: int = 0
    window_violation_count: int = 0
    circulation_score: float = 1.0
    free_floor_ratio: float = 1.0


class GeometryConstraintEvaluator:
    """
    Evaluates physical spatial constraints and circulation using Shapely.
    """

    def __init__(
        self,
        room_polygon: Polygon,
        doors: Optional[List[DoorDTO]] = None,
        windows: Optional[List[WindowDTO]] = None,
        fixed_obstructions: Optional[List[FixedObstructionDTO]] = None,
    ):
        self.room_polygon = room_polygon
        self.doors = doors or []
        self.windows = windows or []
        self.fixed_obstructions = fixed_obstructions or []

        # Deduct fixed obstructions from room polygon to get usable floor area
        self.obstruction_polygons: List[Polygon] = []
        for obs in self.fixed_obstructions:
            obs_poly = self._create_obstruction_polygon(obs)
            if obs_poly and not obs_poly.is_empty:
                self.obstruction_polygons.append(obs_poly)

        if self.obstruction_polygons:
            all_obs = unary_union(self.obstruction_polygons)
            self.usable_polygon = self.room_polygon.difference(all_obs)
        else:
            self.usable_polygon = self.room_polygon

        # Build door swing & clearance zones
        self.door_clearance_polygons: List[Polygon] = []
        for d in self.doors:
            dz = self._create_door_clearance_polygon(d)
            if dz and not dz.is_empty:
                self.door_clearance_polygons.append(dz)

        # Build window protected zones
        self.window_clearance_polygons: List[Tuple[WindowDTO, Polygon]] = []
        for w in self.windows:
            wz = self._create_window_clearance_polygon(w)
            if wz and not wz.is_empty:
                self.window_clearance_polygons.append((w, wz))

    def evaluate(self, placed_assets: List[PlacedAssetDTO]) -> GeometryEvaluationResult:
        """
        Executes complete hard-constraint geometric validation on a spatial arrangement.
        """
        violations: List[str] = []
        total_overlap_area = 0.0
        total_oob_area = 0.0
        door_violations = 0
        window_violations = 0

        num_assets = len(placed_assets)
        footprints: List[Polygon] = []

        # 1. Room Boundary & Obstacle Check for each asset
        for asset in placed_assets:
            fp: Polygon = asset.footprint_polygon
            if fp is None or fp.is_empty:
                continue
            footprints.append(fp)

            # Check room containment
            if not self.usable_polygon.contains(fp):
                # Calculate portion outside room
                outside = fp.difference(self.usable_polygon)
                oob_area = outside.area
                if oob_area > 0.005:  # Tolerance: 50 cm²
                    total_oob_area += oob_area
                    violations.append(
                        f"Asset '{asset.asset_name}' ({asset.instance_id}) extends outside usable room boundaries by {oob_area:.3f}m²."
                    )

            # Check obstruction intersection
            for obs_poly in self.obstruction_polygons:
                if fp.intersects(obs_poly):
                    inter_area = fp.intersection(obs_poly).area
                    if inter_area > 0.005:
                        total_overlap_area += inter_area
                        violations.append(
                            f"Asset '{asset.asset_name}' collides with fixed structural obstruction ({inter_area:.3f}m²)."
                        )

            # Check door clearance intersection
            for door_zone in self.door_clearance_polygons:
                if fp.intersects(door_zone):
                    inter = fp.intersection(door_zone).area
                    if inter > 0.01:
                        door_violations += 1
                        total_overlap_area += inter
                        violations.append(
                            f"Asset '{asset.asset_name}' encroaches into protected door swing/entry clearance zone."
                        )

            # Check window access for tall furniture
            for win_dto, win_zone in self.window_clearance_polygons:
                sill_h = win_dto.sill_height if win_dto.sill_height is not None else 0.90
                # If furniture is taller than window sill and overlaps window access zone
                if asset.dimensions.height > (sill_h + 0.15) and fp.intersects(win_zone):
                    inter = fp.intersection(win_zone).area
                    if inter > 0.02:
                        window_violations += 1
                        violations.append(
                            f"Tall asset '{asset.asset_name}' (height {asset.dimensions.height}m) blocks window aperture (sill {sill_h}m)."
                        )

        # 2. Mutual Furniture Collisions
        for i in range(num_assets):
            fp_i = placed_assets[i].footprint_polygon
            if fp_i is None or fp_i.is_empty:
                continue
            for j in range(i + 1, num_assets):
                fp_j = placed_assets[j].footprint_polygon
                if fp_j is None or fp_j.is_empty:
                    continue

                if fp_i.intersects(fp_j):
                    col_area = fp_i.intersection(fp_j).area
                    if col_area > 0.005:
                        total_overlap_area += col_area
                        violations.append(
                            f"Collision between '{placed_assets[i].asset_name}' and '{placed_assets[j].asset_name}' (overlap: {col_area:.3f}m²)."
                        )

        # 3. Circulation & Free Space Analysis
        total_room_area = self.room_polygon.area
        total_footprint_area = sum(fp.area for fp in footprints)
        free_area = max(0.0, total_room_area - total_footprint_area)
        free_floor_ratio = free_area / total_room_area if total_room_area > 0 else 0.0

        # Circulation connectivity: subtract placed footprints from usable room polygon
        if footprints:
            union_fps = unary_union(footprints)
            free_space_geom = self.usable_polygon.difference(union_fps)
        else:
            free_space_geom = self.usable_polygon

        circulation_score = self._compute_circulation_score(free_space_geom, total_room_area)

        is_valid = (
            len(violations) == 0
            and total_overlap_area < 0.01
            and total_oob_area < 0.01
            and door_violations == 0
        )

        return GeometryEvaluationResult(
            is_valid=is_valid,
            violations=violations,
            overlap_area_sqm=round(total_overlap_area, 4),
            out_of_bounds_area_sqm=round(total_oob_area, 4),
            door_violation_count=door_violations,
            window_violation_count=window_violations,
            circulation_score=round(circulation_score, 3),
            free_floor_ratio=round(free_floor_ratio, 3),
        )

    def _create_obstruction_polygon(self, obs: FixedObstructionDTO) -> Optional[Polygon]:
        """Creates polygon for structural columns, chases, or immovable objects."""
        if obs.polygon and len(obs.polygon) >= 3:
            pts = [(p.x, p.y) for p in obs.polygon]
            return Polygon(pts)
        if obs.position and obs.dimensions:
            w = obs.dimensions.width
            d = obs.dimensions.depth
            hw, hd = w / 2.0, d / 2.0
            return box(obs.position.x - hw, obs.position.y - hd, obs.position.x + hw, obs.position.y + hd)
        return None

    def _create_door_clearance_polygon(self, door: DoorDTO) -> Optional[Polygon]:
        """
        Creates a protected entry clearance zone in front of the door leaf.
        Includes door swing arc/box (leaf width x leaf width) into the room.
        """
        p1 = (door.start.x, door.start.y)
        p2 = (door.end.x, door.end.y)
        leaf_w = door.leaf_width if door.leaf_width is not None else 0.85
        # Door segment line
        line = LineString([p1, p2])
        # Buffer into room by leaf_w + 0.15m margin
        clearance_depth = max(0.80, leaf_w + 0.10)

        # Compute perpendicular vector into room
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length < 1e-4:
            return None

        # Normal unit vectors
        nx1, ny1 = -dy / length, dx / length
        nx2, ny2 = dy / length, -dx / length

        # Test which normal points inside the room polygon
        mid_x = (p1[0] + p2[0]) / 2.0
        mid_y = (p1[1] + p2[1]) / 2.0
        test_pt = Point(mid_x + 0.2 * nx1, mid_y + 0.2 * ny1)

        if self.room_polygon.contains(test_pt):
            nx, ny = nx1, ny1
        else:
            nx, ny = nx2, ny2

        # Create clearance corridor polygon [p1, p2, p2 + norm*depth, p1 + norm*depth]
        c_poly = Polygon([
            p1,
            p2,
            (p2[0] + nx * clearance_depth, p2[1] + ny * clearance_depth),
            (p1[0] + nx * clearance_depth, p1[1] + ny * clearance_depth),
        ])
        return c_poly

    def _create_window_clearance_polygon(self, win: WindowDTO) -> Optional[Polygon]:
        """Creates an access zone in front of the window (depth ~0.45m)."""
        p1 = (win.start.x, win.start.y)
        p2 = (win.end.x, win.end.y)
        depth = win.protected_access_depth if win.protected_access_depth is not None else 0.45

        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length < 1e-4:
            return None

        nx1, ny1 = -dy / length, dx / length
        mid_x = (p1[0] + p2[0]) / 2.0
        mid_y = (p1[1] + p2[1]) / 2.0
        test_pt = Point(mid_x + 0.2 * nx1, mid_y + 0.2 * ny1)

        if self.room_polygon.contains(test_pt):
            nx, ny = nx1, ny1
        else:
            nx, ny = -nx1, -ny1

        return Polygon([
            p1,
            p2,
            (p2[0] + nx * depth, p2[1] + ny * depth),
            (p1[0] + nx * depth, p1[1] + ny * depth),
        ])

    def _compute_circulation_score(self, free_space_geom: Any, total_room_area: float) -> float:
        """
        Evaluates geometric connectivity of free space.
        Penalizes fragmented floor area and disjoint islands.
        """
        if free_space_geom is None or free_space_geom.is_empty:
            return 0.0

        if isinstance(free_space_geom, Polygon):
            main_poly_area = free_space_geom.area
        elif isinstance(free_space_geom, MultiPolygon):
            # Largest contiguous free-space polygon
            main_poly_area = max((p.area for p in free_space_geom.geoms), default=0.0)
        else:
            main_poly_area = getattr(free_space_geom, "area", 0.0)

        # Ratio of largest contiguous corridor to total free space
        total_free_area = getattr(free_space_geom, "area", 1.0)
        continuity_ratio = main_poly_area / total_free_area if total_free_area > 0 else 0.0

        # Normalization between 0.0 and 1.0
        score = min(1.0, max(0.0, continuity_ratio * 0.7 + (total_free_area / total_room_area) * 0.3))
        return score
