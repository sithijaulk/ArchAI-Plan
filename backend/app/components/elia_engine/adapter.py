from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Any, Mapping, Sequence

from .exceptions import ELIAError


def _value(document: Mapping[str, Any], path: Sequence[str]) -> Any:
    current: Any = document
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _canonical_alias(document: Mapping[str, Any], paths: Sequence[Sequence[str]], field: str) -> Any:
    candidates = [(path, _value(document, path)) for path in paths]
    candidates = [(path, value) for path, value in candidates if value is not None]
    if not candidates:
        return None
    first = candidates[0][1]
    if any(value != first for _, value in candidates[1:]):
        names = [".".join(path) for path, _ in candidates]
        raise ELIAError("ELIA_CONFLICTING_MASTER_FIELDS", f"Conflicting Master JSON fields for {field}: {', '.join(names)}.")
    return first


def resolve_upstream_road(document: Mapping[str, Any]) -> tuple[str | None, int | None]:
    """Resolve the authoritative upstream road side and boundary edge."""
    land_info = document.get("land_info") if isinstance(document.get("land_info"), Mapping) else {}
    road_values = []
    for path in (("road_access",), ("road",), ("access",), ("land_info", "road_access")):
        value = _value(document, path)
        if isinstance(value, Mapping):
            road_values.append(value)
    sides = [value.get("side", value.get("road_side", value.get("road_facing"))) for value in road_values]
    sides.extend([document.get("road_facing"), land_info.get("road_facing")])
    sides = [str(value).strip().lower() for value in sides if value is not None]
    canonical_side = sides[0] if sides else None
    if canonical_side is not None and any(value != canonical_side for value in sides[1:]):
        raise ELIAError("ELIA_CONFLICTING_ROAD_ACCESS", "Conflicting upstream road-side aliases were supplied.")

    edges = []
    for value in road_values:
        for key in ("edge_index", "road_edge_index", "road_access_edge"):
            if value.get(key) is not None:
                edges.append(value[key])
    for key in ("road_access_edge", "road_edge_index", "edge_index"):
        if document.get(key) is not None:
            edges.append(document[key])
        if land_info.get(key) is not None:
            edges.append(land_info[key])
    try:
        canonical_edge = int(edges[0]) if edges else None
        if canonical_edge is not None and any(int(value) != canonical_edge for value in edges[1:]):
            raise ELIAError("ELIA_CONFLICTING_ROAD_ACCESS", "Conflicting upstream road edge aliases were supplied.")
    except (TypeError, ValueError) as exc:
        raise ELIAError("ELIA_INVALID_ROAD_ACCESS", "Upstream road edge indices must be integers.") from exc
    return canonical_side, canonical_edge


def _utility_position(value: Any) -> tuple[float, float] | None:
    if isinstance(value, (list, tuple)):
        if len(value) < 2:
            raise ELIAError("ELIA_INVALID_UTILITY_LOCATION", "Utility coordinate arrays must include x and y.")
        point = value
    elif not isinstance(value, Mapping):
        return None
    elif value.get("known") is False:
        return None
    else:
        point = value.get("position", value.get("center", value))
    if isinstance(point, Mapping):
        x, y = point.get("x"), point.get("y")
        if (x is None) != (y is None):
            raise ELIAError("ELIA_INVALID_UTILITY_LOCATION", "Utility coordinates must include both x and y.")
        if x is None:
            return None
    elif isinstance(point, (list, tuple)) and len(point) >= 2:
        x, y = point[0], point[1]
    else:
        if isinstance(value, Mapping) and ("position" in value or "center" in value or "x" in value or "y" in value):
            raise ELIAError("ELIA_INVALID_UTILITY_LOCATION", "Utility coordinates must provide numeric x and y values.")
        return None
    try:
        coordinates = float(x), float(y)
    except (TypeError, ValueError):
        raise ELIAError("ELIA_INVALID_UTILITY_LOCATION", "Utility coordinates must be numeric.")
    if not all(isfinite(part) for part in coordinates):
        raise ELIAError("ELIA_INVALID_UTILITY_LOCATION", "Utility coordinates must be finite.")
    return coordinates


def _normalized_utility(master: Mapping[str, Any], name: str, upstream_name: str) -> Any:
    candidates = []
    for path in (("utilities", name), (name,),
                 ("floor_plan", "ground_floor", "utilities", upstream_name)):
        value = _value(master, path)
        if value is not None:
            candidates.append((path, value))
    if not candidates:
        return None
    canonical_position = _utility_position(candidates[0][1])
    for path, value in candidates[1:]:
        position = _utility_position(value)
        if position != canonical_position:
            fields = [".".join(item[0]) for item in candidates]
            raise ELIAError("ELIA_CONFLICTING_MASTER_FIELDS", f"Conflicting utility locations: {', '.join(fields)}.")
    utility = deepcopy(candidates[0][1])
    if canonical_position is not None and isinstance(utility, dict):
        utility["position"] = list(canonical_position)
    return utility


def normalize_master_json(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return a canonical working view without mutating or rewriting the upstream document."""
    if not isinstance(document, Mapping):
        raise ELIAError("ELIA_INVALID_MASTER_JSON", "Master JSON must be an object.")
    normalized = deepcopy(dict(document))
    land = _canonical_alias(document, (
        ("land_boundary_polygon",), ("land_info", "land_boundary_polygon"),
        ("land_info", "boundary_polygon"), ("land_info", "boundary_points"),
        ("land_info", "mathematical_polygon"),
    ), "land boundary")
    house = _canonical_alias(document, (
        ("house_exterior_polygon",), ("house", "exterior_polygon"),
        ("building_footprint",), ("building", "exterior_polygon"),
        ("building", "footprint"), ("floor_plan", "ground_floor", "house_exterior_polygon"),
        ("floor_plan", "ground_floor", "exterior_polygon"),
        ("buildable_footprint", "house_exterior_polygon"),
        ("structural_rectification", "house_exterior_polygon"),
    ), "house exterior footprint")
    if land is not None:
        normalized["land_boundary_polygon"] = deepcopy(land)
    if house is not None:
        normalized["house_exterior_polygon"] = deepcopy(house)

    north_values = []
    for path in (("north_angle",), ("calculated_north_bearing",),
                 ("land_info", "calculated_north_bearing")):
        value = _value(document, path)
        if value is not None:
            try:
                angle = float(value)
            except (TypeError, ValueError) as exc:
                raise ELIAError("ELIA_INVALID_NORTH_ORIENTATION", f"{'.'.join(path)} must be a numeric angle in degrees.") from exc
            if not isfinite(angle):
                raise ELIAError("ELIA_INVALID_NORTH_ORIENTATION", "North orientation must be a finite angle in degrees.")
            north_values.append((path, angle % 360.0))
    if north_values:
        reference = north_values[0][1]
        if any(min(abs(value - reference), 360.0 - abs(value - reference)) > 1e-6
               for _, value in north_values[1:]):
            names = [".".join(path) for path, _ in north_values]
            raise ELIAError("ELIA_CONFLICTING_NORTH_ORIENTATION", f"Conflicting north orientation fields: {', '.join(names)}.")
        normalized["north_angle"] = reference

    utilities = deepcopy(document.get("utilities") or {})
    if not isinstance(utilities, dict):
        raise ELIAError("ELIA_INVALID_MASTER_JSON", "Master JSON utilities must be an object.")
    for name, upstream_name in (("well", "water_well"), ("septic_tank", "septic_tank")):
        utility = _normalized_utility(document, name, upstream_name)
        if utility is not None:
            utilities[name] = utility
    normalized["utilities"] = utilities
    return normalized