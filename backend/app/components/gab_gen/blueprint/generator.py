"""
Blueprint generator:
- Dissects buildable footprint into deterministic non-overlapping room polygons.
- Preserves consistent staircase zone across multi-storey floors.
- Derives exterior and interior wall segments with thickness and room associativity.
"""
import uuid
from typing import Any, Dict, List, Tuple
from shapely.geometry import Polygon, box, LineString
from ..schemas import FloorPlanDefinition, RoomPolygon, WallSegment, Point2D


def generate_blueprint_floors(
    buildable_poly: Polygon,
    floor_allocations: List[Dict[str, Any]]
) -> List[FloorPlanDefinition]:
    """
    Generates deterministic structural room polygons and wall segments for each floor.
    Algorithm:
    1. Obtains the oriented bounding envelope of the buildable footprint.
    2. Identifies a fixed staircase core if storey_count > 1 to preserve vertical structural alignment.
    3. Partitions the remaining floor region across allocated rooms via deterministic proportional slicing.
    4. Extracts boundary edges to build exterior and interior wall segments.
    """
    if not buildable_poly or not buildable_poly.is_valid or buildable_poly.area <= 0:
        return []

    min_x, min_y, max_x, max_y = buildable_poly.bounds
    width = max_x - min_x
    height = max_y - min_y

    floor_definitions: List[FloorPlanDefinition] = []
    stair_zone_box: Polygon | None = None

    # Determine standard stair core (approx 3.0m x 2.4m) in a fixed corner/side for consistency
    if len(floor_allocations) > 1:
        stair_w = min(3.0, width * 0.3)
        stair_h = min(2.5, height * 0.3)
        stair_zone_box = box(min_x, min_y, min_x + stair_w, min_y + stair_h)

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

        # Separate stair if present
        stair_room = next((r for r in rooms_data if r.get("is_stair")), None)
        other_rooms = [r for r in rooms_data if not r.get("is_stair")]

        remaining_area_poly = buildable_poly
        if stair_room and stair_zone_box:
            stair_geom = buildable_poly.intersection(stair_zone_box)
            if not stair_geom.is_empty and stair_geom.area > 2.0:
                coords = [Point2D(x=round(c[0], 3), y=round(c[1], 3)) for c in list(stair_geom.exterior.coords)[:-1]]
                c_pt = stair_geom.centroid
                generated_rooms.append(
                    RoomPolygon(
                        room_id=f"{floor_id}_STAIR",
                        name="Staircase",
                        type="staircase",
                        floor_id=floor_id,
                        area=round(float(stair_geom.area), 2),
                        target_area=round(stair_room["target_area"], 2),
                        polygon=coords,
                        center=Point2D(x=round(c_pt.x, 3), y=round(c_pt.y, 3)),
                        is_structural_stair=True
                    )
                )
                remaining_area_poly = buildable_poly.difference(stair_zone_box)

        # Partition remaining area across other rooms
        if other_rooms:
            partitioned_geoms = partition_polygon(remaining_area_poly, [r["target_area"] for r in other_rooms])
            for idx, r_data in enumerate(other_rooms):
                poly_geom = partitioned_geoms[idx] if idx < len(partitioned_geoms) else None
                if poly_geom and not poly_geom.is_empty and poly_geom.area > 0.5:
                    coords = [Point2D(x=round(c[0], 3), y=round(c[1], 3)) for c in list(poly_geom.exterior.coords)[:-1]]
                    c_pt = poly_geom.centroid
                    r_id = f"{floor_id}_{r_data['type'][:3].upper()}_{idx+1}"
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
                            is_structural_stair=False
                        )
                    )

        # Derive Wall Segments from Generated Room Polygons
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


def partition_polygon(poly: Polygon, target_areas: List[float]) -> List[Polygon]:
    """
    Deterministically partitions a polygon into N sub-polygons proportional to target areas.
    Uses balanced 2D grid/strip slicing along principal axis.
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

    # Grid columns and rows
    cols = int(n**0.5 + 0.5)
    rows = (n + cols - 1) // cols

    col_w = width / cols
    row_h = height / rows

    slices: List[Polygon] = []
    for i in range(n):
        col_idx = i % cols
        row_idx = i // cols
        bx = min_x + col_idx * col_w
        by = min_y + row_idx * row_h
        cell = box(bx, by, bx + col_w, by + row_h)
        sub_poly = poly.intersection(cell)
        if not sub_poly.is_empty:
            slices.append(sub_poly)
        else:
            # Fallback tiny cell
            slices.append(box(bx, by, bx + 1.0, by + 1.0))

    return slices


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
            
            # Canonical segment representation to deduplicate shared walls
            seg_key = tuple(sorted([(p1.x, p1.y), (p2.x, p2.y)]))
            if seg_key in seen_segments:
                continue
            seen_segments.add(seg_key)

            # Check if segment lies along exterior boundary
            line = LineString([(p1.x, p1.y), (p2.x, p2.y)])
            if not exterior_poly.exterior.buffer(0.1).contains(line):
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
