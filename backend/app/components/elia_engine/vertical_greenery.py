from __future__ import annotations

from typing import Any, Mapping

from math import isfinite
from shapely.geometry import Polygon, box

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
    
    # Explicit disabling at top-level or nested level overrides automatic mode.
    # Top-level vertical_greenery_enabled=False takes precedence over nested enabled=True.
    enabled_nested = preference.get("enabled")
    enabled_top = requirements.get("vertical_greenery_enabled")
    
    is_enabled = True
    if enabled_top is False or enabled_nested is False or mode == "disabled":
        is_enabled = False
        mode = "disabled"

    triggered = mode == "automatic" and ground_ratio < float(config["trigger_ground_space_ratio"])
    requested = mode == "preferred" or triggered
    
    result = {"triggered": triggered, "requested": requested, "mode": mode,
              "trigger_ratio": config["trigger_ground_space_ratio"], "elements": [],
              "status": "disabled" if not is_enabled else "not_triggered"}
    if not is_enabled or not requested:
        return result

    allowed_types = set(preference.get("preferred_types") or ["balcony_planter", "slab_planter", "cascading_creeper"])
    dimensions = config["planter_dimensions_m"]
    for support_kind, surface in _support_surfaces(master):
        coordinates = surface.get("polygon") or surface.get("coordinates")
        if isinstance(coordinates, Mapping):
            coordinates = coordinates.get("coordinates", [[]])[0]
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 3:
            continue
        try:
            polygon = Polygon([(float(point[0]) * unit_scale, float(point[1]) * unit_scale) for point in coordinates])
        except (TypeError, ValueError, IndexError):
            continue
        if not polygon.is_valid or polygon.length < config["minimum_support_length_m"]:
            continue
        center = polygon.representative_point()
        default_type = "balcony_planter" if support_kind == "balconies" else "slab_planter"
        element_type = next((candidate for candidate in (default_type, "cascading_creeper", "wall_planter") if candidate in allowed_types), None)
        if element_type is None:
            continue
        explicit_height = surface.get("elevation_m", surface.get("z_m"))
        source_height = explicit_height if explicit_height is not None else surface.get("z", surface.get("elevation", surface.get("floor_height")))
        try:
            z = float(source_height) * (1.0 if explicit_height is not None else unit_scale)
        except (TypeError, ValueError):
            z = 0.0
        if not isfinite(z):
            z = 0.0
        planter_width = float(dimensions["width"])
        planter_depth = float(dimensions["depth"])
        footprint = box(center.x - planter_width / 2, center.y - planter_depth / 2,
                        center.x + planter_width / 2, center.y + planter_depth / 2)
        floor_id = surface.get("floor_id") or surface.get("floor")
        support_id = surface.get("json_id") or surface.get("id")
        footprint_valid = polygon.covers(footprint)
        elevation_valid = z > 0
        support_valid = bool(floor_id and support_id and footprint_valid and elevation_valid)
        result["elements"].append({
            "json_id": f"VG_{len(result['elements']) + 1:03d}", "type": element_type,
            "floor_id": floor_id, "support_json_id": support_id,
            "position": {"x": center.x, "y": center.y, "z": z},
            "dimensions": dimensions, "footprint": list(footprint.exterior.coords),
            "units": "m", "vegetation_type": "cascading_creeper" if element_type == "cascading_creeper" else "planter",
            "validation": {"support_valid": support_valid, "footprint_valid": footprint_valid,
                           "elevation_valid": elevation_valid, "structural_load_assessed": False},
            "render": {"asset_id": f"{element_type}_generic_01", "visible": support_valid},
        })
    result["status"] = "placed" if any(element["validation"]["support_valid"] for element in result["elements"]) else "no_eligible_support_geometry"
    return result
