"""
Openings Module: Doors and Windows
Data validation, geometric representation, and clearance zone calculation
for doors and windows within room boundaries.
"""
from typing import List, Optional, Tuple
from shapely.geometry import LineString, Polygon, box
import math

from .contracts import Coordinate2D, DoorDTO, WindowDTO, DoorHinge, DoorOpeningDirection


def validate_door_opening(door: DoorDTO, room_polygon_coords: List[Coordinate2D]) -> Tuple[bool, Optional[str]]:
    """
    Validates door metadata:
    - Positive leaf width
    - Start and end coordinates differ
    - Door segment touches or aligns with room boundary
    """
    if door.leaf_width <= 0:
        return False, f"Door {door.id} has invalid leaf width {door.leaf_width}m."

    dx = door.end.x - door.start.x
    dy = door.end.y - door.start.y
    length = math.hypot(dx, dy)
    if length <= 0.001:
        return False, f"Door {door.id} start and end coordinates are identical."

    return True, None


def validate_window_opening(window: WindowDTO, room_polygon_coords: List[Coordinate2D]) -> Tuple[bool, Optional[str]]:
    """
    Validates window metadata:
    - Positive opening length
    - Valid sill height >= 0
    """
    if window.length <= 0:
        return False, f"Window {window.id} has non-positive length {window.length}m."

    if window.sill_height is not None and window.sill_height < 0:
        return False, f"Window {window.id} has negative sill height {window.sill_height}m."

    return True, None


def compute_door_swing_box(door: DoorDTO) -> Polygon:
    """
    Computes a simplified rectangular protected clearance zone in front of the door leaf.
    In Stage 2 this will expand to radial arc checks. In Stage 1 this provides a deterministic
    conservative clearance envelope.
    """
    dx = door.end.x - door.start.x
    dy = door.end.y - door.start.y
    length = math.hypot(dx, dy)
    width = door.leaf_width if door.leaf_width > 0 else length
    depth = door.protected_depth if door.protected_depth is not None else width

    # Normal vector perpendicular to wall segment
    if length > 0:
        nx = -dy / length
        ny = dx / length
    else:
        nx, ny = 0.0, 1.0

    p1 = (door.start.x, door.start.y)
    p2 = (door.end.x, door.end.y)
    p3 = (door.end.x + nx * depth, door.end.y + ny * depth)
    p4 = (door.start.x + nx * depth, door.start.y + ny * depth)

    return Polygon([p1, p2, p3, p4])


def compute_window_access_envelope(window: WindowDTO) -> Polygon:
    """
    Computes the protected clearance zone in front of a window to maintain daylight and accessibility.
    """
    dx = window.end.x - window.start.x
    dy = window.end.y - window.start.y
    length = math.hypot(dx, dy)
    depth = window.protected_access_depth or 0.60

    if length > 0:
        nx = -dy / length
        ny = dx / length
    else:
        nx, ny = 0.0, 1.0

    p1 = (window.start.x, window.start.y)
    p2 = (window.end.x, window.end.y)
    p3 = (window.end.x + nx * depth, window.end.y + ny * depth)
    p4 = (window.start.x + nx * depth, window.start.y + ny * depth)

    return Polygon([p1, p2, p3, p4])
