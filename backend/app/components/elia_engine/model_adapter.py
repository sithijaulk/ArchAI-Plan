from __future__ import annotations

from math import isfinite
from typing import Any, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, ValidationError, model_validator
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import unary_union

from ...config import settings
from .adapter import normalize_master_json
from .exceptions import ELIAError
from .geometry import point_xy
from .parser import parse_exterior_context
from .requirements import normalize_requirements
from .rule_repository import elia_rules
from .utility_safety import validate_utilities
from .vehicle_access import validate_vehicle_route


class ExteriorObject(BaseModel):
    model_config = ConfigDict(extra="allow")

    json_id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    position: list[FiniteFloat] | dict[str, FiniteFloat] | None = None
    polygon: list[list[FiniteFloat]] | None = None
    footprint: list[list[FiniteFloat]] | None = None
    elevation_m: FiniteFloat | None = None
    geometry: dict[str, Any] | None = None
    dimensions: dict[str, FiniteFloat] | None = None
    rotation_degrees: FiniteFloat | None = None
    units: str = "m"
    floor_id: str | None = None
    support_json_id: str | None = None

    @model_validator(mode="after")
    def validate_dimensions_and_position(self):
        if self.units != "m":
            raise ValueError("Exterior output coordinates and dimensions must use meters")
        if isinstance(self.position, list) and len(self.position) < 2:
            raise ValueError("Position must contain x and y coordinates")
        if isinstance(self.position, dict) and not {"x", "y"} <= self.position.keys():
            raise ValueError("Position must contain x and y coordinates")
        if self.dimensions and any(value <= 0 for value in self.dimensions.values()):
            raise ValueError("Object dimensions must be positive")
        if self.position is None and self.polygon is None and self.geometry is None:
            raise ValueError("Each exterior object requires position or geometry")
        if bool(self.floor_id) != bool(self.support_json_id):
            raise ValueError("Elevated objects must include both floor_id and support_json_id")
        return self


class ExteriorLandscapeOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = Field(min_length=1)
    version: str = "1.0"
    coordinate_reference: str = Field(min_length=1)
    access: dict[str, Any]
    site_analysis: dict[str, Any]
    utility_safety: dict[str, Any]
    environment: dict[str, Any]
    metrics: dict[str, Any]
    vegetation_nodes: list[ExteriorObject] = Field(default_factory=list)
    vertical_greenery: dict[str, Any] = Field(default_factory=dict)
    outdoor_lighting: dict[str, Any] = Field(default_factory=dict)
    outdoor_elements: list[ExteriorObject] = Field(default_factory=list)
    validation_summary: dict[str, Any] = Field(default_factory=dict)


class ModelAdapter(Protocol):
    model_version: str | None

    def infer(self, prepared_input: Mapping[str, Any]) -> Mapping[str, Any]: ...


class UnavailableModelAdapter:
    model_version = None

    def infer(self, prepared_input: Mapping[str, Any]) -> Mapping[str, Any]:
        configured = settings.elia_model_artifact_path or settings.elia_model_service_url
        detail = "ELIA trained-model inference is not configured."
        if configured:
            detail += " A connection is configured, but no runtime adapter is installed."
        raise ELIAError("ELIA_MODEL_UNAVAILABLE", detail, 503)


_registered_adapter: ModelAdapter | None = None


def configure_model_adapter(adapter: ModelAdapter | None) -> None:
    """Register the future inference implementation during application startup."""
    global _registered_adapter
    _registered_adapter = adapter


def prepare_model_input(master: Mapping[str, Any], raw_requirements: Mapping[str, Any]) -> dict[str, Any]:
    canonical = normalize_master_json(master)
    context = parse_exterior_context(canonical)
    requirements = normalize_requirements(raw_requirements, canonical, context.source_units)
    from shapely.geometry import mapping

    return {
        "schema_version": "1.0",
        "coordinate_reference": "local Cartesian meters; north angle is clockwise from local +Y toward +X",
        "north_angle_degrees": requirements["north_angle"],
        "land": mapping(context.land),
        "house_exterior": mapping(context.house),
        "requirements": requirements,
        "source_units": context.source_units,
    }


def _all_objects(value: Any):
    if isinstance(value, Mapping):
        if "json_id" in value:
            yield value
        for child in value.values():
            yield from _all_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_objects(child)


def _position_geometry(value: Any) -> Point | None:
    position = value.get("position")
    if isinstance(position, Mapping):
        coordinates = (position.get("x"), position.get("y"))
    elif isinstance(position, (list, tuple)) and len(position) >= 2:
        coordinates = position[:2]
    else:
        return None
    if not all(isinstance(item, (int, float)) and isfinite(float(item)) for item in coordinates):
        raise ValueError("non-finite position")
    return Point(float(coordinates[0]), float(coordinates[1]))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not isfinite(value):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _fixed_obstacles(master: Mapping[str, Any], context: Any, utility_result: Any):
    obstacles = [context.house]
    obstacles.extend(utility_result.buffers)
    utilities = master.get("utilities", {})
    if isinstance(utilities, Mapping):
        utility_radius = float(elia_rules()["utility_rules"]["fixed_utility_buffer"]["value"])
        for name, utility in utilities.items():
            if name in {"well", "septic_tank"}:
                continue
            position = point_xy(utility, context.unit_scale)
            if position is not None and all(isfinite(value) for value in position):
                obstacles.append(Point(position).buffer(utility_radius))
    restrictions = master.get("exterior_restrictions") or master.get("restricted_zones") or []
    restrictions = list(restrictions) if isinstance(restrictions, (list, tuple)) else [restrictions]
    fixed = master.get("fixed_exterior_objects") or master.get("exterior_fixed_objects") or []
    restrictions.extend(fixed if isinstance(fixed, list) else [fixed])
    for item in restrictions:
        raw = item.get("polygon") or item.get("geometry") or item.get("coordinates") if isinstance(item, Mapping) else item
        if raw is None and isinstance(item, Mapping):
            raw = item.get("footprint")
        try:
            if isinstance(raw, Mapping):
                geometry = shape(raw)
            elif isinstance(raw, (list, tuple)) and raw:
                rings = raw if isinstance(raw[0], (list, tuple)) and raw[0] and isinstance(raw[0][0], (list, tuple)) else [raw]
                geometry = Polygon(rings[0], rings[1:])
            else:
                continue
        except Exception as exc:
            raise ELIAError("ELIA_INVALID_MASTER_JSON", "An exterior restriction has invalid polygon geometry.") from exc
        if geometry.is_empty or not geometry.is_valid:
            raise ELIAError("ELIA_INVALID_MASTER_JSON", "An exterior restriction has invalid polygon geometry.")
        if context.unit_scale != 1:
            geometry = affinity.scale(geometry, xfact=context.unit_scale,
                                      yfact=context.unit_scale, origin=(0, 0))
        obstacles.append(geometry)
    return obstacles


def normalize_model_output(raw: Mapping[str, Any], run_id: str,
                           model_version: str | None) -> dict[str, Any]:
    try:
        parsed = ExteriorLandscapeOutput.model_validate(raw)
    except ValidationError as exc:
        raise ELIAError("ELIA_INVALID_MODEL_OUTPUT", f"Model output does not match the exterior schema: {exc.errors()[0]['msg']}.") from exc
    if parsed.schema_version != "1.0":
        raise ELIAError("ELIA_UNSUPPORTED_OUTPUT_SCHEMA", f"Unsupported exterior schema version {parsed.schema_version!r}.")

    result = parsed.model_dump(mode="json")
    result["schema_version"] = "1.0"
    result["version"] = "1.0"
    result["run_id"] = run_id
    result["generation_mode"] = "trained_model"
    result["model_version"] = model_version
    result["coordinate_reference"] = "local Cartesian coordinates in meters; north is clockwise from local +Y toward +X"
    return result


def validate_model_output(result: dict[str, Any], master: Mapping[str, Any],
                          raw_requirements: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    canonical = normalize_master_json(master)
    context = parse_exterior_context(canonical)
    requirements = normalize_requirements(raw_requirements, canonical, context.source_units)
    utility_result = validate_utilities(canonical, raw_requirements, context.source_units,
                                        str(raw_requirements.get("units", context.source_units)).lower())
    fixed_obstacles = _fixed_obstacles(canonical, context, utility_result)
    fixed_geometry = unary_union(fixed_obstacles)
    violations: list[str] = []
    seen_ids: dict[str, Mapping[str, Any]] = {}
    support_ids = set()
    support_by_id: dict[str, Mapping[str, Any]] = {}
    geometry_records: list[tuple[str, str, Any]] = []
    floor_ids = set()
    floor_plan = canonical.get("floor_plan", {})
    if isinstance(floor_plan, Mapping):
        for floor in floor_plan.get("floors", []) if isinstance(floor_plan.get("floors"), list) else []:
            if isinstance(floor, Mapping):
                floor_ids.add(str(floor.get("id", floor.get("json_id", ""))))
        ground = floor_plan.get("ground_floor")
        if isinstance(ground, Mapping):
            floor_ids.add(str(ground.get("id", ground.get("json_id", "ground_floor"))))
    for key in ("balconies", "slabs", "terraces"):
        building = canonical.get("building_exterior", {})
        surfaces = canonical.get(key)
        if surfaces is None and isinstance(building, Mapping):
            surfaces = building.get(key, [])
        if isinstance(surfaces, list):
            for surface in surfaces:
                if not isinstance(surface, Mapping):
                    continue
                support_id = str(surface.get("json_id", surface.get("id", "")))
                support_ids.add(support_id)
                surface_floor = surface.get("floor_id") or surface.get("floor")
                if surface_floor:
                    floor_ids.add(str(surface_floor))
                raw_support = surface.get("polygon") or surface.get("coordinates")
                try:
                    if isinstance(raw_support, Mapping):
                        support_geometry = shape(raw_support)
                    elif isinstance(raw_support, (list, tuple)) and raw_support:
                        rings = raw_support if isinstance(raw_support[0], (list, tuple)) and raw_support[0] and isinstance(raw_support[0][0], (list, tuple)) else [raw_support]
                        support_geometry = Polygon(rings[0], rings[1:])
                    else:
                        support_geometry = None
                    if support_geometry is not None and context.unit_scale != 1:
                        support_geometry = affinity.scale(support_geometry, xfact=context.unit_scale,
                                                          yfact=context.unit_scale, origin=(0, 0))
                except (TypeError, ValueError):
                    support_geometry = None
                if support_geometry is not None:
                    surface = dict(surface)
                    surface["_geometry_m"] = support_geometry
                support_by_id[support_id] = surface
    for item in _all_objects(result):
        object_checks: dict[str, bool] = {}
        try:
            parsed_item = ExteriorObject.model_validate(item)
            object_id = parsed_item.json_id
            if object_id in seen_ids:
                if dict(seen_ids[object_id]) != dict(item):
                    violations.append(f"duplicate_object_id:{object_id}")
            else:
                seen_ids[object_id] = dict(item)
            position = _position_geometry(item)
            object_checks["position_inside_land"] = position is None or context.land.covers(position)
            if not object_checks["position_inside_land"]:
                violations.append(f"position_outside_land:{object_id}")
            if position is not None and item.get("type") not in {"boundary_wall", "garden_zone", "lawn_zone"}:
                object_checks["outside_fixed_obstacles"] = not fixed_geometry.covers(position)
                if not object_checks["outside_fixed_obstacles"]:
                    violations.append(f"fixed_obstacle_overlap:{object_id}")
            geometry = None
            if item.get("polygon") is not None:
                polygon_points = item["polygon"]
                geometry = Polygon(polygon_points)
            elif item.get("geometry") is not None:
                geometry = shape(item["geometry"])
            if geometry is not None:
                object_checks["geometry_valid"] = not geometry.is_empty and geometry.is_valid
                if not object_checks["geometry_valid"]:
                    violations.append(f"invalid_geometry:{object_id}")
                object_checks["inside_land"] = context.land.covers(geometry)
                if not object_checks["inside_land"]:
                    violations.append(f"geometry_outside_land:{object_id}")
                zone_type = item.get("type") in {"boundary_wall", "garden_zone", "lawn_zone"}
                fixed_overlap_allowed = item.get("type") == "boundary_wall"
                object_checks["outside_fixed_obstacles"] = fixed_overlap_allowed or not geometry.intersects(fixed_geometry)
                if not object_checks["outside_fixed_obstacles"]:
                    violations.append(f"house_overlap:{object_id}")
                if not zone_type and not (item.get("type") in {"balcony_planter", "slab_planter", "wall_planter", "cascading_creeper"}
                                          and float((item.get("position") or {}).get("z", item.get("elevation_m", 0)) if isinstance(item.get("position"), Mapping) else item.get("elevation_m", 0)) > 0):
                    for other_id, other_type, other_geometry in geometry_records:
                        if geometry.intersects(other_geometry):
                            overlap = geometry.intersection(other_geometry)
                            line_overlap = (overlap.length > 1e-6 and
                                            (geometry.geom_type.endswith("LineString") or
                                             other_geometry.geom_type.endswith("LineString")))
                            if overlap.area > 1e-6 or line_overlap:
                                violations.append(f"prohibited_overlap:{other_id}:{object_id}")
                    geometry_records.append((object_id, str(item.get("type")), geometry))
            if item.get("type") in {"balcony_planter", "slab_planter", "wall_planter", "cascading_creeper"}:
                support = support_by_id.get(parsed_item.support_json_id or "")
                support_geometry = support.get("_geometry_m") if isinstance(support, Mapping) else None
                raw_footprint = parsed_item.footprint or parsed_item.polygon
                planter_footprint = Polygon(raw_footprint) if raw_footprint else None
                position_value = parsed_item.position
                elevation = (position_value.get("z") if isinstance(position_value, Mapping) else
                             position_value[2] if isinstance(position_value, list) and len(position_value) > 2 else
                             parsed_item.elevation_m)
                object_checks["support_reference_valid"] = bool(
                    support_geometry is not None and planter_footprint is not None and planter_footprint.is_valid and
                    support_geometry.covers(planter_footprint) and parsed_item.floor_id in floor_ids and
                    str(support.get("floor_id", support.get("floor", ""))) == str(parsed_item.floor_id) and
                    isinstance(elevation, (int, float)) and isfinite(float(elevation)) and float(elevation) > 0)
                if not object_checks["support_reference_valid"]:
                    violations.append(f"invalid_support_reference:{object_id}")
            if parsed_item.support_json_id:
                if parsed_item.support_json_id not in support_ids:
                    violations.append(f"unknown_support:{object_id}")
                if parsed_item.floor_id not in floor_ids:
                    violations.append(f"unknown_floor:{object_id}")
            item["validation"] = {"valid": all(object_checks.values()), **object_checks,
                                  "structural_load_assessed": False}
        except (ValidationError, TypeError, ValueError, KeyError) as exc:
            violations.append(f"malformed_object:{item.get('json_id', 'unknown')}:{exc}")
            item["validation"] = {"valid": False, "reason": "independent_schema_or_geometry_check_failed"}

    if utility_result.status == "unknown":
        violations.append("utility_locations_unknown")
    elif utility_result.status == "failed":
        violations.append("utility_separation_violation")
    access = result.get("access", {})
    gate = access.get("gate") if isinstance(access, Mapping) else None
    if isinstance(gate, Mapping):
        gate_position = _position_geometry(gate)
        if gate_position is None or gate_position.distance(context.land.boundary) > float(elia_rules()["access"]["gate_boundary_tolerance_m"]):
            violations.append("gate_not_on_land_boundary")
        preferred_gate = requirements["access"].get("preferred_gate_location")
        if preferred_gate and (gate_position is None or gate_position.distance(Point(preferred_gate)) > 0.5):
            violations.append("requested_gate_position_unfulfilled")
        gates = access.get("gates") or [gate, *gate.get("additional_gates", [])]
        if len(gates) != int(requirements["access"].get("gate_count", 1)):
            violations.append("requested_gate_count_unfulfilled")
    if requirements["access"].get("garage_required"):
        garage = access.get("garage") if isinstance(access, Mapping) else None
        garage_polygon = Polygon(garage.get("polygon", [])) if isinstance(garage, Mapping) and garage.get("polygon") else Polygon()
        bay_config = elia_rules()["access"]
        bay_area = float(bay_config["default_garage_width_m"]) * float(bay_config["default_garage_length_m"])
        actual_capacity = int(garage_polygon.area // bay_area) if garage_polygon.is_valid else 0
        if not garage_polygon.is_valid or actual_capacity < int(requirements["access"].get("garage_capacity", 1)):
            violations.append("required_garage_capacity_unfulfilled")
    driveway = access.get("driveway") if isinstance(access, Mapping) else None
    if requirements["access"].get("driveway_required") and not isinstance(driveway, Mapping):
        violations.append("required_driveway_unfulfilled")
    if isinstance(driveway, Mapping):
        try:
            centerline = LineString(driveway.get("centerline", []))
            coordinates = list(centerline.coords)
            if len(coordinates) < 2 or not centerline.is_simple:
                violations.append("invalid_driveway_centerline")
            if isinstance(gate, Mapping) and gate.get("access_point") and coordinates:
                if Point(coordinates[0]).distance(Point(gate["access_point"])) > 0.25:
                    violations.append("driveway_gate_connection_missing")
            garage = access.get("garage") if isinstance(access, Mapping) else None
            if isinstance(garage, Mapping) and garage.get("entry_point") and coordinates:
                if Point(coordinates[-1]).distance(Point(garage["entry_point"])) > 0.25:
                    violations.append("driveway_garage_connection_missing")
            width = float(driveway.get("width_m", 0))
            if width + 1e-9 < float(requirements["access"].get("preferred_driveway_width", 0)):
                violations.append("driveway_width_unfulfilled")
            turning_checks = [validate_vehicle_route(coordinates, profile, width,
                               float(elia_rules()["access"]["driveway_clearance_m"]))
                              for profile in requirements["access"]["vehicle_profiles"]]
            if any(not check["valid"] for check in turning_checks):
                violations.append("vehicle_turning_radius_or_width")
        except (TypeError, ValueError, KeyError):
            violations.append("invalid_driveway_geometry")
    requested_features = {
        "garden_zone": requirements.get("landscape", {}).get("garden_required"),
        "lawn_zone": requirements.get("landscape", {}).get("lawn_required"),
        "garden_seating": requirements.get("landscape", {}).get("garden_seating_required"),
        "garden_table_set": requirements.get("landscape", {}).get("garden_table_set_required"),
        "pedestrian_path": requirements.get("landscape", {}).get("pedestrian_path_required"),
        "garden_path": requirements.get("landscape", {}).get("garden_path_required"),
        "boundary_wall": requirements.get("landscape", {}).get("boundary_wall_required"),
    }
    output_types = {str(item.get("type")) for item in _all_objects(result)}
    for feature, requested in requested_features.items():
        if requested and feature not in output_types:
            violations.append(f"required_feature_unfulfilled:{feature}")
    lighting = result.get("outdoor_lighting", {})
    lighting_nodes = lighting.get("nodes", []) if isinstance(lighting, Mapping) else []
    requested_lighting = raw_requirements.get("lighting") or {}
    if requested_lighting.get("required") and not lighting_nodes:
        violations.append("required_outdoor_lighting_unavailable")
    for zone in requested_lighting.get("zones", []):
        if requested_lighting.get("required") and not any(node.get("zone") == zone for node in lighting_nodes):
            violations.append(f"requested_lighting_zone_unfulfilled:{zone}")

    raw_landscape = raw_requirements.get("landscape") or {}
    raw_access = raw_requirements.get("access") or {}
    unsupported_preferences = [
        name for name, value in (
            ("preferred_garden_zone", raw_landscape.get("preferred_garden_zone")),
            ("preferred_open_space_ratio", raw_landscape.get("preferred_open_space_ratio")),
            ("low_maintenance_preference", raw_landscape.get("low_maintenance_preference")),
            ("driveway_style", raw_access.get("driveway_style")),
            ("driveway_surface", raw_access.get("driveway_surface")),
            ("entrance_priority", raw_access.get("entrance_priority")),
            ("additional_requirements", raw_requirements.get("additional_requirements")),
        ) if value is not None and value is not False and value != "" and value != {} and value != []
    ]
    requested_categories = raw_landscape.get("preferred_vegetation_categories", [])
    produced_categories = {item.get("category") for item in result.get("vegetation_nodes", [])}
    unfulfilled_preferences = []
    if requested_categories and any(category not in produced_categories for category in requested_categories):
        unfulfilled_preferences.append("preferred_vegetation_categories")
    if raw_access.get("gate_type") and isinstance(gate, Mapping) and gate.get("type") != raw_access["gate_type"]:
        unfulfilled_preferences.append("gate_type")
    preferred_garage = requirements["access"].get("preferred_garage_location")
    garage = access.get("garage") if isinstance(access, Mapping) else None
    if preferred_garage and isinstance(garage, Mapping) and garage.get("polygon"):
        garage_geometry = Polygon(garage["polygon"])
        if Point(preferred_garage).distance(garage_geometry.centroid) > 0.5:
            unfulfilled_preferences.append("preferred_garage_location")
    result["preference_fulfillment"] = {
        "unsupported_preferences": unsupported_preferences,
        "unfulfilled_preferences": unfulfilled_preferences,
    }
    result["overlap_policy"] = {
        "elevated_canopy_access_overlap": "not_permitted_without_verified_clearance",
        "furniture_access_overlap": "prohibited",
        "trunk_radius_assessment": "unavailable; no trunk-radius input is modeled",
        "structural_load_assessed": False,
    }
    result["structural_load_assessed"] = False
    result["vehicle_feasibility_scope"] = "2D centerline turning-radius estimate only; swept-path and full vehicle maneuverability are not established"

    result["validation_summary"] = {
        "valid": not violations,
        "violations": sorted(set(violations)),
        "checks_passed": 0 if violations else 1,
        "checks_total": max(1, len(set(violations))),
        "constraint_satisfaction_rate": 0.0 if violations else 1.0,
        "source": "independent_geometry_and_requirement_validation",
    }
    return result, "valid" if not violations else "infeasible"


def run_model_generation(master: Mapping[str, Any], requirements: Mapping[str, Any], run_id: str,
                         adapter: ModelAdapter | None = None) -> tuple[dict[str, Any], str]:
    prepared = prepare_model_input(master, requirements)
    selected_adapter = adapter or _registered_adapter or UnavailableModelAdapter()
    raw_output = selected_adapter.infer(prepared)
    try:
        normalized = normalize_model_output(raw_output, run_id, selected_adapter.model_version)
        return validate_model_output(normalized, master, requirements)
    except ELIAError as exc:
        exc.candidate_output = _json_safe(raw_output)
        raise