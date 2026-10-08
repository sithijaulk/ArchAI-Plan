from __future__ import annotations

from math import hypot, isfinite
from typing import Any, Mapping, Sequence

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from .exceptions import ELIAError
from .rule_repository import lighting_rules, elia_rules
from .gate_garage import garage_polygon


def place_lighting(land: BaseGeometry, residual: BaseGeometry, driveway: LineString | None,
                   gate: Mapping[str, Any] | None, garage: Mapping[str, Any] | None,
                   requirements: Mapping[str, Any], blocked: BaseGeometry | None = None) -> list[dict[str, Any]]:
    lighting = requirements.get("lighting", {})
    if not lighting.get("required"):
        return []
    rules = lighting_rules()
    raw_spacing = lighting.get("preferred_spacing_m") or rules["minimum_spacing_m"]
    try:
        spacing = float(raw_spacing)
    except (TypeError, ValueError) as exc:
        raise ELIAError("ELIA_INVALID_LIGHTING_SPACING", "Lighting spacing must be a numeric value.") from exc
    if not isfinite(spacing) or spacing <= 0:
        raise ELIAError("ELIA_INVALID_LIGHTING_SPACING",
                        "Lighting spacing must be a finite positive number.")
    spacing = max(spacing, rules["minimum_spacing_m"])

    max_candidates: int = int(rules.get("max_candidates", 5000))
    max_boundary: int = int(rules.get("max_boundary_points", 2000))
    max_final: int = int(rules.get("max_final_comparison_nodes", 500))

    zones = lighting.get("zones") or ["gate", "driveway", "garden"]
    candidates: list[tuple[str, Point]] = []

    if "gate" in zones and gate:
        candidates.append(("gate", Point(gate["position"])))

    if "garage" in zones and garage:
        candidates.extend(_garage_zone_candidates(garage))

    if "driveway" in zones and driveway and driveway.length > 0:
        try:
            offset = driveway.parallel_offset(
                float(requirements.get("access", {}).get("preferred_driveway_width_m", 3.0)) / 2 + 0.4, "left"
            )
            line = max(offset.geoms, key=lambda part: part.length) if hasattr(offset, "geoms") else offset
            count = max(1, int(line.length // spacing))
            # Budget: cap driveway candidates
            if count > max_candidates:
                raise ELIAError("ELIA_PLANNING_LIMIT_EXCEEDED",
                                f"Driveway lighting candidate count ({count}) exceeds budget.")
            candidates.extend(
                ("driveway", line.interpolate(index / (count + 1), normalized=True))
                for index in range(1, count + 1)
            )
        except ELIAError:
            raise
        except (ValueError, TypeError):
            pass

    if "garden" in zones and not residual.is_empty:
        garden_cands = _garden_candidates(residual, spacing)
        if len(candidates) + len(garden_cands) > max_candidates:
            raise ELIAError("ELIA_PLANNING_LIMIT_EXCEEDED",
                            "Total garden lighting candidates exceed the computation budget.")
        candidates.extend(garden_cands)

    if "boundary" in zones:
        boundary_cands = list(_boundary_points(land, spacing, max_boundary))
        if len(candidates) + len(boundary_cands) > max_candidates:
            raise ELIAError("ELIA_PLANNING_LIMIT_EXCEEDED",
                            "Total boundary lighting candidates exceed the computation budget.")
        candidates.extend(("boundary", point) for point in boundary_cands)

    # Total budget guard after all candidate sources
    if len(candidates) > max_candidates:
        raise ELIAError("ELIA_PLANNING_LIMIT_EXCEEDED",
                        f"Total lighting candidates ({len(candidates)}) exceed the computation budget.")

    nodes: list[dict[str, Any]] = []
    enforced_spacing = spacing - 1e-3
    for zone, point in candidates:
        if not land.covers(point):
            continue
        if blocked is not None and blocked.buffer(0.05).covers(point):
            continue
        # Cap final spacing/collision check comparisons
        if len(nodes) >= max_final:
            break
        if any(point.distance(Point(node["position"])) < enforced_spacing for node in nodes):
            continue
        if driveway and zone != "driveway" and point.distance(driveway) < float(
            requirements.get("access", {}).get("preferred_driveway_width_m", 3.0)
        ) / 2:
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
    if estimated_cells > elia_rules()["access"].get("max_grid_cells", 200000):
        raise ELIAError("ELIA_PLANNING_LIMIT_EXCEEDED", "Search budget exhausted for garden lighting.")

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


def _boundary_points(land: BaseGeometry, spacing: float, max_points: int = 2000):
    boundary = land.boundary
    count = max(1, int(boundary.length // spacing))
    if count > max_points:
        raise ELIAError("ELIA_PLANNING_LIMIT_EXCEEDED",
                        f"Boundary lighting point count ({count}) exceeds budget ({max_points}).")
    for index in range(count):
        yield boundary.interpolate((index + 0.5) / count, normalized=True)

