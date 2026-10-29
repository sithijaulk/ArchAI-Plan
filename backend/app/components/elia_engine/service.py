from __future__ import annotations

import logging
import time
import math
from copy import deepcopy
from math import cos, hypot, isfinite, pi, sin
from typing import Any, Mapping

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box, shape, mapping
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
from .solar_planner import plan_solar_pv, evaluate_solar_structural_evidence
from .elevated_features import plan_elevated_features
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


def run_elia(
    master_json: Mapping[str, Any],
    raw_requirements: Mapping[str, Any],
    run_id: str,
    generation_mode: str = "rules_planner",
) -> tuple[dict[str, Any], str]:
    valid_modes = {"rules_planner", "baseline", "rules_and_geometric_planner", "baseline_demo"}
    if generation_mode.lower() not in valid_modes:
        raise ELIAError(
            code="UNSUPPORTED_GENERATION_MODE",
            message=f"Generation mode '{generation_mode}' is unsupported. Production ELIA operates strictly on Rules + Geometric Layout Planner / Optimizer without external neural models or checkpoints.",
            status_code=400,
        )

    started = time.perf_counter()
    master_json = normalize_master_json(master_json)
    context = parse_exterior_context(master_json, default_units=elia_rules()["units"]["default_input"])
    requirements = normalize_requirements(raw_requirements, master_json, context.source_units)
    logger.info("ELIA spatial run started (mode: %s)", generation_mode)
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

    veh_count = int(requirements["access"].get("vehicle_count") or 1)
    if int(requirements["access"].get("garage_capacity") or 1) < veh_count:
        requirements["access"]["garage_capacity"] = veh_count

    garage_obstacles = unary_union([context.house, utility_obstacles]) if not utility_obstacles.is_empty else context.house
    garage = plan_garage(context.land, residual, gate, master_json, requirements["access"], context.unit_scale,
                         garage_obstacles, drive_width / 2 + clearance + 0.1)
    driveway_line: LineString | None = None
    driveway_polygon: Polygon | None = None
    turning: dict[str, Any] | None = None
    explored = 0
    path_metadata: dict[str, Any] | None = None
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
            driveway_style_pref = str(requirements["access"].get("driveway_style") or "auto").lower()
            best_safe_route = None
            direct_route = None
            goal_point = tuple(garage["entry_point"]) if garage else tuple(goal)
            
            # 1. Test direct straight connector
            direct_line = LineString([tuple(gate["access_point"]), goal_point])
            direct_polygon = direct_line.buffer(drive_width / 2, cap_style="flat", join_style="mitre")
            direct_safe = (context.land.covers(direct_polygon) and
                           not direct_polygon.intersects(fixed_obstacles) and
                           (garage is None or direct_polygon.intersection(garage_polygon(garage)).area <= 1e-6))
            if direct_safe:
                checks = [validate_vehicle_route(list(direct_line.coords), profile, drive_width, clearance)
                          for profile in requirements["access"]["vehicle_profiles"]]
                direct_turning = {"valid": all(check["valid"] for check in checks), "vehicles": checks}
                if direct_turning["valid"]:
                    direct_route = (direct_line, direct_polygon, direct_turning, "direct")

            # 2. Test curved A* path
            curved_route = None
            if driveway_style_pref in {"curved", "auto"}:
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
                        if curved_route is None:
                            curved_route = candidate
                        if candidate_turning["valid"]:
                            curved_route = candidate
                            break
                    if curved_route is not None and curved_route[2]["valid"]:
                        break

            # 3. Apply driveway style selection without silent substitution
            if driveway_style_pref == "straight":
                if direct_route is not None:
                    best_safe_route = direct_route
                else:
                    # Explicit straight requested but obstructed: do NOT silently fallback to curved
                    path_metadata = {
                        "json_id": "DRIVEWAY_001",
                        "type": "driveway",
                        "pathfinding": "straight_connector_infeasible",
                        "chosen_style": "straight",
                        "status": "infeasible",
                        "reason": "STRAIGHT_DRIVEWAY_OBSTRUCTED",
                        "explanation": "Explicit straight driveway cannot connect without intersecting buildings or site boundaries.",
                        "validation": {"valid": False},
                        "units": "m",
                    }
            elif driveway_style_pref == "curved":
                if curved_route is not None:
                    best_safe_route = curved_route
                else:
                    path_metadata = {
                        "json_id": "DRIVEWAY_001",
                        "type": "driveway",
                        "pathfinding": "curved_astar_infeasible",
                        "chosen_style": "curved",
                        "status": "infeasible",
                        "reason": "CURVED_DRIVEWAY_OBSTRUCTED",
                        "explanation": "No navigable curved A* path satisfies boundary clearance and turning radius.",
                        "validation": {"valid": False},
                        "units": "m",
                    }
            else:  # "auto"
                if direct_route is not None:
                    best_safe_route = direct_route
                elif curved_route is not None:
                    best_safe_route = curved_route

            if best_safe_route is not None:
                driveway_line, driveway_polygon, turning, used_turn_penalty = best_safe_route
                chosen_style = "straight" if used_turn_penalty == "direct" else "curved"
                driveway_surface = str(requirements["access"].get("driveway_surface") or "asphalt")
                path_metadata = {
                    "json_id": "DRIVEWAY_001",
                    "type": "driveway",
                    "pathfinding": "direct_validated_connector" if used_turn_penalty == "direct" else "A*",
                    "chosen_style": chosen_style,
                    "surface_material": driveway_surface,
                    "turn_penalty_cost": None if used_turn_penalty == "direct" else used_turn_penalty,
                    "explored_nodes": explored,
                    "centerline": list(driveway_line.coords),
                    "polygon": list(driveway_polygon.exterior.coords) if driveway_polygon.geom_type == "Polygon" else None,
                    "width_m": drive_width,
                    "length_m": driveway_line.length,
                    "turning_validation": turning,
                    "units": "m",
                }

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
    live_solar = None
    if requirements.get("include_live_solar", False):
        try:
            location = requirements["location"]
            live_solar = fetch_live_solar_conditions(location["latitude"], location["longitude"],
                                                     location.get("timezone"))
        except ELIAError as exc:
            live_solar = {"status": "unavailable", "provider": "Open-Meteo",
                          "error_code": exc.code, "message": exc.message}

    solar_plan = plan_solar_pv(
        master_json,
        requirements,
        context.unit_scale,
        solar_samples=solar_samples,
        live_solar=live_solar,
    )
    elevated_plan = plan_elevated_features(master_json, requirements, context.unit_scale, solar_plan=solar_plan)
    if solar_plan and solar_plan.get("status") in ("fulfilled", "review_required") and solar_plan.get("outdoor_element"):
        outdoor.append(solar_plan["outdoor_element"])
    if elevated_plan.get("elements"):
        outdoor.extend(elevated_plan["elements"])
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
    water_preferences = raw_requirements.get("water_features", {})
    solar_preferences = raw_requirements.get("solar", {})
    balcony_preferences = raw_requirements.get("balconies", {})
    terrace_preferences = raw_requirements.get("terrace", {})
    # Generate non-overlapping ground surfaces partition
    ground_surfaces: list[dict[str, Any]] = []
    claimed_surface_geom = unary_union([context.house, unary_union(restrictions)]) if restrictions else context.house

    # 1. Driveway surface
    if driveway_polygon and not driveway_polygon.is_empty:
        dsurf = driveway_polygon.difference(claimed_surface_geom)
        if not dsurf.is_empty:
            driveway_surface_mat = str(access_preferences.get("driveway_surface") or "asphalt")
            ground_surfaces.append({
                "json_id": "SURFACE_DRIVEWAY_001",
                "type": "driveway",
                "material": driveway_surface_mat,
                "area_m2": round(float(dsurf.area), 2),
                "polygon": list(dsurf.exterior.coords) if dsurf.geom_type == "Polygon" else None,
                "geometry": mapping(dsurf),
            })
            claimed_surface_geom = claimed_surface_geom.union(dsurf)

    # 2. Pedestrian path surface
    path_surf_mat = str(landscape_preferences.get("pedestrian_path_surface") or landscape_preferences.get("walking_path_surface") or "pavers")
    path_polys = [Polygon(p["polygon"]) for p in requested_paths.values() if p.get("valid") and p.get("polygon")]
    if path_polys:
        psurf = unary_union(path_polys).difference(claimed_surface_geom)
        if not psurf.is_empty:
            ground_surfaces.append({
                "json_id": "SURFACE_PATHS_001",
                "type": "pedestrian_path",
                "material": path_surf_mat,
                "area_m2": round(float(psurf.area), 2),
                "polygon": list(psurf.exterior.coords) if psurf.geom_type == "Polygon" else None,
                "geometry": mapping(psurf),
            })
            claimed_surface_geom = claimed_surface_geom.union(psurf)

    # 3. Garden beds surface
    veg_buffers = [Point(n["position"]).buffer(float(n.get("canopy_radius_m", 1.0)) * 0.7) for n in vegetation if n.get("position")]
    if veg_buffers:
        vsurf = unary_union(veg_buffers).intersection(residual).difference(claimed_surface_geom)
        if not vsurf.is_empty:
            ground_surfaces.append({
                "json_id": "SURFACE_GARDEN_BEDS_001",
                "type": "garden_bed",
                "material": "mulch_soil",
                "area_m2": round(float(vsurf.area), 2),
                "geometry": mapping(vsurf),
            })
            claimed_surface_geom = claimed_surface_geom.union(vsurf)

    # 4. Lawn surface (remaining open residual ground)
    lawn_ground = residual.difference(claimed_surface_geom)
    if not lawn_ground.is_empty:
        lawn_finish_mat = str(landscape_preferences.get("open_space_finish") or "natural_grass")
        ground_surfaces.append({
            "json_id": "SURFACE_LAWN_001",
            "type": "lawn",
            "material": lawn_finish_mat,
            "area_m2": round(float(lawn_ground.area), 2),
            "geometry": mapping(lawn_ground),
        })

    # Unsupported & Unfulfilled tracking
    unsupported_preferences = [
        name for name, value in (
            ("preferred_garden_zone", landscape_preferences.get("preferred_garden_zone")),
            ("preferred_open_space_ratio", landscape_preferences.get("preferred_open_space_ratio")),
            ("entrance_priority", access_preferences.get("entrance_priority")),
            ("property_orientation", raw_requirements.get("property_orientation")),
            ("design_style_geometry", raw_requirements.get("design_style")),
            ("utility_relocation_allowed", raw_requirements.get("utility_relocation_allowed")),
            ("additional_requirements", raw_requirements.get("additional_requirements")),
            ("swimming_pool", water_preferences.get("swimming_pool_required")),
            ("pond", water_preferences.get("pond_required")),
            ("well", water_preferences.get("well_required")),
            ("garden_taps", water_preferences.get("garden_taps_required")),
            ("solar_panels", solar_preferences.get("panels_required")),
            ("rooftop_planting", terrace_preferences.get("planting_required")),
            ("rooftop_seating", terrace_preferences.get("seating_required")),
            ("rooftop_tables", terrace_preferences.get("tables_required")),
            ("balcony_planting", balcony_preferences.get("planting_required")),
            ("balcony_seating", balcony_preferences.get("seating_required")),
            ("balcony_potted_plants", balcony_preferences.get("potted_plants")),
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

    # Detailed Structured Requirement Tracking across 11 preference groups
    fulfillment_items: dict[str, dict[str, Any]] = {}
    
    # Parking & Garage
    if access_preferences.get("parking_required", True):
        bays_placed = sum(1 for el in outdoor if el.get("type") == "parking_bay" and el.get("validation", {}).get("valid"))
        has_garage = garage is not None and garage.get("valid", True)
        if has_garage or bays_placed > 0:
            fulfillment_items["parking"] = {
                "status": "fulfilled",
                "original_request": {"parking_required": True, "vehicle_count": access_preferences.get("vehicle_count", 1)},
                "actual_quantity": (garage.get("capacity", 1) if garage else 0) + bays_placed,
                "generated_type": "garage" if garage else "parking_bay",
            }
        else:
            fulfillment_items["parking"] = {
                "status": "infeasible",
                "original_request": {"parking_required": True},
                "actual_quantity": 0,
                "reason_codes": ["NO_RESIDUAL_SPACE_FOR_PARKING"],
            }
    else:
        fulfillment_items["parking"] = {"status": "explicitly_disabled", "original_request": False, "actual_quantity": 0}

    # Driveway style
    req_style = str(access_preferences.get("driveway_style") or "auto").lower()
    if access_preferences.get("driveway_required", True):
        if path_metadata and path_metadata.get("status") == "infeasible":
            fulfillment_items["driveway_style"] = {
                "status": "infeasible",
                "original_request": req_style,
                "actual_state": None,
                "reason_codes": [path_metadata.get("reason", "DRIVEWAY_OBSTRUCTED")],
                "supported_alternatives": ["curved"] if req_style == "straight" else ["straight"],
            }
        elif driveway_polygon is not None:
            chosen_style = path_metadata.get("chosen_style", req_style)
            fulfillment_items["driveway_style"] = {
                "status": "fulfilled",
                "original_request": req_style,
                "actual_state": chosen_style,
                "material": path_metadata.get("surface_material"),
            }
        else:
            fulfillment_items["driveway_style"] = {
                "status": "infeasible",
                "original_request": req_style,
                "actual_state": None,
                "reason_codes": ["DRIVEWAY_UNRESOLVED"],
            }

    # Water features
    for wf_key, elem_type in [("garden_taps_required", "garden_tap"), ("well_required", "water_well"),
                              ("septic_tank_required", "septic_tank"), ("pond_required", "garden_pond"),
                              ("swimming_pool_required", "swimming_pool")]:
        if water_preferences.get(wf_key):
            matched = [el for el in outdoor if el.get("type") == elem_type]
            if matched and any(m.get("validation", {}).get("valid") for m in matched):
                fulfillment_items[wf_key] = {
                    "status": "review_required",
                    "original_request": True,
                    "actual_quantity": len(matched),
                    "missing_evidence": ["technical_plumbing_or_excavation_certification"],
                    "reason_codes": ["PROPOSAL_REQUIRES_TECHNICAL_EVIDENCE"],
                }
            else:
                fulfillment_items[wf_key] = {
                    "status": "infeasible",
                    "original_request": True,
                    "actual_quantity": 0,
                    "reason_codes": ["INSUFFICIENT_SPACE_OR_BUFFER_CONFLICT"],
                }

    # Balcony & Rooftop Elevated Features
    if elevated_plan and elevated_plan.get("fulfillment_updates"):
        fulfillment_items.update(elevated_plan["fulfillment_updates"])

    # Solar PV Fulfillment
    if solar_preferences.get("panels_required"):
        if solar_plan and solar_plan.get("status") == "fulfilled":
            fulfillment_items["solar_panels"] = {
                "status": "fulfilled",
                "approval_status": "approved",
                "original_request": True,
                "actual_quantity": solar_plan["module_count"],
                "installed_capacity_kw": solar_plan["system_capacity_kw"],
                "surface_id": solar_plan["surface_id"],
                "estimated_annual_generation_kwh": solar_plan.get("estimated_annual_yield_kwh") or solar_plan.get("energy_estimation", {}).get("estimated_annual_yield_kwh", 0.0),
            }
        elif solar_plan and solar_plan.get("status") == "review_required":
            fulfillment_items["solar_panels"] = {
                "status": "review_required",
                "approval_status": "provisional_review_required",
                "provisional_preview": True,
                "original_request": True,
                "actual_quantity": solar_plan.get("module_count", 0),
                "installed_capacity_kw": solar_plan.get("system_capacity_kw", 0.0),
                "surface_id": solar_plan.get("surface_id"),
                "reason_codes": ["PROVISIONAL_GEOMETRIC_PREVIEW_REQUIRING_STRUCTURAL_SIGN_OFF"],
                "missing_evidence": solar_plan.get("missing_evidence", ["structural_load_certification"]),
                "estimated_annual_generation_kwh": solar_plan.get("estimated_annual_yield_kwh") or solar_plan.get("energy_estimation", {}).get("estimated_annual_yield_kwh", 0.0),
            }
        elif solar_plan and solar_plan.get("status") in ("evidence_missing",):
            fulfillment_items["solar_panels"] = {
                "status": "evidence_missing",
                "original_request": True,
                "actual_quantity": 0,
                "reason_codes": [solar_plan.get("reason", "MISSING_ROOF_GEOMETRY")],
                "missing_evidence": solar_plan.get("missing_evidence", ["authoritative_roof_surfaces"]),
                "supported_alternatives": ["Ground solar array or community microgrid."],
            }
        else:
            fulfillment_items["solar_panels"] = {
                "status": solar_plan.get("status", "infeasible") if solar_plan else "infeasible",
                "original_request": True,
                "actual_quantity": 0,
                "reason_codes": [solar_plan.get("reason", "MISSING_ROOF_GEOMETRY")] if solar_plan else ["MISSING_ROOF_GEOMETRY"],
                "supported_alternatives": ["Ground solar array or community microgrid."],
            }
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
                "solar_installation": solar_plan,
                "live_solar_conditions": live_solar or {"status": "not_requested"}},
        "vegetation_nodes": vegetation, "vertical_greenery": vertical,
        "outdoor_lighting": {"nodes": lighting, "style": requirements.get("lighting", {}).get("style")},
        "outdoor_elements": outdoor,
        "ground_surfaces": ground_surfaces,
        "factors_assessment": factors_assessment,
        "concept_rules_applied": concept_rules,
        "rule_evaluations": rule_results["rule_evaluations"],
        "rule_summary": rule_results["category_summaries"],
        "approval_status": rule_results["approval_status"],
        "preference_fulfillment": {
            "items": fulfillment_items,
            "unsupported_preferences": unsupported_preferences,
            "unfulfilled_preferences": unfulfilled_preferences,
            "label_only_preferences": [],
        },
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


PARAMETRIC_OUTDOOR_TYPES = {
    "garden_seating", "garden_table_set", "pergola", "deck", "gazebo",
    "parking_bay", "rooftop_table", "rooftop_chair", "rooftop_table_set",
    "rooftop_planter", "balcony_pot"
}

POLYGON_AUTHORITATIVE_TYPES = {
    "boundary_wall", "garden_zone", "lawn_zone", "patio", "path",
    "pedestrian_path", "garden_path", "custom_feature", "water_body",
    "pond", "rockery", "swimming_pool"
}


def _parse_strict_positive(val: Any) -> tuple[bool, float | None]:
    if val is None:
        return True, None
    if isinstance(val, bool):
        return False, None
    try:
        f = float(val)
        if math.isfinite(f) and f > 0:
            return True, f
    except (TypeError, ValueError):
        pass
    return False, None


def _parse_strict_angle(val: Any) -> tuple[bool, float]:
    if val is None:
        return True, 0.0
    if isinstance(val, bool):
        return False, 0.0
    try:
        f = float(val)
        if math.isfinite(f):
            return True, f
    except (TypeError, ValueError):
        pass
    return False, 0.0


def validate_candidate_exterior(
    master_json: Mapping[str, Any],
    candidate: Mapping[str, Any],
    raw_requirements: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    if not isinstance(candidate, Mapping):
        raise ELIAError("ELIA_INVALID_CANDIDATE_PAYLOAD", "Candidate must be a valid JSON object.")

    # Guarantee input candidate immutability
    candidate = deepcopy(dict(candidate))
    master_json = normalize_master_json(master_json)
    context = parse_exterior_context(master_json, default_units=elia_rules()["units"]["default_input"])
    
    if raw_requirements is None:
        saved_reqs = master_json.get("exterior_requirements") or master_json.get("processing", {}).get("elia_engine", {}).get("requirements")
        if saved_reqs:
            effective_raw_reqs = saved_reqs
        elif ("access" not in candidate or not candidate.get("access")):
            effective_raw_reqs = {"access": {"driveway_required": False, "gate_required": False}}
        else:
            effective_raw_reqs = {}
    else:
        effective_raw_reqs = raw_requirements

    requirements = normalize_requirements(effective_raw_reqs, master_json, context.source_units)
    utilities = validate_utilities(master_json, effective_raw_reqs, context.source_units, "m")
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

    violations: list[str] = []
    checks_passed = 0
    checks_total = 0

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
            and not isinstance(pos[0], bool)
            and not isinstance(pos[1], bool)
            and isfinite(float(pos[0]))
            and isfinite(float(pos[1]))
        )
        record_check(valid_pos, f"invalid_position_{v.get('json_id')}")
        if not valid_pos:
            continue
        px, py = float(pos[0]), float(pos[1])
        r = float(v.get("canopy_radius_m") or 1.0)
        valid_r = not isinstance(v.get("canopy_radius_m"), bool) and isfinite(r) and 0.1 <= r <= 10.0
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

    # 3. Clean and validate outdoor elements by Category
    clean_outdoor: list[dict[str, Any]] = []
    for o in outdoor:
        jid = str(o.get("json_id") or "").strip()
        o_type = str(o.get("type") or "").lower()
        dims = o.get("dimensions") if isinstance(o.get("dimensions"), Mapping) else {}
        pos = o.get("position")

        raw_w = dims.get("width_m") if "width_m" in dims else dims.get("width")
        raw_d = dims.get("depth_m") if "depth_m" in dims else (dims.get("depth") if "depth" in dims else (dims.get("length_m") if "length_m" in dims else dims.get("length")))

        w_valid, parsed_w = _parse_strict_positive(raw_w)
        d_valid, parsed_d = _parse_strict_positive(raw_d)
        record_check(w_valid and d_valid, f"invalid_dimensions_{jid}")

        raw_rot = o.get("rotation_deg") if "rotation_deg" in o else (o.get("orientation_deg") if "orientation_deg" in o else o.get("azimuth_degrees"))
        rot_valid, angle = _parse_strict_angle(raw_rot)
        record_check(rot_valid, f"invalid_rotation_{jid}")

        pos_valid = (
            isinstance(pos, (list, tuple))
            and len(pos) == 2
            and not isinstance(pos[0], bool)
            and not isinstance(pos[1], bool)
            and isfinite(float(pos[0]))
            and isfinite(float(pos[1]))
        )
        if pos is not None:
            record_check(pos_valid, f"invalid_position_{jid}")

        w = parsed_w if parsed_w is not None else 1.5
        d = parsed_d if parsed_d is not None else 1.5

        if o_type in {"garden_seating", "garden_table_set", "pergola", "deck", "gazebo"}:
            dim_within_limits = (0.5 <= w <= 10.0) and (0.5 <= d <= 10.0)
            record_check(dim_within_limits, f"dimension_limits_exceeded_{jid}")

        footprint = None
        poly_coords = None
        px, py = 0.0, 0.0
        clean_o = dict(o)
        clean_o.pop("budget_estimate", None)
        clean_o.pop("budget_assessment", None)

        if o_type in PARAMETRIC_OUTDOOR_TYPES:
            # Canonical footprint derived server-side from parameters
            if pos_valid:
                px, py = float(pos[0]), float(pos[1])
                base_box = box(px - w / 2, py - d / 2, px + w / 2, py + d / 2)
                canonical_poly = affinity.rotate(base_box, angle, origin=(px, py)) if (angle % 360) != 0 else base_box
                footprint = canonical_poly
                poly_coords = list(canonical_poly.exterior.coords)

                # Check if supplied polygon contradicts canonical parameters
                if o.get("polygon"):
                    try:
                        cand = Polygon(o["polygon"])
                        if cand.is_valid and not cand.is_empty:
                            c_dist = canonical_poly.centroid.distance(cand.centroid)
                            a_diff = abs(canonical_poly.area - cand.area)
                            # If contradictory beyond numerical tolerance, canonical geometry replaces it
                            if c_dist > 0.05 or a_diff > 0.05:
                                footprint = canonical_poly
                                poly_coords = list(canonical_poly.exterior.coords)
                    except Exception:
                        pass
            elif o.get("polygon"):
                try:
                    cand = Polygon(o["polygon"])
                    if cand.is_valid and not cand.is_empty:
                        footprint = cand
                        poly_coords = list(cand.exterior.coords)
                        px, py = cand.centroid.x, cand.centroid.y
                except Exception:
                    footprint = None

        elif o_type in POLYGON_AUTHORITATIVE_TYPES or o.get("authoritative_geometry") == "polygon":
            # Preserve irregular geometry and interior holes verbatim
            raw_p = o.get("polygon") or o.get("geometry") or o.get("coordinates")
            cand_poly = None
            if raw_p is not None:
                try:
                    if isinstance(raw_p, Mapping):
                        cand_poly = shape(raw_p)
                    elif isinstance(raw_p, (list, tuple)) and raw_p:
                        if isinstance(raw_p[0], (list, tuple)) and len(raw_p[0]) > 0 and isinstance(raw_p[0][0], (list, tuple)):
                            cand_poly = Polygon(raw_p[0], raw_p[1:])
                        else:
                            cand_poly = Polygon(raw_p)
                except Exception:
                    cand_poly = None

            if cand_poly is not None and cand_poly.is_valid and not cand_poly.is_empty:
                footprint = cand_poly
                if cand_poly.geom_type == "Polygon":
                    poly_coords = list(cand_poly.exterior.coords)
                    if cand_poly.interiors:
                        clean_o["holes"] = [list(ring.coords) for ring in cand_poly.interiors]
                elif hasattr(cand_poly, "geoms") and len(cand_poly.geoms) > 0:
                    poly_coords = list(cand_poly.geoms[0].exterior.coords)
                else:
                    poly_coords = list(cand_poly.convex_hull.exterior.coords)
                px, py = cand_poly.centroid.x, cand_poly.centroid.y
                record_check(True, f"valid_irregular_polygon_{jid}")
            else:
                record_check(False, f"invalid_irregular_polygon_{jid}")

        elif o_type in ("solar_panel_array", "solar_panel"):
            # Solar array: preserve all individual modules and their geometry
            modules = o.get("modules") or o.get("panels") or []
            clean_modules = []
            module_polys = []
            for mod in modules:
                if isinstance(mod, Mapping):
                    mod_p = mod.get("polygon") or mod.get("footprint") or mod.get("coordinates")
                    if mod_p and isinstance(mod_p, (list, tuple)) and len(mod_p) >= 3:
                        try:
                            mpoly = Polygon(mod_p)
                            if mpoly.is_valid and not mpoly.is_empty:
                                module_polys.append(mpoly)
                                clean_m = dict(mod)
                                clean_m["polygon"] = list(mpoly.exterior.coords)
                                clean_modules.append(clean_m)
                        except Exception:
                            pass
            if clean_modules:
                clean_o["modules"] = clean_modules
            if module_polys:
                footprint = unary_union(module_polys)
                poly_coords = list(footprint.exterior.coords) if footprint.geom_type == "Polygon" else list(footprint.convex_hull.exterior.coords)
                px, py = footprint.centroid.x, footprint.centroid.y
            elif o.get("polygon"):
                try:
                    cand = Polygon(o["polygon"])
                    if cand.is_valid and not cand.is_empty:
                        footprint = cand
                        poly_coords = list(cand.exterior.coords)
                        px, py = cand.centroid.x, cand.centroid.y
                except Exception:
                    footprint = None
            if footprint is None and pos_valid:
                px, py = float(pos[0]), float(pos[1])
                base_box = box(px - w / 2, py - d / 2, px + w / 2, py + d / 2)
                footprint = affinity.rotate(base_box, angle, origin=(px, py)) if (angle % 360) != 0 else base_box
                poly_coords = list(footprint.exterior.coords)

            # Unified authoritative solar evidence validation
            ev_eval = evaluate_solar_structural_evidence(
                supporting_surface_id=o.get("supporting_surface_id"),
                master_json=master_json,
                requirements=requirements,
                element=o,
            )
            clean_o["structural_evidence_evaluation"] = ev_eval
            clean_o["is_approved"] = ev_eval["is_approved"]
            clean_o["provisional_geometric_preview"] = not ev_eval["is_approved"]
            if not ev_eval["is_approved"] and ev_eval.get("reason"):
                clean_o["review_reason"] = ev_eval["reason"]

        else:
            # Generic / custom outdoor element
            if o.get("polygon"):
                try:
                    cand = shape(o["polygon"]) if isinstance(o["polygon"], Mapping) else Polygon(o["polygon"])
                    if cand.is_valid and not cand.is_empty:
                        footprint = cand
                        if cand.geom_type == "Polygon":
                            poly_coords = list(cand.exterior.coords)
                        elif hasattr(cand, "geoms") and len(cand.geoms) > 0:
                            poly_coords = list(cand.geoms[0].exterior.coords)
                        else:
                            poly_coords = list(cand.convex_hull.exterior.coords)
                        px, py = cand.centroid.x, cand.centroid.y
                except Exception:
                    footprint = None
            if footprint is None and pos_valid:
                px, py = float(pos[0]), float(pos[1])
                base_box = box(px - w / 2, py - d / 2, px + w / 2, py + d / 2)
                footprint = affinity.rotate(base_box, angle, origin=(px, py)) if (angle % 360) != 0 else base_box
                poly_coords = list(footprint.exterior.coords)

        if footprint is not None:
            clean_o["position"] = [round(px, 3), round(py, 3)]
            clean_o["polygon"] = poly_coords
            is_elevated = bool(o.get("supporting_surface_id")) or o_type in (
                "solar_panel_array", "solar_panel", "balcony_pot", "rooftop_planter",
                "rooftop_table", "rooftop_chair", "rooftop_table_set"
            )
            is_zone_or_boundary = o_type in {"boundary_wall", "garden_zone", "lawn_zone"}
            if not is_elevated and not is_zone_or_boundary:
                record_check(context.land.covers(footprint), f"outdoor_element_outside_land_{jid}")
                record_check(not footprint.intersects(fixed_obstacles), f"outdoor_element_intersects_obstacles_{jid}")
            elif is_zone_or_boundary:
                record_check(context.land.covers(footprint), f"outdoor_element_outside_land_{jid}")
        clean_outdoor.append(clean_o)

    # Outdoor pairwise overlap: allow legitimate path connections to seating, and ignore zones
    for i, o1 in enumerate(clean_outdoor):
        poly1 = Polygon(o1["polygon"]) if o1.get("polygon") else None
        t1 = str(o1.get("type") or "").lower()
        if not poly1 or t1 in {"boundary_wall", "garden_zone", "lawn_zone"}:
            continue
        for j in range(i + 1, len(clean_outdoor)):
            o2 = clean_outdoor[j]
            poly2 = Polygon(o2["polygon"]) if o2.get("polygon") else None
            t2 = str(o2.get("type") or "").lower()
            if not poly2 or t2 in {"boundary_wall", "garden_zone", "lawn_zone"}:
                continue
            if ("path" in t1 and ("seating" in t2 or "table" in t2 or "dining" in t2)) or \
               ("path" in t2 and ("seating" in t1 or "table" in t1 or "dining" in t1)):
                continue
            elev1 = bool(o1.get("supporting_surface_id")) or t1 in ("solar_panel_array", "solar_panel", "balcony_pot", "rooftop_planter", "rooftop_table", "rooftop_chair")
            elev2 = bool(o2.get("supporting_surface_id")) or t2 in ("solar_panel_array", "solar_panel", "balcony_pot", "rooftop_planter", "rooftop_table", "rooftop_chair")
            if elev1 != elev2:
                continue
            if elev1 and elev2 and o1.get("supporting_surface_id") != o2.get("supporting_surface_id"):
                continue
            is_overlap = poly1.intersects(poly2) and poly1.intersection(poly2).area > 1e-4
            record_check(not is_overlap, f"outdoor_element_overlap_{o1.get('json_id')}_{o2.get('json_id')}")

    # 4. Clean and validate lighting
    clean_lighting: list[dict[str, Any]] = []
    for l in lighting:
        pos = l.get("position")
        valid_pos = (
            isinstance(pos, (list, tuple))
            and len(pos) == 2
            and not isinstance(pos[0], bool)
            and not isinstance(pos[1], bool)
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

    # 5. Base layout validation using identical canonical geometries
    drive_width = float(requirements["access"].get("preferred_driveway_width_m") or elia_rules()["access"]["default_driveway_width_m"])
    base_validation = validate_layout(
        context.land, context.house, gate, garage, driveway_poly, driveway_line,
        turning, {"status": utilities.status}, clean_vegetation, clean_lighting, vertical, clean_outdoor,
        solar_samples, fixed_obstacles, master_json, context.unit_scale,
        requirements["access"]["vehicle_profiles"], drive_width, requirements,
        residual=residual
    )
    for bv in base_validation.get("violations", []):
        if bv not in violations:
            violations.append(bv)
    checks_passed += base_validation.get("checks_passed", 0)
    checks_total += base_validation.get("checks_total", 0)

    # 6. Evaluate rules on canonical candidate
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

    has_solar_elements = any(
        str(o.get("type")).lower() in ("solar_panel_array", "solar_panel")
        for o in clean_outdoor
    )
    solar_unverified = any(
        not o.get("structural_evidence_evaluation", {}).get("is_approved", True)
        for o in clean_outdoor if str(o.get("type")).lower() in ("solar_panel_array", "solar_panel")
    )
    if solar_unverified:
        rule_results["approval_status"] = "review_required"
        reviews = rule_results.setdefault("conditional_reviews", [])
        if not any(cr.get("rule_id") == "SOLAR_STRUCTURAL_EVIDENCE" for cr in reviews):
            reviews.append({
                "rule_id": "SOLAR_STRUCTURAL_EVIDENCE",
                "category": "solar_panels",
                "severity": "review",
                "message": "Solar PV installation requires verified structural engineering sign-off.",
                "missing_evidence": ["structural_load_certification"],
            })
    elif has_solar_elements and len(violations) == 0 and len(rule_results.get("hard_blocks", [])) == 0:
        rule_results["approval_status"] = "approved"

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


def evaluate_acceptance_policy(
    validation_result: Mapping[str, Any],
    candidate: Mapping[str, Any] | None = None,
    master_json: Mapping[str, Any] | None = None,
    requirements: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Authoritative ELIA acceptance policy evaluator.
    
    Determines whether an exterior candidate is approved for accepted persistence.
    - Geometric validity alone does NOT imply approval.
    - Derives approval strictly from server evaluations, never client-supplied flags.
    - Unresolved blocking reviews (review_required) or missing evidence (evidence_missing)
      block acceptance and preserve existing accepted designs.
    - Unrecognized/unknown approval states are rejected.
    - Distinguishes informational warnings from blocking reviews.
    - Returns structured decision: accepted (bool), approval_status, blocking_reasons,
      blocking_features, missing_evidence, warnings, message.
    """
    valid = bool(validation_result.get("valid", False))
    violations = list(validation_result.get("violations", []))
    hard_blocks = list(validation_result.get("hard_blocks", []))
    conditional_reviews = list(validation_result.get("conditional_reviews", []))
    
    # Server approval status from validation_result or candidate
    server_status = str(
        validation_result.get("approval_status")
        or (candidate.get("approval_status") if isinstance(candidate, Mapping) else None)
        or "unknown"
    ).strip().lower()

    blocking_reasons: list[str] = []
    blocking_features: list[str] = []
    missing_evidence: list[str] = []
    warnings: list[str] = []

    if not valid:
        blocking_reasons.extend(violations)
        for v in violations:
            if "solar" in v:
                blocking_features.append("solar_panels")
            elif "vegetation" in v:
                blocking_features.append("vegetation")
            elif "outdoor" in v or "furniture" in v:
                blocking_features.append("outdoor_elements")
            elif "lighting" in v:
                blocking_features.append("lighting")
            elif "gate" in v or "driveway" in v or "garage" in v:
                blocking_features.append("access")
            elif "utility" in v:
                blocking_features.append("utilities")
            else:
                blocking_features.append("geometry")

    for hb in hard_blocks:
        rule_id = hb.get("rule_id", "rule_violation")
        msg = f"HARD_BLOCK: {rule_id} - {hb.get('message', 'Compliance rule violation')}"
        if msg not in blocking_reasons:
            blocking_reasons.append(msg)
        blocking_features.append(hb.get("category", "compliance"))

    has_solar_element = False
    solar_element_unapproved = False
    # Inspect candidate elements for unverified solar structural evidence
    if isinstance(candidate, Mapping):
        for o in candidate.get("outdoor_elements", []):
            if isinstance(o, Mapping) and str(o.get("type")).lower() in ("solar_panel_array", "solar_panel"):
                has_solar_element = True
                ev = o.get("structural_evidence_evaluation")
                if not ev:
                    ev = evaluate_solar_structural_evidence(
                        supporting_surface_id=o.get("supporting_surface_id"),
                        master_json=master_json or {},
                        requirements=requirements,
                        element=o,
                    )
                if not ev.get("is_approved"):
                    solar_element_unapproved = True
                    blocking_features.append("solar_panels")
                    reason = f"SOLAR_STRUCTURAL_EVIDENCE_REJECTED: {ev.get('reason', 'Missing structural certification')}"
                    if reason not in blocking_reasons:
                        blocking_reasons.append(reason)
                    for me in ev.get("missing_evidence", []):
                        if me not in missing_evidence:
                            missing_evidence.append(me)

        # Inspect candidate environment solar installation
        env_solar = candidate.get("environment", {}).get("solar_installation")
        if isinstance(env_solar, Mapping):
            if env_solar.get("provisional_geometric_preview") is True or env_solar.get("status") in ("review_required", "evidence_missing"):
                solar_element_unapproved = True
                blocking_features.append("solar_panels")
                for me in env_solar.get("missing_evidence", []):
                    if me not in missing_evidence:
                        missing_evidence.append(me)

        # Inspect preference fulfillment
        fulfillment = (candidate.get("preference_fulfillment") or {}).get("items") or {}
        solar_ful = fulfillment.get("solar_panels")
        if isinstance(solar_ful, Mapping) and solar_ful.get("status") in ("review_required", "evidence_missing"):
            solar_element_unapproved = True
            blocking_features.append("solar_panels")
            for me in solar_ful.get("missing_evidence", []):
                if me not in missing_evidence:
                    missing_evidence.append(me)

    # Server approval status validation
    if server_status in ("review_required", "evidence_missing", "infeasible", "blocked", "rejected"):
        msg = f"UNAPPROVED_STATUS: Server evaluation resulted in '{server_status}'"
        if msg not in blocking_reasons:
            blocking_reasons.append(msg)
        if server_status == "review_required" and has_solar_element and solar_element_unapproved:
            blocking_features.append("solar_panels")
    elif server_status not in ("approved", "compliant", "conditional_draft_review_required"):
        blocking_reasons.append(f"UNRECOGNIZED_APPROVAL_STATUS: Server evaluation returned unknown status '{server_status}'")
        blocking_features.append("governance")

    # Distinguish blocking reviews from informational warnings in conditional_reviews
    for cr in conditional_reviews:
        rule_id = str(cr.get("rule_id") or "")
        category = str(cr.get("category") or "").lower()
        severity = str(cr.get("severity") or "").lower()
        is_info = cr.get("is_informational") is True or severity in ("info", "warning", "advisory")
        
        is_blocking = (
            rule_id == "SOLAR_STRUCTURAL_EVIDENCE"
            or category in ("solar_panels", "elevated_installation")
            or severity in ("blocking", "error", "hard_block")
            or cr.get("enforcement_consequence") == "block_acceptance"
        )
        
        if is_blocking and not is_info:
            reason = f"CONDITIONAL_REVIEW: {rule_id} - {cr.get('message', 'Review required')}"
            if reason not in blocking_reasons:
                blocking_reasons.append(reason)
            blocking_features.append(category or "compliance")
            for me in cr.get("missing_evidence", []):
                if me not in missing_evidence:
                    missing_evidence.append(me)
        else:
            msg = cr.get("message") or f"{rule_id}: Advisory review"
            if msg not in warnings:
                warnings.append(msg)

    # Check if required access features (driveway, gate) were omitted in save request
    if requirements and isinstance(requirements, Mapping):
        access_req = requirements.get("access") or {}
        if isinstance(candidate, Mapping):
            cand_acc = candidate.get("access") or {}
            if access_req.get("driveway_required") and not cand_acc.get("driveway"):
                blocking_features.append("access")
                blocking_reasons.append("MISSING_REQUIRED_DRIVEWAY: Driveway is required but absent from candidate.")
            if access_req.get("gate_required") and not cand_acc.get("gate"):
                blocking_features.append("access")
                blocking_reasons.append("MISSING_REQUIRED_GATE: Gate is required but absent from candidate.")

    accepted = (
        valid
        and len(hard_blocks) == 0
        and len(blocking_reasons) == 0
        and not solar_element_unapproved
    )

    message = None
    if not accepted:
        feats = ", ".join(sorted(set(blocking_features))) if blocking_features else "compliance"
        ev_info = f" Missing evidence: {', '.join(sorted(set(missing_evidence)))}." if missing_evidence else ""
        message = f"Candidate design cannot be accepted for persistence due to blocking compliance reviews ({feats}).{ev_info}"

    evaluated_status = "approved" if accepted else (
        "review_required" if any("solar" in f for f in blocking_features) else (
            server_status if server_status in ("review_required", "evidence_missing", "infeasible", "blocked") else "review_required"
        )
    )

    return {
        "accepted": accepted,
        "approval_status": evaluated_status,
        "blocking_reasons": sorted(set(blocking_reasons)),
        "blocking_features": sorted(set(blocking_features)),
        "missing_evidence": sorted(set(missing_evidence)),
        "warnings": warnings,
        "message": message,
    }

