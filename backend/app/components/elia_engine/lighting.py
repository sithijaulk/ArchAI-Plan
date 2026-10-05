from __future__ import annotations

from math import hypot
from typing import Any, Mapping, Sequence

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from .rule_repository import lighting_rules
from .gate_garage import garage_polygon


def place_lighting(land: BaseGeometry, residual: BaseGeometry, driveway: LineString | None,
                   gate: Mapping[str, Any] | None, garage: Mapping[str, Any] | None,
                   requirements: Mapping[str, Any], blocked: BaseGeometry | None = None) -> list[dict[str, Any]]:
    lighting = requirements.get("lighting", {})
    if not lighting.get("required"):
        return []
    rules = lighting_rules()
    spacing = float(lighting.get("preferred_spacing_m") or rules["minimum_spacing_m"])
    zones = lighting.get("zones") or ["gate", "driveway", "garden"]
    candidates: list[tuple[str, Point]] = []
    if "gate" in zones and gate:
        candidates.append(("gate", Point(gate["position"])))
    if "garage" in zones and garage:
        candidates.extend(_garage_zone_candidates(garage))
    if "driveway" in zones and driveway and driveway.length > 0:
        try:
            offset = driveway.parallel_offset(float(requirements.get("access", {}).get("preferred_driveway_width_m", 3.0)) / 2 + 0.4, "left")
            line = max(offset.geoms, key=lambda part: part.length) if hasattr(offset, "geoms") else offset
            count = max(1, int(line.length // spacing))
            candidates.extend(("driveway", line.interpolate(index / (count + 1), normalized=True)) for index in range(1, count + 1))
        except (ValueError, TypeError):
            pass
    if "garden" in zones and not residual.is_empty:
        candidates.extend(_garden_candidates(residual, spacing))
    if "boundary" in zones:
        candidates.extend(("boundary", point) for point in _boundary_points(land, spacing))

    nodes = []
    enforced_spacing = spacing - 1e-3
    for zone, point in candidates:
        if (not land.covers(point) or (blocked is not None and blocked.buffer(0.05).covers(point)) or
            any(point.distance(Point(node["position"])) < enforced_spacing for node in nodes)):
            continue
        if driveway and zone != "driveway" and point.distance(driveway) < float(requirements.get("access", {}).get("preferred_driveway_width_m", 3.0)) / 2:
            continue
        light_type = rules["render_types"].get(lighting.get("style", "minimal"), "bollard")
        nodes.append({"json_id": f"LIGHT_{len(nodes) + 1:03d}", "position": [point.x, point.y], "type": light_type,
                      "zone": zone, "height_m": rules["mounting_height_m"].get(zone, 1.0),
                      "orientation_degrees": None, "render": {"visible": True}})
    return nodes


def _garden_candidates(residual: BaseGeometry, spacing: float) -> list[tuple[str, Point]]:
    """Return multiple garden candidates: representative_point first, then grid."""
    candidates: list[tuple[str, Point]] = []
    candidates.append(("garden", residual.representative_point()))
    min_x, min_y, max_x, max_y = residual.bounds
    step = max(spacing, 1.0)
    
    estimated_cells = ((max_x - min_x) / step) * ((max_y - min_y) / step)
    from .rule_repository import elia_rules
    if estimated_cells > elia_rules()["access"].get("max_grid_cells", 200000):
        from .exceptions import ELIAError
        raise ELIAError("ELIA_PLANNING_LIMIT_EXCEEDED", "Search budget exhausted for lighting.")
        
    y = min_y + step / 2
    while y <= max_y:
        x = min_x + step / 2
        while x <= max_x:
            pt = Point(x, y)
            if residual.covers(pt):
                candidates.append(("garden", pt))
            x += step
        y += step
    return candidates


def _garage_zone_candidates(garage: Mapping[str, Any]) -> list[tuple[str, Point]]:
    """Return exterior positions near the garage entry, clearly outside the polygon."""
    candidates: list[tuple[str, Point]] = []
    try:
        garage_poly = garage_polygon(garage)
        entry = Point(garage["entry_point"])
        centroid = garage_poly.centroid
        dx = entry.x - centroid.x
        dy = entry.y - centroid.y
        mag = hypot(dx, dy) or 1.0
        lateral_dist = 2.0
        for dist in (0.5, 1.5, 2.5):
            out_x, out_y = entry.x + dx / mag * dist, entry.y + dy / mag * dist
            for lat_mag in (1, -1):
                lat_x, lat_y = -dy / mag * lateral_dist * lat_mag, dx / mag * lateral_dist * lat_mag
                pt = Point(out_x + lat_x, out_y + lat_y)
                if not garage_poly.buffer(0.05).covers(pt):
                    candidates.append(("garage", pt))
    except (KeyError, TypeError, ValueError):
        pass
    return candidates


def _boundary_points(land: BaseGeometry, spacing: float):
    boundary = land.boundary
    count = max(1, int(boundary.length // spacing))
    for index in range(count):
        yield boundary.interpolate((index + 0.5) / count, normalized=True)
