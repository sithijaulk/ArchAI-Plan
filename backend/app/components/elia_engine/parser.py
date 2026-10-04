from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from shapely import affinity
from shapely.geometry import Polygon, shape
from shapely.geometry.base import BaseGeometry

from .exceptions import ELIAError

UNIT_TO_METERS = {"m": 1.0, "meter": 1.0, "meters": 1.0, "ft": 0.3048, "foot": 0.3048, "feet": 0.3048}


@dataclass(frozen=True)
class ExteriorContext:
    land: Polygon
    house: Polygon
    source_units: str
    normalized_units: str
    normalized_rings: tuple[str, ...]
    raw_land: Mapping[str, Any]
    raw_house: Mapping[str, Any]
    unit_scale: float


def _get_path(document: Mapping[str, Any], *path: str) -> Any:
    current: Any = document
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _first(document: Mapping[str, Any], paths: Sequence[tuple[str, ...]]) -> Any:
    for path in paths:
        value = _get_path(document, *path)
        if value is not None:
            return value
    return None


def _coordinates(value: Any, field: str) -> Any:
    if isinstance(value, Mapping):
        if value.get("type") in {"Polygon", "MultiPolygon"}:
            geometry = shape(value)
            if geometry.geom_type != "Polygon":
                raise ELIAError("ELIA_INVALID_POLYGON", f"{field} must be a single Polygon.")
            return list(geometry.exterior.coords)
        for key in ("coordinates", "points", "vertices", "boundary_points", "polygon"):
            if key in value:
                return _coordinates(value[key], field)
        raise ELIAError("ELIA_INVALID_POLYGON", f"{field} has no polygon coordinates.")

    if not isinstance(value, (list, tuple)):
        raise ELIAError("ELIA_INVALID_POLYGON", f"{field} must be an array of coordinates.")
    if value and isinstance(value[0], (list, tuple)) and value[0] and isinstance(value[0][0], (list, tuple)):
        value = value[0]
    if len(value) < 3:
        raise ELIAError("ELIA_INVALID_POLYGON", f"{field} requires at least three points.")

    points: list[tuple[float, float]] = []
    for point in value:
        if isinstance(point, Mapping):
            x, y = point.get("x"), point.get("y")
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            x, y = point[0], point[1]
        else:
            raise ELIAError("ELIA_INVALID_POLYGON", f"{field} contains an invalid point.")
        try:
            x_value, y_value = float(x), float(y)
        except (TypeError, ValueError) as exc:
            raise ELIAError("ELIA_INVALID_POLYGON", f"{field} contains non-numeric coordinates.") from exc
        if not math.isfinite(x_value) or not math.isfinite(y_value):
            raise ELIAError("ELIA_INVALID_POLYGON", f"{field} coordinates must be finite.")
        points.append((x_value, y_value))
    return points


def _polygon(value: Any, field: str, scale: float) -> tuple[Polygon, bool]:
    points = _coordinates(value, field)
    was_closed = points[0] == points[-1]
    if not was_closed:
        points.append(points[0])
    polygon = Polygon(points)
    if polygon.is_empty or polygon.area <= 0 or not polygon.is_valid:
        raise ELIAError("ELIA_INVALID_POLYGON", f"{field} is not a valid polygon.")
    if scale != 1:
        polygon = affinity.scale(polygon, xfact=scale, yfact=scale, origin=(0, 0))
    return polygon, not was_closed


def _unit(document: Mapping[str, Any], default_units: str) -> str:
    value = document.get("units", default_units)
    if isinstance(value, Mapping):
        value = value.get("length", value.get("distance", default_units))
    normalized = str(value).strip().lower()
    if normalized not in UNIT_TO_METERS:
        raise ELIAError("ELIA_INVALID_UNITS", f"Unsupported Master JSON length unit: {value!r}.")
    return normalized


def parse_exterior_context(document: Any, default_units: str = "m") -> ExteriorContext:
    """Extract and normalize required exterior polygons without repairing invalid geometry."""
    if not isinstance(document, Mapping):
        raise ELIAError("ELIA_INVALID_MASTER_JSON", "Master JSON must be an object.")

    land_raw = _first(document, (
        ("land_boundary_polygon",),
        ("land_info", "land_boundary_polygon"),
        ("land_info", "boundary_polygon"),
        ("land_info", "boundary_points"),
    ))
    house_raw = _first(document, (
        ("house_exterior_polygon",),
        ("building_footprint",),
        ("house", "exterior_polygon"),
        ("building", "footprint"),
        ("structural_rectification", "house_exterior_polygon"),
        ("buildable_footprint", "house_exterior_polygon"),
        ("buildable_footprint", "building_footprint"),
    ))
    if land_raw is None:
        raise ELIAError("ELIA_MISSING_LAND_BOUNDARY", "ELIA requires a valid land boundary polygon.")
    if house_raw is None:
        raise ELIAError("ELIA_MISSING_HOUSE_EXTERIOR", "ELIA requires a valid house exterior polygon.")

    units = _unit(document, default_units)
    scale = UNIT_TO_METERS[units]
    land, land_normalized = _polygon(land_raw, "land boundary", scale)
    house, house_normalized = _polygon(house_raw, "house exterior", scale)
    if not land.covers(house):
        raise ELIAError("ELIA_HOUSE_OUTSIDE_LAND", "House exterior polygon must lie within the land boundary.")

    normalized: list[str] = []
    if land_normalized:
        normalized.append("land_boundary_polygon")
    if house_normalized:
        normalized.append("house_exterior_polygon")
    return ExteriorContext(
        land=land,
        house=house,
        source_units=units,
        normalized_units="m",
        normalized_rings=tuple(normalized),
        raw_land=land_raw,
        raw_house=house_raw,
        unit_scale=scale,
    )
