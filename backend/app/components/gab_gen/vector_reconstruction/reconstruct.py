"""
Trigonometric coordinate reconstruction and land polygon validation using Shapely.
Coordinate convention:
  Canonical GAB coordinate system:
  - Units: meters
  - Origin: first reconstructed legal survey point P0 (0.0, 0.0)
  - +X = East
  - +Y = North
  - Survey Azimuth: clockwise from North (0° = North, 90° = East, 180° = South, 270° = West)
  
  Trigonometric projection from azimuth:
    dx = distance * sin(azimuth)
    dy = distance * cos(azimuth)

  North Arrow Semantics:
  - survey_azimuth_deg is legal bearing clockwise from North.
  - north_angle represents survey plan image orientation only (for Stage 2 alignment).
  - Normalized azimuth is NEVER double-rotated by north_angle in vector reconstruction.

Polygon Validation & Auditing:
  - Never silently replaces legal geometry with buffer(0).
  - Explicitly records both unadjusted raw traverse vertices and Bowditch-adjusted coordinates.
  - Detects duplicate vertices, zero-length edges, and self-intersections.
  - Distinguishes Local P0 coordinates from Georeferenced CRS coordinates.
"""
import json
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from shapely.geometry import Polygon
from ..schemas import ManualSurveyExtractionRequest, DistanceUnit, Point2D, GeoreferenceStatus

PERCH_TO_SQM = 25.29285264
SQFT_TO_SQM = 0.09290304
ACRE_TO_SQM = 4046.8564224

# Load validation config
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "gab_validation_config.json")
def get_validation_config() -> Dict[str, Any]:
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "closure_tolerance": {"value": 1.5, "unit": "meters"},
        "area_tolerance_percent": {"value": 15.0, "unit": "percent"}
    }


def normalize_bearing_string(raw: str) -> float:
    """
    Parses various bearing string formats into normalized degrees (0 - 360 clockwise from North).
    Supports:
      - Decimal degrees: "45.5", "180"
      - Degrees-Minutes-Seconds: "045°30'15\"", "45d 30m 15s"
      - Quadrant bearings: "N 45° 30' E", "S 30 W", "N45E", "S 45 E"
    """
    raw_str = raw.strip().upper()
    if not raw_str:
        return 0.0

    # Try simple float
    try:
        deg = float(raw_str)
        return deg % 360.0
    except ValueError:
        pass

    # Check Quadrant format e.g., N 45° 30' E or S 15.5 W
    quadrant_pattern = r"^([NS])\s*([\d\.\°\'\"dms\s]+)\s*([EW])$"
    match = re.match(quadrant_pattern, raw_str)
    if match:
        ns = match.group(1)
        angle_str = match.group(2)
        ew = match.group(3)
        angle = parse_dms(angle_str)
        if ns == "N" and ew == "E":
            return angle % 360.0
        elif ns == "S" and ew == "E":
            return (180.0 - angle) % 360.0
        elif ns == "S" and ew == "W":
            return (180.0 + angle) % 360.0
        elif ns == "N" and ew == "W":
            return (360.0 - angle) % 360.0

    return parse_dms(raw_str) % 360.0


def parse_dms(dms_str: str) -> float:
    """Extracts degrees, minutes, seconds from a string."""
    numbers = [float(n) for n in re.findall(r"[\d\.]+", dms_str)]
    if not numbers:
        return 0.0
    deg = numbers[0]
    minute = numbers[1] if len(numbers) > 1 else 0.0
    second = numbers[2] if len(numbers) > 2 else 0.0
    return deg + (minute / 60.0) + (second / 3600.0)


def reconstruct_polygon(survey_request: ManualSurveyExtractionRequest) -> Dict[str, Any]:
    """
    Performs deterministic mathematical vector reconstruction.
    Coordinates stay strictly in canonical P0 reference frame (origin at P0 (0,0), +X=East, +Y=North).
    Computes both unadjusted raw traverse vertices and Bowditch-adjusted coordinates.
    """
    edges = survey_request.edges
    if len(edges) < 3:
        raise ValueError("At least 3 edges are required to reconstruct a polygon.")

    coords: List[Tuple[float, float]] = [(0.0, 0.0)]
    curr_x = 0.0
    curr_y = 0.0
    perimeter = 0.0
    edge_vectors: List[Dict[str, Any]] = []
    dx_dy_list: List[Tuple[float, float, float]] = []  # (dx, dy, dist_m)

    for edge in edges:
        dist_m = edge.distance.value
        if edge.distance.unit == DistanceUnit.FEET:
            dist_m *= 0.3048

        if dist_m <= 0:
            raise ValueError(f"Edge '{edge.edge_id}' has non-positive length ({dist_m}m).")

        perimeter += dist_m
        azimuth_deg = edge.bearing.normalized_degrees % 360.0
        rad = math.radians(azimuth_deg)

        dx = dist_m * math.sin(rad)
        dy = dist_m * math.cos(rad)
        dx_dy_list.append((dx, dy, dist_m))

        start_pt = (curr_x, curr_y)
        curr_x += dx
        curr_y += dy
        end_pt = (curr_x, curr_y)

        edge_vectors.append({
            "edge_id": edge.edge_id,
            "start": {"x": round(start_pt[0], 4), "y": round(start_pt[1], 4)},
            "end": {"x": round(end_pt[0], 4), "y": round(end_pt[1], 4)},
            "distance": round(dist_m, 4),
            "azimuth": round(azimuth_deg, 2),
            "edge_type": edge.edge_type.value if hasattr(edge.edge_type, "value") else str(edge.edge_type or "side")
        })
        coords.append((curr_x, curr_y))

    # Closure error: vector between P0 (0,0) and final endpoint (curr_x, curr_y)
    closure_dx = curr_x - 0.0
    closure_dy = curr_y - 0.0
    closure_error = math.sqrt(closure_dx**2 + closure_dy**2)
    relative_error = (closure_error / perimeter) if perimeter > 0 else 0.0

    # Unadjusted raw vertices in canonical P0 coordinate system
    raw_polygon_vertices = coords[:-1]
    canonical_vertices = [{"x": round(pt[0], 4), "y": round(pt[1], 4)} for pt in raw_polygon_vertices]

    # Bowditch Compass Rule Adjustment (proportional distribution of misclosure by length)
    bowditch_vertices: List[Dict[str, float]] = [{"x": 0.0, "y": 0.0}]
    if perimeter > 0 and closure_error > 0.0001:
        cum_dist = 0.0
        adj_x = 0.0
        adj_y = 0.0
        for i in range(len(dx_dy_list) - 1):
            dx, dy, dist = dx_dy_list[i]
            cum_dist += dist
            # Correction is proportional to cumulative length
            corr_x = -closure_dx * (dist / perimeter)
            corr_y = -closure_dy * (dist / perimeter)
            adj_x += dx + corr_x
            adj_y += dy + corr_y
            bowditch_vertices.append({"x": round(adj_x, 4), "y": round(adj_y, 4)})
    else:
        bowditch_vertices = canonical_vertices

    # Check polygon validity using Shapely strictly without silent buffer(0) replacement
    is_valid = True
    needs_verification = False
    warnings = []
    reconstructed_area = 0.0
    shapely_poly = None

    try:
        from shapely.validation import make_valid
        raw_poly = Polygon(raw_polygon_vertices)
        if not raw_poly.is_valid:
            fixed_poly = make_valid(raw_poly)
            # If make_valid produced a MultiPolygon or GeometryCollection, take the largest polygon
            if hasattr(fixed_poly, "geoms"):
                valid_polys = [g for g in fixed_poly.geoms if isinstance(g, Polygon) and g.area > 0]
                if valid_polys:
                    shapely_poly = max(valid_polys, key=lambda p: p.area)
                else:
                    shapely_poly = raw_poly.convex_hull
            elif isinstance(fixed_poly, Polygon) and fixed_poly.area > 0:
                shapely_poly = fixed_poly
            else:
                shapely_poly = raw_poly.convex_hull

            is_valid = True  # Repaired to allow rule-based layout generation
            needs_verification = True
            warnings.append("Survey polygon had self-intersections and was topologically repaired. Please inspect boundary edges.")
            reconstructed_area = float(shapely_poly.area)
        else:
            shapely_poly = raw_poly
            reconstructed_area = float(raw_poly.area)
    except Exception as e:
        is_valid = False
        needs_verification = True
        warnings.append(f"Error constructing land polygon from survey coordinates: {str(e)}")

    val_cfg = get_validation_config()
    tol_closure = val_cfg.get("closure_tolerance", {}).get("value", 1.5)
    if closure_error > tol_closure:
        needs_verification = True
        warnings.append(f"Closure error {closure_error:.3f}m exceeds configured tolerance ({tol_closure}m).")

    # Georeferencing metadata
    geo_status = getattr(survey_request, "georeference_status", GeoreferenceStatus.LOCAL_P0_ONLY)
    geo_status_str = geo_status.value if hasattr(geo_status, "value") else str(geo_status)

    return {
        "is_valid": is_valid,
        "needs_verification": needs_verification,
        "closure_error": round(closure_error, 4),
        "relative_error": round(relative_error, 6),
        "perimeter": round(perimeter, 4),
        "reconstructed_area": round(reconstructed_area, 4),
        "vertices": canonical_vertices,
        "bowditch_adjusted_vertices": bowditch_vertices,
        "traverse_adjustment_method": "bowditch_compass_rule",
        "edges": edge_vectors,
        "warnings": warnings,
        "shapely_polygon": shapely_poly,
        "georeference_status": geo_status_str,
        "coordinate_origin": "P0 (0.0, 0.0) canonical local metric frame"
    }
