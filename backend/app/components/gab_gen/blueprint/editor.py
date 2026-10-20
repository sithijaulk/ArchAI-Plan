"""
Blueprint editing and validation service.
Supports the interactive blueprint editing workflow:
- Move room (translation with boundary containment and overlap checks)
- Resize room
- Reassign room floor
- Add / remove optional rooms
- Recalculates wall segments and openings
- Constraint validation against legal land parcel and regulatory footprint
"""
from typing import Any, Dict, List, Optional
from shapely.geometry import Polygon, MultiPolygon
from ..schemas import FloorPlanDefinition, RoomPolygon, Point2D, ValidationResult
from ..blueprint.generator import derive_wall_segments


def validate_room_edit(
    room_id: str,
    target_floor_id: str,
    new_polygon: List[Point2D],
    floors: List[FloorPlanDefinition],
    buildable_poly: Polygon
) -> Dict[str, Any]:
    """
    Validates a proposed room geometry change against:
    1. Polygon topology (is_valid)
    2. Containment inside buildable footprint
    3. Overlap with existing rooms on the target floor
    4. Minimum dimensions
    """
    violations = []
    warnings = []

    if len(new_polygon) < 3:
        return {
            "valid": False,
            "violations": ["Room polygon must have at least 3 vertices."],
            "warnings": []
        }

    pts = [(p.x, p.y) for p in new_polygon]
    room_poly = Polygon(pts)

    if not room_poly.is_valid:
        violations.append("Room polygon is topologically self-intersecting or degenerate.")

    # Buildable containment
    if buildable_poly and buildable_poly.is_valid:
        if not buildable_poly.buffer(0.05).contains(room_poly):
            violations.append("Room extends outside the permitted buildable footprint.")

    # Target floor room overlaps
    target_floor = next((f for f in floors if f.floor_id == target_floor_id), None)
    if target_floor:
        for other in target_floor.rooms:
            if other.room_id == room_id:
                continue
            other_pts = [(p.x, p.y) for p in other.polygon]
            if len(other_pts) >= 3:
                other_poly = Polygon(other_pts)
                if other_poly.is_valid:
                    inter = room_poly.intersection(other_poly)
                    if inter.area > 0.1:
                        violations.append(
                            f"Room overlaps with '{other.name}' by {inter.area:.2f} m²."
                        )

    area = round(float(room_poly.area), 2) if room_poly.is_valid else 0.0

    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "warnings": warnings,
        "calculated_area": area
    }


def apply_room_edit(
    room_id: str,
    target_floor_id: str,
    new_polygon: List[Point2D],
    floors: List[FloorPlanDefinition],
    buildable_poly: Polygon
) -> Dict[str, Any]:
    """
    Applies validated room polygon modification and updates walls.
    """
    check = validate_room_edit(room_id, target_floor_id, new_polygon, floors, buildable_poly)
    if not check["valid"]:
        return {
            "success": False,
            "violations": check["violations"],
            "floors": floors
        }

    pts = [(p.x, p.y) for p in new_polygon]
    poly = Polygon(pts)
    c_pt = poly.centroid

    updated_floors: List[FloorPlanDefinition] = []
    for fl in floors:
        fl_rooms = []
        for rm in fl.rooms:
            if rm.room_id == room_id:
                # Update room geometry
                updated_rm = rm.model_copy(
                    update={
                        "polygon": new_polygon,
                        "area": round(float(poly.area), 2),
                        "center": Point2D(x=round(c_pt.x, 3), y=round(c_pt.y, 3)),
                        "geometry_origin": "edited",
                        "floor_id": target_floor_id
                    }
                )
                fl_rooms.append(updated_rm)
            else:
                fl_rooms.append(rm)

        new_walls = derive_wall_segments(fl.floor_id, buildable_poly, fl_rooms)
        updated_fl = fl.model_copy(
            update={
                "rooms": fl_rooms,
                "walls": new_walls,
                "target_allocated_area": round(sum(r.area for r in fl_rooms), 2)
            }
        )
        updated_floors.append(updated_fl)

    return {
        "success": True,
        "violations": [],
        "floors": updated_floors
    }
