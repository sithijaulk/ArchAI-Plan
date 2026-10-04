from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping

from shapely.geometry import Point

from .geometry import feet_to_meters, point_xy
from .parser import UNIT_TO_METERS
from .rule_repository import elia_rules


@dataclass(frozen=True)
class UtilitySafetyResult:
    wells: tuple[Point, ...]
    septic_tanks: tuple[Point, ...]
    buffers: tuple[Point, ...]
    checks: tuple[dict[str, Any], ...]
    status: str


def _master_utility(master: Mapping[str, Any], key: str) -> Any:
    utilities = master.get("utilities", {})
    if isinstance(utilities, Mapping) and key in utilities:
        return utilities[key]
    return master.get(key)


def _utility_point(master_value: Any, request_value: Any, master_scale: float, request_scale: float) -> Point | None:
    for value, scale in ((request_value, request_scale), (master_value, master_scale)):
        if isinstance(value, Mapping) and value.get("known") is False:
            continue
        coordinate = point_xy(value, scale)
        if coordinate and all(isfinite(part) for part in coordinate):
            return Point(coordinate)
    return None


def validate_utilities(master: Mapping[str, Any], requirements: Mapping[str, Any], source_units: str,
                       requirement_units: str | None = None) -> UtilitySafetyResult:
    master_scale = UNIT_TO_METERS[source_units]
    request_scale = UNIT_TO_METERS[requirement_units or source_units]
    requested = requirements.get("utilities", {}) if isinstance(requirements, Mapping) else {}
    well = _utility_point(_master_utility(master, "well"), requested.get("well"), master_scale, request_scale)
    septic = _utility_point(_master_utility(master, "septic_tank"), requested.get("septic_tank"), master_scale, request_scale)
    configured_ft = elia_rules()["utility_rules"]["well_septic_min_distance"]["value"]
    required_m = feet_to_meters(float(configured_ft))
    checks: list[dict[str, Any]] = []
    if well is not None and septic is not None:
        actual_m = well.distance(septic)
        passed = actual_m + 1e-9 >= required_m
        checks.append({
            "required_distance_ft": configured_ft,
            "actual_distance_ft": actual_m / 0.3048,
            "status": "passed" if passed else "failed",
            "rule_source": "elia_rules.json",
        })
    status = "failed" if any(check["status"] == "failed" for check in checks) else "passed" if checks else "unknown"
    protection_radius = float(elia_rules()["utility_rules"]["fixed_utility_buffer"]["value"])
    buffers = tuple(point.buffer(protection_radius) for point in (well, septic) if point is not None)
    return UtilitySafetyResult(
        wells=() if well is None else (well,),
        septic_tanks=() if septic is None else (septic,),
        buffers=buffers,
        checks=tuple(checks),
        status=status,
    )
