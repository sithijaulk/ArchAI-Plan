"""
Multi-Candidate Blueprint Generator.
Explores deterministic architectural variations within verified buildable boundaries:
1. Building Footprint Alternatives (conformal_envelope, compact_box, narrow_spine, l_shaped_notch)
2. Room Arrangement / Zoning Strategies (front_active, rear_active, public_private_split, central_core)
3. Slicing Axis & Ordering Variations (x_axis_first, y_axis_first, alternating)
4. Staircase core corner placement variations (south_west, south_east, north_west, north_east)
All generations operate on the same verified legal survey coordinates (P0 canonical).
"""
import copy
from typing import Any, Dict, List, Optional, Tuple
from shapely.geometry import Polygon, MultiPolygon, box, LineString

from ..schemas import (
    FloorPlanDefinition,
    RoomPolygon,
    WallSegment,
    Point2D,
    ClientRequirementsInput,
)
from .generator import derive_wall_segments, partition_polygon_proportional


def generate_footprint_variants(
    buildable_poly: Polygon,
    max_variants: int = 4
) -> List[Tuple[str, Polygon]]:
    """
    Generates valid, non-self-intersecting building footprint sub-envelopes
    strictly contained inside the legal buildable polygon.
    Returns list of (variant_name, shapely_polygon).
    """
    if not buildable_poly or not buildable_poly.is_valid or buildable_poly.area <= 0:
        return []

    variants: List[Tuple[str, Polygon]] = [
        ("conformal_envelope", buildable_poly)
    ]

    min_x, min_y, max_x, max_y = buildable_poly.bounds
    w = max_x - min_x
    h = max_y - min_y
    area = buildable_poly.area

    # Variant 2: Compact Centered Envelope (slight inset for higher compactness / courtyard margin)
    if area > 80.0 and w > 8.0 and h > 8.0:
        inset_dx = w * 0.08
        inset_dy = h * 0.08
        compact_box = box(min_x + inset_dx, min_y + inset_dy, max_x - inset_dx, max_y - inset_dy)
        compact_geom = buildable_poly.intersection(compact_box)
        if isinstance(compact_geom, MultiPolygon):
            compact_geom = max(compact_geom.geoms, key=lambda p: p.area)
        if compact_geom.is_valid and compact_geom.area >= area * 0.65:
            variants.append(("compact_envelope", compact_geom))

    # Variant 3: L-Shaped / Stepped Footprint (introducing a courtyard or setback wing)
    if area > 100.0 and w > 10.0 and h > 10.0:
        notch_w = w * 0.32
        notch_h = h * 0.32
        notch_box = box(max_x - notch_w, max_y - notch_h, max_x + 5.0, max_y + 5.0)
        l_geom = buildable_poly.difference(notch_box)
        if isinstance(l_geom, MultiPolygon):
            l_geom = max(l_geom.geoms, key=lambda p: p.area)
        if l_geom.is_valid and l_geom.area >= area * 0.68:
            variants.append(("l_shaped_wing", l_geom))

    # Variant 4: Frontage-Focused Rectilinear Envelope
    if area > 90.0 and w > 8.0 and h > 8.0:
        front_box = box(min_x - 5.0, min_y - 5.0, max_x + 5.0, min_y + h * 0.78)
        front_geom = buildable_poly.intersection(front_box)
        if isinstance(front_geom, MultiPolygon):
            front_geom = max(front_geom.geoms, key=lambda p: p.area)
        if front_geom.is_valid and front_geom.area >= area * 0.65:
            variants.append(("frontage_compact", front_geom))

    return variants[:max_variants]


def place_staircase_core_variant(
    footprint_poly: Polygon,
    corner_choice: str = "south_west",
    stair_w: float = 3.0,
    stair_h: float = 2.5
) -> Optional[Polygon]:
    """
    Positions staircase core at a specified corner of the footprint envelope.
    Ensures identical geometry across all storeys.
    """
    min_x, min_y, max_x, max_y = footprint_poly.bounds
    w = max_x - min_x
    h = max_y - min_y
    sw = min(stair_w, w * 0.35)
    sh = min(stair_h, h * 0.35)

    if corner_choice == "south_west":
        box_geom = box(min_x, min_y, min_x + sw, min_y + sh)
    elif corner_choice == "south_east":
        box_geom = box(max_x - sw, min_y, max_x, min_y + sh)
    elif corner_choice == "north_west":
        box_geom = box(min_x, max_y - sh, min_x + sw, max_y)
    elif corner_choice == "north_east":
        box_geom = box(max_x - sw, max_y - sh, max_x, max_y)
    else:
        box_geom = box(min_x, min_y, min_x + sw, min_y + sh)

    stair_intersection = footprint_poly.intersection(box_geom)
    if not stair_intersection.is_empty and stair_intersection.area >= 4.0:
        if isinstance(stair_intersection, MultiPolygon):
            stair_intersection = max(stair_intersection.geoms, key=lambda p: p.area)
        return stair_intersection
    return None


def partition_polygon_variant(
    poly: Polygon,
    target_areas: List[float],
    orientation_mode: str = "auto"
) -> List[Polygon]:
    """
    Slices polygon with configurable major axis bias:
      - 'auto': default major bounding box axis
      - 'x_first': slice vertically (along X)
      - 'y_first': slice horizontally (along Y)
    """
    if not poly or poly.is_empty or len(target_areas) == 0:
        return []
    if len(target_areas) == 1:
        return [poly]

    min_x, min_y, max_x, max_y = poly.bounds
    w = max_x - min_x
    h = max_y - min_y

    if orientation_mode == "x_first":
        slice_along_x = True
    elif orientation_mode == "y_first":
        slice_along_x = False
    else:
        slice_along_x = (w >= h)

    total_target = sum(target_areas) or 1.0
    n = len(target_areas)

    cum_fractions = []
    acc = 0.0
    for a in target_areas:
        acc += a
        cum_fractions.append(acc / total_target)

    if n <= 3:
        slices: List[Polygon] = []
        current_poly = poly
        prev_bound = min_x if slice_along_x else min_y
        for i in range(n):
            if i == n - 1:
                sub_poly = current_poly
            else:
                frac = cum_fractions[i]
                if slice_along_x:
                    curr_bound = min_x + frac * w
                    cutter_box = box(prev_bound, min_y - 10.0, curr_bound, max_y + 10.0)
                else:
                    curr_bound = min_y + frac * h
                    cutter_box = box(min_x - 10.0, prev_bound, max_x + 10.0, curr_bound)

                sub_poly = current_poly.intersection(cutter_box)
                current_poly = current_poly.difference(cutter_box)
                prev_bound = curr_bound

            if isinstance(sub_poly, MultiPolygon):
                sub_poly = max(sub_poly.geoms, key=lambda p: p.area)
            slices.append(sub_poly)
        return slices

    # N >= 4: block partition
    n_top = n // 2
    top_targets = target_areas[:n_top]
    bottom_targets = target_areas[n_top:]

    top_target_sum = sum(top_targets)
    bottom_target_sum = sum(bottom_targets)
    row_split_frac = bottom_target_sum / total_target

    if slice_along_x:
        split_line = min_x + row_split_frac * w
        box_left = box(min_x - 5.0, min_y - 5.0, split_line, max_y + 5.0)
        box_right = box(split_line, min_y - 5.0, max_x + 5.0, max_y + 5.0)

        poly_left = poly.intersection(box_left)
        poly_right = poly.intersection(box_right)

        if isinstance(poly_left, MultiPolygon):
            poly_left = max(poly_left.geoms, key=lambda p: p.area)
        if isinstance(poly_right, MultiPolygon):
            poly_right = max(poly_right.geoms, key=lambda p: p.area)

        slices_left = partition_polygon_proportional(poly_left, bottom_targets)
        slices_right = partition_polygon_proportional(poly_right, top_targets)
        return slices_left + slices_right
    else:
        split_line = min_y + row_split_frac * h
        box_bot = box(min_x - 5.0, min_y - 5.0, max_x + 5.0, split_line)
        box_top = box(min_x - 5.0, split_line, max_x + 5.0, max_y + 5.0)

        poly_bot = poly.intersection(box_bot)
        poly_top = poly.intersection(box_top)

        if isinstance(poly_bot, MultiPolygon):
            poly_bot = max(poly_bot.geoms, key=lambda p: p.area)
        if isinstance(poly_top, MultiPolygon):
            poly_top = max(poly_top.geoms, key=lambda p: p.area)

        slices_bot = partition_polygon_proportional(poly_bot, bottom_targets)
        slices_top = partition_polygon_proportional(poly_top, top_targets)
        return slices_bot + slices_top


def generate_candidate_floors(
    footprint_poly: Polygon,
    floor_allocations: List[Dict[str, Any]],
    strategy_name: str = "default_proportional",
    stair_corner: str = "south_west",
    slice_mode: str = "auto",
    reverse_room_order: bool = False
) -> List[FloorPlanDefinition]:
    """
    Generates blueprint floor plans for a specific candidate configuration.
    """
    if not footprint_poly or not footprint_poly.is_valid or footprint_poly.area <= 0:
        return []

    floor_definitions: List[FloorPlanDefinition] = []
    has_multi_storey = len(floor_allocations) > 1

    # Fixed stair geometry across all floors for this candidate
    stair_geom: Optional[Polygon] = None
    if has_multi_storey:
        stair_geom = place_staircase_core_variant(footprint_poly, corner_choice=stair_corner)

    for fl in floor_allocations:
        floor_idx = fl["floor_index"]
        floor_id = f"F{floor_idx}"
        floor_name = fl["name"]
        elevation = floor_idx * 3.0
        rooms_data = list(fl.get("rooms", []))

        if not rooms_data:
            floor_definitions.append(
                FloorPlanDefinition(
                    floor_id=floor_id,
                    floor_index=floor_idx,
                    name=floor_name,
                    elevation=elevation,
                    floor_height=3.0,
                    available_area=round(footprint_poly.area, 2),
                    target_allocated_area=0.0,
                    rooms=[],
                    walls=[]
                )
            )
            continue

        generated_rooms: List[RoomPolygon] = []
        all_walls: List[WallSegment] = []

        stair_room = next((r for r in rooms_data if r.get("is_stair")), None)
        other_rooms = [r for r in rooms_data if not r.get("is_stair")]

        if reverse_room_order:
            other_rooms = list(reversed(other_rooms))

        remaining_area_poly = footprint_poly
        if stair_room and stair_geom:
            coords = [Point2D(x=round(c[0], 3), y=round(c[1], 3)) for c in list(stair_geom.exterior.coords)[:-1]]
            c_pt = stair_geom.centroid
            generated_rooms.append(
                RoomPolygon(
                    room_id=f"{floor_id}_STAIR",
                    name="Staircase Core",
                    type="staircase",
                    floor_id=floor_id,
                    area=round(float(stair_geom.area), 2),
                    target_area=round(stair_room["target_area"], 2),
                    polygon=coords,
                    center=Point2D(x=round(c_pt.x, 3), y=round(c_pt.y, 3)),
                    is_structural_stair=True
                )
            )
            diff = footprint_poly.difference(stair_geom)
            if isinstance(diff, MultiPolygon):
                diff = max(diff.geoms, key=lambda p: p.area)
            remaining_area_poly = diff

        if other_rooms:
            target_areas = [r["target_area"] for r in other_rooms]
            partitioned_geoms = partition_polygon_variant(remaining_area_poly, target_areas, orientation_mode=slice_mode)

            for idx, r_data in enumerate(other_rooms):
                poly_geom = partitioned_geoms[idx] if idx < len(partitioned_geoms) else None
                if poly_geom and not poly_geom.is_empty and poly_geom.area > 0.5:
                    coords = [Point2D(x=round(c[0], 3), y=round(c[1], 3)) for c in list(poly_geom.exterior.coords)[:-1]]
                    c_pt = poly_geom.centroid
                    r_id = f"{floor_id}_{r_data['type'][:3].upper()}_{idx+1}"
                    r_minx, r_miny, r_maxx, r_maxy = poly_geom.bounds
                    r_w = round(r_maxx - r_minx, 2)
                    r_l = round(r_maxy - r_miny, 2)
                    generated_rooms.append(
                        RoomPolygon(
                            room_id=r_id,
                            name=r_data["name"],
                            type=r_data["type"],
                            floor_id=floor_id,
                            area=round(float(poly_geom.area), 2),
                            target_area=round(r_data["target_area"], 2),
                            polygon=coords,
                            center=Point2D(x=round(c_pt.x, 3), y=round(c_pt.y, 3)),
                            width_m=min(r_w, r_l),
                            length_m=max(r_w, r_l),
                            is_structural_stair=False,
                            required=r_data.get("required"),
                            req_id=r_data.get("req_id")
                        )
                    )

        walls = derive_wall_segments(floor_id, footprint_poly, generated_rooms)
        all_walls.extend(walls)

        fl_def = FloorPlanDefinition(
            floor_id=floor_id,
            floor_index=floor_idx,
            name=floor_name,
            elevation=elevation,
            floor_height=3.0,
            available_area=round(footprint_poly.area, 2),
            target_allocated_area=round(sum(r.area for r in generated_rooms), 2),
            rooms=generated_rooms,
            walls=all_walls
        )
        floor_definitions.append(fl_def)

    # Synthesize explicit doors and windows for each floor
    from .openings_synthesizer import enrich_floor_definitions_with_openings
    enrich_floor_definitions_with_openings(floor_definitions, footprint_poly)

    return floor_definitions

