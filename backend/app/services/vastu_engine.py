import json
import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Sector constants
SECTOR_NORTH = "NORTH"
SECTOR_NORTH_EAST = "NORTH_EAST"
SECTOR_EAST = "EAST"
SECTOR_SOUTH_EAST = "SOUTH_EAST"
SECTOR_SOUTH = "SOUTH"
SECTOR_SOUTH_WEST = "SOUTH_WEST"
SECTOR_WEST = "WEST"
SECTOR_NORTH_WEST = "NORTH_WEST"
SECTOR_CENTER = "CENTER"

SECTOR_DISPLAY_NAMES = {
    SECTOR_NORTH: "North (Uttara / Kubera)",
    SECTOR_NORTH_EAST: "North-East (Ishanya / Shiva)",
    SECTOR_EAST: "East (Purva / Indra)",
    SECTOR_SOUTH_EAST: "South-East (Agneya / Agni)",
    SECTOR_SOUTH: "South (Dakshina / Yama)",
    SECTOR_SOUTH_WEST: "South-West (Nairutya / Nirrithi)",
    SECTOR_WEST: "West (Pashchima / Varuna)",
    SECTOR_NORTH_WEST: "North-West (Vayavya / Vayu)",
    SECTOR_CENTER: "Brahmasthan (Center / Brahma Core)",
}

ORIENTATION_OFFSETS = {
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


def load_vastu_rules() -> List[Dict[str, Any]]:
    """Loads rule definitions from vastu_rules.json."""
    rules_path = Path(__file__).parent / "vastu_rules.json"
    if not rules_path.exists():
        logger.warning(f"vastu_rules.json not found at {rules_path}, using defaults")
        return []
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("rules", [])
    except Exception as ex:
        logger.error(f"Failed to load vastu_rules.json: {ex}")
        return []


def calculate_polygon_centroid(polygon: List[List[float]]) -> Tuple[float, float]:
    """Calculates polygon centroid [x, y]."""
    if not polygon:
        return (0.0, 0.0)
    n = len(polygon)
    cx = sum(p[0] for p in polygon) / n
    cy = sum(p[1] for p in polygon) / n
    return (cx, cy)


def calculate_polygon_bounds(polygon: List[List[float]]) -> Tuple[float, float, float, float]:
    """Returns (min_x, max_x, min_y, max_y) for a polygon."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return (min(xs), max(xs), min(ys), max(ys))


def determine_sector_3x3(
    cx: float,
    cy: float,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    orientation_str: str = "north",
) -> str:
    """
    Divides the bounding box into a 3x3 Padavinyasa grid and maps [cx, cy]
    to one of the 8 directions or CENTER (Brahmasthan), taking orientation into account.
    """
    w = max_x - min_x
    h = max_y - min_y
    if w <= 0 or h <= 0:
        return SECTOR_CENTER

    # Relative coordinates normalized 0.0 to 1.0 (0=min, 1=max)
    rx = (cx - min_x) / w
    ry = (cy - min_y) / h

    # 3x3 grid row/col (col: 0=West, 1=Center, 2=East in canonical upward orientation)
    # Note: in floor plan coordinate systems, Y often points upward or downward.
    col = 0 if rx < (1.0 / 3.0) else (1 if rx < (2.0 / 3.0) else 2)
    row = 0 if ry < (1.0 / 3.0) else (1 if ry < (2.0 / 3.0) else 2)

    # Base grid map assuming top is North (row 2=North, row 0=South) or screen Y
    # Row 0=Bottom, Row 1=Middle, Row 2=Top
    base_grid = {
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

    base_sector = base_grid.get((col, row), SECTOR_CENTER)

    # If orientation is specified (e.g. North-East facing), adjust directional sectors
    clean_orientation = orientation_str.strip().lower()
    offset_deg = ORIENTATION_OFFSETS.get(clean_orientation, 0)

    if base_sector == SECTOR_CENTER or offset_deg == 0:
        return base_sector

    # Circular sectors ordered clockwise by 45 degrees
    circle = [
        SECTOR_NORTH,
        SECTOR_NORTH_EAST,
        SECTOR_EAST,
        SECTOR_SOUTH_EAST,
        SECTOR_SOUTH,
        SECTOR_SOUTH_WEST,
        SECTOR_WEST,
        SECTOR_NORTH_WEST,
    ]

    try:
        idx = circle.index(base_sector)
        steps = round(offset_deg / 45.0)
        new_idx = (idx + steps) % 8
        return circle[new_idx]
    except ValueError:
        return base_sector


def evaluate_vastu_shastra(
    master_json: Dict[str, Any],
    rules: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Evaluates Master JSON floor plan against configurable Vastu rules.
    Returns Vastu score, letter grade, good aspects, defects, and room sector mapping.
    """
    if rules is None:
        rules = load_vastu_rules()

    floor_plan = master_json.get("floor_plan", {})
    land_info = master_json.get("land_info", {})
    orientation = land_info.get("orientation", "North")

    rooms = floor_plan.get("rooms", [])
    structural = floor_plan.get("structural_elements", [])
    doors = floor_plan.get("doors", [])
    walls = floor_plan.get("walls", [])

    if not rooms:
        return {
            "score": 0,
            "grade": "N/A",
            "grade_description": "No floor plan rooms detected to evaluate Vastu compliance.",
            "good_aspects": [],
            "defects": [{
                "rule_id": "vastu.general.empty",
                "title": "Missing Room Geometries",
                "severity": "CRITICAL",
                "room_id": None,
                "room_name": "General",
                "sector": "GLOBAL",
                "description": "Floor plan contains no rooms to evaluate spatial compliance.",
                "remedy": "Upload a Master JSON containing valid room polygons.",
                "points_deducted": 0,
            }],
            "total_rules_evaluated": 0,
            "passed_rules_count": 0,
            "failed_rules_count": 1,
            "room_sectors": {},
            "brahmasthan": {"status": "UNKNOWN", "obstructing_rooms": []},
        }

    # 1. Compute overall bounding box
    all_points = []
    for r in rooms:
        poly = r.get("polygon", [])
        if isinstance(poly, list):
            all_points.extend(poly)

    if not all_points:
        min_x = max_x = min_y = max_y = 0.0
    else:
        min_x = min(p[0] for p in all_points)
        max_x = max(p[0] for p in all_points)
        min_y = min(p[1] for p in all_points)
        max_y = max(p[1] for p in all_points)

    total_width = max_x - min_x
    total_height = max_y - min_y
    total_area_sqft = land_info.get("area_sqft") or round(total_width * total_height)

    # 2. Map every room to its 3x3 sector
    room_sectors: Dict[str, Dict[str, Any]] = {}
    brahmasthan_rooms: List[str] = []

    for r in rooms:
        rid = str(r.get("id"))
        rname = r.get("name") or r.get("type") or rid
        rtype = str(r.get("type") or rname).strip().lower()
        poly = r.get("polygon", [])
        if not poly or len(poly) < 3:
            continue

        cx, cy = calculate_polygon_centroid(poly)
        rmin_x, rmax_x, rmin_y, rmax_y = calculate_polygon_bounds(poly)

        sector = determine_sector_3x3(cx, cy, min_x, max_x, min_y, max_y, orientation)

        # Check if room overlaps Brahmasthan center zone (middle 1/3 in X and Y)
        b_min_x = min_x + (total_width / 3.0)
        b_max_x = min_x + (2.0 * total_width / 3.0)
        b_min_y = min_y + (total_height / 3.0)
        b_max_y = min_y + (2.0 * total_height / 3.0)

        # Overlap check between room bounding box and Brahmasthan core
        overlaps_brahma = not (rmax_x < b_min_x or rmin_x > b_max_x or rmax_y < b_min_y or rmin_y > b_max_y)
        if overlaps_brahma and rtype not in ("courtyard", "atrium", "lobby"):
            brahmasthan_rooms.append(rname)

        room_sectors[rid] = {
            "id": rid,
            "name": rname,
            "type": rtype,
            "sector": sector,
            "sector_display": SECTOR_DISPLAY_NAMES.get(sector, sector),
            "centroid": [round(cx, 2), round(cy, 2)],
            "polygon": poly,
            "overlaps_brahmasthan": overlaps_brahma,
        }

    # 3. Evaluate Configured Rules
    good_aspects: List[Dict[str, Any]] = []
    defects: List[Dict[str, Any]] = []

    total_weight = 0
    earned_weight = 0

    for rule in rules:
        rule_id = rule.get("rule_id", "")
        weight = rule.get("weight", 10)
        total_weight += weight
        category = rule.get("category", "")
        target_types = [t.lower() for t in rule.get("target_room_types", [])]
        preferred = rule.get("preferred_sectors", [])
        tolerated = rule.get("tolerated_sectors", [])
        forbidden = rule.get("forbidden_sectors", [])

        # Rule evaluation logic per category
        if category == "room_placement":
            # Match rooms of target type
            matched_rooms = []
            for rid, rdata in room_sectors.items():
                rtype = rdata["type"]
                rname_lower = rdata["name"].lower()
                if any(t in rtype or t in rname_lower for t in target_types):
                    matched_rooms.append(rdata)

            if not matched_rooms:
                # Rule not applicable to this plan -> grant partial score
                earned_weight += weight
                continue

            # Evaluate each matched room
            room_all_good = True
            for rdata in matched_rooms:
                sector = rdata["sector"]
                sector_name = rdata["sector_display"]
                rname = rdata["name"]
                rid = rdata["id"]

                if sector in preferred:
                    good_aspects.append({
                        "rule_id": rule_id,
                        "title": f"{rule['name']} - Compliant",
                        "room_id": rid,
                        "room_name": rname,
                        "sector": sector,
                        "sector_display": sector_name,
                        "polygon": rdata["polygon"],
                        "description": rule.get("good_description", ""),
                        "points_earned": weight,
                    })
                elif sector in tolerated:
                    good_aspects.append({
                        "rule_id": rule_id,
                        "title": f"{rule['name']} - Acceptable Sector",
                        "room_id": rid,
                        "room_name": rname,
                        "sector": sector,
                        "sector_display": sector_name,
                        "polygon": rdata["polygon"],
                        "description": f"{rname} is in {sector_name}, which is permissible as a secondary alternative in Vastu.",
                        "points_earned": round(weight * 0.7),
                    })
                else:
                    room_all_good = False
                    defect_msg = rule.get("defect_description", "").replace("%CURRENT_SECTOR%", sector_name)
                    defects.append({
                        "rule_id": rule_id,
                        "title": f"{rule['name']} - Defect Detected",
                        "severity": rule.get("severity", "HIGH"),
                        "room_id": rid,
                        "room_name": rname,
                        "sector": sector,
                        "sector_display": sector_name,
                        "polygon": rdata["polygon"],
                        "description": defect_msg,
                        "remedy": rule.get("remedy", ""),
                        "points_deducted": weight,
                    })

            if room_all_good:
                earned_weight += weight

        elif category == "brahmasthan":
            if not brahmasthan_rooms:
                earned_weight += weight
                good_aspects.append({
                    "rule_id": rule_id,
                    "title": "Brahmasthan Center is Open & Balanced",
                    "room_id": None,
                    "room_name": "Brahmasthan Center",
                    "sector": SECTOR_CENTER,
                    "sector_display": SECTOR_DISPLAY_NAMES[SECTOR_CENTER],
                    "polygon": None,
                    "description": rule.get("good_description", ""),
                    "points_earned": weight,
                })
            else:
                defect_msg = rule.get("defect_description", "").replace(
                    "%OBSTRUCTION_ELEMENTS%", ", ".join(brahmasthan_rooms)
                )
                defects.append({
                    "rule_id": rule_id,
                    "title": "Brahmasthan Center Obstructed",
                    "severity": "CRITICAL",
                    "room_id": None,
                    "room_name": ", ".join(brahmasthan_rooms),
                    "sector": SECTOR_CENTER,
                    "sector_display": SECTOR_DISPLAY_NAMES[SECTOR_CENTER],
                    "polygon": None,
                    "description": defect_msg,
                    "remedy": rule.get("remedy", ""),
                    "points_deducted": weight,
                })

        elif category == "structural":
            col_count = len(structural)
            # Rule: residential span safety — if area > 1500 sqft and columns <= 4, flag defect
            if total_area_sqft > 1500 and col_count > 0 and col_count <= 4:
                defect_msg = rule.get("defect_description", "").replace(
                    "%COLUMN_COUNT%", str(col_count)
                ).replace("%AREA_SQFT%", f"{total_area_sqft:,}")
                defects.append({
                    "rule_id": rule_id,
                    "title": "Inadequate Structural Column Grid",
                    "severity": "HIGH",
                    "room_id": None,
                    "room_name": "Columns / Span",
                    "sector": "GLOBAL",
                    "sector_display": "Global Structure",
                    "polygon": None,
                    "description": defect_msg,
                    "remedy": rule.get("remedy", ""),
                    "points_deducted": weight,
                })
            else:
                earned_weight += weight
                good_aspects.append({
                    "rule_id": rule_id,
                    "title": "Structural Column Support Verified",
                    "room_id": None,
                    "room_name": "Columns",
                    "sector": "GLOBAL",
                    "sector_display": "Global Structure",
                    "polygon": None,
                    "description": rule.get("good_description", ""),
                    "points_earned": weight,
                })

    # 4. Final Score & Grade Calculation
    if total_weight > 0:
        score = int(round((earned_weight / total_weight) * 100))
    else:
        score = 80

    score = max(0, min(100, score))

    if score >= 90:
        grade = "A+"
        grade_desc = "Excellent Vastu Harmony: Space aligns with universal cosmic principles."
    elif score >= 75:
        grade = "A"
        grade_desc = "Good Compliance: Solid Vastu layout with minimal non-critical adjustments."
    elif score >= 55:
        grade = "B"
        grade_desc = "Moderate Vastu Harmony: Key elemental or directional rectifications needed."
    elif score >= 35:
        grade = "C"
        grade_desc = "Significant Vastu Defects: Critical zones (e.g. Brahmasthan or Toilet) need relocation."
    else:
        grade = "D"
        grade_desc = "Major Non-Compliance: Fundamental spatial redesign recommended."

    return {
        "score": score,
        "grade": grade,
        "grade_description": grade_desc,
        "good_aspects": good_aspects,
        "defects": defects,
        "total_rules_evaluated": len(rules),
        "passed_rules_count": len(good_aspects),
        "failed_rules_count": len(defects),
        "room_sectors": room_sectors,
        "brahmasthan": {
            "status": "OPEN" if not brahmasthan_rooms else "OBSTRUCTED",
            "obstructing_rooms": brahmasthan_rooms,
        },
        "bounding_box": {
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
            "width": total_width,
            "height": total_height,
            "area_sqft": total_area_sqft,
        },
    }
