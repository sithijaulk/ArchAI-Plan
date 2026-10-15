import json
import math
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple, Set

from ..utils.vsai_geometry import (
    GeometryValidationError,
    _signed_area,
    _has_self_intersection,
    find_room_overlaps,
)

VALID_COMPONENTS = ("gab_gen", "vsai_rectifier", "esai_engine", "elia_engine")

KNOWN_ROOM_TYPES = {
    "living", "kitchen", "master_bedroom", "bedroom", "pooja", "pooja_room",
    "bathroom", "bath", "toilet", "dining", "store", "study", "balcony", "entrance"
}

VALID_ORIENTATIONS = {
    "north", "south", "east", "west",
    "north-east", "northeast", "north-west", "northwest",
    "south-east", "southeast", "south-west", "southwest"
}


def validate_master_json(
    raw_content: Any,
    filename: str = "master.json",
) -> Dict[str, Any]:
    """
    Executes multi-stage validation on a Master JSON payload:
    Stage A: JSON File Validation (syntax, emptiness)
    Stage B: Required Structure Validation (schema top-level, types, unique IDs)
    Stage C: Coordinate and Geometry Validation (coordinates, polygons, bounds, overlaps)
    Stage D: Orientation and Vastu-Readiness Validation (Padavinyasa, Brahmasthan, Entrance, Placement)
    Stage E: Validation Results Formulation
    """
    errors: List[str] = []
    warnings: List[str] = []
    missing_fields: List[str] = []

    # -------------------------------------------------------------
    # Stage A: JSON File Validation
    # -------------------------------------------------------------
    data: Optional[Dict[str, Any]] = None

    if isinstance(raw_content, (bytes, bytearray)):
        try:
            content_str = raw_content.decode("utf-8")
        except UnicodeDecodeError as ex:
            return _build_invalid_response(
                errors=[f"File encoding error: {str(ex)}. Expected UTF-8."],
                summary="Uploaded file is not a valid UTF-8 text document.",
                filename=filename,
            )
        if not content_str.strip():
            return _build_invalid_response(
                errors=["Uploaded JSON file is empty."],
                summary="The uploaded file contains no data.",
                filename=filename,
            )
        try:
            data = json.loads(content_str)
        except json.JSONDecodeError as ex:
            return _build_invalid_response(
                errors=[f"Malformed JSON syntax at line {ex.lineno}, column {ex.colno}: {ex.msg}"],
                summary=f"Failed to parse JSON file '{filename}'.",
                filename=filename,
            )
    elif isinstance(raw_content, str):
        if not raw_content.strip():
            return _build_invalid_response(
                errors=["Uploaded JSON string is empty."],
                summary="The uploaded file contains no data.",
                filename=filename,
            )
        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as ex:
            return _build_invalid_response(
                errors=[f"Malformed JSON syntax at line {ex.lineno}, column {ex.colno}: {ex.msg}"],
                summary=f"Failed to parse JSON string: {ex.msg}",
                filename=filename,
            )
    elif isinstance(raw_content, dict):
        data = raw_content
    else:
        return _build_invalid_response(
            errors=[f"Unsupported input type '{type(raw_content).__name__}'. Expected JSON string, bytes, or dict."],
            summary="Invalid input payload type.",
            filename=filename,
        )

    if not isinstance(data, dict):
        return _build_invalid_response(
            errors=["Master JSON root must be a JSON object ({...})."],
            summary="Root of Master JSON is not an object.",
            filename=filename,
        )

    # -------------------------------------------------------------
    # Stage B: Required Structure Validation
    # -------------------------------------------------------------
    project_id = data.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        errors.append("Required field 'project_id' is missing or not a non-empty string.")
        missing_fields.append("project_id")

    project_name = data.get("project_name")
    if not isinstance(project_name, str) or not project_name.strip():
        errors.append("Required field 'project_name' is missing or not a non-empty string.")
        missing_fields.append("project_name")

    floor_plan = data.get("floor_plan")
    if floor_plan is None:
        errors.append("Required field 'floor_plan' is missing from Master JSON.")
        missing_fields.append("floor_plan")
        floor_plan = {}
    elif not isinstance(floor_plan, dict):
        errors.append("Field 'floor_plan' must be a JSON object.")
        floor_plan = {}

    land_info = data.get("land_info")
    if land_info is None:
        warnings.append("Optional section 'land_info' is missing; orientation and boundary metadata will be limited.")
        missing_fields.append("land_info")
        land_info = {}
    elif not isinstance(land_info, dict):
        errors.append("Field 'land_info' must be a JSON object.")
        land_info = {}

    # Check collections inside floor_plan
    rooms_raw = floor_plan.get("rooms")
    if rooms_raw is None:
        errors.append("Field 'floor_plan.rooms' is missing.")
        missing_fields.append("floor_plan.rooms")
        rooms_raw = []
    elif not isinstance(rooms_raw, list):
        errors.append("Field 'floor_plan.rooms' must be an array of room objects.")
        rooms_raw = []

    structural_elements_raw = floor_plan.get("structural_elements", [])
    if not isinstance(structural_elements_raw, list):
        errors.append("Field 'floor_plan.structural_elements' must be an array.")
        structural_elements_raw = []

    walls_raw = floor_plan.get("walls", [])
    if not isinstance(walls_raw, list):
        errors.append("Field 'floor_plan.walls' must be an array if provided.")
        walls_raw = []

    doors_raw = floor_plan.get("doors", [])
    if not isinstance(doors_raw, list):
        errors.append("Field 'floor_plan.doors' must be an array if provided.")
        doors_raw = []

    windows_raw = floor_plan.get("windows", [])
    if not isinstance(windows_raw, list):
        errors.append("Field 'floor_plan.windows' must be an array if provided.")
        windows_raw = []

    # Check for duplicate IDs across all elements
    all_element_ids: Set[str] = set()
    for col_name, elements in [
        ("rooms", rooms_raw),
        ("structural_elements", structural_elements_raw),
        ("walls", walls_raw),
        ("doors", doors_raw),
        ("windows", windows_raw),
    ]:
        for idx, el in enumerate(elements):
            if isinstance(el, dict):
                eid = el.get("id")
                if not isinstance(eid, str) or not eid.strip():
                    errors.append(f"Element in 'floor_plan.{col_name}[{idx}]' has missing or empty 'id'.")
                elif eid in all_element_ids:
                    errors.append(f"Duplicate element ID detected: '{eid}' in 'floor_plan.{col_name}'.")
                else:
                    all_element_ids.add(eid)

    # -------------------------------------------------------------
    # Stage C: Coordinate and Geometry Validation
    # -------------------------------------------------------------
    valid_rooms: List[Dict[str, Any]] = []
    all_spatial_points: List[Tuple[float, float]] = []

    # Validate Rooms Polygons
    for idx, room in enumerate(rooms_raw):
        if not isinstance(room, dict):
            errors.append(f"Room at floor_plan.rooms[{idx}] must be a JSON object.")
            continue

        rid = room.get("id", f"room_{idx}")
        polygon = room.get("polygon")
        label = f"floor_plan.rooms[{idx}] ('{rid}')"

        if polygon is None:
            errors.append(f"{label} is missing required 'polygon' field.")
            continue

        points, geom_err = _validate_polygon_coordinates(polygon, label)
        if geom_err:
            errors.append(geom_err)
        else:
            valid_rooms.append({
                "id": rid,
                "name": room.get("name") or room.get("type") or rid,
                "type": room.get("type", "room"),
                "polygon": points,
            })
            for p in points:
                all_spatial_points.append((p[0], p[1]))

    # Validate Structural Elements Polygons
    valid_structural: List[Dict[str, Any]] = []
    for idx, elem in enumerate(structural_elements_raw):
        if not isinstance(elem, dict):
            errors.append(f"Structural element at floor_plan.structural_elements[{idx}] must be an object.")
            continue
        eid = elem.get("id", f"elem_{idx}")
        polygon = elem.get("polygon")
        label = f"floor_plan.structural_elements[{idx}] ('{eid}')"
        if polygon is not None:
            points, geom_err = _validate_polygon_coordinates(polygon, label)
            if geom_err:
                errors.append(geom_err)
            else:
                valid_structural.append({"id": eid, "type": elem.get("type", "column"), "polygon": points})
                for p in points:
                    all_spatial_points.append((p[0], p[1]))

    # Validate Walls (if provided)
    valid_wall_ids: Set[str] = set()
    for idx, wall in enumerate(walls_raw):
        if not isinstance(wall, dict):
            errors.append(f"Wall at floor_plan.walls[{idx}] must be an object.")
            continue
        wid = wall.get("id", f"wall_{idx}")
        valid_wall_ids.add(wid)
        coords = wall.get("coordinates") or wall.get("polygon")
        if coords is not None:
            if not isinstance(coords, list) or len(coords) < 2:
                errors.append(f"Wall '{wid}' coordinates must contain at least 2 points.")
            else:
                for cidx, pt in enumerate(coords):
                    if not isinstance(pt, (list, tuple)) or len(pt) != 2 or not all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in pt):
                        errors.append(f"Wall '{wid}' point[{cidx}] must contain finite numeric coordinates.")
                    else:
                        all_spatial_points.append((float(pt[0]), float(pt[1])))

    # Validate Doors (if provided)
    for idx, door in enumerate(doors_raw):
        if not isinstance(door, dict):
            errors.append(f"Door at floor_plan.doors[{idx}] must be an object.")
            continue
        did = door.get("id", f"door_{idx}")
        wall_ref = door.get("wall_id")
        if wall_ref and walls_raw and wall_ref not in valid_wall_ids:
            warnings.append(f"Door '{did}' references wall_id '{wall_ref}' which was not found in floor_plan.walls.")
        loc = door.get("location") or door.get("coordinates")
        if loc and isinstance(loc, (list, tuple)):
            for pt in (loc if isinstance(loc[0], (list, tuple)) else [loc]):
                if len(pt) == 2 and all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in pt):
                    all_spatial_points.append((float(pt[0]), float(pt[1])))

    # Validate Windows (if provided)
    for idx, win in enumerate(windows_raw):
        if not isinstance(win, dict):
            errors.append(f"Window at floor_plan.windows[{idx}] must be an object.")
            continue
        wid = win.get("id", f"window_{idx}")
        wall_ref = win.get("wall_id")
        if wall_ref and walls_raw and wall_ref not in valid_wall_ids:
            warnings.append(f"Window '{wid}' references wall_id '{wall_ref}' which was not found in floor_plan.walls.")

    # Boundary points from land_info
    boundary_points_raw = land_info.get("boundary_points", [])
    if isinstance(boundary_points_raw, list):
        for pt in boundary_points_raw:
            if isinstance(pt, (list, tuple)) and len(pt) == 2 and all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in pt):
                all_spatial_points.append((float(pt[0]), float(pt[1])))

    # Compute Bounding Box & Dimensions
    bounding_box = None
    usable_dimensions = False
    if all_spatial_points:
        xs = [p[0] for p in all_spatial_points]
        ys = [p[1] for p in all_spatial_points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        width = max_x - min_x
        height = max_y - min_y
        bounding_box = {
            "min_x": round(min_x, 3),
            "max_x": round(max_x, 3),
            "min_y": round(min_y, 3),
            "max_y": round(max_y, 3),
            "width": round(width, 3),
            "height": round(height, 3),
        }
        if width > 0 and height > 0:
            usable_dimensions = True
        else:
            errors.append("Floor plan boundary dimensions are degenerate (width or height is zero).")

    # Non-destructive Room Overlap Detection
    overlaps: List[Dict[str, str]] = []
    if len(valid_rooms) > 1:
        try:
            overlaps = find_room_overlaps(valid_rooms)
            if overlaps:
                for ov in overlaps:
                    warnings.append(
                        f"Room overlap detected between '{ov['first_room_id']}' and '{ov['second_room_id']}'. "
                        "Coordinates preserved; geometry rectification may require adjustment."
                    )
        except Exception as ex:
            warnings.append(f"Could not calculate room overlaps: {ex}")

    # Forward-compatibility warnings for walls, doors, windows
    if not walls_raw:
        warnings.append("No walls defined in 'floor_plan.walls'; structural wall-boundary analysis will rely on room polygons.")
    if not doors_raw:
        warnings.append("No doors defined in 'floor_plan.doors'; 32-Pada entrance orientation rule cannot evaluate entrance placement.")
    if not windows_raw:
        warnings.append("No windows defined in 'floor_plan.windows'; natural lighting & ventilation orientation checks will be skipped.")

    # -------------------------------------------------------------
    # Stage D: Orientation and Vastu-Readiness Validation
    # -------------------------------------------------------------
    orientation_val = (
        land_info.get("orientation")
        or floor_plan.get("orientation")
        or data.get("orientation")
        or data.get("north_direction")
    )

    has_valid_orientation = False
    orientation_str = "Not specified"
    if isinstance(orientation_val, str) and orientation_val.strip():
        orientation_str = orientation_val.strip()
        cleaned_orient = orientation_str.lower().replace("_", "-")
        if cleaned_orient in VALID_ORIENTATIONS or cleaned_orient.replace("-", "") in VALID_ORIENTATIONS:
            has_valid_orientation = True
        else:
            warnings.append(f"Non-standard orientation '{orientation_str}'; accepted standard cardinal/ordinal values are North, South, East, West, North-East, etc.")
            has_valid_orientation = True  # treat as provided with warning
    elif isinstance(orientation_val, (int, float)) and math.isfinite(orientation_val):
        orientation_str = f"{orientation_val}°"
        has_valid_orientation = True
    else:
        warnings.append("Orientation / North direction is missing from Master JSON. Critical for 9x9 Padavinyasa grid mapping and Vastu quadrant assignment.")
        missing_fields.append("land_info.orientation")

    # Vastu Readiness Criteria Checks
    # 1. Padavinyasa 9x9 Grid Mapping
    padavinyasa_ready = bool(usable_dimensions and len(valid_rooms) > 0 and has_valid_orientation)
    padavinyasa_reason = None
    if not usable_dimensions or len(valid_rooms) == 0:
        padavinyasa_reason = "Requires usable non-zero bounding dimensions and at least one valid room polygon."
    elif not has_valid_orientation:
        padavinyasa_reason = "Missing North orientation; 9x9 Padavinyasa grid cannot determine directional sector alignments."

    # 2. Brahmasthan (central 3x3 core)
    brahmasthan_ready = padavinyasa_ready
    brahmasthan_reason = padavinyasa_reason or None

    # 3. 32-Pada Entrance Rule
    has_doors = len(doors_raw) > 0
    entrance_ready = bool(has_doors and has_valid_orientation and usable_dimensions)
    entrance_reason = None
    if not has_doors:
        entrance_reason = "No door elements defined in floor_plan.doors; 32-Pada entrance calculation cannot evaluate door sector."
    elif not has_valid_orientation:
        entrance_reason = "Missing orientation; cannot map entrance pada along building perimeter."

    # 4. Directional Room Placement
    has_typed_rooms = any(
        r.get("type", "").lower() in KNOWN_ROOM_TYPES
        or any(k in r.get("name", "").lower() for k in ["kitchen", "pooja", "bed", "living", "bath"])
        for r in valid_rooms
    )
    directional_ready = bool(len(valid_rooms) > 0 and has_valid_orientation and has_typed_rooms)
    directional_reason = None
    if not has_valid_orientation:
        directional_reason = "Missing orientation; cannot resolve Cardinal and Ordinal sectors."
    elif not has_typed_rooms:
        directional_reason = "Rooms lack functional classifications (type/name) such as kitchen, pooja, master_bedroom, etc."

    # Overall Vastu Readiness Status
    if padavinyasa_ready and entrance_ready and directional_ready:
        vastu_status = "READY"
    elif padavinyasa_ready:
        vastu_status = "PARTIALLY_READY"
    else:
        vastu_status = "NOT_READY"

    # -------------------------------------------------------------
    # Stage E: Validation Results Formulation
    # -------------------------------------------------------------
    has_rooms = len(rooms_raw) > 0

    if errors:
        overall_status = "INVALID"
        is_valid = False
        can_rectify = False
        summary = f"JSON validation failed with {len(errors)} error(s). Review and correct input errors."
    elif not has_rooms or len(valid_rooms) == 0:
        overall_status = "INSUFFICIENT_DATA"
        is_valid = False
        can_rectify = False
        summary = "JSON structure is parsed, but floor_plan contains 0 rooms. Geometry is insufficient for processing."
    elif warnings:
        overall_status = "VALID_WITH_WARNINGS"
        is_valid = True
        can_rectify = True
        summary = f"JSON is valid with {len(warnings)} warning(s). Spatial data is usable for rectification."
    else:
        overall_status = "VALID"
        is_valid = True
        can_rectify = True
        summary = "JSON file and spatial geometry passed all structural and geometric validation checks."

    element_counts = {
        "rooms": len(rooms_raw),
        "structural_elements": len(structural_elements_raw),
        "walls": len(walls_raw),
        "doors": len(doors_raw),
        "windows": len(windows_raw),
    }

    spatial_summary = {
        "room_count": len(valid_rooms),
        "rooms": [
            {
                "id": r["id"],
                "name": r["name"],
                "type": r["type"],
                "points_count": len(r["polygon"]),
            }
            for r in valid_rooms
        ],
        "structural_elements_count": len(valid_structural),
        "walls_count": len(walls_raw),
        "doors_count": len(doors_raw),
        "windows_count": len(windows_raw),
        "orientation": orientation_str,
        "road_facing": land_info.get("road_facing", "Not specified"),
        "area_sqft": land_info.get("area_sqft"),
        "boundary_points_count": len(boundary_points_raw) if isinstance(boundary_points_raw, list) else 0,
        "bounding_box": bounding_box,
    }

    vastu_readiness = {
        "status": vastu_status,
        "padavinyasa_9x9": {"ready": padavinyasa_ready, "reason": padavinyasa_reason},
        "brahmasthan": {"ready": brahmasthan_ready, "reason": brahmasthan_reason},
        "entrance_32_pada": {"ready": entrance_ready, "reason": entrance_reason},
        "directional_room_placement": {"ready": directional_ready, "reason": directional_reason},
    }

    return {
        "status": overall_status,
        "is_valid": is_valid,
        "can_rectify": can_rectify,
        "errors": errors,
        "warnings": warnings,
        "missing_fields": missing_fields,
        "summary": summary,
        "element_counts": element_counts,
        "vastu_readiness": vastu_readiness,
        "spatial_summary": spatial_summary,
    }


def _validate_polygon_coordinates(polygon: Any, label: str) -> Tuple[Optional[List[List[float]]], Optional[str]]:
    """Helper to validate polygon format without crashing or mutating."""
    if not isinstance(polygon, list) or len(polygon) < 3:
        return None, f"{label}: polygon must be a list containing at least 3 points."

    points: List[List[float]] = []
    for idx, pt in enumerate(polygon):
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            return None, f"{label}[{idx}]: point must contain exactly two numeric coordinates [x, y]."
        x, y = pt[0], pt[1]
        if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return None, f"{label}[{idx}]: coordinates must be numeric (not boolean, string, or null)."
        if not math.isfinite(x) or not math.isfinite(y):
            return None, f"{label}[{idx}]: coordinates must be finite numbers (not NaN or Infinity)."
        points.append([float(x), float(y)])

    open_pts = points[:-1] if points[0] == points[-1] else points
    if len(open_pts) < 3 or len(set(map(tuple, open_pts))) < 3:
        return None, f"{label}: polygon is degenerate (fewer than 3 unique points)."

    try:
        if _has_self_intersection(open_pts):
            return None, f"{label}: polygon has self-intersecting edges."
        if _signed_area(open_pts) == 0:
            return None, f"{label}: polygon has zero geometric area."
    except Exception as ex:
        return None, f"{label}: geometry calculation error ({ex})."

    return points, None


def _build_invalid_response(errors: List[str], summary: str, filename: str) -> Dict[str, Any]:
    """Fallback generator for early syntax and file errors."""
    return {
        "status": "INVALID",
        "is_valid": False,
        "can_rectify": False,
        "errors": errors,
        "warnings": [],
        "missing_fields": [],
        "summary": summary,
        "element_counts": {
            "rooms": 0,
            "structural_elements": 0,
            "walls": 0,
            "doors": 0,
            "windows": 0,
        },
        "vastu_readiness": {
            "status": "NOT_READY",
            "padavinyasa_9x9": {"ready": False, "reason": "Invalid or unparseable input file."},
            "brahmasthan": {"ready": False, "reason": "Invalid or unparseable input file."},
            "entrance_32_pada": {"ready": False, "reason": "Invalid or unparseable input file."},
            "directional_room_placement": {"ready": False, "reason": "Invalid or unparseable input file."},
        },
        "spatial_summary": {
            "room_count": 0,
            "rooms": [],
            "structural_elements_count": 0,
            "walls_count": 0,
            "doors_count": 0,
            "windows_count": 0,
            "orientation": "Not specified",
            "road_facing": "Not specified",
            "area_sqft": None,
            "boundary_points_count": 0,
            "bounding_box": None,
        },
    }
