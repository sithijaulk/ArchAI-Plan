from __future__ import annotations

import logging
import time
from math import cos, hypot, pi, sin
from typing import Any, Mapping

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .adapter import normalize_master_json
from .exceptions import ELIAError
from .gate_garage import plan_garage, plan_gate
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
from .vegetation import place_vegetation
from .vertical_greenery import plan_vertical_greenery

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
        return float(explicit_meters)
    value = master.get("building_height")
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
    return float(value) * scale if value is not None else None


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
            path_obstacles = unary_union([path_obstacles, Polygon(garage["polygon"])])
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
                drive_width = float(requirements["access"].get("preferred_driveway_width") or rules["default_driveway_width_m"])
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
    validation = {"valid": False, "violations": violations, "checks_passed": 0, "checks_total": len(violations),
                  "constraint_satisfaction_rate": 0.0}
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
    utilities = validate_utilities(master_json, raw_requirements, context.source_units,
                                   str(raw_requirements.get("units", "m")).lower())
    restrictions = _auxiliary_polygons(master_json, context.unit_scale)
    restrictions.extend(utilities.buffers)
    residual_result = calculate_residual_space(context.land, context.house, restrictions)
    residual = residual_result.geometry
    solar_samples = calculate_solar_samples(requirements)
    shadows = analyze_shadows(context.house, _building_height(master_json, context.unit_scale), solar_samples,
                              requirements.get("north_angle"))

    utility_obstacles = unary_union(restrictions) if restrictions else Polygon()
    drive_width = float(requirements["access"].get("preferred_driveway_width") or elia_rules()["access"]["default_driveway_width_m"])
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
                navigation_obstacles = unary_union([navigation_obstacles, Polygon(garage["polygon"])])
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
                               direct_polygon.intersection(Polygon(garage["polygon"])).area <= 1e-6)
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
                                      (garage is None or candidate_polygon.intersection(Polygon(garage["polygon"])).area <= 1e-6))
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
    garage_obstacle = Polygon(garage["polygon"]) if garage else Polygon()
    vegetation_blocked = unary_union([fixed_obstacles, driveway_obstacle, garage_obstacle])
    vegetation = place_vegetation(residual, context.land, vegetation_blocked, requirements, shadows)
    requested_paths = _requested_paths(context, master_json, gate, garage, driveway_polygon,
                                        driveway_line, fixed_obstacles, residual, requirements)
    allocated_access = [driveway_obstacle, garage_obstacle]
    allocated_access.extend(Polygon(path["polygon"]) for path in requested_paths.values()
                            if path.get("valid") and path.get("polygon"))
    access_area = unary_union([geometry for geometry in allocated_access if not geometry.is_empty])
    plantable_ground = residual.difference(access_area)
    usable_planting_ratio = plantable_ground.area / context.land.area if context.land.area else 0.0
    vertical = plan_vertical_greenery(usable_planting_ratio, requirements, master_json, context.unit_scale)
    outdoor_obstacles = [vegetation_blocked]
    outdoor_obstacles.extend(Point(node["position"]).buffer(float(node["canopy_radius_m"])) for node in vegetation)
    outdoor_blocked = unary_union(outdoor_obstacles)
    outdoor = place_outdoor_elements(residual, outdoor_blocked, requirements, gate, context.land,
                                     driveway_polygon, requested_paths)
    lighting_obstacles = [fixed_obstacles, garage_obstacle]
    lighting_obstacles.extend(Point(node["position"]).buffer(float(node["canopy_radius_m"])) for node in vegetation)
    lighting_obstacles.extend(Polygon(item["polygon"]) for item in outdoor
                              if item.get("type") in {"garden_seating", "garden_table_set"} and item.get("polygon"))
    lighting = place_lighting(context.land, residual, driveway_line, gate, garage, requirements,
                              unary_union(lighting_obstacles))
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
                                 requirements["access"]["vehicle_profiles"], drive_width, requirements)
    validation["valid"] = not validation["violations"]
    validation["constraint_satisfaction_rate"] = (validation["checks_passed"] / validation["checks_total"]
                                                   if validation["checks_total"] else 1.0)
    outcome = "valid" if validation["valid"] else "infeasible"
    used_area = (driveway_polygon.area if driveway_polygon else 0.0) + sum(3.14159 * node["canopy_radius_m"] ** 2 for node in vegetation)
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
            ("low_maintenance_preference", landscape_preferences.get("low_maintenance_preference")),
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
    preferred_garage = requirements["access"].get("preferred_garage_location")
    if preferred_garage and garage and Point(preferred_garage).distance(Polygon(garage["polygon"]).centroid) > 0.5:
        unfulfilled_preferences.append("preferred_garage_location")
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
        "preference_fulfillment": {"unsupported_preferences": unsupported_preferences,
                       "unfulfilled_preferences": unfulfilled_preferences,
                       "label_only_preferences": ["design_style"] if raw_requirements.get("design_style") else []},
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
