from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from .adapter import normalize_master_json
from .exceptions import ELIAError
from .parser import UNIT_TO_METERS
from .rule_repository import elia_rules, vehicle_profiles


def normalize_requirements(requirements: Mapping[str, Any], master: Mapping[str, Any], source_units: str) -> dict[str, Any]:
    """Resolve requirement defaults and convert all dimensional inputs to meters."""
    master = normalize_master_json(master)
    normalized = dict(requirements)
    input_units = str(requirements.get("units", source_units)).lower()
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

    access = dict(requirements.get("access") or {})
    config = elia_rules()["access"]
    for key in ("gate_width", "preferred_driveway_width"):
        if access.get(key) is not None:
            access[key] = float(access[key]) * scale
    access.setdefault("gate_width", config["default_gate_width_m"])
    access.setdefault("preferred_driveway_width", config["default_driveway_width_m"])
    for key in ("preferred_gate_location", "preferred_garage_location"):
        if access.get(key) is not None:
            access[key] = [float(coordinate) * scale for coordinate in access[key]]
    profile_config = vehicle_profiles()["profiles"]
    profiles = []
    source_profiles = access.get("vehicle_profiles") or []
    if not source_profiles:
        source_profiles = [{"vehicle_type": "car"}]
    for supplied in source_profiles:
        profile = dict(supplied)
        vehicle_type = str(profile.get("vehicle_type", "car")).lower()
        defaults = profile_config.get(vehicle_type)
        if defaults is None and profile.get("length") is not None and profile.get("width") is not None:
            defaults = {}
        if defaults is None:
            raise ELIAError("ELIA_INVALID_VEHICLE_PROFILE", f"Unknown vehicle profile {vehicle_type!r}; provide custom dimensions.")
        for input_key, default_key in (("length", "length_m"), ("width", "width_m")):
            raw = profile.get(input_key)
            is_default = raw is None
            if is_default:
                raw = defaults.get(default_key)
            if raw is None or float(raw) <= 0:
                raise ELIAError("ELIA_INVALID_VEHICLE_PROFILE", f"A positive vehicle {input_key} is required.")
            profile[input_key] = float(raw) * (1.0 if is_default else scale)
        radius = profile.get("minimum_turning_radius")
        radius_is_default = radius is None
        if radius is None:
            radius = defaults.get("minimum_turning_radius_m")
            profile["turning_radius_source"] = "configured_project_default"
        else:
            profile["turning_radius_source"] = "user"
        if radius is None:
            radius = config["default_turning_radius_m"]
            radius_is_default = True
        profile["minimum_turning_radius"] = float(radius) * (1.0 if radius_is_default else scale)
        profile["vehicle_type"] = vehicle_type
        profiles.append(profile)
    access["vehicle_profiles"] = profiles

    landscape = dict(requirements.get("landscape") or {})
    if landscape.get("boundary_wall_height") is not None:
        landscape["boundary_wall_height"] = float(landscape["boundary_wall_height"]) * scale
    lighting = dict(requirements.get("lighting") or {})
    if lighting.get("preferred_spacing") is not None:
        lighting["preferred_spacing"] = float(lighting["preferred_spacing"]) * scale

    requested_date = requirements.get("solar_analysis_date")
    if requested_date is not None:
        try:
            date.fromisoformat(requested_date)
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

    normalized.update({
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": location.get("timezone") or requirements.get("timezone") or master_location.get("timezone") or elia_rules()["solar"]["default_timezone"],
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
    })
    return normalized
