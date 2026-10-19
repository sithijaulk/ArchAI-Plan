"""
Geometry Primitives and Validation Module
Implements deterministic 2D room spatial calculations using Shapely:
polygon validation, containment checks, coordinate transformation,
bounding boxes, and door/window opening clearance zones.
NOTE: Stage 1 does NOT implement Genetic Algorithms or auto-layout placement.
"""
from typing import List, Tuple, Optional, Dict, Any
from shapely.geometry import Polygon, Point, LineString, box
from shapely.validation import explain_validity

from .contracts import Coordinate2D, Dimensions3D, DoorDTO, WindowDTO


def create_polygon_from_coordinates(coords: List[Coordinate2D]) -> Polygon:
    """Create a Shapely Polygon from a list of Coordinate2D points."""
    if len(coords) < 3:
        raise ValueError(f"Polygon requires at least 3 points, got {len(coords)}")
    raw_points = [(c.x, c.y) for c in coords]
    return Polygon(raw_points)


def validate_room_polygon(coords: List[Coordinate2D]) -> Tuple[bool, Optional[str], float]:
    """
    Validates a room boundary polygon:
    - Minimum 3 points
    - Finite numerical values
    - Valid non-self-intersecting ring
    - Positive usable area
    Returns: (is_valid, error_message, area_sqm)
    """
    if len(coords) < 3:
        return False, f"Room boundary requires at least 3 points, received {len(coords)}.", 0.0

    raw_points = []
    for i, c in enumerate(coords):
        if not isinstance(c.x, (int, float)) or not isinstance(c.y, (int, float)):
            return False, f"Coordinate at index {i} has non-numeric values ({c.x}, {c.y}).", 0.0
        raw_points.append((float(c.x), float(c.y)))

    poly = Polygon(raw_points)

    if not poly.is_valid:
        reason = explain_validity(poly)
        return False, f"Room polygon is topologically invalid: {reason}.", 0.0

    if poly.is_empty:
        return False, "Room polygon is empty.", 0.0

    area = poly.area
    if area <= 0.0001:
        return False, f"Room polygon area must be positive, got {area:.4f} m².", 0.0

    return True, None, round(area, 4)


def get_polygon_bounding_box(coords: List[Coordinate2D]) -> Tuple[float, float, float, float]:
    """Returns (min_x, min_y, max_x, max_y) for the coordinates."""
    poly = create_polygon_from_coordinates(coords)
    return poly.bounds


def is_point_inside_room(point: Coordinate2D, room_coords: List[Coordinate2D]) -> bool:
    """Check whether a 2D point is contained inside the room boundary polygon."""
    poly = create_polygon_from_coordinates(room_coords)
    pt = Point(point.x, point.y)
    return poly.contains(pt) or poly.touches(pt)


def compute_footprint_polygon(
    center: Coordinate2D,
    dimensions: Dimensions3D,
    rotation_deg: int
) -> Polygon:
    """
    Computes a 2D bounding polygon for an asset given its center, width, depth, and 0/90/180/270 rotation.
    For 0 or 180 degrees: width is along X, depth is along Y.
    For 90 or 270 degrees: depth is along X, width is along Y.
    """
    if rotation_deg in (90, 270):
        dx = dimensions.depth / 2.0
        dy = dimensions.width / 2.0
    else:
        dx = dimensions.width / 2.0
        dy = dimensions.depth / 2.0

    min_x = center.x - dx
    max_x = center.x + dx
    min_y = center.y - dy
    max_y = center.y + dy

    return box(min_x, min_y, max_x, max_y)


def is_footprint_within_room(
    footprint: Polygon,
    room_coords: List[Coordinate2D]
) -> bool:
    """Checks if the asset footprint polygon is entirely contained within the room polygon."""
    room_poly = create_polygon_from_coordinates(room_coords)
    return room_poly.contains(footprint)


def check_collision(poly_a: Polygon, poly_b: Polygon) -> bool:
    """Check if two geometric polygons intersect with positive overlap area."""
    if not poly_a.intersects(poly_b):
        return False
    intersection = poly_a.intersection(poly_b)
    # Ignore boundary touches
    return intersection.area > 0.0001


def compute_geometry_fingerprint(structural_input: Any) -> str:
    """
    Computes a deterministic SHA-256 fingerprint of the authoritative structural geometry.
    Covers:
    - unit
    - floors (ordered by floor_id)
    - rooms (ordered by room_id): coordinates, area, elevation, ceiling height
    - walls (ordered by id): start, end, thickness
    - openings (doors, windows ordered by id): start, end, width/length
    Unrelated changes (client preferences, metadata, reports, exterior landscape)
    do NOT alter this fingerprint.
    """
    import hashlib
    import json

    floors_data = []
    for fl in sorted(structural_input.floors, key=lambda f: str(f.floor_id)):
        rooms_data = []
        for rm in sorted(fl.rooms, key=lambda r: str(r.room_id)):
            poly_coords = [[round(pt.x, 4), round(pt.y, 4)] for pt in rm.polygon]
            doors_data = [
                {
                    "id": d.id,
                    "start": [round(d.start.x, 4), round(d.start.y, 4)],
                    "end": [round(d.end.x, 4), round(d.end.y, 4)],
                    "width": round(d.leaf_width, 4)
                }
                for d in sorted(rm.doors, key=lambda d: str(d.id))
            ]
            windows_data = [
                {
                    "id": w.id,
                    "start": [round(w.start.x, 4), round(w.start.y, 4)],
                    "end": [round(w.end.x, 4), round(w.end.y, 4)],
                    "length": round(w.length, 4)
                }
                for w in sorted(rm.windows, key=lambda w: str(w.id))
            ]
            rooms_data.append({
                "room_id": rm.room_id,
                "room_type": rm.room_type.value if hasattr(rm.room_type, "value") else str(rm.room_type),
                "area_sqm": round(rm.area_sqm, 3),
                "polygon": poly_coords,
                "ceiling_height": round(rm.ceiling_height, 2) if rm.ceiling_height else None,
                "doors": doors_data,
                "windows": windows_data
            })

        walls_data = [
            {
                "id": w.id,
                "start": [round(w.start.x, 4), round(w.start.y, 4)],
                "end": [round(w.end.x, 4), round(w.end.y, 4)],
                "thickness": round(w.thickness, 4)
            }
            for w in sorted(getattr(fl, "walls", []), key=lambda w: str(w.id))
        ]

        floors_data.append({
            "floor_id": fl.floor_id,
            "elevation": round(fl.elevation, 3) if fl.elevation else 0.0,
            "rooms": rooms_data,
            "walls": walls_data
        })

    canonical_obj = {
        "unit": structural_input.unit.value if hasattr(structural_input.unit, "value") else str(structural_input.unit),
        "floors": floors_data
    }
    encoded = json.dumps(canonical_obj, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()

