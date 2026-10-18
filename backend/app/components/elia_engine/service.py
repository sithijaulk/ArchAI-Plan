from __future__ import annotations

import logging
import time
from math import cos, hypot, isfinite, pi, sin
from typing import Any, Mapping

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .adapter import normalize_master_json
from .exceptions import ELIAError
from .gate_garage import garage_polygon, plan_garage, plan_gate
from .geometry import point_xy
from .grid import build_navigation_grid
from .lighting import place_lighting
from .metrics import collect_metrics
from .outdoor_elements import place_outdoor_elements
from .parser import ExteriorContext, UNIT_TO_METERS, parse_exterior_context
from .pathfinding import astar_path
from .requirements import normalize_requirements
from .residual_space import calculate_residual_space
from .rule_repository import elia_rules, vegetation_catalog
from .shadow import analyze_shadows
from .solar import calculate_solar_samples, fetch_live_solar_conditions
from .utility_safety import validate_utilities
from .validator import validate_layout
from .vehicle_access import validate_vehicle_route
from .vegetation import place_vegetation, _calculate_afternoon_sun_score
from .vertical_greenery import plan_vertical_greenery
from .assessment import build_factors_assessment
from .rule_evaluator import evaluate_rules

logger = logging.getLogger(__name__)


def _auxiliary_polygons(master: Mapping[str, Any], scale: float) -> list[BaseGeometry]:
    restrictions = master.get("exterior_restrictions") or master.get("restricted_zones") or []
    restrictions = list(restrictions) if isinstance(restrictions, (list, tuple)) else [restrictions]
    fixed_objects = master.get("fixed_exterior_objects") or master.get("exterior_fixed_objects") or []
    restrictions.extend(fixed_objects if isinstance(fixed_objects, list) else [fixed_objects])
    result = []
    for item in restrictions:
        raw = item.get("polygon") or item.get("geometry") or item.get("coordinates") if isinstance(item, Mapping) else item
        if raw is None and isinstance(item, Mapping):
            raw = item.get("footprint")
        if raw is None:
            continue
        try:
            if isinstance(raw, Mapping):
                geometry = shape(raw)
            else:
                rings = raw if (isinstance(raw, (list, tuple)) and raw and
                                isinstance(raw[0], (list, tuple)) and raw[0] and
                                isinstance(raw[0][0], (list, tuple))) else [raw]
                geometry = Polygon(rings[0], rings[1:])
        except Exception as exc:
            raise ELIAError("ELIA_INVALID_POLYGON", "An exterior restriction has malformed polygon geometry.") from exc
        if not geometry.is_valid or geometry.is_empty:
            raise ELIAError("ELIA_INVALID_POLYGON", "An exterior restriction has invalid polygon geometry.")
        result.append(affinity.scale(geometry, xfact=scale, yfact=scale, origin=(0, 0)))
    utilities = master.get("utilities", {})
    if isinstance(utilities, Mapping):
        radius = float(elia_rules()["utility_rules"]["fixed_utility_buffer"]["value"])
        for name, utility in utilities.items():
            if name in {"well", "septic_tank"}:
                continue
            position = point_xy(utility, scale)
            if position is not None:
                result.append(Point(position).buffer(radius))
    return result


def _building_height(master: Mapping[str, Any], scale: float) -> float | None:
    explicit_meters = master.get("house_height_m", master.get("building_height_m"))
    building = master.get("building")
    if explicit_meters is None and isinstance(building, Mapping):
        explicit_meters = building.get("height_m")
    if explicit_meters is not None:

        try:
            value = float(explicit_meters)
        except (TypeError, ValueError) as exc:
            raise ELIAError("ELIA_INVALID_BUILDING_HEIGHT", "Building height must be numeric.") from exc
        if not isfinite(value) or value <= 0:
            raise ELIAError("ELIA_INVALID_BUILDING_HEIGHT", "Building height must be finite and positive.")
        return value

    value = master.get("building_height") or master.get("house_height")
    if value is None and isinstance(building, Mapping):
        value = building.get("height")
    if value is None:
        floors = master.get("floors")
        if isinstance(floors, list):
            floor_heights = [floor.get("height_m", floor.get("height")) for floor in floors if isinstance(floor, Mapping)]
            if floor_heights and all(height is not None for height in floor_heights):
                return sum(float(floor["height_m"]) if floor.get("height_m") is not None
                           else float(floor["height"]) * scale
                           for floor in floors if isinstance(floor, Mapping))
    if value is None:
        return None
    try:
        result = float(value) * scale
    except (TypeError, ValueError) as exc:
        raise ELIAError("ELIA_INVALID_BUILDING_HEIGHT", "Building height must be numeric.") from exc
    if not isfinite(result) or result <= 0:
        raise ELIAError("ELIA_INVALID_BUILDING_HEIGHT", "Building height must be finite and positive.")
    return result


def _entrance_target(master: Mapping[str, Any], house: Polygon, scale: float) -> tuple[float, float] | None:
    value = master.get("main_entrance")
    coordinate = point_xy(value, scale)
    if coordinate is None:
        return None
    entrance = Point(coordinate)
    if house.contains(entrance):
        boundary_point = house.exterior.interpolate(house.exterior.project(entrance))
    else:
        boundary_point = entrance
    center = house.centroid
    dx, dy = boundary_point.x - center.x, boundary_point.y - center.y
    length = hypot(dx, dy) or 1.0
    return boundary_point.x + dx / length * 0.75, boundary_point.y + dy / length * 0.75


def _requested_paths(context: ExteriorContext, master: Mapping[str, Any], gate: Mapping[str, Any], garage: Mapping[str, Any] | None,
                     driveway: Polygon | None, driveway_line: LineString | None,
                     fixed_obstacles: BaseGeometry, residual: BaseGeometry, requirements: Mapping[str, Any]) -> dict[str, Any]:
    landscape = requirements.get("landscape", {})
    requested = []
    if landscape.get("pedestrian_path_required"):
        requested.append("pedestrian_path")
    if landscape.get("garden_path_required"):
        requested.append("garden_path")
    if not requested:
        return {}
    rules = elia_rules()["access"]
    outdoor_rules = elia_rules()["outdoor_elements"]
    results = {}
    for kind in requested:
        width = float(outdoor_rules["pedestrian_path_width_m" if kind == "pedestrian_path" else "garden_path_width_m"])
        path_obstacles = fixed_obstacles
        if garage:
            path_obstacles = unary_union([path_obstacles, garage_polygon(garage)])
        obstacles = path_obstacles.buffer(width / 2 + float(rules["driveway_clearance_m"]))
        if driveway is not None:
            obstacles = obstacles.union(driveway.buffer(width / 2 + float(rules["pedestrian_driveway_lateral_clearance_m"])))
        navigable = context.land.buffer(-(width / 2 + float(rules["boundary_clearance_m"]))).difference(obstacles)
        if kind == "garden_path":
            garden_ground = residual.difference(path_obstacles)
            if driveway is not None:
                garden_ground = garden_ground.difference(driveway.buffer(width / 2 + float(rules["pedestrian_driveway_lateral_clearance_m"])))
            target = garden_ground.representative_point() if not garden_ground.is_empty else None
        else:
            entrance = _entrance_target(master, context.house, context.unit_scale)
            target = Point(entrance) if entrance else None
        if target is None or target.is_empty:
            results[kind] = {"valid": False, "reason": "required_path_endpoint_unavailable"}
            continue
        start = Point(gate["access_point"])
        if driveway_line is not None:
            route_coords = list(driveway_line.coords) if driveway_line.geom_type == "LineString" else []
            if len(route_coords) >= 2:
                dx, dy = route_coords[1][0] - route_coords[0][0], route_coords[1][1] - route_coords[0][1]
                length = hypot(dx, dy) or 1.0
                drive_width = float(requirements["access"].get("preferred_driveway_width_m") or rules["default_driveway_width_m"])
                offset = drive_width / 2 + width / 2 + float(rules["gate_obstacle_clearance_m"])
                alternatives = [Point(start.x - dy / length * offset, start.y + dx / length * offset),
                                Point(start.x + dy / length * offset, start.y - dx / length * offset)]
                radial_samples = int(rules["pedestrian_gate_radial_samples"])
                alternatives.extend(
                    Point(start.x + cos(index * 2 * pi / radial_samples) * offset,
                          start.y + sin(index * 2 * pi / radial_samples) * offset)
                    for index in range(radial_samples)
                )
                valid_starts = [point for point in alternatives if navigable.covers(point)]
                if valid_starts:
                    start = min(valid_starts, key=lambda point: point.distance(Point(gate["position"])))
                else:
                    results[kind] = {"valid": False, "reason": "no_separate_walkable_gate_approach"}
                    continue
        grid = build_navigation_grid(navigable, float(rules["grid_resolution_m"]), int(rules["max_grid_cells"]))
        route = astar_path(grid, (start.x, start.y), (target.x, target.y))
        if not route["found"]:
            results[kind] = {"valid": False, "reason": "no_feasible_route"}
            continue
        centerline = LineString(route["coordinates"])
        polygon = centerline.buffer(width / 2, cap_style="flat")
        valid = context.land.covers(polygon) and not polygon.intersects(path_obstacles)
        if driveway is not None:
            valid = valid and polygon.intersection(driveway).area <= 1e-6
        results[kind] = {"centerline": list(centerline.coords), "gate_connector": [list(gate["access_point"]), [start.x, start.y]],
                 "shared_gate_apron": True,
                 "polygon": list(polygon.exterior.coords) if polygon.geom_type == "Polygon" else None,
                         "width_m": width, "length_m": centerline.length, "pathfinding": "A*", "valid": valid,
                         "reason": None if valid else "path_clearance_or_land_containment"}
    return results


def _empty_result(context: ExteriorContext, requirements: Mapping[str, Any], utilities: Any, solar: list[dict[str, Any]],
                  shadows: list[dict[str, Any]], violations: list[str], reason: str, started: float) -> dict[str, Any]:
    area = context.land.area
    validation = {"valid": False, "violations": violations, "checks_passed": 0, "checks_total": max(len(violations), 1),
                  "constraint_satisfaction_rate": 0.0}
    rule_results = evaluate_rules(
        candidate={
            "vegetation_nodes": [],
            "outdoor_elements": [],
            "outdoor_lighting": {"nodes": []},
            "access": {},
            "vertical_greenery": {},
        },
        context=context,
        master_json=None,
        requirements=requirements,
        validation_summary=validation,
        shadow_samples=shadows,
    )
    assessment = build_factors_assessment(
        residual_area_m2=max(0.0, area - context.house.area),
        land_area_m2=area,
        house_area_m2=context.house.area,
        vegetation=[],
        shadow_samples=shadows,
        requirements=requirements,
        concept_rules_applied=[],
        validation_summary=validation,
        rule_evaluations=rule_results["rule_evaluations"],
        category_summaries=rule_results["category_summaries"],
        approval_status="blocked" if violations else rule_results["approval_status"],
    )
    return {
        "version": "1.0", "theme_concept": requirements.get("design_style"), "spatial_strategy": "horizontal",
        "site_analysis": {"land_area_m2": area, "house_footprint_area_m2": context.house.area,
                          "available_ground_area_m2": max(0.0, area - context.house.area),
                          "available_ground_ratio": max(0.0, area - context.house.area) / area if area else 0.0},
        "utility_safety": {"checks": list(utilities.checks), "status": utilities.status,
                   "required_separation_ft": elia_rules()["utility_rules"]["well_septic_min_distance"]["value"],
                   "well_positions": [list(point.coords[0]) for point in utilities.wells],
                   "septic_positions": [list(point.coords[0]) for point in utilities.septic_tanks]},
        "access": {"gate": None, "garage": None, "driveway": None},
        "environment": {"location": requirements.get("location"), "solar_samples": solar, "shadow_analysis": shadows},
        "vegetation_nodes": [], "vertical_greenery": {"triggered": False, "elements": [], "status": "not_evaluated"},
        "outdoor_lighting": {"nodes": []}, "outdoor_elements": [],
        "factors_assessment": assessment,
        "concept_rules_applied": [],
        "rule_evaluations": rule_results["rule_evaluations"],
        "rule_summary": rule_results["category_summaries"],
        "approval_status": "blocked" if violations else rule_results["approval_status"],
        "validation_summary": {**validation, "reason": reason},
        "metrics": collect_metrics(started, area, max(0.0, area - context.house.area), 0, 0, utilities.status,
                                    False, bool(solar), False, validation),
        "coordinate_reference": "local Cartesian coordinates in meters; source unit normalized by ELIA",
    }


def run_elia(master_json: Mapping[str, Any], raw_requirements: Mapping[str, Any], run_id: str) -> tuple[dict[str, Any], str]:
    started = time.perf_counter()
    master_json = normalize_master_json(master_json)
    context = parse_exterior_context(master_json, default_units=elia_rules()["units"]["default_input"])
    requirements = normalize_requirements(raw_requirements, master_json, context.source_units)
    logger.info("ELIA spatial run started")
    req_units_raw = raw_requirements.get("units")  # None means omitted → treat as "m"
    req_units = str(req_units_raw).lower() if req_units_raw is not None else "m"
    utilities = validate_utilities(master_json, raw_requirements, context.source_units, req_units)
    restrictions = _auxiliary_polygons(master_json, context.unit_scale)
    restrictions.extend(utilities.buffers)
    residual_result = calculate_residual_space(context.land, context.house, restrictions)
    residual = residual_result.geometry
    solar_samples = calculate_solar_samples(requirements)
    shadows = analyze_shadows(context.house, _building_height(master_json, context.unit_scale), solar_samples,
                              requirements.get("north_angle"))

    utility_obstacles = unary_union(restrictions) if restrictions else Polygon()
    drive_width = float(requirements["access"].get("preferred_driveway_width_m") or elia_rules()["access"]["default_driveway_width_m"])
    clearance = float(elia_rules()["access"]["driveway_clearance_m"])
    fixed_obstacles = unary_union([context.house, utility_obstacles]) if not utility_obstacles.is_empty else context.house
    gate = plan_gate(context.land, context.house, master_json, requirements["access"], context.unit_scale, utility_obstacles)
    if gate is None:
        violations = ["gate_candidate_or_road_access"]
        if utilities.status == "failed":
            violations.append("well_septic_separation")
        elif utilities.status == "unknown":
            violations.append("utility_locations_unknown")
        output = _empty_result(context, requirements, utilities, solar_samples, shadows, violations,
                               "No valid gate lies on a road-accessible land-boundary segment.", started)
        output["run_id"] = run_id
        return output, "infeasible"

    garage_obstacles = unary_union([context.house, utility_obstacles]) if not utility_obstacles.is_empty else context.house
    garage = plan_garage(context.land, residual, gate, master_json, requirements["access"], context.unit_scale,
                         garage_obstacles, drive_width / 2 + clearance + 0.1)
    driveway_line: LineString | None = None
    driveway_polygon: Polygon | None = None
    turning: dict[str, Any] | None = None
    explored = 0
    path_metadata: dict[str, Any] | None = None
    if requirements["access"].get("garage_required") and int(requirements["access"].get("garage_capacity", 1)) < int(requirements["access"].get("vehicle_count", 1)):
        violations = ["garage_capacity"]
        output = _empty_result(context, requirements, utilities, solar_samples, shadows, violations,
                               "Requested garage capacity is lower than the vehicle count.", started)
        output["access"]["gate"] = gate
        output["run_id"] = run_id
        return output, "infeasible"
    if (master_json.get("garage") or master_json.get("existing_garage")) and garage is None:
        violations = ["fixed_garage_geometry"]
        output = _empty_result(context, requirements, utilities, solar_samples, shadows, violations,
                               "The fixed garage in Master JSON fails exterior containment or clearance validation.", started)
        output["access"]["gate"] = gate
        output["run_id"] = run_id
        return output, "infeasible"
    if requirements["access"].get("garage_required") and garage is None:
        violations = ["garage_candidate"]
        output = _empty_result(context, requirements, utilities, solar_samples, shadows, violations,
                               "No garage candidate satisfies residual-space and fixed-obstacle constraints.", started)
        output["access"]["gate"] = gate
        output["run_id"] = run_id
        return output, "infeasible"

    if requirements["access"].get("driveway_required"):
        goal = garage.get("access_point") if garage else _entrance_target(master_json, context.house, context.unit_scale)
        if goal is not None:
            navigation_obstacles = fixed_obstacles
            if garage:
                navigation_obstacles = unary_union([navigation_obstacles, garage_polygon(garage)])
            navigable = context.land.buffer(-float(elia_rules()["access"]["boundary_clearance_m"])).difference(
                navigation_obstacles.buffer(drive_width / 2 + clearance))
            access_rules = elia_rules()["access"]
            resolution = float(access_rules["grid_resolution_m"])
            grid = build_navigation_grid(navigable, resolution,
                                         int(elia_rules()["access"]["max_grid_cells"]))
            best_safe_route = None
            direct_route = None
            if garage:
                direct_line = LineString([tuple(gate["access_point"]), tuple(garage["entry_point"])])
                direct_polygon = direct_line.buffer(drive_width / 2, cap_style="flat", join_style="mitre")
                direct_safe = (context.land.covers(direct_polygon) and
                               not direct_polygon.intersects(fixed_obstacles) and
                               direct_polygon.intersection(garage_polygon(garage)).area <= 1e-6)
                direct_turning = {"valid": False, "vehicles": []}
                if direct_safe:
                    checks = [validate_vehicle_route(list(direct_line.coords), profile, drive_width, clearance)
                              for profile in requirements["access"]["vehicle_profiles"]]
                    direct_turning = {"valid": all(check["valid"] for check in checks), "vehicles": checks}
                    if direct_turning["valid"]:
                        direct_route = (direct_line, direct_polygon, direct_turning, "direct")
            for turn_penalty in (0.0, float(access_rules["astar_turn_penalty_m"])):
                route = astar_path(grid, tuple(gate["access_point"]), tuple(goal), turn_penalty=turn_penalty)
                explored += route["explored_nodes"]
                if not route["found"]:
                    continue
                route_coordinates = list(route["coordinates"])
                if garage:
                    if Point(route_coordinates[-1]).distance(Point(goal)) > 1e-6:
                        route_coordinates.append(tuple(goal))
                    route_coordinates.append(tuple(garage["entry_point"]))
                raw_line = LineString(route_coordinates)
                for multiplier in access_rules["route_smoothing_multipliers"]:
                    tolerance = resolution * float(multiplier)
                    candidate_line = raw_line.simplify(tolerance, preserve_topology=True)
                    if candidate_line.geom_type != "LineString" or len(candidate_line.coords) < 2:
                        candidate_line = raw_line
                    candidate_polygon = candidate_line.buffer(drive_width / 2, cap_style="flat", join_style="mitre")
                    candidate_safe = (context.land.covers(candidate_polygon) and
                                      not candidate_polygon.intersects(fixed_obstacles) and
                                      (garage is None or candidate_polygon.intersection(garage_polygon(garage)).area <= 1e-6))
                    if not candidate_safe:
                        continue
                    vehicle_checks = [validate_vehicle_route(list(candidate_line.coords), profile, drive_width, clearance)
                                      for profile in requirements["access"]["vehicle_profiles"]]
                    candidate_turning = {"valid": all(check["valid"] for check in vehicle_checks), "vehicles": vehicle_checks}
                    candidate = (candidate_line, candidate_polygon, candidate_turning, route["turn_penalty"])
                    if best_safe_route is None:
                        best_safe_route = candidate
                    if candidate_turning["valid"]:
                        best_safe_route = candidate
                        break
                if best_safe_route is not None and best_safe_route[2]["valid"]:
                    break
            if direct_route is not None:
                best_safe_route = direct_route
            if best_safe_route is not None:
                driveway_line, driveway_polygon, turning, used_turn_penalty = best_safe_route
                path_metadata = {"pathfinding": "direct_validated_connector" if used_turn_penalty == "direct" else "A*",
                                 "turn_penalty_cost": None if used_turn_penalty == "direct" else used_turn_penalty,
                                 "explored_nodes": explored, "centerline": list(driveway_line.coords),
                                 "polygon": list(driveway_polygon.exterior.coords) if driveway_polygon.geom_type == "Polygon" else None,
                                 "width_m": drive_width, "length_m": driveway_line.length, "turning_validation": turning}

    driveway_obstacle = driveway_polygon if driveway_polygon is not None else Polygon()
    garage_obstacle = garage_polygon(garage) if garage else Polygon()
    requested_paths = _requested_paths(context, master_json, gate, garage, driveway_polygon,
                                        driveway_line, fixed_obstacles, residual, requirements)
    path_obstacles = [Polygon(path["polygon"]) for path in requested_paths.values()
                      if path.get("valid") and path.get("polygon")]
    vegetation_blocked = unary_union([fixed_obstacles, driveway_obstacle, garage_obstacle, *path_obstacles])

    # Route locked features by category to respective planners
    locked_features = requirements.get("locked_features") or []
    locked_veg = []
    locked_outdoor = []
    locked_lighting = []
    for lf in locked_features:
        cat = str(lf.get("category") or lf.get("feature_type") or lf.get("type") or "").lower()
        if cat in {"seating", "outdoor_seating", "dining", "garden_seating", "garden_table_set"}:
            locked_outdoor.append(lf)
        elif cat in {"lighting", "light", "luminaire", "fixture"}:
            locked_lighting.append(lf)
        else:
            locked_veg.append(lf)

    vegetation = place_vegetation(residual, context.land, vegetation_blocked, requirements, shadows, locked_nodes=locked_veg)
    concept_rules = getattr(vegetation, "concept_rules", [])
    allocated_access = [driveway_obstacle, garage_obstacle]
    allocated_access.extend(Polygon(path["polygon"]) for path in requested_paths.values()
                            if path.get("valid") and path.get("polygon"))
    access_area = unary_union([geometry for geometry in allocated_access if not geometry.is_empty])
    plantable_ground = residual.difference(access_area)
    usable_planting_ratio = plantable_ground.area / context.land.area if context.land.area else 0.0
    vertical = plan_vertical_greenery(usable_planting_ratio, requirements, master_json, context.unit_scale)
    outdoor_obstacles = [vegetation_blocked, *path_obstacles]
    outdoor_obstacles.extend(Point(node["position"]).buffer(float(node["canopy_radius_m"])) for node in vegetation)
    outdoor_blocked = unary_union(outdoor_obstacles)
    outdoor = place_outdoor_elements(residual, outdoor_blocked, requirements, gate, context.land,
                                     driveway_polygon, requested_paths, locked_features=locked_outdoor)
    lighting_obstacles = [fixed_obstacles, garage_obstacle, *path_obstacles]
    lighting_obstacles.extend(Point(node["position"]).buffer(float(node["canopy_radius_m"])) for node in vegetation)
    lighting_obstacles.extend(Polygon(item["polygon"]) for item in outdoor
                              if item.get("type") in {"garden_seating", "garden_table_set"} and item.get("polygon"))
    lighting = place_lighting(context.land, residual, driveway_line, gate, garage, requirements,
                              unary_union(lighting_obstacles), locked_features=locked_lighting)
    requested_lighting_zones = raw_requirements.get("lighting", {}).get("zones", [])
    missing_lighting_zones = [zone for zone in requested_lighting_zones
                              if requirements.get("lighting", {}).get("required") and
                              not any(node.get("zone") == zone for node in lighting)]
    live_solar = None
    if requirements.get("include_live_solar", False):
        try:
            location = requirements["location"]
            live_solar = fetch_live_solar_conditions(location["latitude"], location["longitude"],
                                                     location.get("timezone"))
        except ELIAError as exc:
            live_solar = {"status": "unavailable", "provider": "Open-Meteo",
                          "error_code": exc.code, "message": exc.message}
    obstacles = fixed_obstacles
    validation = validate_layout(context.land, context.house, gate, garage, driveway_polygon, driveway_line,
                                 turning, {"status": utilities.status}, vegetation, lighting, vertical, outdoor,
                                 solar_samples, obstacles, master_json, context.unit_scale,
                                 requirements["access"]["vehicle_profiles"], drive_width, requirements,
                                 residual=residual)

    validation["valid"] = not validation["violations"]
    validation["constraint_satisfaction_rate"] = (validation["checks_passed"] / validation["checks_total"]
                                                   if validation["checks_total"] else 1.0)
    outcome = "valid" if validation["valid"] else "infeasible"

    candidate_preview = {
        "vegetation_nodes": vegetation,
        "outdoor_elements": outdoor,
        "outdoor_lighting": {"nodes": lighting},
        "access": {"gate": gate, "garage": garage, "driveway": path_metadata},
        "vertical_greenery": vertical,
    }
    rule_results = evaluate_rules(
        candidate=candidate_preview,
        context=context,
        master_json=master_json,
        requirements=requirements,
        validation_summary=validation,
        shadow_samples=shadows,
    )

    factors_assessment = build_factors_assessment(
        residual_area_m2=residual.area,
        land_area_m2=context.land.area,
        house_area_m2=context.house.area,
        vegetation=vegetation,
        shadow_samples=shadows,
        requirements=requirements,
        concept_rules_applied=concept_rules,
        validation_summary=validation,
        rule_evaluations=rule_results["rule_evaluations"],
        category_summaries=rule_results["category_summaries"],
        approval_status=rule_results["approval_status"],
    )

    ground_features = []
    if driveway_polygon:
        ground_features.append(driveway_polygon)

    if garage:
        ground_features.append(garage_polygon(garage))
    for path in requested_paths.values():
        if path.get("valid") and path.get("polygon"):
            ground_features.append(Polygon(path["polygon"]))
    for node in vegetation:
        ground_features.append(Point(node["position"]).buffer(float(node["canopy_radius_m"])))
    for item in outdoor:
        if item.get("polygon"):
            ground_features.append(Polygon(item["polygon"]))
    used_area = unary_union(ground_features).intersection(residual).area if ground_features else 0.0
    metrics = collect_metrics(started, context.land.area, residual_result.available_area,
                              driveway_line.length if driveway_line else 0.0, explored, utilities.status,
                              bool(turning and turning["valid"]), bool(solar_samples), vertical["triggered"],
                              validation, used_area)
    landscape_preferences = raw_requirements.get("landscape", {})
    access_preferences = raw_requirements.get("access", {})
    unsupported_preferences = [
        name for name, value in (
            ("preferred_garden_zone", landscape_preferences.get("preferred_garden_zone")),
            ("preferred_open_space_ratio", landscape_preferences.get("preferred_open_space_ratio")),
            ("driveway_style", access_preferences.get("driveway_style")),
            ("driveway_surface", access_preferences.get("driveway_surface")),
            ("entrance_priority", access_preferences.get("entrance_priority")),
            ("property_orientation", raw_requirements.get("property_orientation")),
            ("design_style_geometry", raw_requirements.get("design_style")),
            ("utility_relocation_allowed", raw_requirements.get("utility_relocation_allowed")),
            ("additional_requirements", raw_requirements.get("additional_requirements")),
        ) if value is not None and value is not False and value != "" and value != {} and value != []
    ]
    requested_categories = landscape_preferences.get("preferred_vegetation_categories", [])
    produced_categories = {node.get("category") for node in vegetation}
    unfulfilled_preferences = []
    if requested_categories and any(category not in produced_categories for category in requested_categories):
        unfulfilled_preferences.append("preferred_vegetation_categories")
    if landscape_preferences.get("shade_tree_preference") and "shade_tree" not in produced_categories:
        unfulfilled_preferences.append("shade_tree_preference")
    if raw_requirements.get("utility_relocation_allowed"):
        unfulfilled_preferences.append("utility_relocation_allowed")
    if access_preferences.get("gate_type") and gate.get("type") != access_preferences["gate_type"]:
        unfulfilled_preferences.append("gate_type")
    preferred_gate = requirements["access"].get("preferred_gate_location_m") or requirements["access"].get("preferred_gate_location")
    if preferred_gate and gate and Point(preferred_gate).distance(Point(gate["position"])) > 0.5:
        unfulfilled_preferences.append("preferred_gate_location")
    preferred_garage = requirements["access"].get("preferred_garage_location_m") or requirements["access"].get("preferred_garage_location")
    if preferred_garage and garage and Point(preferred_garage).distance(garage_polygon(garage).centroid) > 0.5:
        unfulfilled_preferences.append("preferred_garage_location")
    for pref_key, type_val in (("garden_table_set_required", "garden_table_set"), ("garden_seating_required", "garden_seating")):
        if landscape_preferences.get(pref_key) and not any(item.get("type") == type_val and item.get("validation", {}).get("valid") for item in outdoor):
            unfulfilled_preferences.append(pref_key)
    unfulfilled_preferences.extend(f"lighting_zone:{zone}" for zone in missing_lighting_zones)
    result = {
        "version": "1.0", "run_id": run_id, "theme_concept": requirements.get("design_style"),
        "spatial_strategy": "vertical" if vertical["status"] == "placed" else "horizontal",
        "site_analysis": {"land_area_m2": residual_result.land_area, "house_footprint_area_m2": residual_result.house_area,
                          "available_ground_area_m2": residual_result.available_area,
                          "available_ground_ratio": residual_result.available_ratio,
                          "restricted_area_m2": residual_result.restricted_area,
                          "preferred_open_space_ratio": requirements.get("landscape", {}).get("preferred_open_space_ratio")},
        "utility_safety": {"checks": list(utilities.checks), "status": utilities.status,
                   "required_separation_ft": elia_rules()["utility_rules"]["well_septic_min_distance"]["value"],
                   "well_positions": [list(point.coords[0]) for point in utilities.wells],
                   "septic_positions": [list(point.coords[0]) for point in utilities.septic_tanks],
                   "relocation_allowed_by_user": bool(requirements.get("utility_relocation_allowed", False)),
                   "relocation_performed": False},
        "access": {"gate": gate, "gates": [gate, *gate.get("additional_gates", [])],
               "garage": garage, "driveway": path_metadata},
        "environment": {"location": requirements["location"], "property_orientation": requirements.get("property_orientation"),
                "north_angle": requirements.get("north_angle"), "solar_analysis_date": requirements["solar_analysis_date"],
            "north_orientation_convention": requirements["north_orientation_convention"],
                "solar_samples": solar_samples, "shadow_analysis": shadows,
                "live_solar_conditions": live_solar or {"status": "not_requested"}},
        "vegetation_nodes": vegetation, "vertical_greenery": vertical,
        "outdoor_lighting": {"nodes": lighting, "style": requirements.get("lighting", {}).get("style")},
        "outdoor_elements": outdoor,
        "factors_assessment": factors_assessment,
        "concept_rules_applied": concept_rules,
        "rule_evaluations": rule_results["rule_evaluations"],
        "rule_summary": rule_results["category_summaries"],
        "approval_status": rule_results["approval_status"],
        "preference_fulfillment": {"unsupported_preferences": unsupported_preferences,
                       "unfulfilled_preferences": unfulfilled_preferences,
                       "label_only_preferences": []},
        "overlap_policy": {"elevated_canopy_access_overlap": "not_permitted_without_verified_clearance",
                   "furniture_access_overlap": "prohibited",
                   "trunk_radius_assessment": "unavailable; no trunk-radius input is modeled",
                   "structural_load_assessed": False},
        "vehicle_feasibility_scope": "2D centerline turning-radius estimate only; swept-path and full vehicle maneuverability are not established",
        "structural_load_assessed": False,
        "validation_summary": validation, "metrics": metrics,
        "input_traceability": {"requirements": dict(raw_requirements), "source_units": context.source_units,
                               "normalized_units": "m", "normalized_polygon_rings": list(context.normalized_rings)},
        "coordinate_reference": "local Cartesian coordinates in meters; source unit normalized by ELIA",
    }
    logger.info("ELIA run finished: project=%s outcome=%s explored=%d", master_json.get("project_id"), outcome, explored)
    return result, outcome


def validate_candidate_exterior(
    master_json: Mapping[str, Any],
    candidate: Mapping[str, Any],
    raw_requirements: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    if not isinstance(candidate, Mapping):
        raise ELIAError("ELIA_INVALID_CANDIDATE_PAYLOAD", "Candidate must be a valid JSON object.")

    master_json = normalize_master_json(master_json)
    context = parse_exterior_context(master_json, default_units=elia_rules()["units"]["default_input"])
    requirements = normalize_requirements(raw_requirements or {}, master_json, context.source_units)
    utilities = validate_utilities(master_json, raw_requirements or {}, context.source_units, "m")
    restrictions = _auxiliary_polygons(master_json, context.unit_scale)
    restrictions.extend(utilities.buffers)
    residual_result = calculate_residual_space(context.land, context.house, restrictions)
    residual = residual_result.geometry
    fixed_obstacles = unary_union([context.house, unary_union(restrictions)]) if restrictions else context.house

    solar_samples = calculate_solar_samples(requirements)
    shadows_result = analyze_shadows(context.house, _building_height(master_json, context.unit_scale), solar_samples,
                                     requirements.get("north_angle"))
    shadow_samples = shadows_result

    access = candidate.get("access", {})
    gate = access.get("gate")
    garage = access.get("garage")
    driveway_meta = access.get("driveway") or {}
    driveway_poly = Polygon(driveway_meta["polygon"]) if driveway_meta.get("polygon") else None
    driveway_line = LineString(driveway_meta["centerline"]) if driveway_meta.get("centerline") else None
    turning = driveway_meta.get("turning_validation")

    vegetation = list(candidate.get("vegetation_nodes", []))
    lighting = list(candidate.get("outdoor_lighting", {}).get("nodes", []))
    outdoor = list(candidate.get("outdoor_elements", []))
    vertical = candidate.get("vertical_greenery", {"triggered": False, "elements": []})

    drive_width = float(requirements["access"].get("preferred_driveway_width_m") or elia_rules()["access"]["default_driveway_width_m"])

    # Base layout validation (gate, garage, driveway, turning)
    base_validation = validate_layout(
        context.land, context.house, gate, garage, driveway_poly, driveway_line,
        turning, {"status": utilities.status}, vegetation, lighting, vertical, outdoor,
        solar_samples, fixed_obstacles, master_json, context.unit_scale,
        requirements["access"]["vehicle_profiles"], drive_width, requirements,
        residual=residual
    )

    violations: list[str] = list(base_validation.get("violations", []))
    checks_passed = base_validation.get("checks_passed", 0)
    checks_total = base_validation.get("checks_total", 0)

    def record_check(passed: bool, violation_name: str | None = None):
        nonlocal checks_passed, checks_total
        checks_total += 1
        if passed:
            checks_passed += 1
        elif violation_name and violation_name not in violations:
            violations.append(violation_name)

    # 1. Structural and ID validation
    seen_ids: set[str] = set()
    for v in vegetation:
        jid = str(v.get("json_id") or "").strip()
        record_check(bool(jid and jid not in seen_ids), f"duplicate_or_missing_id_{jid}" if jid else "missing_vegetation_id")
        if jid:
            seen_ids.add(jid)

    for o in outdoor:
        jid = str(o.get("json_id") or "").strip()
        record_check(bool(jid and jid not in seen_ids), f"duplicate_or_missing_id_{jid}" if jid else "missing_outdoor_id")
        if jid:
            seen_ids.add(jid)

    for l in lighting:
        jid = str(l.get("json_id") or "").strip()
        record_check(bool(jid and jid not in seen_ids), f"duplicate_or_missing_id_{jid}" if jid else "missing_lighting_id")
        if jid:
            seen_ids.add(jid)

    # 2. Recompute and validate vegetation
    cat_entries = {e["vegetation_id"]: e for e in vegetation_catalog()["entries"]}
    clean_vegetation: list[dict[str, Any]] = []

    for v in vegetation:
        pos = v.get("position")
        valid_pos = (
            isinstance(pos, (list, tuple))
            and len(pos) == 2
            and isfinite(float(pos[0]))
            and isfinite(float(pos[1]))
        )
        record_check(valid_pos, f"invalid_position_{v.get('json_id')}")
        if not valid_pos:
            continue
        px, py = float(pos[0]), float(pos[1])
        r = float(v.get("canopy_radius_m") or 1.0)
        valid_r = isfinite(r) and r > 0
        record_check(valid_r, f"invalid_canopy_radius_{v.get('json_id')}")
        if not valid_r:
            continue

        pt = Point(px, py)
        canopy = pt.buffer(r)
        record_check(context.land.covers(canopy), f"vegetation_outside_land_{v.get('json_id')}")
        record_check(not canopy.intersects(fixed_obstacles), f"vegetation_intersects_obstacles_{v.get('json_id')}")

        pid = v.get("plant_id")
        cat_entry = cat_entries.get(pid, {})
        is_verified = bool(cat_entry.get("verified_species_data", False))
        sun_score = _calculate_afternoon_sun_score(pt, shadow_samples)

        if is_verified:
            sun_text = f"Sunlight exposure {sun_score * 100:.0f}%" if sun_score is not None else "Sunlight exposure unmeasured/unknown"
            suitability_reason = (
                f"Species '{cat_entry.get('scientific_name') or cat_entry.get('display_name')}': "
                f"{sun_text}, Water need '{cat_entry.get('water_demand', 'unknown')}', "
                f"Maintenance '{cat_entry.get('maintenance_level', 'unknown')}'."
            )
        else:
            suitability_reason = "Procedural planning envelope; species suitability not assessed."

        clean_v = dict(v)
        clean_v.pop("budget_estimate", None)
        clean_v.pop("budget_assessment", None)
        clean_v["position"] = [round(px, 3), round(py, 3)]
        clean_v["canopy_radius_m"] = r
        clean_v["solar_suitability"] = round(sun_score, 3) if sun_score is not None else None
        clean_v["exposure_status"] = "estimated" if sun_score is not None else "unknown"
        clean_v["verified_species_data"] = is_verified
        clean_v["source_reference"] = cat_entry.get("source_reference")
        clean_v["suitability_explanation"] = suitability_reason
        clean_vegetation.append(clean_v)

    # Feature-specific vegetation canopy overlap
    for i, v1 in enumerate(clean_vegetation):
        p1 = Point(v1["position"])
        r1 = float(v1["canopy_radius_m"])
        for j in range(i + 1, len(clean_vegetation)):
            v2 = clean_vegetation[j]
            p2 = Point(v2["position"])
            r2 = float(v2["canopy_radius_m"])
            record_check(p1.distance(p2) >= max(r1, r2), f"vegetation_overlap_{v1.get('json_id')}_{v2.get('json_id')}")

    # 3. Recompute and validate outdoor elements (recomputing footprints when position changes)
    clean_outdoor: list[dict[str, Any]] = []
    for o in outdoor:
        pos = o.get("position")
        dims = o.get("dimensions") or {}
        w = float(dims.get("width_m") or dims.get("width") or 1.5)
        d = float(dims.get("depth_m") or dims.get("depth") or 1.5)
        valid_dims = isfinite(w) and isfinite(d) and w > 0 and d > 0
        record_check(valid_dims, f"invalid_dimensions_{o.get('json_id')}")

        if pos and isinstance(pos, (list, tuple)) and len(pos) == 2 and isfinite(float(pos[0])) and isfinite(float(pos[1])):
            px, py = float(pos[0]), float(pos[1])
            footprint = box(px - w / 2, py - d / 2, px + w / 2, py + d / 2)
            poly_coords = list(footprint.exterior.coords)
        elif o.get("polygon"):
            poly = Polygon(o["polygon"])
            footprint = poly
            poly_coords = list(poly.exterior.coords)
            px, py = poly.centroid.x, poly.centroid.y
        else:
            footprint = None
            poly_coords = None
            px, py = 0.0, 0.0

        clean_o = dict(o)
        clean_o.pop("budget_estimate", None)
        clean_o.pop("budget_assessment", None)
        if footprint is not None:
            clean_o["position"] = [round(px, 3), round(py, 3)]
            clean_o["polygon"] = poly_coords
            clean_o["dimensions"] = {"width_m": w, "depth_m": d}
            record_check(context.land.covers(footprint), f"outdoor_element_outside_land_{o.get('json_id')}")
            record_check(not footprint.intersects(fixed_obstacles), f"outdoor_element_intersects_obstacles_{o.get('json_id')}")
        clean_outdoor.append(clean_o)

    # Outdoor pairwise overlap: allow legitimate path connections to seating
    for i, o1 in enumerate(clean_outdoor):
        poly1 = Polygon(o1["polygon"]) if o1.get("polygon") else None
        t1 = str(o1.get("type") or "").lower()
        if not poly1:
            continue
        for j in range(i + 1, len(clean_outdoor)):
            o2 = clean_outdoor[j]
            poly2 = Polygon(o2["polygon"]) if o2.get("polygon") else None
            t2 = str(o2.get("type") or "").lower()
            if not poly2:
                continue
            if ("path" in t1 and ("seating" in t2 or "table" in t2 or "dining" in t2)) or \
               ("path" in t2 and ("seating" in t1 or "table" in t1 or "dining" in t1)):
                continue
            is_overlap = poly1.intersects(poly2) and poly1.intersection(poly2).area > 1e-4
            record_check(not is_overlap, f"outdoor_element_overlap_{o1.get('json_id')}_{o2.get('json_id')}")

    # 4. Recompute and validate lighting
    clean_lighting: list[dict[str, Any]] = []
    for l in lighting:
        pos = l.get("position")
        valid_pos = (
            isinstance(pos, (list, tuple))
            and len(pos) == 2
            and isfinite(float(pos[0]))
            and isfinite(float(pos[1]))
        )
        record_check(valid_pos, f"invalid_position_{l.get('json_id')}")
        if not valid_pos:
            continue
        px, py = float(pos[0]), float(pos[1])
        pt = Point(px, py)
        record_check(context.land.covers(pt), f"lighting_outside_land_{l.get('json_id')}")
        clean_l = dict(l)
        clean_l.pop("budget_estimate", None)
        clean_l.pop("budget_assessment", None)
        clean_l["position"] = [round(px, 3), round(py, 3)]
        clean_lighting.append(clean_l)

    rule_results = evaluate_rules(
        candidate={
            "vegetation_nodes": clean_vegetation,
            "outdoor_elements": clean_outdoor,
            "outdoor_lighting": {"nodes": clean_lighting},
            "access": candidate.get("access", {}),
            "vertical_greenery": candidate.get("vertical_greenery", {}),
        },
        context=context,
        master_json=master_json,
        requirements=requirements,
        validation_summary={
            "valid": len(violations) == 0,
            "violations": violations,
            "checks_passed": checks_passed,
            "checks_total": checks_total,
        },
        shadow_samples=shadow_samples,
    )

    for hb in rule_results.get("hard_blocks", []):
        hb_id = f"rule_violation_{hb['rule_id']}"
        if hb_id not in violations:
            violations.append(hb_id)

    validation_summary = {
        "valid": len(violations) == 0,
        "violations": violations,
        "checks_passed": checks_passed,
        "checks_total": max(checks_total, 1),
        "constraint_satisfaction_rate": round(checks_passed / checks_total, 3) if checks_total else 1.0,
    }

    factors_assessment = build_factors_assessment(
        residual_area_m2=residual.area,
        land_area_m2=context.land.area,
        house_area_m2=context.house.area,
        vegetation=clean_vegetation,
        shadow_samples=shadow_samples,
        requirements=requirements,
        concept_rules_applied=candidate.get("concept_rules_applied", []),
        validation_summary=validation_summary,
        rule_evaluations=rule_results["rule_evaluations"],
        category_summaries=rule_results["category_summaries"],
        approval_status=rule_results["approval_status"],
    )

    canonical_candidate = dict(candidate)
    obsolete_keys = [k for k in canonical_candidate if any(fin in k.lower() for fin in ("budget", "price", "cost", "quotation", "lkr", "subtotal"))]
    for k in obsolete_keys:
        canonical_candidate.pop(k, None)
    canonical_candidate["vegetation_nodes"] = clean_vegetation
    canonical_candidate["outdoor_elements"] = clean_outdoor
    canonical_candidate["outdoor_lighting"] = {
        **(candidate.get("outdoor_lighting") or {}),
        "nodes": clean_lighting,
    }
    canonical_candidate["validation_summary"] = validation_summary
    canonical_candidate["factors_assessment"] = factors_assessment
    canonical_candidate["rule_evaluations"] = rule_results["rule_evaluations"]
    canonical_candidate["rule_summary"] = rule_results["category_summaries"]
    canonical_candidate["approval_status"] = rule_results["approval_status"]

    return {
        "valid": validation_summary["valid"],
        "violations": violations,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "constraint_satisfaction_rate": validation_summary["constraint_satisfaction_rate"],
        "factors_assessment": factors_assessment,
        "rule_evaluations": rule_results["rule_evaluations"],
        "rule_summary": rule_results["category_summaries"],
        "approval_status": rule_results["approval_status"],
        "hard_blocks": rule_results["hard_blocks"],
        "conditional_reviews": rule_results["conditional_reviews"],
        "validation_summary": validation_summary,
        "canonical_candidate": canonical_candidate,
    }
