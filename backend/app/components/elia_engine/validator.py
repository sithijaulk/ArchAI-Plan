from __future__ import annotations

from typing import Any, Mapping, Sequence

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.geometry.base import BaseGeometry

from .rule_repository import elia_rules
from .vehicle_access import validate_vehicle_route


def validate_layout(land: Polygon, house: Polygon, gate: Mapping[str, Any] | None,
                    garage: Mapping[str, Any] | None, driveway: Polygon | None,
                    centerline: LineString | None, turning: Mapping[str, Any] | None,
                    utilities: Mapping[str, Any], vegetation: Sequence[Mapping[str, Any]],
                    lighting: Sequence[Mapping[str, Any]], vertical: Mapping[str, Any],
                    outdoor_elements: Sequence[Mapping[str, Any]], solar_samples: Sequence[Mapping[str, Any]],
                    obstacles: BaseGeometry, master: Mapping[str, Any] | None = None,
                    support_scale: float = 1.0, vehicle_profiles: Sequence[Mapping[str, Any]] = (),
                    driveway_width: float | None = None,
                    requirements: Mapping[str, Any] | None = None) -> dict[str, Any]:
    checks: list[tuple[str, bool]] = []
    requirements = requirements or {}
    access_requirements = requirements.get("access", {})
    landscape_requirements = requirements.get("landscape", {})
    lighting_requirements = requirements.get("lighting", {})
    ground_obstacles = obstacles.union(Polygon(garage["polygon"])) if garage is not None else obstacles
    if gate is not None:
        gates = [gate, *gate.get("additional_gates", [])]
        checks.extend((f"{item['json_id']}_on_valid_land_boundary",
                       Point(item["position"]).distance(land.boundary) <=
                       float(elia_rules()["access"]["gate_boundary_tolerance_m"])) for item in gates)
        checks.extend((f"{item['json_id']}_clear_of_fixed_obstacles",
                   not obstacles.buffer(float(elia_rules()["access"]["gate_obstacle_clearance_m"])).covers(Point(item["position"])))
                  for item in gates)
        checks.append(("gate_plan_count_consistent", len(gates) == int(gate.get("planned_gate_count", 1))))
        checks.append(("requested_gate_count_satisfied",
                       len(gates) == int(access_requirements.get("gate_count", 1))))
        preferred_gate = access_requirements.get("preferred_gate_location")
        if preferred_gate:
            checks.append(("requested_gate_position_satisfied",
                           Point(gate["position"]).distance(Point(preferred_gate)) <= 0.5))
    if garage is not None:
        garage_polygon = Polygon(garage["polygon"])
        checks.extend((("garage_inside_land", land.covers(garage_polygon)), ("garage_not_in_restricted_space", not garage_polygon.intersects(obstacles))))
        if access_requirements.get("garage_required"):
            bay_area = float(elia_rules()["access"]["default_garage_width_m"]) * float(elia_rules()["access"]["default_garage_length_m"])
            checks.append(("requested_garage_capacity_satisfied",
                           int(garage_polygon.area // bay_area) >= int(access_requirements.get("garage_capacity", 1))))
    elif access_requirements.get("garage_required"):
        checks.append(("requested_garage_available", False))
    if driveway is not None:
        checks.extend((("driveway_inside_land", land.covers(driveway)), ("driveway_avoids_house_and_restrictions", not driveway.intersects(obstacles))))
        if garage is not None:
            checks.append(("driveway_connects_without_crossing_garage", driveway.intersection(Polygon(garage["polygon"])).area <= 1e-6))
    if centerline is not None:
        checks.append(("driveway_connectivity", centerline.is_simple and centerline.length > 0))
        if gate is not None:
            checks.append(("driveway_connects_to_gate",
                           Point(centerline.coords[0]).distance(Point(gate["access_point"])) <= 0.25))
        if garage is not None:
            checks.append(("driveway_connects_to_garage_entry",
                           Point(centerline.coords[-1]).distance(Point(garage["entry_point"])) <= 0.25))
        if vehicle_profiles and driveway_width is not None:
            vehicle_checks = [validate_vehicle_route(list(centerline.coords), dict(profile), driveway_width,
                              float(elia_rules()["access"]["driveway_clearance_m"]))
                              for profile in vehicle_profiles]
            checks.append(("vehicle_turning_radius_or_width", all(item["valid"] for item in vehicle_checks)))
    elif access_requirements.get("driveway_required"):
        checks.append(("required_driveway_available", False))
    checks.append(("utility_safety", utilities.get("status") in {"passed", "not_applicable"}))
    checks.append(("solar_analysis_completed", bool(solar_samples)))
    for node in vegetation:
        canopy = Point(node["position"]).buffer(float(node["canopy_radius_m"]))
        checks.append((f"{node['json_id']}_containment", land.covers(canopy)))
        checks.append((f"{node['json_id']}_clearance", not canopy.intersects(ground_obstacles) and (driveway is None or not canopy.intersects(driveway))))
    for node in lighting:
        point = Point(node["position"])
        checks.append((f"{node['json_id']}_land_containment", land.covers(point)))
        checks.append((f"{node['json_id']}_fixed_clearance", not ground_obstacles.buffer(0.05).covers(point)))
        checks.append((f"{node['json_id']}_vegetation_clearance",
                       all(point.distance(Point(plant["position"])) > float(plant["canopy_radius_m"])
                           for plant in vegetation)))
        furniture_clear = True
        for element in outdoor_elements:
            if element.get("type") in {"garden_seating", "garden_table_set"} and element.get("polygon"):
                furniture = Polygon(element["polygon"])
                if furniture.buffer(0.05).covers(point):
                    furniture_clear = False
                    break
        checks.append((f"{node['json_id']}_furniture_clearance", furniture_clear))
        if driveway is not None and node.get("zone") != "driveway":
            checks.append((f"{node['json_id']}_driveway_clearance", point.distance(driveway) > 0))
    vertical_support_checks = []
    for element in vertical.get("elements", []):
        footprint = Polygon(element.get("footprint", [])) if element.get("footprint") else Polygon()
        position = element.get("position", {})
        support = None
        floor_id = None
        if isinstance(master, Mapping):
            building = master.get("building_exterior", {})
            for key in ("balconies", "slabs", "terraces"):
                surfaces = master.get(key)
                if surfaces is None and isinstance(building, Mapping):
                    surfaces = building.get(key)
                if isinstance(surfaces, list):
                    support = next((surface for surface in surfaces if isinstance(surface, Mapping) and
                                    str(surface.get("json_id", surface.get("id", ""))) ==
                                    str(element.get("support_json_id", ""))), None)
                    if support:
                        floor_id = support.get("floor_id") or support.get("floor")
                        raw = support.get("polygon") or support.get("coordinates")
                        try:
                            if isinstance(raw, Mapping):
                                support_geometry = shape(raw)
                            elif isinstance(raw, (list, tuple)) and raw:
                                rings = raw if (isinstance(raw[0], (list, tuple)) and raw[0] and
                                                isinstance(raw[0][0], (list, tuple))) else [raw]
                                support_geometry = Polygon(rings[0], rings[1:])
                            else:
                                support_geometry = None
                            if support_geometry is not None and support_scale != 1:
                                support_geometry = affinity.scale(support_geometry, xfact=support_scale,
                                                                  yfact=support_scale, origin=(0, 0))
                            if support_geometry is not None and support_geometry.is_valid:
                                support = {**support, "_geometry": support_geometry}
                            else:
                                support = None
                        except (TypeError, ValueError):
                            support = None
                        break
        support_geometry = support.get("_geometry") if isinstance(support, Mapping) else None
        support_valid = (support_geometry is not None and support_geometry.is_valid and
                         support_geometry.covers(footprint) and bool(element.get("support_json_id")) and
                         bool(element.get("floor_id")) and str(element.get("floor_id")) == str(floor_id))
        elevation_valid = isinstance(position, Mapping) and isinstance(position.get("z"), (int, float)) and position["z"] > 0
        independently_valid = bool(support_valid and elevation_valid and footprint.is_valid)
        vertical_support_checks.append(independently_valid)
        checks.append((f"{element.get('json_id', 'vertical_object')}_support", independently_valid))
    if vertical.get("requested"):
        checks.append(("requested_vertical_greenery_fulfilled",
                       vertical.get("status") == "placed" and
                       any(vertical_support_checks)))
    for element in outdoor_elements:
        object_id = element.get("json_id", "outdoor_object")
        geometry = None
        try:
            if element.get("geometry") is not None:
                geometry = shape(element["geometry"])
            elif element.get("polygon") is not None:
                geometry = Polygon(element["polygon"])
        except (TypeError, ValueError):
            geometry = None
        if element.get("type") in {"garden_seating", "garden_table_set"}:
            valid = geometry is not None and geometry.is_valid and land.covers(geometry) and not geometry.intersects(ground_obstacles)
            if driveway is not None:
                valid = valid and not geometry.intersects(driveway)
            checks.append((f"{object_id}_placement", valid))
        elif element.get("type", "").endswith("path"):
            try:
                route = LineString(element.get("centerline", []))
                valid = (geometry is not None and geometry.is_valid and land.covers(geometry) and
                         route.is_simple and route.length > 0 and not geometry.intersects(ground_obstacles))
            except (TypeError, ValueError):
                valid = False
            checks.append((f"{object_id}_route", valid))
        elif element.get("type") in {"boundary_wall", "garden_zone", "lawn_zone"}:
            checks.append((f"{object_id}_geometry", geometry is not None and geometry.is_valid and land.covers(geometry)))
    output_types = {str(element.get("type")) for element in outdoor_elements}
    for field, feature in (("garden_required", "garden_zone"), ("lawn_required", "lawn_zone"),
                           ("garden_seating_required", "garden_seating"),
                           ("garden_table_set_required", "garden_table_set"),
                           ("pedestrian_path_required", "pedestrian_path"),
                           ("garden_path_required", "garden_path"),
                           ("boundary_wall_required", "boundary_wall")):
        if landscape_requirements.get(field):
            checks.append((f"required_{feature}_present", feature in output_types))
    if lighting_requirements.get("required"):
        zones = lighting_requirements.get("zones") or ["gate", "driveway", "garden"]
        checks.append(("required_outdoor_lighting_present", bool(lighting)))
        for zone in zones:
            checks.append((f"requested_lighting_zone_{zone}_fulfilled",
                           any(node.get("zone") == zone for node in lighting)))
    violations = [name for name, passed in checks if not passed]
    return {"valid": not violations, "violations": violations,
            "checks_passed": sum(passed for _, passed in checks), "checks_total": len(checks),
            "constraint_satisfaction_rate": (sum(passed for _, passed in checks) / len(checks)) if checks else 1.0}
