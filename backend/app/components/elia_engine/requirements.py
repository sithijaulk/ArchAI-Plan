from __future__ import annotations

from datetime import date, time
from math import isfinite
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .adapter import normalize_master_json, resolve_upstream_road
from .exceptions import ELIAError
from .parser import UNIT_TO_METERS
from .rule_repository import elia_rules, lighting_rules, vehicle_profiles


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
    greenery_density = landscape.get("greenery_density", requirements.get("greenery_level", "medium"))
    if greenery_density not in elia_rules()["vegetation"]["density_targets"]:
        raise ELIAError("ELIA_INVALID_GREENERY_DENSITY", "Greenery density must be low, medium, or high.")
    landscape_priority = requirements.get("landscape_priority", "balanced")
    if landscape_priority not in {"balanced", "maximum_open_space", "maximum_greenery"}:
        raise ELIAError("ELIA_INVALID_LANDSCAPE_PRIORITY", "Landscape priority must be balanced, maximum_open_space, or maximum_greenery.")

    wall_height_m = landscape.get("boundary_wall_height_m")
    if wall_height_m is not None:
        landscape["boundary_wall_height_m"] = float(wall_height_m)
    elif landscape.get("boundary_wall_height") is not None:
        landscape["boundary_wall_height_m"] = float(landscape["boundary_wall_height"]) * (1.0 if already_normalized else scale)
    landscape.pop("boundary_wall_height", None)

    lighting = dict(requirements.get("lighting") or {})
    spacing_m = lighting.get("preferred_spacing_m")
    if spacing_m is not None:
        lighting["preferred_spacing_m"] = float(spacing_m)
    elif lighting.get("preferred_spacing") is not None:
        lighting["preferred_spacing_m"] = float(lighting["preferred_spacing"]) * (1.0 if already_normalized else scale)
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
            util_data = dict(utilities[util_key])
            explicit_m = util_data.get("position_m")
            if explicit_m is not None:
                pass # keep as is
            elif "position" in util_data:
                coords = util_data["position"]
                if isinstance(coords, (list, tuple)) and len(coords) == 2:
                    try:
                        parsed = [float(c) for c in coords]
                        if all(isfinite(c) for c in parsed):
                            coord_scale = 1.0 if already_normalized else scale
                            util_data["position_m"] = [c * coord_scale for c in parsed]
                    except (TypeError, ValueError):
                        pass
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
        "utilities": utilities,
    })
    normalized.pop("units", None)
    # Build a _TaggedDict so callers can detect this is normalized output.
    result = _TaggedDict(normalized)
    result.__elia_normalized__ = True
    return result
