from __future__ import annotations

from typing import Any, Mapping, Sequence

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from .rule_repository import elia_rules, vegetation_catalog


def _afternoon_sun_score(point: Point, shadows: Sequence[Mapping[str, Any]]) -> float:
    afternoon_start = int(elia_rules()["vegetation"]["afternoon_start_hour"])
    afternoon = [sample for sample in shadows
                 if int(str(sample.get("timestamp", "T12:")).split("T")[-1][:2]) >= afternoon_start]
    usable = [sample for sample in afternoon if sample.get("status") == "estimated" and sample.get("geometry")]
    if not usable:
        return 0.5
    shaded = 0
    for sample in usable:
        shadow_polygon = sample.get("geometry", {}).get("coordinates", [[]])[0]
        if shadow_polygon:
            from shapely.geometry import Polygon
            if Polygon(shadow_polygon).covers(point):
                shaded += 1
    return 1.0 - shaded / len(usable)


def place_vegetation(residual: BaseGeometry, land: BaseGeometry, blocked: BaseGeometry,
                     requirements: Mapping[str, Any], shadows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if residual is None or residual.is_empty:
        return []
    landscape = requirements.get("landscape", {})
    if not (landscape.get("garden_required") or landscape.get("preferred_vegetation_categories") or
            landscape.get("shade_tree_preference")):
        return []
    catalogue = vegetation_catalog()["entries"]
    supported = {entry["category"]: entry for entry in catalogue}
    preferred = landscape.get("preferred_vegetation_categories") or (["shade_tree"] if landscape.get("shade_tree_preference") else ["shrub", "ground_cover"])
    excluded = set(landscape.get("vegetation_to_avoid", []))
    categories = [category for category in preferred if category in supported and category not in excluded]
    if not categories:
        return []
    rules = elia_rules()["vegetation"]
    density = str(landscape.get("greenery_density", requirements.get("greenery_level", "medium"))).lower()
    targets = rules["density_targets"]
    target_count = targets.get(density, targets["medium"])
    if requirements.get("landscape_priority") == "maximum_open_space":
        target_count = min(target_count, targets["low"])
    elif requirements.get("landscape_priority") == "maximum_greenery":
        target_count = max(target_count, targets["high"])
    min_x, min_y, max_x, max_y = residual.bounds
    step = float(rules["candidate_grid_spacing_m"])
    candidates = []
    y = min_y + step / 2
    while y < max_y:
        x = min_x + step / 2
        while x < max_x:
            point = Point(x, y)
            if residual.covers(point) and not blocked.buffer(0.05).covers(point):
                candidates.append(point)
            x += step
        y += step
    candidates.sort(key=lambda point: (-_afternoon_sun_score(point, shadows), point.y, point.x))
    nodes = []
    for index in range(target_count):
        category = categories[index % len(categories)]
        envelope = rules["generic_planning_envelopes_m"].get(category)
        if envelope is None:
            continue
        entry = supported[category]
        radius = float(envelope["canopy_radius"])
        for point in candidates:
            canopy = point.buffer(radius)
            if not land.covers(canopy) or not residual.covers(canopy) or canopy.intersects(blocked):
                continue
            spacing = float(rules["minimum_spacing_m"].get(category, radius * 2))
            if any(point.distance(Point(node["position"])) < max(spacing, radius + node["canopy_radius_m"]) for node in nodes):
                continue
            nodes.append({
                "json_id": f"{category.upper()}_{len(nodes) + 1:03d}", "category": category,
                "position": [point.x, point.y], "height_m": envelope["height"], "canopy_radius_m": radius,
                "height_basis": "configurable_procedural_planning_envelope_not_botanical_data",
                "solar_suitability": _afternoon_sun_score(point, shadows),
                "validation": {"inside_land": True, "outside_driveway_and_utilities": True},
                "render": {"asset_id": entry["render_asset_id"], "visible": True},
                "verified_species_data": False,
            })
            candidates.remove(point)
            break
    return nodes
