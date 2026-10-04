from __future__ import annotations

from typing import Any, Mapping

from shapely.geometry import LineString, Point, box, mapping
from shapely.geometry.base import BaseGeometry

from .rule_repository import elia_rules


def place_outdoor_elements(residual: BaseGeometry, blocked: BaseGeometry, requirements: Mapping[str, Any],
                           gate: Mapping[str, Any] | None, land: BaseGeometry | None = None,
                           driveway: BaseGeometry | None = None, paths: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    landscape = requirements.get("landscape", {})
    elements = []
    dimensions = elia_rules()["outdoor_elements"]
    garden_ground = residual.difference(blocked)
    if landscape.get("garden_required"):
        elements.append({"json_id": "GARDEN_ZONE_001", "type": "garden_zone",
                         "geometry": mapping(garden_ground) if not garden_ground.is_empty else None,
                         "area_m2": garden_ground.area, "validation": {"valid": not garden_ground.is_empty}})
    if landscape.get("lawn_required"):
        elements.append({"json_id": "LAWN_ZONE_001", "type": "lawn_zone",
                         "geometry": mapping(garden_ground) if not garden_ground.is_empty else None,
                         "area_m2": garden_ground.area, "validation": {"valid": not garden_ground.is_empty},
                         "render": {"asset_id": "lawn_generic_01", "visible": True}})
    requested = []
    if landscape.get("garden_table_set_required"):
        requested.append(("garden_table_set", dimensions["garden_table_set_width_m"], dimensions["garden_table_set_depth_m"]))
    if landscape.get("garden_seating_required"):
        requested.append(("garden_seating", dimensions["garden_seating_width_m"], dimensions["garden_seating_depth_m"]))
    for name, width, depth in requested:
        placement = _find_footprint(residual, blocked, width, depth)
        if placement is None:
            elements.append({"json_id": f"{name.upper()}_001", "type": name, "validation": {"valid": False, "reason": "no_residual_space"}})
        else:
            center, footprint = placement
            elements.append({"json_id": f"{name.upper()}_001", "type": name,
                             "position": [center.x, center.y], "dimensions": {"width_m": width, "depth_m": depth},
                             "polygon": list(footprint.exterior.coords), "validation": {"valid": True},
                             "render": {"asset_id": f"{name}_generic_01", "visible": True}})
    for key, required in (("pedestrian_path_required", "pedestrian_path"), ("garden_path_required", "garden_path")):
        if landscape.get(key):
            path = (paths or {}).get(required)
            if path:
                elements.append({"json_id": f"{required.upper()}_001", "type": required,
                                 **path, "validation": {"valid": path.get("valid", False), "reason": path.get("reason")},
                                 "render": {"visible": True}})
            else:
                elements.append({"json_id": f"{required.upper()}_001", "type": required,
                                 "validation": {"valid": False, "reason": "no_feasible_route"}})
    if landscape.get("boundary_wall_required"):
        wall = None
        if land is not None and gate is not None:
            wall = land.boundary
            for gate_item in [gate, *gate.get("additional_gates", [])]:
                wall = wall.difference(Point(gate_item["position"]).buffer(float(gate_item["width"]) / 2))
        elements.append({"json_id": "BOUNDARY_WALL_001", "type": "boundary_wall",
                         "geometry": None if wall is None else mapping(wall),
                         "boundary": "land_polygon.exterior", "height_m": landscape.get("boundary_wall_height"),
                         "wall_type": landscape.get("boundary_wall_type"),
                         "gate_openings": [] if gate is None else [
                             {"gate_json_id": item["json_id"], "width_m": item["width"]}
                             for item in [gate, *gate.get("additional_gates", [])]
                         ],
                         "validation": {"valid": wall is not None, "follows_legal_land_boundary": wall is not None}})
    return elements


def _find_footprint(residual: BaseGeometry, blocked: BaseGeometry, width: float, depth: float):
    if residual.is_empty:
        return None
    min_x, min_y, max_x, max_y = residual.bounds
    step = max(width / 2, float(elia_rules()["outdoor_elements"]["candidate_grid_spacing_m"]))
    candidates = []
    y = min_y + depth / 2
    while y <= max_y - depth / 2:
        x = min_x + width / 2
        while x <= max_x - width / 2:
            center = Point(x, y)
            footprint = box(x - width / 2, y - depth / 2, x + width / 2, y + depth / 2)
            if residual.covers(footprint) and not footprint.intersects(blocked):
                candidates.append((center, footprint))
            x += step
        y += step
    return min(candidates, key=lambda item: (item[0].y, item[0].x)) if candidates else None
