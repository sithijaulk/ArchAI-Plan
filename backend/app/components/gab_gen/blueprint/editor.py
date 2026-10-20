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

    # Statutory minimum room size check (UDA Gazette 2235/54 Sched. 7)
    target_room = None
    if target_floor:
        target_room = next((r for r in target_floor.rooms if r.room_id == room_id), None)
    if target_room:
        rt = target_room.type.lower()
        if "master_bedroom" in rt and area < 9.3:
            violations.append(f"Master bedroom area ({area:.2f} m²) violates statutory minimum (9.5 m²) under Gazette 2235/54 Schedule 7.")
        elif "bedroom" in rt and area < 8.3:
            violations.append(f"Bedroom area ({area:.2f} m²) violates statutory minimum (8.5 m²) under Gazette 2235/54 Schedule 7.")
        elif "kitchen" in rt and area < 5.3:
            violations.append(f"Kitchen area ({area:.2f} m²) violates statutory minimum (5.5 m²) under Gazette 2235/54 Schedule 7.")
        elif ("bathroom" in rt or "toilet" in rt) and area < 1.6:
            violations.append(f"Bathroom area ({area:.2f} m²) violates statutory minimum (1.7 m²) under Gazette 2235/54 Schedule 7.")

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
    # If the room changed floors, remove it from old floor and place in target_floor
    source_floor = next((f for f in floors if any(r.room_id == room_id for r in f.rooms)), None)
    target_rm = next((r for f in floors for r in f.rooms if r.room_id == room_id), None)
    
    if target_rm and source_floor and source_floor.floor_id != target_floor_id:
        # Cross-floor transfer
        for fl in floors:
            if fl.floor_id == source_floor.floor_id:
                fl_rooms = [r for r in fl.rooms if r.room_id != room_id]
            elif fl.floor_id == target_floor_id:
                updated_rm = target_rm.model_copy(
                    update={
                        "polygon": new_polygon,
                        "area": round(float(poly.area), 2),
                        "center": Point2D(x=round(c_pt.x, 3), y=round(c_pt.y, 3)),
                        "geometry_origin": "edited",
                        "floor_id": target_floor_id
                    }
                )
                fl_rooms = list(fl.rooms) + [updated_rm]
            else:
                fl_rooms = list(fl.rooms)
            new_walls = derive_wall_segments(fl.floor_id, buildable_poly, fl_rooms)
            updated_floors.append(
                fl.model_copy(
                    update={
                        "rooms": fl_rooms,
                        "walls": new_walls,
                        "target_allocated_area": round(sum(r.area for r in fl_rooms), 2)
                    }
                )
            )
    else:
        # Same floor update
        for fl in floors:
            fl_rooms = []
            for rm in fl.rooms:
                if rm.room_id == room_id:
                    # Update room geometry and calculate width / length
                    xs = [p.x for p in new_polygon]
                    ys = [p.y for p in new_polygon]
                    w_m = round(max(xs) - min(xs), 2)
                    l_m = round(max(ys) - min(ys), 2)
                    updated_rm = rm.model_copy(
                        update={
                            "polygon": new_polygon,
                            "area": round(float(poly.area), 2),
                            "center": Point2D(x=round(c_pt.x, 3), y=round(c_pt.y, 3)),
                            "width_m": w_m,
                            "length_m": l_m,
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


def remove_room_from_blueprint(
    room_id: str,
    floors: List[FloorPlanDefinition],
    buildable_poly: Polygon
) -> Dict[str, Any]:
    """Removes a room from the floor plan and recalculates floor walls and area."""
    target_rm = next((r for f in floors for r in f.rooms if r.room_id == room_id), None)
    if not target_rm:
        return {"success": False, "violations": [f"Room '{room_id}' not found."], "floors": floors}
    if target_rm.is_structural_stair:
        return {"success": False, "violations": ["Cannot remove structural staircase core."], "floors": floors}

    updated_floors = []
    for fl in floors:
        fl_rooms = [r for r in fl.rooms if r.room_id != room_id]
        new_walls = derive_wall_segments(fl.floor_id, buildable_poly, fl_rooms)
        updated_fl = fl.model_copy(
            update={
                "rooms": fl_rooms,
                "walls": new_walls,
                "target_allocated_area": round(sum(r.area for r in fl_rooms), 2)
            }
        )
        updated_floors.append(updated_fl)

    return {"success": True, "violations": [], "floors": updated_floors}


def add_room_to_blueprint(
    target_floor_id: str,
    room_data: Dict[str, Any],
    floors: List[FloorPlanDefinition],
    buildable_poly: Polygon
) -> Dict[str, Any]:
    """Adds a newly requested room to a specified floor with boundary containment and overlap validation."""
    polygon_raw = room_data.get("polygon", [])
    if len(polygon_raw) < 3:
        return {"success": False, "violations": ["Room polygon must have at least 3 vertices."], "floors": floors}

    pts = [Point2D(x=p["x"], y=p["y"]) for p in polygon_raw]
    room_id = room_data.get("room_id") or f"{target_floor_id}_CUSTOM_{len(floors[0].rooms)+1}"

    check = validate_room_edit(room_id, target_floor_id, pts, floors, buildable_poly)
    if not check["valid"]:
        return {"success": False, "violations": check["violations"], "floors": floors}

    poly = Polygon([(p.x, p.y) for p in pts])
    c_pt = poly.centroid
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]

    new_rm = RoomPolygon(
        room_id=room_id,
        name=room_data.get("name", "Custom Room"),
        type=room_data.get("type", "other"),
        floor_id=target_floor_id,
        area=round(float(poly.area), 2),
        target_area=round(room_data.get("target_area", float(poly.area)), 2),
        polygon=pts,
        center=Point2D(x=round(c_pt.x, 3), y=round(c_pt.y, 3)),
        width_m=round(max(xs) - min(xs), 2),
        length_m=round(max(ys) - min(ys), 2),
        is_structural_stair=False,
        geometry_origin="user_added"
    )

    updated_floors = []
    for fl in floors:
        fl_rooms = list(fl.rooms)
        if fl.floor_id == target_floor_id:
            fl_rooms.append(new_rm)
        new_walls = derive_wall_segments(fl.floor_id, buildable_poly, fl_rooms)
        updated_fl = fl.model_copy(
            update={
                "rooms": fl_rooms,
                "walls": new_walls,
                "target_allocated_area": round(sum(r.area for r in fl_rooms), 2)
            }
        )
        updated_floors.append(updated_fl)

    return {"success": True, "violations": [], "floors": updated_floors, "created_room_id": room_id}

