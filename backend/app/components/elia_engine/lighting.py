from __future__ import annotations

from typing import Any, Mapping, Sequence

from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry

from .rule_repository import lighting_rules


def place_lighting(land: BaseGeometry, residual: BaseGeometry, driveway: LineString | None,
                   gate: Mapping[str, Any] | None, garage: Mapping[str, Any] | None,
                   requirements: Mapping[str, Any], blocked: BaseGeometry | None = None) -> list[dict[str, Any]]:
    lighting = requirements.get("lighting", {})
    if not lighting.get("required"):
        return []
    rules = lighting_rules()
    spacing = float(lighting.get("preferred_spacing") or rules["minimum_spacing_m"])
    zones = lighting.get("zones") or ["gate", "driveway", "garden"]
    candidates: list[tuple[str, Point]] = []
    if "gate" in zones and gate:
        candidates.append(("gate", Point(gate["position"])))
    if "garage" in zones and garage:
        candidates.append(("garage", Point(garage["entry_point"])))
    if "driveway" in zones and driveway and driveway.length > 0:
        try:
            offset = driveway.parallel_offset(float(requirements.get("access", {}).get("preferred_driveway_width", 3.0)) / 2 + 0.4, "left")
            line = max(offset.geoms, key=lambda part: part.length) if hasattr(offset, "geoms") else offset
            count = max(1, int(line.length // spacing))
            candidates.extend(("driveway", line.interpolate(index / (count + 1), normalized=True)) for index in range(1, count + 1))
        except (ValueError, TypeError):
            pass
    if "garden" in zones and not residual.is_empty:
        candidates.append(("garden", residual.representative_point()))
    if "boundary" in zones:
        candidates.extend(("boundary", point) for point in _boundary_points(land, spacing))

    nodes = []
    min_spacing = float(rules["minimum_spacing_m"])
    for zone, point in candidates:
        if (not land.covers(point) or (blocked is not None and blocked.buffer(0.05).covers(point)) or
            any(point.distance(Point(node["position"])) < min_spacing for node in nodes)):
            continue
        if driveway and zone != "driveway" and point.distance(driveway) < float(requirements.get("access", {}).get("preferred_driveway_width", 3.0)) / 2:
            continue
        light_type = rules["render_types"].get(lighting.get("style", "minimal"), "bollard")
        nodes.append({"json_id": f"LIGHT_{len(nodes) + 1:03d}", "position": [point.x, point.y], "type": light_type,
                      "zone": zone, "height_m": rules["mounting_height_m"].get(zone, 1.0),
                      "orientation_degrees": None, "render": {"visible": True}})
    return nodes


def _boundary_points(land: BaseGeometry, spacing: float):
    boundary = land.boundary
    count = max(1, int(boundary.length // spacing))
    for index in range(count):
        yield boundary.interpolate((index + 0.5) / count, normalized=True)
