from __future__ import annotations

from math import isfinite
from typing import Any, Mapping, Sequence

from shapely.geometry import LineString, Point, box, mapping
from shapely.geometry.base import BaseGeometry

from .exceptions import ELIAError
from .rule_repository import elia_rules


def place_outdoor_elements(residual: BaseGeometry, blocked: BaseGeometry, requirements: Mapping[str, Any],
                           gate: Mapping[str, Any] | None, land: BaseGeometry | None = None,
                           driveway: BaseGeometry | None = None, paths: Mapping[str, Any] | None = None,
                           locked_features: Sequence[Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    landscape = requirements.get("landscape", {})
    elements = []
    dimensions = elia_rules()["outdoor_elements"]
    garden_ground = residual.difference(blocked)
    used_ids: set[str] = set()

    # 1. Process Locked Outdoor Features First
    if locked_features is None:
        locked_features = requirements.get("locked_features") or []

    for locked in locked_features:
        feat_type = str(locked.get("category") or locked.get("feature_type") or locked.get("type") or "").lower()
        if feat_type not in {"garden_seating", "garden_table_set", "seating", "dining", "outdoor_seating"}:
            continue
        jid = str(locked.get("json_id") or "").strip()
        if not jid:
            raise ELIAError("ELIA_INVALID_LOCKED_FEATURE", "Locked outdoor feature missing valid identifier.")
        pos = locked.get("position")
        if not (isinstance(pos, (list, tuple)) and len(pos) == 2):
            raise ELIAError("ELIA_INVALID_LOCKED_FEATURE", f"Locked outdoor feature '{jid}' has invalid position.")
        try:
            px, py = float(pos[0]), float(pos[1])
        except (TypeError, ValueError) as exc:
            raise ELIAError("ELIA_INVALID_LOCKED_FEATURE", f"Locked outdoor feature '{jid}' coordinates must be numeric.") from exc
        if not (isfinite(px) and isfinite(py)):
            raise ELIAError("ELIA_INVALID_LOCKED_FEATURE", f"Locked outdoor feature '{jid}' coordinates must be finite.")

        dims = locked.get("dimensions") or {}
        w = float(dims.get("width_m") or dims.get("width") or dimensions.get(f"{feat_type}_width_m", 1.5))
        d = float(dims.get("depth_m") or dims.get("depth") or dimensions.get(f"{feat_type}_depth_m", 1.5))
        if w <= 0 or d <= 0 or not isfinite(w) or not isfinite(d):
            raise ELIAError("ELIA_INVALID_LOCKED_FEATURE", f"Locked outdoor feature '{jid}' dimensions must be positive and finite.")

        footprint = box(px - w / 2, py - d / 2, px + w / 2, py + d / 2)
        if land is not None and not land.covers(footprint):
            raise ELIAError("ELIA_LOCKED_FEATURE_CONFLICT", f"Locked outdoor feature '{jid}' falls outside permissible land boundary.")
        if footprint.intersects(blocked):
            raise ELIAError("ELIA_LOCKED_FEATURE_CONFLICT", f"Locked outdoor feature '{jid}' conflicts with boundary, obstacle, or prior locked feature.")

        locked_entry = dict(locked)
        locked_entry["locked"] = True
        locked_entry["position"] = [px, py]
        locked_entry["dimensions"] = {"width_m": w, "depth_m": d}
        locked_entry["polygon"] = list(footprint.exterior.coords)
        locked_entry["validation"] = {"valid": True}
        elements.append(locked_entry)
        used_ids.add(jid)
        blocked = blocked.union(footprint)

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
        elem_id = f"{name.upper()}_001"
        idx = 1
        while elem_id in used_ids:
            idx += 1
            elem_id = f"{name.upper()}_{idx:03d}"
        used_ids.add(elem_id)

        if placement is None:
            elements.append({"json_id": elem_id, "type": name, "validation": {"valid": False, "reason": "no_residual_space"}})
        else:
            center, footprint = placement
            blocked = blocked.union(footprint)
            elements.append({"json_id": elem_id, "type": name,
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
                         "boundary": "land_polygon.exterior", "height_m": landscape.get("boundary_wall_height_m"),
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

    estimated_cells = ((max_x - min_x) / step) * ((max_y - min_y) / step)
    if estimated_cells > elia_rules()["access"].get("max_grid_cells", 200000):
        raise ELIAError("ELIA_PLANNING_LIMIT_EXCEEDED", "Search limit exhausted for outdoor elements.")

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

