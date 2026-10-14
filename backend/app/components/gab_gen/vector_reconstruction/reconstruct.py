"""
Trigonometric coordinate reconstruction and land polygon validation using Shapely and Python math.
Calculates:
  Δx = d * sin(θ)  [in standard surveying where θ=0 is North, clockwise]
  or standard Cartesian rotation.
Produces:
  Ordered X-Y vertices, closed legal polygon, closure error, perimeter, and area.
"""
import math
import re
from typing import Any, Dict, List, Optional, Tuple
from shapely.geometry import Polygon, LinearRing
from ..schemas import ManualSurveyExtractionRequest, DistanceUnit, Point2D


PERCH_TO_SQM = 25.29285264
SQFT_TO_SQM = 0.09290304


def normalize_bearing_string(raw: str) -> float:
    """
    Parses various bearing string formats into normalized degrees (0 - 360 clockwise from North).
    Supports:
      - Decimal degrees: "45.5", "180"
      - Degrees-Minutes-Seconds: "045°30'15\"", "45d 30m 15s"
      - Quadrant bearings: "N 45° 30' E", "S 30 W", "N45E"
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
    Surveying standard coordinate system:
      North is along +Y (azimuth = 0°).
      East is along +X (azimuth = 90°).
      Δx = distance * sin(azimuth)
      Δy = distance * cos(azimuth)
    """
    edges = survey_request.edges
    if len(edges) < 3:
        raise ValueError("At least 3 edges are required to reconstruct a polygon.")

    coords: List[Tuple[float, float]] = [(0.0, 0.0)]
    curr_x = 0.0
    curr_y = 0.0
    perimeter = 0.0
    edge_vectors: List[Dict[str, Any]] = []

    for edge in edges:
        dist_m = edge.distance.value
        if edge.distance.unit == DistanceUnit.FEET:
            dist_m *= 0.3048
        
        perimeter += dist_m
        azimuth_deg = edge.bearing.normalized_degrees
        
        # Adjust with north orientation angle if provided
        adjusted_azimuth = (azimuth_deg + survey_request.north_angle) % 360.0
        rad = math.radians(adjusted_azimuth)

        dx = dist_m * math.sin(rad)
        dy = dist_m * math.cos(rad)

        start_pt = (curr_x, curr_y)
        curr_x += dx
        curr_y += dy
        end_pt = (curr_x, curr_y)

        edge_vectors.append({
            "edge_id": edge.edge_id,
            "start": {"x": round(start_pt[0], 4), "y": round(start_pt[1], 4)},
            "end": {"x": round(end_pt[0], 4), "y": round(end_pt[1], 4)},
            "distance": round(dist_m, 4),
            "azimuth": round(adjusted_azimuth, 2),
            "edge_type": edge.edge_type.value if edge.edge_type else "side"
        })
        coords.append((curr_x, curr_y))

    # Closure error: distance between start (0,0) and final endpoint
    closure_dx = curr_x - 0.0
    closure_dy = curr_y - 0.0
    closure_error = math.sqrt(closure_dx**2 + closure_dy**2)
    relative_error = (closure_error / perimeter) if perimeter > 0 else 0.0

    # Ensure closed ring for Shapely
    # If closure error is within reasonable surveying precision tolerance (e.g. 1.0m or 1/50 perimeter),
    # close the ring with the origin (0, 0)
    polygon_vertices = coords[:-1]  # Exclude loose endpoint, start is already (0,0)
    
    # Check polygon validity using Shapely
    is_valid = True
    warnings = []
    reconstructed_area = 0.0
    shapely_poly = None

    try:
        shapely_poly = Polygon(polygon_vertices)
        if not shapely_poly.is_valid:
            # Try buffer(0) if slight self-intersection
            repaired = shapely_poly.buffer(0)
            if isinstance(repaired, Polygon) and repaired.is_valid and repaired.area > 0:
                shapely_poly = repaired
                warnings.append("Polygon had self-intersection repaired by zero-buffer.")
            else:
                is_valid = False
                warnings.append(f"Polygon is topologically invalid: {shapely_poly.is_valid}")
        reconstructed_area = float(shapely_poly.area)
    except Exception as e:
        is_valid = False
        warnings.append(f"Error creating polygon: {str(e)}")

    # Shift coordinates so minimum bounding box corner is at (0, 0) for intuitive layout
    min_x = min(pt[0] for pt in polygon_vertices)
    min_y = min(pt[1] for pt in polygon_vertices)
    normalized_vertices = [{"x": round(pt[0] - min_x, 4), "y": round(pt[1] - min_y, 4)} for pt in polygon_vertices]

    return {
        "is_valid": is_valid,
        "closure_error": round(closure_error, 4),
        "relative_error": round(relative_error, 6),
        "perimeter": round(perimeter, 4),
        "reconstructed_area": round(reconstructed_area, 4),
        "vertices": normalized_vertices,
        "edges": edge_vectors,
        "warnings": warnings,
        "shapely_polygon": shapely_poly
    }
