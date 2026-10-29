from __future__ import annotations

from typing import Any

from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

FEET_PER_METER = 1 / 0.3048


def feet_to_meters(value: float) -> float:
    return value * 0.3048


def meters_to_feet(value: float) -> float:
    return value * FEET_PER_METER


def geometry_coordinates(geometry: BaseGeometry) -> Any:
    """Return JSON-compatible GeoJSON geometry coordinates."""
    return mapping(geometry)


def point_xy(value: Any, scale: float = 1.0) -> tuple[float, float] | None:
    if isinstance(value, dict):
        value = value.get("position", value)
        if isinstance(value, dict):
            x, y = value.get("x"), value.get("y")
        elif isinstance(value, (list, tuple)) and len(value) >= 2:
            x, y = value[0], value[1]
        else:
            return None
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        x, y = value[0], value[1]
    else:
        return None
    try:
        return float(x) * scale, float(y) * scale
    except (TypeError, ValueError):
        return None
