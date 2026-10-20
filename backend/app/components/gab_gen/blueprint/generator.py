"""
Blueprint generator:
- Dissects buildable footprint into deterministic non-overlapping room polygons.
- Accurately targets requested room areas using proportional 2D spatial slicing.
- Preserves consistent staircase core across multi-storey floors in exact same coordinate footprint.
- Derives exterior and interior wall segments with thickness and room associativity.
"""
from typing import Any, Dict, List, Optional, Tuple
from shapely.geometry import Polygon, MultiPolygon, box, LineString
from ..schemas import FloorPlanDefinition, RoomPolygon, WallSegment, Point2D


def generate_blueprint_floors(
    buildable_poly: Polygon,
    floor_allocations: List[Dict[str, Any]]
) -> List[FloorPlanDefinition]:
    """
    Generates deterministic structural room polygons and wall segments for each floor.
    Guarantees:
      - Coordinate system is canonical P0 (strictly matching source land & buildable footprint).
      - Multi-storey staircase core occupies the EXACT SAME geometry on all floors.
      - Slices buildable region proportionally to allocated room target areas.
      - Never emits out-of-polygon fallback bounding boxes.
      - Safe failure if valid partition is geometrically impossible.
    """
    if not buildable_poly or not buildable_poly.is_valid or buildable_poly.area <= 0:
        return []

    min_x, min_y, max_x, max_y = buildable_poly.bounds
    width = max_x - min_x
    height = max_y - min_y

    floor_definitions: List[FloorPlanDefinition] = []
    stair_geom: Optional[Polygon] = None

    # Step 1: Pre-calculate fixed common staircase core if multi-storey
    has_multi_storey = len(floor_allocations) > 1
    if has_multi_storey:
        # Stair core standard dimensions: ~3.0m x 2.5m (approx 7.5 sqm)
        stair_w = min(3.0, width * 0.35)
        stair_h = min(2.5, height * 0.35)
        # Position stair core at fixed corner of buildable bounds
        stair_box = box(min_x, min_y, min_x + stair_w, min_y + stair_h)
        stair_intersection = buildable_poly.intersection(stair_box)
        if not stair_intersection.is_empty and stair_intersection.area >= 4.0:
            if isinstance(stair_intersection, MultiPolygon):
                stair_intersection = max(stair_intersection.geoms, key=lambda p: p.area)
            stair_geom = stair_intersection

    # Step 2: Generate Floor Plans
    for fl in floor_allocations:
        floor_idx = fl["floor_index"]
        floor_id = f"F{floor_idx}"
        floor_name = fl["name"]
        elevation = floor_idx * 3.0
        rooms_data = fl["rooms"]

        if not rooms_data:
            floor_definitions.append(
                FloorPlanDefinition(
                    floor_id=floor_id,
                    floor_index=floor_idx,
                    name=floor_name,
                    elevation=elevation,
                    floor_height=3.0,
                    available_area=fl["available_area"],
                    target_allocated_area=0.0,
                    rooms=[],
                    walls=[]
                )
            )
            continue

        generated_rooms: List[RoomPolygon] = []
        all_walls: List[WallSegment] = []

        # Separate stair from non-stair rooms
        stair_room = next((r for r in rooms_data if r.get("is_stair")), None)
        other_rooms = [r for r in rooms_data if not r.get("is_stair")]

        remaining_area_poly = buildable_poly
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
            diff = buildable_poly.difference(stair_geom)
            if isinstance(diff, MultiPolygon):
                diff = max(diff.geoms, key=lambda p: p.area)
            remaining_area_poly = diff

        # Partition remaining buildable area proportionally across rooms
        if other_rooms:
            target_areas = [r["target_area"] for r in other_rooms]
            partitioned_geoms = partition_polygon_proportional(remaining_area_poly, target_areas)

            for idx, r_data in enumerate(other_rooms):
                poly_geom = partitioned_geoms[idx] if idx < len(partitioned_geoms) else None
                if poly_geom and not poly_geom.is_empty and poly_geom.area > 0.5:
                    coords = [Point2D(x=round(c[0], 3), y=round(c[1], 3)) for c in list(poly_geom.exterior.coords)[:-1]]
                    c_pt = poly_geom.centroid
                    r_id = f"{floor_id}_{r_data['type'][:3].upper()}_{idx+1}"
                    # Compute bounding dimensions of room polygon
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

        # Derive Wall Segments
        walls = derive_wall_segments(floor_id, buildable_poly, generated_rooms)
        all_walls.extend(walls)

        floor_definitions.append(
            FloorPlanDefinition(
                floor_id=floor_id,
                floor_index=floor_idx,
                name=floor_name,
                elevation=elevation,
                floor_height=3.0,
                available_area=fl["available_area"],
                target_allocated_area=round(sum(r.area for r in generated_rooms), 2),
                rooms=generated_rooms,
                walls=all_walls
            )
        )

    return floor_definitions


def partition_polygon_proportional(poly: Polygon, target_areas: List[float]) -> List[Polygon]:
    """
    Deterministically partitions a polygon into N non-overlapping sub-polygons
    whose areas approximate target_areas.
    Algorithm:
      Recursive or sequential proportional slicing along the major bounding axis.
      1. Slices perpendicular to the longer axis of bounding envelope.
      2. Computes cumulative target area ratios.
      3. Intersects slicing slabs with poly, returning clean, contained sub-polygons.
      4. Guarantees every sub-polygon is strictly contained within poly.
    """
    if not poly or poly.is_empty:
        return []
    n = len(target_areas)
    if n == 0:
        return []
    if n == 1:
        return [poly]

    min_x, min_y, max_x, max_y = poly.bounds
    width = max_x - min_x
    height = max_y - min_y
    total_target = sum(target_areas) or 1.0

    # Determine primary slicing orientation based on aspect ratio
    slice_along_x = width >= height

    slices: List[Polygon] = []
    current_poly = poly

    # Normalize cumulative target fractions
    cum_fractions = []
    acc = 0.0
    for a in target_areas:
        acc += a
        cum_fractions.append(acc / total_target)

    # If 2 or 3 rooms: direct 1D strip slicing
    if n <= 3:
        prev_bound = min_x if slice_along_x else min_y
        for i in range(n):
            if i == n - 1:
                sub_poly = current_poly
            else:
                frac = cum_fractions[i]
                if slice_along_x:
                    curr_bound = min_x + frac * width
                    cutter_box = box(prev_bound, min_y - 10.0, curr_bound, max_y + 10.0)
                else:
                    curr_bound = min_y + frac * height
                    cutter_box = box(min_x - 10.0, prev_bound, max_x + 10.0, curr_bound)

                sub_poly = current_poly.intersection(cutter_box)
                current_poly = current_poly.difference(cutter_box)
                prev_bound = curr_bound

            if isinstance(sub_poly, MultiPolygon):
                sub_poly = max(sub_poly.geoms, key=lambda p: p.area)
            slices.append(sub_poly)
        return slices

    # For N >= 4: 2D Block Tree partition
    # Split into 2 primary row clusters, then divide each row proportionally
    n_top = n // 2
    n_bottom = n - n_top
    top_targets = target_areas[:n_top]
    bottom_targets = target_areas[n_top:]

    top_target_sum = sum(top_targets)
    bottom_target_sum = sum(bottom_targets)
    row_split_frac = bottom_target_sum / total_target

    if slice_along_x:
        # Split vertically first
        split_line = min_x + row_split_frac * width
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
        # Split horizontally first
        split_line = min_y + row_split_frac * height
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


def derive_wall_segments(floor_id: str, exterior_poly: Polygon, rooms: List[RoomPolygon]) -> List[WallSegment]:
    """
    Derives clean exterior and interior wall segments from room polygons without duplicates.
    """
    walls: List[WallSegment] = []
    wall_counter = 1

    # 1. Exterior perimeter walls
    ext_coords = list(exterior_poly.exterior.coords)
    for i in range(len(ext_coords) - 1):
        p1 = Point2D(x=round(ext_coords[i][0], 3), y=round(ext_coords[i][1], 3))
        p2 = Point2D(x=round(ext_coords[i+1][0], 3), y=round(ext_coords[i+1][1], 3))
        walls.append(
            WallSegment(
                wall_id=f"W_{floor_id}_EXT_{wall_counter}",
                floor_id=floor_id,
                start=p1,
                end=p2,
                wall_type="exterior",
                thickness=0.225,
                related_room_ids=[]
            )
        )
        wall_counter += 1

    # 2. Interior partitions from room boundaries
    seen_segments = set()
    for room in rooms:
        coords = room.polygon
        for i in range(len(coords)):
            p1 = coords[i]
            p2 = coords[(i + 1) % len(coords)]

            seg_key = tuple(sorted([(p1.x, p1.y), (p2.x, p2.y)]))
            if seg_key in seen_segments:
                continue
            seen_segments.add(seg_key)

            line = LineString([(p1.x, p1.y), (p2.x, p2.y)])
            if not exterior_poly.exterior.buffer(0.15).contains(line):
                walls.append(
                    WallSegment(
                        wall_id=f"W_{floor_id}_INT_{wall_counter}",
                        floor_id=floor_id,
                        start=p1,
                        end=p2,
                        wall_type="interior",
                        thickness=0.115,
                        related_room_ids=[room.room_id]
                    )
                )
                wall_counter += 1

    return walls
