from __future__ import annotations

from math import hypot
from typing import Any, Sequence

from shapely.geometry import LineString


def _turn_radius(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    ab, bc, ca = hypot(b[0] - a[0], b[1] - a[1]), hypot(c[0] - b[0], c[1] - b[1]), hypot(a[0] - c[0], a[1] - c[1])
    twice_area = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
    return float("inf") if twice_area < 1e-9 else ab * bc * ca / (2 * twice_area)


def validate_vehicle_route(coordinates: Sequence[tuple[float, float]], vehicle: dict[str, Any], driveway_width: float, clearance: float) -> dict[str, Any]:
    required_radius = float(vehicle["minimum_turning_radius"])
    required_width = float(vehicle["width"]) + 2 * clearance
    radii = [_turn_radius(coordinates[index - 1], coordinates[index], coordinates[index + 1])
             for index in range(1, len(coordinates) - 1)]
    minimum_observed = min(radii, default=float("inf"))
    width_ok = driveway_width + 1e-9 >= required_width
    turning_ok = minimum_observed + 1e-9 >= required_radius
    return {
        "valid": width_ok and turning_ok,
        "minimum_turning_radius_m": required_radius,
        "observed_minimum_radius_m": None if minimum_observed == float("inf") else minimum_observed,
        "driveway_width_m": driveway_width,
        "required_driveway_width_m": required_width,
        "width_valid": width_ok,
        "turning_valid": turning_ok,
        "route_length_m": LineString(coordinates).length if len(coordinates) >= 2 else 0.0,
    }
