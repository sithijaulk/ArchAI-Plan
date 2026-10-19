from __future__ import annotations

from datetime import date, time
from math import isfinite
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .adapter import normalize_master_json, resolve_upstream_road
from .exceptions import ELIAError
from .parser import UNIT_TO_METERS
from .rule_repository import elia_rules, lighting_rules, vehicle_profiles, vegetation_catalog


# ---------------------------------------------------------------------------
# Internal sentinel — prevents double-conversion when normalize_requirements()
# output is fed back into itself.
#
# We use a minimal dict subclass (_TaggedDict) that carries one extra attribute.
# The tag is never exposed as a key, so:
#   - JSON serialization sees only string keys.
#   - User-supplied dicts (plain dict) can never carry the tag.
#   - A new dict() created from the output loses the tag — which is correct
#     because the copy is untrusted user input again.
# ---------------------------------------------------------------------------
class _TaggedDict(dict):  # type: ignore[type-arg]
    """dict subclass that supports instance attributes for internal tagging."""
    __slots__ = ("__elia_normalized__",)


def _is_internally_normalized(requirements: Mapping[str, Any]) -> bool:
    """Return True only if *requirements* was produced by normalize_requirements().

    A plain dict, even with keys like '_elia_internal_normalized' or
    'normalized_units', returns False because only _TaggedDict instances can
    carry the sentinel attribute.
    """
    return (
        isinstance(requirements, _TaggedDict)
        and getattr(requirements, "__elia_normalized__", None) is True
    )


def normalize_requirements(requirements: Mapping[str, Any], master: Mapping[str, Any], source_units: str) -> _TaggedDict:
    """Resolve requirement defaults and convert all dimensional inputs to meters."""
    master = normalize_master_json(master)
    normalized = dict(requirements)
    already_normalized = _is_internally_normalized(requirements)
    if already_normalized:
        input_units = "m"
        scale = 1.0
    else:
        input_units = str(requirements.get("units") or "m").lower()
        if input_units not in UNIT_TO_METERS:
            raise ELIAError("ELIA_INVALID_UNITS", f"Unsupported requirement unit: {input_units!r}.")
        scale = UNIT_TO_METERS[input_units]
    location = dict(requirements.get("location") or {})
    latitude = requirements.get("latitude", location.get("latitude"))
    longitude = requirements.get("longitude", location.get("longitude"))
    master_location = master.get("location") or master.get("site_location") or master.get("geolocation") or {}
    if not isinstance(master_location, Mapping) or not master_location:
        site = master.get("site") or master.get("property") or {}
        master_location = site.get("location", site) if isinstance(site, Mapping) else {}
    if (not isinstance(master_location, Mapping) or not master_location) and isinstance(master.get("land_info"), Mapping):
        master_location = master["land_info"].get("location") or {}
    if latitude is None:
        latitude = master_location.get("latitude") if isinstance(master_location, Mapping) else None
    if longitude is None:
        longitude = master_location.get("longitude") if isinstance(master_location, Mapping) else None
    if latitude is None or longitude is None:
        raise ELIAError("ELIA_INVALID_LOCATION", "ELIA solar analysis requires latitude and longitude from the request or Master JSON.")
    try:
        latitude, longitude = float(latitude), float(longitude)
    except (TypeError, ValueError) as exc:
        raise ELIAError("ELIA_INVALID_LOCATION", "Latitude and longitude must be numeric.") from exc
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ELIAError("ELIA_INVALID_LOCATION", "Latitude or longitude is outside its valid range.")

    timezone = location.get("timezone") or requirements.get("timezone")
    if not timezone and isinstance(master_location, Mapping):
        timezone = master_location.get("timezone")
        
    if not timezone:
        timezone = elia_rules()["solar"]["default_timezone"]

    normalized["location"] = {"latitude": latitude, "longitude": longitude, "timezone": timezone}

    access = dict(requirements.get("access") or {})
    access.setdefault("driveway_required", True)

    parking_required = access.get("parking_required", True)
    if parking_required is False:
        if access.get("garage_required") is True:
            raise ELIAError("ELIA_CONTRADICTORY_REQUIREMENTS", "Cannot request a garage when parking_required is explicitly false.")
        access["garage_required"] = False
        access["vehicle_count"] = 0
        access["vehicle_profiles"] = []
        access.pop("vehicle_type", None)
        access.pop("parking_type", None)
        access.pop("garage_capacity", None)
        access.pop("turning_space_required", None)
    else:
        veh_count = access.get("vehicle_count", 1)
        if veh_count == 0 and access.get("garage_required") is True:
            raise ELIAError("ELIA_CONTRADICTORY_REQUIREMENTS", "Cannot request a garage when vehicle_count is 0.")

    if access.get("driveway_required") is False:
        access.pop("driveway_style", None)
        access.pop("driveway_surface", None)

    gate_required = access.get("gate_required", True)
    access["gate_required"] = bool(gate_required)
    if gate_required is False:
        access.pop("gate_type", None)
        access.pop("gate_width_m", None)
        access.pop("gate_opening_mechanism", None)
        access.pop("gate_style", None)

    for surf_key, allowed_surfaces in (
        ("driveway_surface", {"interlock", "paving_stones", "concrete", "gravel", "grass", "asphalt", "mixed"}),
        ("walking_path_surface", {"paving_stones", "interlock", "gravel", "stepping_stones", "grass", "mixed"}),
    ):
        surf_val = access.get(surf_key)
        if surf_val is not None:
            surf_val = str(surf_val).strip().lower()
            if surf_val not in allowed_surfaces:
                raise ELIAError("ELIA_INVALID_SURFACE_MATERIAL", f"Unsupported {surf_key}: {surf_val!r}.")
            access[surf_key] = surf_val

    gate_mech = access.get("gate_opening_mechanism")
    if gate_mech is not None:
        gate_mech = str(gate_mech).strip().lower()
        if gate_mech not in {"swing_inward", "swing_outward", "sliding", "bi_fold", "manual", "automated", "unspecified"}:
            raise ELIAError("ELIA_INVALID_GATE_MECHANISM", f"Unsupported gate_opening_mechanism: {gate_mech!r}.")
        access["gate_opening_mechanism"] = gate_mech

    upstream_side, upstream_edge = resolve_upstream_road(master)
    
    req_side = access.get("road_side")
    req_edge = access.get("road_access_edge")

    if req_side is not None and upstream_side is not None and str(req_side).lower() != str(upstream_side).lower():
        raise ELIAError("ELIA_CONFLICTING_ROAD_ACCESS", f"Requested road_side {req_side!r} conflicts with fixed upstream road_side {upstream_side!r}.")
    if req_edge is not None and upstream_edge is not None and int(req_edge) != int(upstream_edge):
        raise ELIAError("ELIA_CONFLICTING_ROAD_ACCESS", f"Requested road_access_edge {req_edge!r} conflicts with fixed upstream edge {upstream_edge!r}.")

    access["road_side"] = str(upstream_side).lower() if upstream_side else (str(req_side).lower() if req_side else None)
    access["road_access_edge"] = int(upstream_edge) if upstream_edge is not None else (int(req_edge) if req_edge is not None else None)

    if access["road_side"] is not None and access["road_side"] not in {"north", "south", "east", "west"}:
        raise ELIAError("ELIA_INVALID_ROAD_ACCESS", f"Unrecognized road_side {access['road_side']!r}.")

    config = elia_rules()["access"]

    # gate_width / gate_width_m
    explicit_gate_width_m = access.get("gate_width_m")
    if explicit_gate_width_m is not None:
        access["gate_width_m"] = float(explicit_gate_width_m)
    elif access.get("gate_width") is not None:
        access["gate_width_m"] = float(access["gate_width"]) * (1.0 if already_normalized else scale)
    else:
        access["gate_width_m"] = float(config["default_gate_width_m"])

    if access["gate_width_m"] <= 0 or not isfinite(access["gate_width_m"]):
        raise ELIAError("ELIA_INVALID_GATE_GEOMETRY", f"Gate width must be finite and positive, got {access['gate_width_m']}.")
    access.pop("gate_width", None)

    # preferred_driveway_width / preferred_driveway_width_m
    explicit_drive_width_m = access.get("preferred_driveway_width_m")
    if explicit_drive_width_m is not None:
        access["preferred_driveway_width_m"] = float(explicit_drive_width_m)
    elif access.get("preferred_driveway_width") is not None:
        access["preferred_driveway_width_m"] = float(access["preferred_driveway_width"]) * (1.0 if already_normalized else scale)
    else:
        access["preferred_driveway_width_m"] = float(config["default_driveway_width_m"])
    access.pop("preferred_driveway_width", None)

    for key in ("preferred_gate_location", "preferred_garage_location"):
        explicit_coords_m = access.get(f"{key}_m")
        coord_scale = 1.0 if (explicit_coords_m is not None or already_normalized) else scale
        coords = explicit_coords_m if explicit_coords_m is not None else access.get(key)
        if coords is not None:
            if not isinstance(coords, (list, tuple)) or len(coords) != 2:
                raise ELIAError("ELIA_INVALID_COORDINATES", f"{key} must contain exactly x and y.")
            try:
                parsed_coords = [float(coordinate) for coordinate in coords]
            except (TypeError, ValueError) as exc:
                raise ELIAError("ELIA_INVALID_COORDINATES", f"{key} coordinates must be numeric.") from exc
            if not all(isfinite(coordinate) for coordinate in parsed_coords):
                raise ELIAError("ELIA_INVALID_COORDINATES", f"{key} coordinates must be finite.")
            access[key] = [coordinate * coord_scale for coordinate in parsed_coords]

    profile_config = vehicle_profiles()["profiles"]
    profiles = []
    source_profiles = access.get("vehicle_profiles") or []
    if not source_profiles:
        source_profiles = [{"vehicle_type": "car"}]
    for supplied in source_profiles:
        profile = dict(supplied)
        vehicle_type = str(profile.get("vehicle_type", "car")).lower()
        defaults = profile_config.get(vehicle_type)
        if defaults is None and (profile.get("length") is not None or profile.get("length_m") is not None) and (profile.get("width") is not None or profile.get("width_m") is not None):
            defaults = {}
        if defaults is None:
            raise ELIAError("ELIA_INVALID_VEHICLE_PROFILE", f"Unknown vehicle profile {vehicle_type!r}; provide custom dimensions.")
        for dim in ("length", "width"):
            explicit_m = profile.get(f"{dim}_m")
            raw = explicit_m if explicit_m is not None else profile.get(dim)
            dim_scale = 1.0 if (explicit_m is not None or already_normalized) else scale
            is_default = raw is None
            if is_default:
                raw = defaults.get(f"{dim}_m")
                dim_scale = 1.0
            if raw is None or float(raw) <= 0:
                raise ELIAError("ELIA_INVALID_VEHICLE_PROFILE", f"A positive vehicle {dim} is required.")
            profile[f"{dim}_m"] = float(raw) * dim_scale
            profile.pop(dim, None)

        explicit_radius_m = profile.get("minimum_turning_radius_m")
        radius = explicit_radius_m if explicit_radius_m is not None else profile.get("minimum_turning_radius")
        radius_scale = 1.0 if (explicit_radius_m is not None or already_normalized) else scale
        if radius is None:
            radius = defaults.get("minimum_turning_radius_m")
            radius_scale = 1.0
            profile["turning_radius_source"] = "configured_project_default"
        else:
            profile["turning_radius_source"] = "user"
        if radius is None:
            radius = config["default_turning_radius_m"]
            radius_scale = 1.0
        profile["minimum_turning_radius_m"] = float(radius) * radius_scale
        profile.pop("minimum_turning_radius", None)
        profile["vehicle_type"] = vehicle_type
        profiles.append(profile)
    access["vehicle_profiles"] = profiles

    landscape = dict(requirements.get("landscape") or {})
    # Strip obsolete financial fields at read boundary
    for bf in ("budget_limit_lkr", "budget_preference", "budget_estimate", "budget_assessment"):
        landscape.pop(bf, None)
        normalized.pop(bf, None)

    explicit_density = (
        ("greenery_density" in (requirements.get("landscape") or {}))
        or ("greenery_level" in requirements)
        or ("greenery_density" in requirements)
    )
    greenery_density = landscape.get("greenery_density", requirements.get("greenery_level", "medium"))
    if greenery_density not in elia_rules()["vegetation"]["density_targets"]:
        raise ELIAError("ELIA_INVALID_GREENERY_DENSITY", "Greenery density must be low, medium, or high.")
    landscape["greenery_density"] = greenery_density
    landscape["explicit_greenery_density"] = explicit_density
    normalized["explicit_greenery_density"] = explicit_density
    landscape_priority = requirements.get("landscape_priority", "balanced")
    if landscape_priority not in {"balanced", "maximum_open_space", "maximum_greenery"}:
        raise ELIAError("ELIA_INVALID_LANDSCAPE_PRIORITY", "Landscape priority must be balanced, maximum_open_space, or maximum_greenery.")

    # 1. Design Concept / Style
    raw_style = requirements.get("design_style") or requirements.get("design_concept") or "contemporary"
    canonical_style = str(raw_style).strip().lower()
    if canonical_style in ("minimalist", "minimalistic"):
        canonical_style = "minimalistic"
    elif canonical_style in ("contemporary", "modern"):
        canonical_style = "modern"
    elif canonical_style in ("green", "greeny", "lush"):
        canonical_style = "greeny"
    normalized["design_style"] = canonical_style

    # Ground Finish
    garden_finish = landscape.get("garden_ground_finish")
    if garden_finish is not None:
        garden_finish = str(garden_finish).strip().lower()
        if garden_finish not in {"grass", "interlock", "paving_stones", "mixed"}:
            raise ELIAError("ELIA_INVALID_GROUND_FINISH", f"Unsupported garden_ground_finish: {garden_finish!r}.")
        landscape["garden_ground_finish"] = garden_finish
        if garden_finish == "grass":
            landscape["lawn_required"] = True

    # Inactive dependent omission for landscape
    if landscape.get("trees_required") is False:
        landscape.pop("tree_quantity", None)
        landscape.pop("compact_trees_preference", None)
        landscape.pop("shade_tree_preference", None)
    if landscape.get("shrubs_required") is False:
        landscape.pop("shrubs_quantity", None)
    if landscape.get("ground_planters_required") is False:
        landscape.pop("ground_planters_count", None)
    if landscape.get("garden_seating_required") is False:
        landscape.pop("garden_seating_count", None)
    if landscape.get("garden_table_set_required") is False:
        landscape.pop("garden_table_set_count", None)
    if landscape.get("boundary_wall_required") is False:
        landscape.pop("boundary_wall_type", None)
        landscape.pop("boundary_wall_height", None)
        landscape.pop("boundary_wall_height_m", None)

    # 2. Maintenance preference
    maint_pref = requirements.get("maintenance_preference") or landscape.get("maintenance_preference")
    low_maint = requirements.get("low_maintenance_preference") if requirements.get("low_maintenance_preference") is not None else landscape.get("low_maintenance_preference")
    if not maint_pref and low_maint is True:
        maint_pref = "low"
    elif not maint_pref and low_maint is False:
        maint_pref = "no_preference"
    if maint_pref is not None:
        maint_pref = str(maint_pref).strip().lower()
        if maint_pref not in {"low", "medium", "high", "no_preference", "unknown"}:
            raise ELIAError("ELIA_INVALID_MAINTENANCE_PREFERENCE", "Maintenance preference must be low, medium, high, or no_preference.")
    landscape["maintenance_preference"] = maint_pref
    if maint_pref is not None:
        landscape["low_maintenance_preference"] = (maint_pref == "low")
    normalized["maintenance_preference"] = maint_pref

    # 3. Water availability
    water_avail = requirements.get("water_availability") or landscape.get("water_availability")
    if water_avail is not None:
        water_avail = str(water_avail).strip().lower()
        if water_avail not in {"limited", "regular", "irrigation_available", "unknown"}:
            raise ELIAError("ELIA_INVALID_WATER_AVAILABILITY", "Water availability must be limited, regular, irrigation_available, or unknown.")
    landscape["water_availability"] = water_avail
    normalized["water_availability"] = water_avail

    # 5. Climate & Environmental Context
    climate_zone = requirements.get("climate_zone") or landscape.get("climate_zone")
    if climate_zone is not None:
        climate_zone = str(climate_zone).strip().lower()
    normalized["climate_zone"] = climate_zone
    landscape["climate_zone"] = climate_zone

    site_exposure = requirements.get("site_exposure") or landscape.get("site_exposure")
    if site_exposure is not None:
        site_exposure = str(site_exposure).strip().lower()
    normalized["site_exposure"] = site_exposure
    landscape["site_exposure"] = site_exposure

    # 6. Specific plant preferences & avoidances validated against catalogue
    pref_plants = list(landscape.get("preferred_plant_ids") or requirements.get("preferred_plant_ids") or [])
    avoid_plants = list(landscape.get("plant_ids_to_avoid") or requirements.get("plant_ids_to_avoid") or [])
    
    cat_entries = vegetation_catalog().get("entries", [])
    valid_veg_ids = {entry["vegetation_id"] for entry in cat_entries if "vegetation_id" in entry}
    for p in pref_plants:
        if valid_veg_ids and str(p) not in valid_veg_ids:
            raise ELIAError("ELIA_INVALID_PLANT_ID", f"Plant ID {p!r} is not in the botanical catalogue.")
    for p in avoid_plants:
        if valid_veg_ids and str(p) not in valid_veg_ids:
            raise ELIAError("ELIA_INVALID_PLANT_ID", f"Plant ID {p!r} is not in the botanical catalogue.")

    landscape["preferred_plant_ids"] = [str(p) for p in pref_plants]
    landscape["plant_ids_to_avoid"] = [str(p) for p in avoid_plants]
    normalized["preferred_plant_ids"] = landscape["preferred_plant_ids"]
    normalized["plant_ids_to_avoid"] = landscape["plant_ids_to_avoid"]

    # 7. Locked features
    raw_locked = requirements.get("locked_features") or []
    locked_features = []
    if isinstance(raw_locked, (list, tuple)):
        for item in raw_locked:
            if isinstance(item, Mapping):
                item_dict = dict(item)
                if "json_id" in item_dict and "position" in item_dict:
                    pos = item_dict["position"]
                    if isinstance(pos, (list, tuple)) and len(pos) == 2:
                        try:
                            item_dict["position"] = [float(pos[0]), float(pos[1])]
                            item_dict["locked"] = True
                            locked_features.append(item_dict)
                        except (TypeError, ValueError):
                            pass
    normalized["locked_features"] = locked_features

    wall_height_m = landscape.get("boundary_wall_height_m")
    if wall_height_m is not None:
        landscape["boundary_wall_height_m"] = float(wall_height_m)
    elif landscape.get("boundary_wall_height") is not None:
        landscape["boundary_wall_height_m"] = float(landscape["boundary_wall_height"]) * (1.0 if already_normalized else scale)
    landscape.pop("boundary_wall_height", None)

    # Lighting normalization
    lighting = dict(requirements.get("lighting") or {})
    if not lighting.get("required"):
        # When lighting is disabled, dependent zones/spacing are inactive
        lighting["zones"] = []
        lighting.pop("style", None)
        lighting.pop("desired_fixture_count", None)
        lighting.pop("preferred_spacing_m", None)
        lighting.pop("garden_lighting", None)
        lighting.pop("pathway_lighting", None)
        lighting.pop("seating_lighting", None)
        lighting.pop("wall_lighting", None)
    else:
        # Zone mapping from specific toggles
        zones = list(lighting.get("zones") or [])
        if lighting.get("garden_lighting") and "garden" not in zones:
            zones.append("garden")
        if lighting.get("seating_lighting") and "seating" not in zones:
            zones.append("seating")
        if lighting.get("wall_lighting") and "boundary_wall" not in zones:
            zones.append("boundary_wall")
        lighting["zones"] = zones

        spacing_m = lighting.get("preferred_spacing_m")
        if spacing_m is not None:
            lighting["preferred_spacing_m"] = float(spacing_m)
        elif lighting.get("preferred_spacing") is not None:
            lighting["preferred_spacing_m"] = float(lighting["preferred_spacing"]) * (1.0 if already_normalized else scale)
        elif lighting.get("desired_fixture_count") is not None:
            # Derived spacing guideline if spacing omitted
            lighting["preferred_spacing_m"] = float(elia_rules()["lighting"]["default_spacing_m"] if "default_spacing_m" in elia_rules().get("lighting", {}) else 8.0)
        lighting.pop("preferred_spacing", None)

        lighting_config = lighting_rules()
        if lighting.get("style", "minimal") not in lighting_config["render_types"]:
            raise ELIAError("ELIA_INVALID_LIGHTING_STYLE", "Lighting style must be one of the configured ELIA styles.")
        zones = lighting.get("zones")
        if zones is not None and "pathway" in zones:
            raise ELIAError("ELIA_UNSUPPORTED_LIGHTING_ZONE", "The pathway zone is currently unsupported for exterior lighting.")
        if zones is not None and any(zone not in lighting_config["mounting_height_m"] for zone in zones):
            raise ELIAError("ELIA_INVALID_LIGHTING_ZONE", "Lighting zones must be configured ELIA placement zones.")
        if lighting.get("required") and zones is not None and not zones:
            raise ELIAError("ELIA_INVALID_LIGHTING_ZONE", "At least one lighting zone is required when lighting is requested.")
        if (lighting.get("preferred_spacing_m") is not None and
                lighting["preferred_spacing_m"] < float(lighting_config["minimum_spacing_m"])):
            raise ELIAError("ELIA_INVALID_LIGHTING_SPACING", "Preferred light spacing must meet the configured minimum.")

    # Vertical Greenery
    vertical_req = dict(requirements.get("vertical_greenery") or {})
    vertical_req.setdefault("mode", "automatic")
    vertical_req.setdefault("enabled", True)
    vertical_req.setdefault("wall_climbing_plants", False)
    vertical_req.setdefault("wall_mounted_greenery", False)
    vertical_req.setdefault("hanging_trailing_greenery", False)
    vertical_req.setdefault("accept_vertical_alternatives", False)
    normalized["vertical_greenery"] = vertical_req

    # Balconies
    balconies_req = dict(requirements.get("balconies") or {})
    balconies_req.setdefault("planting_required", False)
    balconies_req.setdefault("potted_plants", False)
    balconies_req.setdefault("hanging_plants", False)
    balconies_req.setdefault("seating_required", False)
    master_balconies = master.get("balconies") or []
    valid_balcony_ids = {b.get("json_id") for b in master_balconies if isinstance(b, Mapping) and b.get("json_id")}
    for b_id in balconies_req.get("target_balcony_ids", []):
        if valid_balcony_ids and b_id not in valid_balcony_ids:
            raise ELIAError("ELIA_INVALID_BALCONY_ID", f"Target balcony ID {b_id!r} not found in upstream Master JSON.")
    normalized["balconies"] = balconies_req

    # Terrace
    terrace_req = dict(requirements.get("terrace") or {})
    terrace_req.setdefault("planting_required", False)
    terrace_req.setdefault("planters_required", False)
    terrace_req.setdefault("seating_required", False)
    terrace_req.setdefault("tables_required", False)
    master_terraces = master.get("terraces") or master.get("flat_roofs") or []
    valid_terrace_ids = {t.get("json_id") for t in master_terraces if isinstance(t, Mapping) and t.get("json_id")}
    for t_id in terrace_req.get("target_terrace_ids", []):
        if valid_terrace_ids and t_id not in valid_terrace_ids:
            raise ELIAError("ELIA_INVALID_TERRACE_ID", f"Target terrace ID {t_id!r} not found in upstream Master JSON.")
    normalized["terrace"] = terrace_req

    # Water Features & Utilities (requested)
    water_req = dict(requirements.get("water_features") or {})
    water_req.setdefault("well_required", False)
    water_req.setdefault("garden_taps_required", False)
    water_req.setdefault("garden_taps_count", 1 if water_req.get("garden_taps_required") else 0)
    water_req.setdefault("pond_required", False)
    water_req.setdefault("swimming_pool_required", False)
    water_req.setdefault("septic_tank_required", False)
    normalized["water_features"] = water_req

    # Solar
    solar_req = dict(requirements.get("solar") or {})
    solar_req.setdefault("panels_required", False)
    solar_req.setdefault("preferred_roof_surface", "auto")
    solar_req.setdefault("placement_priority", "balanced")
    live_solar_val = solar_req.get("include_live_solar", requirements.get("include_live_solar", False))
    solar_req["include_live_solar"] = bool(live_solar_val)
    normalized["solar"] = solar_req
    normalized["include_live_solar"] = bool(live_solar_val)

    # Track Unsupported Generation Preferences
    unsupported_features: list[str] = []
    if water_req.get("swimming_pool_required"):
        unsupported_features.append("swimming_pool")
    if water_req.get("pond_required"):
        unsupported_features.append("pond")
    if water_req.get("well_required"):
        unsupported_features.append("new_well")
    if water_req.get("garden_taps_required"):
        unsupported_features.append("garden_taps")
    if solar_req.get("panels_required"):
        unsupported_features.append("solar_panels")
    if (terrace_req.get("planting_required") or terrace_req.get("seating_required") or
            terrace_req.get("tables_required") or terrace_req.get("planters_required")):
        unsupported_features.append("rooftop_terrace")
    if balconies_req.get("seating_required") or balconies_req.get("potted_plants"):
        unsupported_features.append("balcony_features")
    normalized["unsupported_generation_features"] = unsupported_features

    requested_date = requirements.get("solar_analysis_date")
    if requested_date is not None:
        try:
            parsed_date = date.fromisoformat(str(requested_date))
            if parsed_date.isoformat() != requested_date:
                raise ValueError("date must use YYYY-MM-DD")
        except (TypeError, ValueError) as exc:
            raise ELIAError("ELIA_INVALID_SOLAR_DATE", "solar_analysis_date must use YYYY-MM-DD.") from exc
    else:
        requested_date = elia_rules()["solar"]["default_analysis_date"]

    upstream_north = master.get("north_angle")
    requested_north = requirements.get("north_angle")
    if upstream_north is not None and requested_north is not None:
        upstream_north, requested_north = float(upstream_north) % 360.0, float(requested_north) % 360.0
        if min(abs(upstream_north - requested_north), 360.0 - abs(upstream_north - requested_north)) > 1e-6:
            raise ELIAError("ELIA_CONFLICTING_NORTH_ORIENTATION", "The requested north angle conflicts with the inherited Master JSON orientation.")
    north_angle = upstream_north if upstream_north is not None else requested_north
    if north_angle is None:
        raise ELIAError("ELIA_MISSING_NORTH_ORIENTATION", "ELIA requires the north bearing already marked in the upstream Master JSON.")

    timezone = (location.get("timezone") or requirements.get("timezone") or
                master_location.get("timezone") or elia_rules()["solar"]["default_timezone"])
    try:
        ZoneInfo(str(timezone))
    except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
        raise ELIAError("ELIA_INVALID_TIMEZONE", f"Unknown IANA timezone {timezone!r}.") from exc
    time_range = requirements.get("solar_analysis_time_range")
    if time_range is not None:
        if not isinstance(time_range, (list, tuple)) or not time_range:
            raise ELIAError("ELIA_INVALID_SOLAR_TIME", "solar_analysis_time_range must contain at least one local time.")
        try:
            for value in time_range:
                hour_minute = str(value).split(":")
                time(int(hour_minute[0]), int(hour_minute[1]) if len(hour_minute) > 1 else 0)
        except (TypeError, ValueError, IndexError) as exc:
            raise ELIAError("ELIA_INVALID_SOLAR_TIME", "Solar analysis times must use valid local HH:MM values.") from exc

    utilities = dict(requirements.get("utilities") or {})
    for util_key in ("well", "septic_tank"):
        if util_key in utilities:
            raw_util = utilities[util_key]
            if not isinstance(raw_util, Mapping):
                raise ELIAError(
                    "ELIA_INVALID_UTILITY_DATA",
                    f"utilities.{util_key} must be an object, got {type(raw_util).__name__}.",
                )
            util_data = dict(raw_util)
            explicit_m = util_data.get("position_m")
            if explicit_m is not None:
                # Validate explicit_m and leave as-is (already in meters)
                if not (isinstance(explicit_m, (list, tuple)) and len(explicit_m) == 2):
                    raise ELIAError(
                        "ELIA_INVALID_UTILITY_POSITION",
                        f"utilities.{util_key}.position_m must be a two-element list [x, y].",
                    )
                try:
                    pm = [float(c) for c in explicit_m]
                    if not all(isfinite(c) for c in pm):
                        raise ValueError("non-finite")
                    util_data["position_m"] = pm
                except (TypeError, ValueError) as exc:
                    raise ELIAError(
                        "ELIA_INVALID_UTILITY_POSITION",
                        f"utilities.{util_key}.position_m must contain finite numbers.",
                    ) from exc
            elif "position" in util_data:
                coords = util_data["position"]
                # Support both list/tuple [x, y] and dict {x: ..., y: ...}
                if isinstance(coords, Mapping):
                    raw_x, raw_y = coords.get("x"), coords.get("y")
                    if raw_x is None or raw_y is None:
                        raise ELIAError(
                            "ELIA_INVALID_UTILITY_POSITION",
                            f"utilities.{util_key}.position dict must have 'x' and 'y' keys.",
                        )
                    try:
                        parsed = [float(raw_x), float(raw_y)]
                    except (TypeError, ValueError) as exc:
                        raise ELIAError(
                            "ELIA_INVALID_UTILITY_POSITION",
                            f"utilities.{util_key}.position x/y must be numeric.",
                        ) from exc
                elif isinstance(coords, (list, tuple)):
                    if len(coords) != 2:
                        raise ELIAError(
                            "ELIA_INVALID_UTILITY_POSITION",
                            f"utilities.{util_key}.position must have exactly 2 elements.",
                        )
                    try:
                        parsed = [float(c) for c in coords]
                    except (TypeError, ValueError) as exc:
                        raise ELIAError(
                            "ELIA_INVALID_UTILITY_POSITION",
                            f"utilities.{util_key}.position must contain numeric values.",
                        ) from exc
                else:
                    raise ELIAError(
                        "ELIA_INVALID_UTILITY_POSITION",
                        f"utilities.{util_key}.position must be a list [x, y] or dict {{x, y}}.",
                    )
                if not all(isfinite(c) for c in parsed):
                    raise ELIAError(
                        "ELIA_INVALID_UTILITY_POSITION",
                        f"utilities.{util_key}.position coordinates must be finite numbers.",
                    )
                coord_scale = 1.0 if already_normalized else scale
                util_data["position_m"] = [c * coord_scale for c in parsed]
                util_data.pop("position", None)
            utilities[util_key] = util_data

    normalized.update({
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone,
            "city": location.get("city") or location.get("name"),
        },
        "solar_analysis_date": requested_date,
        "source_units": input_units,
        "normalized_units": "m",
        "property_orientation": requirements.get("property_orientation") or master.get("property_orientation") or
                       (master.get("land_info", {}).get("orientation") if isinstance(master.get("land_info"), Mapping) else None),
        "north_angle": float(north_angle) % 360.0,
        "north_orientation_convention": "degrees clockwise from local +Y toward local +X; 0 means local +Y is north",
        "access": access,
        "landscape": landscape,
        "lighting": lighting,
        "vertical_greenery": vertical_req,
        "balconies": balconies_req,
        "terrace": terrace_req,
        "water_features": water_req,
        "solar": solar_req,
        "utilities": utilities,
        "unsupported_generation_features": unsupported_features,
    })
    normalized.pop("units", None)
    # Build a _TaggedDict so callers can detect this is normalized output.
    result = _TaggedDict(normalized)
    result.__elia_normalized__ = True
    return result
