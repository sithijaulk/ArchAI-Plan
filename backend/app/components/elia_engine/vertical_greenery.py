from __future__ import annotations

from typing import Any, Mapping

from shapely.geometry import Polygon

from .rule_repository import elia_rules


def _support_surfaces(master: Mapping[str, Any]):
    building = master.get("building_exterior", {})
    for key in ("balconies", "slabs", "terraces"):
        value = master.get(key)
        if value is None and isinstance(building, Mapping):
            value = building.get(key)
        if isinstance(value, list):
            for surface in value:
                if isinstance(surface, Mapping):
                    yield key, surface


def plan_vertical_greenery(ground_ratio: float, requirements: Mapping[str, Any], master: Mapping[str, Any], unit_scale: float = 1.0) -> dict[str, Any]:
    config = elia_rules()["vertical_greenery"]
    preference = requirements.get("vertical_greenery", {})
    mode = preference.get("mode", config["default_mode"])
    enabled = bool(preference.get("enabled", True) and requirements.get("vertical_greenery_enabled", True))
    triggered = mode == "automatic" and ground_ratio < float(config["trigger_ground_space_ratio"])
    requested = mode == "preferred" or triggered
    result = {"triggered": triggered, "requested": requested, "mode": mode,
              "trigger_ratio": config["trigger_ground_space_ratio"], "elements": [],
              "status": "disabled" if not enabled or mode == "disabled" else "not_triggered"}
    if not enabled or mode == "disabled" or not requested:
        return result

    allowed_types = set(preference.get("preferred_types") or ["balcony_planter", "slab_planter", "cascading_creeper"])
    dimensions = config["planter_dimensions_m"]
    for support_kind, surface in _support_surfaces(master):
        coordinates = surface.get("polygon") or surface.get("coordinates")
        if isinstance(coordinates, Mapping):
            coordinates = coordinates.get("coordinates", [[]])[0]
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 3:
            continue
        polygon = Polygon([(float(point[0]) * unit_scale, float(point[1]) * unit_scale) for point in coordinates])
        if not polygon.is_valid or polygon.length < config["minimum_support_length_m"]:
            continue
        center = polygon.representative_point()
        default_type = "balcony_planter" if support_kind == "balconies" else "slab_planter"
        element_type = next((candidate for candidate in (default_type, "cascading_creeper", "wall_planter") if candidate in allowed_types), None)
        if element_type is None:
            continue
        z = float(surface.get("z", surface.get("elevation", surface.get("floor_height", 0.0)))) * unit_scale
        floor_id = surface.get("floor_id") or surface.get("floor")
        support_id = surface.get("json_id") or surface.get("id")
        result["elements"].append({
            "json_id": f"VG_{len(result['elements']) + 1:03d}", "type": element_type,
            "floor_id": floor_id, "support_json_id": support_id,
            "position": {"x": center.x, "y": center.y, "z": z},
            "dimensions": dimensions, "vegetation_type": "cascading_creeper" if element_type == "cascading_creeper" else "planter",
            "validation": {"support_valid": True, "clearance_valid": True},
            "render": {"asset_id": f"{element_type}_generic_01", "visible": True},
        })
    result["status"] = "placed" if result["elements"] else "no_eligible_support_geometry"
    return result
