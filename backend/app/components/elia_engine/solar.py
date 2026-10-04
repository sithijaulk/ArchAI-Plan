from __future__ import annotations

from datetime import date, datetime, time
from math import isfinite
from threading import Lock
from time import monotonic, sleep
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any, Mapping
from copy import deepcopy

import httpx
import pandas as pd
import pvlib

from .exceptions import ELIAError
from .rule_repository import elia_rules

_LIVE_CACHE: dict[tuple[float, float, str], tuple[float, dict[str, Any]]] = {}
_LOCATION_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_LIVE_CACHE_LOCK = Lock()
_GEOCODING_REQUEST_LOCK = Lock()
_LAST_GEOCODING_REQUEST = 0.0
_LIVE_FIELDS = (
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
    "direct_normal_irradiance",
    "cloud_cover",
    "is_day",
    "temperature_2m",
    "relative_humidity_2m",
)


def calculate_solar_samples(requirements: Mapping[str, Any]) -> list[dict[str, Any]]:
    location = requirements["location"]
    timezone = location.get("timezone") or "UTC"
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ELIAError("ELIA_INVALID_LOCATION", f"Unknown IANA timezone {timezone!r}.") from exc
    try:
        analysis_date = date.fromisoformat(str(requirements["solar_analysis_date"]))
        time_values = requirements.get("solar_analysis_time_range") or elia_rules()["solar"]["sample_hours"]
        parsed_times = []
        for value in time_values:
            if isinstance(value, (int, float)):
                parsed_times.append(time(int(value), 0))
            else:
                hour, minute = (str(value).split(":") + ["0"])[:2]
                parsed_times.append(time(int(hour), int(minute)))
        timestamps = pd.DatetimeIndex([datetime.combine(analysis_date, item, tzinfo=zone) for item in parsed_times])
        position = pvlib.solarposition.get_solarposition(
            timestamps,
            latitude=float(location["latitude"]),
            longitude=float(location["longitude"]),
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ELIAError("ELIA_SOLAR_CALCULATION_ERROR", "Solar analysis inputs are invalid.") from exc
    samples = []
    for timestamp, row in position.iterrows():
        azimuth, elevation = float(row["azimuth"]), float(row["apparent_elevation"])
        if not (-360 <= azimuth <= 360 and -90 <= elevation <= 90):
            raise ELIAError("ELIA_SOLAR_CALCULATION_ERROR", "Solar library returned out-of-range angles.")
        samples.append({"timestamp": timestamp.isoformat(), "solar_azimuth_degrees": azimuth,
                        "solar_elevation_degrees": elevation, "sun_up": elevation > 0})
    return samples


def extract_master_location(master: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve an existing Master JSON location without guessing coordinates."""
    candidates = [master.get("location"), master.get("site_location"), master.get("geolocation")]
    for key in ("site", "property", "land_info"):
        item = master.get(key)
        if isinstance(item, Mapping):
            candidates.extend((item.get("location"), item))
    candidates.append(master)
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        latitude = candidate.get("latitude", master.get("latitude"))
        longitude = candidate.get("longitude", master.get("longitude"))
        if latitude is None or longitude is None:
            continue
        try:
            latitude, longitude = float(latitude), float(longitude)
        except (TypeError, ValueError) as exc:
            raise ELIAError("ELIA_INVALID_LOCATION", "Master JSON latitude and longitude must be numeric.") from exc
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ELIAError("ELIA_INVALID_LOCATION", "Master JSON latitude or longitude is outside its valid range.")
        return {"latitude": latitude, "longitude": longitude,
                "timezone": candidate.get("timezone") or "auto"}
    raise ELIAError("ELIA_INVALID_LOCATION", "Solar API requires latitude and longitude in the Master JSON or request.")


def search_sri_lanka_locations(name: str) -> list[dict[str, Any]]:
    """Resolve an explicitly submitted city/locality query via rate-limited Nominatim."""
    query = " ".join(str(name).split())
    if len(query) < 2 or len(query) > 100:
        raise ELIAError("ELIA_INVALID_LOCATION_QUERY", "Enter at least two characters for a Sri Lankan city or locality.")
    cache_key = query.casefold()
    api_rules = elia_rules()["live_solar_api"]
    now = monotonic()
    with _LIVE_CACHE_LOCK:
        cached = _LOCATION_CACHE.get(cache_key)
        if cached and now - cached[0] < float(api_rules["geocoding_cache_ttl_seconds"]):
            return deepcopy(cached[1])

    global _LAST_GEOCODING_REQUEST
    try:
        with _GEOCODING_REQUEST_LOCK:
            with _LIVE_CACHE_LOCK:
                cached = _LOCATION_CACHE.get(cache_key)
                if cached and monotonic() - cached[0] < float(api_rules["geocoding_cache_ttl_seconds"]):
                    return deepcopy(cached[1])
            wait = float(api_rules["geocoding_min_interval_seconds"]) - (monotonic() - _LAST_GEOCODING_REQUEST)
            if wait > 0:
                sleep(wait)
            response = httpx.get(
                api_rules["geocoding_url"],
                params={"q": f"{query}, Sri Lanka", "format": "jsonv2", "addressdetails": 1,
                        "limit": int(api_rules["geocoding_result_count"]),
                        "countrycodes": api_rules["geocoding_country_code"]},
                headers={"User-Agent": api_rules["geocoding_user_agent"]},
                timeout=float(api_rules["timeout_seconds"]),
            )
            _LAST_GEOCODING_REQUEST = monotonic()
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ELIAError("ELIA_LOCATION_SEARCH_UNAVAILABLE", "Sri Lankan location search is temporarily unavailable.", status_code=503) from exc

    results = payload if isinstance(payload, list) else []
    locations = []
    for result in results:
        if not isinstance(result, Mapping):
            continue
        address = result.get("address", {})
        if not isinstance(address, Mapping) or address.get("country_code", "").lower() != api_rules["geocoding_country_code"]:
            continue
        try:
            latitude, longitude = float(result["lat"]), float(result["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue
        locations.append({
            "id": result.get("place_id"), "name": result.get("name") or result.get("display_name", "").split(",")[0],
            "display_name": result.get("display_name"),
            "admin1": address.get("state") or address.get("province"),
            "admin2": address.get("county") or address.get("state_district"),
            "country": address.get("country", "Sri Lanka"),
            "country_code": address.get("country_code", "lk").upper(),
            "latitude": latitude, "longitude": longitude,
            "elevation_m": None, "timezone": None,
            "population": None, "feature_code": result.get("type"),
            "attribution": "© OpenStreetMap contributors",
        })
    with _LIVE_CACHE_LOCK:
        _LOCATION_CACHE[cache_key] = (monotonic(), deepcopy(locations))
    return locations


def fetch_live_solar_conditions(latitude: float, longitude: float, timezone: str | None = None) -> dict[str, Any]:
    """Fetch Open-Meteo's latest current-condition irradiance estimate and solar position."""
    try:
        latitude, longitude = float(latitude), float(longitude)
    except (TypeError, ValueError) as exc:
        raise ELIAError("ELIA_INVALID_LOCATION", "Latitude and longitude must be numeric.") from exc
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ELIAError("ELIA_INVALID_LOCATION", "Latitude or longitude is outside its valid range.")

    api_rules = elia_rules()["live_solar_api"]
    cache_key = (round(latitude, 5), round(longitude, 5), timezone or "auto")
    now = monotonic()
    with _LIVE_CACHE_LOCK:
        cached = _LIVE_CACHE.get(cache_key)
        if cached and now - cached[0] < float(api_rules["cache_ttl_seconds"]):
            result = deepcopy(cached[1])
            result["cache"] = "hit"
            return result

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join(_LIVE_FIELDS),
        "timezone": timezone or "auto",
        "forecast_days": 1,
    }
    try:
        response = httpx.get(api_rules["base_url"], params=params, timeout=float(api_rules["timeout_seconds"]))
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ELIAError("ELIA_SOLAR_API_UNAVAILABLE", "Live solar conditions are temporarily unavailable.", status_code=503) from exc

    current = payload.get("current") if isinstance(payload, Mapping) else None
    if not isinstance(current, Mapping) or not current.get("time"):
        raise ELIAError("ELIA_SOLAR_API_INVALID_RESPONSE", "Solar provider returned no current-condition timestamp.", status_code=502)
    provider_timezone = payload.get("timezone") or timezone or "UTC"
    try:
        zone = ZoneInfo(provider_timezone)
        timestamp = datetime.fromisoformat(str(current["time"]))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=zone)
        solar_position = pvlib.solarposition.get_solarposition(
            pd.DatetimeIndex([timestamp]), latitude=latitude, longitude=longitude
        ).iloc[0]
    except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
        raise ELIAError("ELIA_SOLAR_API_INVALID_RESPONSE", "Solar provider returned an invalid timestamp or timezone.", status_code=502) from exc

    irradiance: dict[str, float | None] = {}
    for name in ("shortwave_radiation", "direct_radiation", "diffuse_radiation", "direct_normal_irradiance"):
        value = current.get(name)
        if value is None:
            irradiance[name] = None
            continue
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ELIAError("ELIA_SOLAR_API_INVALID_RESPONSE", f"Solar provider returned invalid {name}.", status_code=502) from exc
        if not isfinite(number) or number < 0 or number > 2500:
            raise ELIAError("ELIA_SOLAR_API_INVALID_RESPONSE", f"Solar provider returned out-of-range {name}.", status_code=502)
        irradiance[name] = number

    result = {
        "status": "available",
        "provider": "Open-Meteo",
        "data_type": "current_weather_model_estimate",
        "observation_note": "Provider current conditions are model-based estimates, not ground-station measurements.",
        "timestamp": timestamp.isoformat(),
        "retrieved_at_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
        "interval_seconds": current.get("interval"),
        "location": {"requested_latitude": latitude, "requested_longitude": longitude,
                     "grid_latitude": payload.get("latitude"), "grid_longitude": payload.get("longitude"),
                     "elevation_m": payload.get("elevation"), "timezone": provider_timezone},
        "solar_position": {"azimuth_degrees": float(solar_position["azimuth"]),
                           "elevation_degrees": float(solar_position["apparent_elevation"]),
                           "is_day": bool(current.get("is_day", 0))},
        "irradiance_w_m2": irradiance,
        "cloud_cover_percent": current.get("cloud_cover"),
        "air_temperature_c": current.get("temperature_2m"),
        "relative_humidity_percent": current.get("relative_humidity_2m"),
        "units": payload.get("current_units", {}),
        "cache": "miss",
    }
    with _LIVE_CACHE_LOCK:
        _LIVE_CACHE[cache_key] = (monotonic(), deepcopy(result))
    return result
