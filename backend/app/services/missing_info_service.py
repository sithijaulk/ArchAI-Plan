from copy import deepcopy
import logging
from typing import Any, Dict, List, Optional, Tuple

from .master_json import MasterJsonAdapter, load_master_json_config

logger = logging.getLogger(__name__)

VALID_CARDINAL_DIRECTIONS = ["NORTH", "EAST", "SOUTH", "WEST"]
VALID_ORDINAL_DIRECTIONS = ["NORTH_EAST", "SOUTH_EAST", "SOUTH_WEST", "NORTH_WEST"]
ALL_DIRECTIONS = [
    ("NORTH", "North (Uttara)"),
    ("EAST", "East (Purva)"),
    ("SOUTH", "South (Dakshina)"),
    ("WEST", "West (Pashchima)"),
    ("NORTH_EAST", "North-East (Ishanya)"),
    ("SOUTH_EAST", "South-East (Agneya)"),
    ("SOUTH_WEST", "South-West (Nairutya)"),
    ("NORTH_WEST", "North-West (Vayavya)"),
]

CANONICAL_ROOM_TYPES = [
    ("living_room", "Living Room / Sitting Area"),
    ("kitchen", "Kitchen / Cooking"),
    ("master_bedroom", "Master Bedroom (Head of Household)"),
    ("bedroom", "Bedroom (Family / Guest)"),
    ("pooja_room", "Pooja Room / Sacred Sanctum"),
    ("toilet", "Toilet / Bathroom / Washroom"),
    ("dining", "Dining Area"),
    ("store_room", "Store Room / Storage"),
    ("garage", "Garage / Atelier / Workshop"),
    ("hallway", "Central Hall / Corridor"),
    ("staircase", "Staircase"),
    ("courtyard", "Open Courtyard / Atrium"),
]


def _derive_cardinal_side_from_position(
    pos: Tuple[float, float],
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> str:
    """Derives which boundary side (NORTH, SOUTH, EAST, WEST) a coordinate point lies on."""
    px, py = pos
    width = max(max_x - min_x, 0.001)
    height = max(max_y - min_y, 0.001)

    dist_north = abs(py - min_y)
    dist_south = abs(py - max_y)
    dist_west = abs(px - min_x)
    dist_east = abs(px - max_x)

    # Normalize distances as fraction of dimensions
    norm_n = dist_north / height
    norm_s = dist_south / height
    norm_w = dist_west / width
    norm_e = dist_east / width

    min_norm = min(norm_n, norm_s, norm_w, norm_e)
    if min_norm == norm_n:
        return "NORTH"
    if min_norm == norm_s:
        return "SOUTH"
    if min_norm == norm_e:
        return "EAST"
    return "WEST"


def detect_missing_and_ambiguous_info(master_json: Dict[str, Any]) -> Dict[str, Any]:
    """Inspects a Master JSON against Vastu requirements and returns a structured report
    containing only the missing, ambiguous, or conflicting items that require user input."""
    if not isinstance(master_json, dict):
        return {
            "has_blocking_missing_info": True,
            "questions": [],
            "summary": "Input is not a valid JSON object.",
        }

    config = load_master_json_config()
    questions: List[Dict[str, Any]] = []

    floor_plan = master_json.get("floor_plan") if isinstance(master_json.get("floor_plan"), dict) else {}
    land_info = master_json.get("land_info") if isinstance(master_json.get("land_info"), dict) else {}
    spatial_meta = master_json.get("spatial_metadata") if isinstance(master_json.get("spatial_metadata"), dict) else {}

    rooms = floor_plan.get("rooms") or []
    doors = floor_plan.get("doors") or []

    # Calculate overall floor plan bounds
    all_points: List[Tuple[float, float]] = []
    for r in rooms:
        poly = r.get("polygon")
        if isinstance(poly, list):
            for pt in poly:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    try:
                        all_points.append((float(pt[0]), float(pt[1])))
                    except (ValueError, TypeError):
                        pass

    has_geometry = len(all_points) >= 3
    min_x, max_x, min_y, max_y = 0.0, 100.0, 0.0, 100.0
    if has_geometry:
        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

    # -------------------------------------------------------------
    # 1. Orientation & North Direction Check
    # -------------------------------------------------------------
    raw_orient = (
        land_info.get("orientation")
        or spatial_meta.get("north_direction")
        or master_json.get("orientation")
    )
    resolved_orient = None
    if raw_orient and isinstance(raw_orient, str) and raw_orient.strip():
        resolved_orient = MasterJsonAdapter.resolve_direction(raw_orient, config)

    is_orientation_missing = not resolved_orient or resolved_orient.upper() in ("UNKNOWN", "NOT SPECIFIED")
    questions.append({
        "id": "orientation",
        "category": "orientation",
        "title": "Plot / House Orientation" if is_orientation_missing else "Confirm Plot / House Orientation",
        "description": (
            "Orientation (North direction) is required to establish the 9x9 Padavinyasa cosmic grid and evaluate directional zones."
            if is_orientation_missing
            else f"Current orientation is detected as '{resolved_orient or raw_orient}'. You can confirm or change it."
        ),
        "field_path": "land_info.orientation",
        "current_value": resolved_orient or raw_orient or "",
        "suggested_value": resolved_orient or "NORTH",
        "has_conflict": False,
        "is_required": is_orientation_missing,
        "input_type": "select",
        "options": [{"value": val, "label": lbl} for val, lbl in ALL_DIRECTIONS],
    })

    # -------------------------------------------------------------
    # 2. Main Entrance Check
    # -------------------------------------------------------------
    if isinstance(doors, list) and len(doors) > 0:
        door_options = []
        for i, d in enumerate(doors):
            if isinstance(d, dict):
                d_id = str(d.get("id") or f"door-{i+1}")
                d_name = str(d.get("name") or d_id)
                d_dir = d.get("direction") or "unspecified"
                door_options.append({"value": d_id, "label": f"{d_name} (Direction: {d_dir})"})

        explicit_main = [
            d for d in doors
            if isinstance(d, dict) and (
                d.get("is_main_entrance") is True
                or "main" in str(d.get("id", "")).lower()
                or "main" in str(d.get("name", "")).lower()
                or "front" in str(d.get("name", "")).lower()
            )
        ]
        if len(explicit_main) == 0 and len(doors) == 1:
            explicit_main = [doors[0]]

        if len(explicit_main) == 1:
            main_id = str(explicit_main[0].get("id"))
            main_name = str(explicit_main[0].get("name") or main_id)
            questions.append({
                "id": "main_entrance",
                "category": "main_entrance",
                "title": "Confirm Main Entrance Door",
                "description": f"Door '{main_name}' is currently designated as the main entrance. You may confirm or select another door.",
                "field_path": "floor_plan.doors.is_main_entrance",
                "current_value": main_id,
                "suggested_value": main_id,
                "has_conflict": False,
                "is_required": False,
                "input_type": "select",
                "options": door_options,
            })
        elif len(explicit_main) > 1:
            questions.append({
                "id": "main_entrance",
                "category": "main_entrance",
                "title": "Multiple Main Entrances Found — Select Primary",
                "description": "Multiple doors are flagged as 'is_main_entrance'. Please confirm which one serves as the official primary house entrance.",
                "field_path": "floor_plan.doors.is_main_entrance",
                "current_value": str(explicit_main[0].get("id")),
                "suggested_value": str(explicit_main[0].get("id")),
                "has_conflict": True,
                "is_required": True,
                "input_type": "select",
                "options": door_options,
            })
        else:  # len(explicit_main) == 0
            suggested_main = door_options[0]["value"] if door_options else ""
            questions.append({
                "id": "main_entrance",
                "category": "main_entrance",
                "title": "Designate Main Entrance Door",
                "description": "None of the doors in the layout are marked as the primary main entrance. Main entrance orientation is a fundamental Vastu rule.",
                "field_path": "floor_plan.doors.is_main_entrance",
                "current_value": None,
                "suggested_value": suggested_main,
                "has_conflict": False,
                "is_required": True,
                "input_type": "select",
                "options": door_options,
            })
    else:
        # No doors defined anywhere
        questions.append({
            "id": "has_no_doors_confirmation",
            "category": "main_entrance",
            "title": "No Doors Defined in Layout",
            "description": "No doors were detected. In Vastu, a house with zero doors anywhere is classified under Dhruva. If this floor plan has an entrance door, please specify it.",
            "field_path": "floor_plan.doors",
            "current_value": "dhruva_no_doors",
            "suggested_value": "dhruva_no_doors",
            "has_conflict": False,
            "is_required": False,
            "input_type": "radio",
            "options": [
                {"value": "dhruva_no_doors", "label": "Layout intentionally has no doors (Evaluate as Dhruva)"},
                {"value": "add_entrance_manually", "label": "I want to specify an entrance door direction"}
            ],
        })

    # -------------------------------------------------------------
    # 3. Door Direction and Geometric Conflict Checks
    # -------------------------------------------------------------
    if isinstance(doors, list):
        for i, d in enumerate(doors):
            if not isinstance(d, dict):
                continue
            did = str(d.get("id") or f"door-{i+1}")
            dname = str(d.get("name") or did)
            raw_dir = d.get("direction")
            pos = d.get("position") or d.get("location") or d.get("coordinates")

            # Check if direction is missing
            canonical_d_dir = MasterJsonAdapter.resolve_direction(raw_dir, config) if raw_dir else None
            derived_dir = None
            if has_geometry and isinstance(pos, (list, tuple)) and len(pos) >= 2:
                try:
                    derived_dir = _derive_cardinal_side_from_position(
                        (float(pos[0]), float(pos[1])), min_x, min_y, max_x, max_y
                    )
                except Exception:
                    pass

            if not canonical_d_dir:
                questions.append({
                    "id": f"door_direction_{did}",
                    "category": "door_direction",
                    "target_element_id": did,
                    "title": f"Door Direction: {dname}",
                    "description": f"Direction is missing for door '{dname}'. Based on position {pos or 'unknown'}, it appears to face {derived_dir or 'unknown'}.",
                    "field_path": f"floor_plan.doors[{did}].direction",
                    "current_value": "",
                    "suggested_value": derived_dir or "NORTH",
                    "has_conflict": False,
                    "is_required": derived_dir is None,
                    "input_type": "select",
                    "options": [{"value": val, "label": lbl} for val, lbl in ALL_DIRECTIONS[:4]],
                })
            elif derived_dir and canonical_d_dir in VALID_CARDINAL_DIRECTIONS:
                # Check for major conflict: declared direction is opposite or different from wall boundary
                opposite_pairs = {("NORTH", "SOUTH"), ("SOUTH", "NORTH"), ("EAST", "WEST"), ("WEST", "EAST")}
                if (canonical_d_dir, derived_dir) in opposite_pairs:
                    questions.append({
                        "id": f"door_conflict_{did}",
                        "category": "geometry_conflict",
                        "target_element_id": did,
                        "title": f"Conflicting Direction on Door '{dname}'",
                        "description": (
                            f"Door '{dname}' has declared direction '{canonical_d_dir}', "
                            f"but its coordinates {pos} place it on the {derived_dir} exterior wall. "
                            f"Please confirm which direction this door opens toward."
                        ),
                        "field_path": f"floor_plan.doors[{did}].direction",
                        "current_value": canonical_d_dir,
                        "suggested_value": derived_dir,
                        "has_conflict": True,
                        "is_required": True,
                        "input_type": "radio",
                        "options": [
                            {"value": canonical_d_dir, "label": f"Keep declared direction: {canonical_d_dir}"},
                            {"value": derived_dir, "label": f"Correct to wall location: {derived_dir} (Recommended)"},
                        ],
                    })

    # -------------------------------------------------------------
    # 4. Room Type & Ambiguity Checks
    # -------------------------------------------------------------
    if isinstance(rooms, list):
        for i, r in enumerate(rooms):
            if not isinstance(r, dict):
                continue
            rid = str(r.get("id") or f"room-{i+1}")
            rname = str(r.get("name") or rid)
            rtype = str(r.get("type") or "").strip().lower()

            # Check if room has geometry
            poly = r.get("polygon")
            if not poly or not isinstance(poly, list) or len(poly) < 3:
                questions.append({
                    "id": f"room_poly_missing_{rid}",
                    "category": "missing_geometry",
                    "target_element_id": rid,
                    "title": f"Missing Polygon Coordinates for '{rname}'",
                    "description": f"Room '{rname}' lacks a closed polygon geometry with at least 3 points. Spatial analysis cannot calculate its center or quadrant.",
                    "field_path": f"floor_plan.rooms[{rid}].polygon",
                    "current_value": None,
                    "suggested_value": None,
                    "has_conflict": True,
                    "is_required": True,
                    "input_type": "text",
                    "options": [],
                })

            # Check if room type is generic or ambiguous
            canonical_type = MasterJsonAdapter.resolve_room_type(rtype, rname, config)
            if canonical_type in ("room", "space", "unknown", "zone", ""):
                questions.append({
                    "id": f"room_type_{rid}",
                    "category": "room_type",
                    "target_element_id": rid,
                    "title": f"Identify Room Type for '{rname}'",
                    "description": f"Room '{rname}' has ambiguous or generic type '{rtype or 'unspecified'}'. Vastu Shastra rules evaluate auspicious quadrants based on room function.",
                    "field_path": f"floor_plan.rooms[{rid}].type",
                    "current_value": rtype,
                    "suggested_value": "living_room",
                    "has_conflict": False,
                    "is_required": True,
                    "input_type": "select",
                    "options": [{"value": val, "label": lbl} for val, lbl in CANONICAL_ROOM_TYPES],
                })

    has_blocking = any(q.get("is_required") for q in questions)
    return {
        "has_blocking_missing_info": has_blocking,
        "questions_count": len(questions),
        "questions": questions,
        "summary": (
            f"Detected {len(questions)} item(s) requiring user review or confirmation before Vastu analysis."
            if questions
            else "Master JSON is complete and valid with no missing or conflicting information."
        ),
    }


def merge_confirmed_inputs(
    master_json: Dict[str, Any],
    confirmed_answers: Dict[str, Any],
) -> Dict[str, Any]:
    """Applies user-confirmed inputs to a clean, normalized copy of the Master JSON.
    Preserves the original source data under 'original_source_snapshot' without destructive overwrite."""
    if not isinstance(master_json, dict):
        return {}

    normalized = deepcopy(master_json)
    if "original_source_snapshot" not in normalized:
        normalized["original_source_snapshot"] = deepcopy(master_json)

    if "user_confirmations" not in normalized or not isinstance(normalized["user_confirmations"], dict):
        normalized["user_confirmations"] = {}

    normalized["user_confirmations"].update(deepcopy(confirmed_answers))

    floor_plan = normalized.setdefault("floor_plan", {})
    land_info = normalized.setdefault("land_info", {})
    spatial_meta = normalized.setdefault("spatial_metadata", {})
    rooms = floor_plan.setdefault("rooms", [])
    doors = floor_plan.setdefault("doors", [])

    for q_id, answer in confirmed_answers.items():
        if answer is None:
            continue

        # 1. Orientation
        if q_id == "orientation":
            orient_str = str(answer).strip()
            land_info["orientation"] = orient_str.capitalize()
            spatial_meta["north_direction"] = orient_str.capitalize()

        # 2. Main Entrance
        elif q_id == "main_entrance":
            selected_door_id = str(answer).strip()
            for d in doors:
                if isinstance(d, dict):
                    did = str(d.get("id"))
                    d["is_main_entrance"] = (did == selected_door_id)

        # 3. No doors - manual entrance creation
        elif q_id == "has_no_doors_confirmation":
            if answer == "add_entrance_manually":
                if not doors:
                    doors.append({
                        "id": "door-main-manual",
                        "name": "Main Entrance (User Confirmed)",
                        "direction": "EAST",
                        "is_main_entrance": True,
                        "position": [0, 0],
                    })

        # 4. Door direction or conflict
        elif q_id.startswith("door_direction_") or q_id.startswith("door_conflict_"):
            target_id = q_id.replace("door_direction_", "").replace("door_conflict_", "")
            for d in doors:
                if isinstance(d, dict) and str(d.get("id")) == target_id:
                    d["direction"] = str(answer).strip().upper()

        # 5. Room Type
        elif q_id.startswith("room_type_"):
            target_id = q_id.replace("room_type_", "")
            for r in rooms:
                if isinstance(r, dict) and str(r.get("id")) == target_id:
                    r["type"] = str(answer).strip().lower()

    return normalized
