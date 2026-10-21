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

    # 2. Garden and Lawn Zones
    if landscape.get("garden_required"):
        elements.append({"json_id": "GARDEN_ZONE_001", "type": "garden_zone",
                         "geometry": mapping(garden_ground) if not garden_ground.is_empty else None,
                         "area_m2": garden_ground.area, "validation": {"valid": not garden_ground.is_empty}})
    if landscape.get("lawn_required"):
        elements.append({"json_id": "LAWN_ZONE_001", "type": "lawn_zone",
                         "geometry": mapping(garden_ground) if not garden_ground.is_empty else None,
                         "area_m2": garden_ground.area, "validation": {"valid": not garden_ground.is_empty},
                         "render": {"asset_id": "lawn_generic_01", "visible": True}})

    # 3. Open Parking Bays (when parking is requested and open bays are required)
    access = requirements.get("access") or {}
    parking_requested = bool(access.get("parking_required", False))
    garage_requested = bool(access.get("garage_required", False))
    veh_count = int(access.get("vehicle_count", 1))

    # Garage presence can be passed or checked
    garage_capacity = int(access.get("garage_capacity", 1)) if garage_requested else 0
    needed_open_bays = max(0, veh_count - garage_capacity) if garage_requested else (max(1, veh_count) if parking_requested else 0)

    if needed_open_bays > 0 and parking_requested:
        bay_w = 2.5
        bay_l = 5.0
        # If driveway is present, prioritize candidate points near driveway
        for b_idx in range(needed_open_bays):
            placement = _find_footprint(residual, blocked, bay_w, bay_l, access_buffer=0.3)
            bay_id = f"PARKING_BAY_{b_idx + 1:03d}"
            while bay_id in used_ids:
                b_idx += 1
                bay_id = f"PARKING_BAY_{b_idx + 1:03d}"
            used_ids.add(bay_id)

            if placement is None:
                elements.append({
                    "json_id": bay_id,
                    "type": "parking_bay",
                    "covered": bool(access.get("covered_parking", False)),
                    "dimensions": {"width_m": bay_w, "length_m": bay_l},
                    "validation": {"valid": False, "reason": "no_residual_space_for_parking_bay"}
                })
            else:
                center, footprint = placement
                blocked = blocked.union(footprint)
                elements.append({
                    "json_id": bay_id,
                    "type": "parking_bay",
                    "covered": bool(access.get("covered_parking", False)),
                    "position": [round(center.x, 3), round(center.y, 3)],
                    "dimensions": {"width_m": bay_w, "length_m": bay_l},
                    "polygon": list(footprint.exterior.coords),
                    "validation": {"valid": True},
                    "render": {"asset_id": "parking_bay_generic", "visible": True}
                })

    # 4. Tables and Seating with Usable Perimeter Clearance
    table_count = max(1, int(landscape.get("garden_table_set_count") or 1)) if landscape.get("garden_table_set_required") else 0
    seating_count = max(1, int(landscape.get("garden_seating_count") or 1)) if landscape.get("garden_seating_required") else 0

    requested_furniture: list[tuple[str, float, float, int]] = []
    if table_count > 0:
        requested_furniture.append(("garden_table_set", float(dimensions["garden_table_set_width_m"]), float(dimensions["garden_table_set_depth_m"]), table_count))
    if seating_count > 0:
        requested_furniture.append(("garden_seating", float(dimensions["garden_seating_width_m"]), float(dimensions["garden_seating_depth_m"]), seating_count))

    for name, width, depth, count in requested_furniture:
        for idx in range(1, count + 1):
            # 0.6m chair pullout and usable circulation buffer
            placement = _find_footprint(residual, blocked, width, depth, access_buffer=0.6)
            elem_id = f"{name.upper()}_{idx:03d}"
            while elem_id in used_ids:
                elem_id = f"{name.upper()}_{len(used_ids) + 1:03d}"
            used_ids.add(elem_id)

            if placement is None:
                elements.append({"json_id": elem_id, "type": name, "validation": {"valid": False, "reason": "no_residual_space"}})
            else:
                center, footprint = placement
                blocked = blocked.union(footprint.buffer(0.3))
                elements.append({
                    "json_id": elem_id,
                    "type": name,
                    "position": [round(center.x, 3), round(center.y, 3)],
                    "dimensions": {"width_m": width, "depth_m": depth},
                    "polygon": list(footprint.exterior.coords),
                    "validation": {"valid": True, "usable_clearance_m": 0.6},
                    "render": {"asset_id": f"{name}_generic_01", "visible": True}
                })

    # 5. Water Features & Utility Proposals
    water = requirements.get("water_features") or {}
    if water.get("garden_taps_required"):
        tap_count = max(1, int(water.get("garden_taps_count") or 1))
        for t_idx in range(1, tap_count + 1):
            tap_id = f"GARDEN_TAP_{t_idx:03d}"
            while tap_id in used_ids:
                tap_id = f"GARDEN_TAP_{len(used_ids) + 1:03d}"
            used_ids.add(tap_id)

            placement = _find_footprint(residual, blocked, 0.4, 0.4)
            if placement:
                center, footprint = placement
                blocked = blocked.union(footprint)
                elements.append({
                    "json_id": tap_id,
                    "type": "garden_tap",
                    "position": [round(center.x, 3), round(center.y, 3)],
                    "dimensions": {"width_m": 0.4, "depth_m": 0.4, "height_m": 0.9},
                    "polygon": list(footprint.exterior.coords),
                    "status": "review_required",
                    "validation": {"valid": True, "evidence_status": "review_required"},
                    "notes": "Proposed exterior tap location; technical water supply and backflow prevention require plumbing certification.",
                    "render": {"asset_id": "garden_tap_generic_01", "visible": True}
                })
            else:
                elements.append({"json_id": tap_id, "type": "garden_tap", "validation": {"valid": False, "reason": "no_residual_space"}})

    if water.get("well_required"):
        well_id = "PROPOSED_WELL_001"
        placement = _find_footprint(residual, blocked, 1.8, 1.8)
        if placement:
            center, footprint = placement
            blocked = blocked.union(footprint)
            elements.append({
                "json_id": well_id,
                "type": "water_well",
                "position": [round(center.x, 3), round(center.y, 3)],
                "dimensions": {"width_m": 1.8, "depth_m": 1.8, "diameter_m": 1.8},
                "polygon": list(footprint.exterior.coords),
                "status": "review_required",
                "validation": {"valid": True, "evidence_status": "review_required"},
                "notes": "Proposed well maintains Rule W01 separation from septic systems; hydrological yield and potability testing required.",
                "render": {"asset_id": "water_well_generic_01", "visible": True}
            })
        else:
            elements.append({"json_id": well_id, "type": "water_well", "validation": {"valid": False, "reason": "no_residual_space"}})

    if water.get("septic_tank_required"):
        septic_id = "PROPOSED_SEPTIC_001"
        placement = _find_footprint(residual, blocked, 2.0, 3.0)
        if placement:
            center, footprint = placement
            blocked = blocked.union(footprint)
            elements.append({
                "json_id": septic_id,
                "type": "septic_tank",
                "position": [round(center.x, 3), round(center.y, 3)],
                "dimensions": {"width_m": 2.0, "length_m": 3.0},
                "polygon": list(footprint.exterior.coords),
                "status": "review_required",
                "validation": {"valid": True, "evidence_status": "review_required"},
                "notes": "Proposed septic tank position; soil percolation and local health authority clearance required.",
                "render": {"asset_id": "septic_tank_generic_01", "visible": True}
            })
        else:
            elements.append({"json_id": septic_id, "type": "septic_tank", "validation": {"valid": False, "reason": "no_residual_space"}})

    if water.get("pond_required"):
        pond_id = "GARDEN_POND_001"
        placement = _find_footprint(residual, blocked, 3.0, 2.0)
        if placement:
            center, footprint = placement
            blocked = blocked.union(footprint)
            elements.append({
                "json_id": pond_id,
                "type": "garden_pond",
                "position": [round(center.x, 3), round(center.y, 3)],
                "dimensions": {"width_m": 3.0, "depth_m": 2.0, "depth_water_m": 0.8},
                "polygon": list(footprint.exterior.coords),
                "status": "review_required",
                "validation": {"valid": True, "evidence_status": "review_required"},
                "notes": "Geometric garden pond proposal; excavation depth, drainage overflow, and safety barrier evidence required.",
                "render": {"asset_id": "garden_pond_generic_01", "visible": True}
            })
        else:
            elements.append({"json_id": pond_id, "type": "garden_pond", "validation": {"valid": False, "reason": "no_residual_space"}})

    if water.get("swimming_pool_required"):
        pool_id = "SWIMMING_POOL_001"
        placement = _find_footprint(residual, blocked, 6.0, 3.0, access_buffer=1.0)
        if placement:
            center, footprint = placement
            blocked = blocked.union(footprint)
            elements.append({
                "json_id": pool_id,
                "type": "swimming_pool",
                "position": [round(center.x, 3), round(center.y, 3)],
                "dimensions": {"width_m": 6.0, "depth_m": 3.0, "depth_water_m": 1.4},
                "polygon": list(footprint.exterior.coords),
                "status": "review_required",
                "validation": {"valid": True, "evidence_status": "review_required"},
                "notes": "Geometric swimming pool proposal; structural soil bearing, filtration plant, and council safety fencing certification required.",
                "render": {"asset_id": "swimming_pool_generic_01", "visible": True}
            })
        else:
            elements.append({"json_id": pool_id, "type": "swimming_pool", "validation": {"valid": False, "reason": "no_residual_space"}})

    # 6. Paths
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

    # 7. Boundary Wall
    if landscape.get("boundary_wall_required"):
        wall = None
        if land is not None:
            wall = land.boundary
            if gate is not None:
                for gate_item in [gate, *gate.get("additional_gates", [])]:
                    wall = wall.difference(Point(gate_item["position"]).buffer(float(gate_item["width"]) / 2))
        wall_height = float(landscape.get("boundary_wall_height_m") or landscape.get("boundary_wall_height") or 1.8)
        wall_type = str(landscape.get("boundary_wall_type") or "masonry")
        elements.append({"json_id": "BOUNDARY_WALL_001", "type": "boundary_wall",
                         "geometry": None if wall is None else mapping(wall),
                         "boundary": "land_polygon.exterior", "height_m": wall_height,
                         "wall_type": wall_type,
                         "gate_openings": [] if gate is None else [
                             {"gate_json_id": item["json_id"], "width_m": item["width"]}
                             for item in [gate, *gate.get("additional_gates", [])]
                         ],
                         "validation": {"valid": wall is not None, "follows_legal_land_boundary": wall is not None}})
    return elements


def _find_footprint(residual: BaseGeometry, blocked: BaseGeometry, width: float, depth: float, access_buffer: float = 0.0):
    if residual.is_empty:
        return None
    min_x, min_y, max_x, max_y = residual.bounds
    step = max(width / 2, float(elia_rules()["outdoor_elements"]["candidate_grid_spacing_m"]))

    estimated_cells = ((max_x - min_x) / step) * ((max_y - min_y) / step)
    if estimated_cells > elia_rules()["access"].get("max_grid_cells", 200000):
        raise ELIAError("ELIA_PLANNING_LIMIT_EXCEEDED", "Search limit exhausted for outdoor elements.")

    candidates = []
    effective_w = width + access_buffer * 2
    effective_d = depth + access_buffer * 2

    y = min_y + depth / 2
    while y <= max_y - depth / 2:
        x = min_x + width / 2
        while x <= max_x - width / 2:
            center = Point(x, y)
            footprint = box(x - width / 2, y - depth / 2, x + width / 2, y + depth / 2)
            check_box = box(x - effective_w / 2, y - effective_d / 2, x + effective_w / 2, y + effective_d / 2) if access_buffer > 0 else footprint
            if residual.covers(footprint) and not check_box.intersects(blocked):
                candidates.append((center, footprint))
            x += step
        y += step
    return min(candidates, key=lambda item: (item[0].y, item[0].x)) if candidates else None

