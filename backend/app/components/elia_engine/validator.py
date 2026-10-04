from __future__ import annotations

from typing import Any, Mapping, Sequence

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from .rule_repository import elia_rules


def validate_layout(land: Polygon, house: Polygon, gate: Mapping[str, Any] | None,
                    garage: Mapping[str, Any] | None, driveway: Polygon | None,
                    centerline: LineString | None, turning: Mapping[str, Any] | None,
                    utilities: Mapping[str, Any], vegetation: Sequence[Mapping[str, Any]],
                    lighting: Sequence[Mapping[str, Any]], vertical: Mapping[str, Any],
                    outdoor_elements: Sequence[Mapping[str, Any]], solar_samples: Sequence[Mapping[str, Any]],
                    obstacles: BaseGeometry) -> dict[str, Any]:
    checks: list[tuple[str, bool]] = []
    if gate is not None:
        gates = [gate, *gate.get("additional_gates", [])]
        checks.extend((f"{item['json_id']}_on_valid_land_boundary",
                       Point(item["position"]).distance(land.boundary) <=
                       float(elia_rules()["access"]["gate_boundary_tolerance_m"])) for item in gates)
        checks.append(("requested_gate_count_satisfied", len(gates) == int(gate.get("planned_gate_count", 1))))
    if garage is not None:
        garage_polygon = Polygon(garage["polygon"])
        checks.extend((("garage_inside_land", land.covers(garage_polygon)), ("garage_not_in_restricted_space", not garage_polygon.intersects(obstacles))))
    if driveway is not None:
        checks.extend((("driveway_inside_land", land.covers(driveway)), ("driveway_avoids_house_and_restrictions", not driveway.intersects(obstacles))))
        if garage is not None:
            checks.append(("driveway_connects_without_crossing_garage", driveway.intersection(Polygon(garage["polygon"])).area <= 1e-6))
    if centerline is not None:
        checks.append(("driveway_connectivity", centerline.is_simple and centerline.length > 0))
    if turning is not None:
        checks.append(("vehicle_turning_feasibility", bool(turning.get("valid"))))
    checks.append(("utility_safety", utilities.get("status") == "passed"))
    checks.append(("solar_analysis_completed", bool(solar_samples)))
    for node in vegetation:
        canopy = Point(node["position"]).buffer(float(node["canopy_radius_m"]))
        checks.append((f"{node['json_id']}_containment", land.covers(canopy)))
        checks.append((f"{node['json_id']}_clearance", not canopy.intersects(obstacles) and (driveway is None or not canopy.intersects(driveway))))
    for node in lighting:
        point = Point(node["position"])
        checks.append((f"{node['json_id']}_land_containment", land.covers(point)))
        checks.append((f"{node['json_id']}_fixed_clearance", not obstacles.buffer(0.05).covers(point)))
        if driveway is not None and node.get("zone") != "driveway":
            checks.append((f"{node['json_id']}_driveway_clearance", point.distance(driveway) > 0))
    for element in vertical.get("elements", []):
        checks.append((f"{element['json_id']}_support", bool(element.get("validation", {}).get("support_valid"))))
    for element in outdoor_elements:
        if element.get("type") in {"garden_seating", "garden_table_set"}:
            checks.append((f"{element['json_id']}_placement", bool(element.get("validation", {}).get("valid"))))
        elif element.get("type", "").endswith("path"):
            checks.append((f"{element['json_id']}_route", bool(element.get("validation", {}).get("valid"))))
        elif element.get("type") in {"boundary_wall", "garden_zone", "lawn_zone"}:
            checks.append((f"{element['json_id']}_geometry", bool(element.get("validation", {}).get("valid"))))
    violations = [name for name, passed in checks if not passed]
    return {"valid": not violations, "violations": violations,
            "checks_passed": sum(passed for _, passed in checks), "checks_total": len(checks),
            "constraint_satisfaction_rate": (sum(passed for _, passed in checks) / len(checks)) if checks else 1.0}
