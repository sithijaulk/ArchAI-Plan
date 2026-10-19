import httpx
import pytest

from app.components.elia_engine.exceptions import ELIAError
from app.components.elia_engine.solar import extract_master_location, fetch_live_solar_conditions, search_sri_lanka_locations


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "latitude": 6.91,
            "longitude": 79.87,
            "elevation": 12,
            "timezone": "Asia/Colombo",
            "current": {
                "time": "2026-10-04T11:00",
                "interval": 900,
                "shortwave_radiation": 620.0,
                "direct_radiation": 240.0,
                "diffuse_radiation": 380.0,
                "direct_normal_irradiance": 710.0,
                "cloud_cover": 32,
                "is_day": 1,
                "temperature_2m": 30.4,
                "relative_humidity_2m": 72,
            },
            "current_units": {"shortwave_radiation": "W/m²"},
        }


def test_fetches_current_open_meteo_irradiance_and_position(monkeypatch):
    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return FakeResponse()

    monkeypatch.setattr("app.components.elia_engine.solar.httpx.get", fake_get)
    data = fetch_live_solar_conditions(6.91234, 79.87321, "Asia/Colombo")
    cached = fetch_live_solar_conditions(6.91234, 79.87321, "Asia/Colombo")

    assert data["provider"] == "Open-Meteo"
    assert data["data_type"] == "current_weather_model_estimate"
    assert data["interval_seconds"] == 900
    assert data["irradiance_w_m2"]["shortwave_radiation"] == 620
    assert data["solar_position"]["elevation_degrees"] > 0
    assert data["observation_note"].startswith("Provider current conditions are model-based")
    assert cached["cache"] == "hit"
    assert len(calls) == 1
    assert "direct_normal_irradiance" in calls[0][1]["current"]


def test_master_location_is_required_and_validated():
    location = extract_master_location({"site": {"latitude": 6.9, "longitude": 79.8, "timezone": "Asia/Colombo"}})
    assert location == {"latitude": 6.9, "longitude": 79.8, "timezone": "Asia/Colombo"}
    with pytest.raises(ELIAError) as missing:
        extract_master_location({})
    assert missing.value.code == "ELIA_INVALID_LOCATION"


def test_sri_lanka_city_search_filters_country_and_caches(monkeypatch):
    calls = []

    class GeocodingResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {"place_id": 123, "name": "Malabe", "display_name": "Malabe, Colombo District, Western Province, Sri Lanka",
                 "lat": "6.9040723", "lon": "79.9546189", "type": "town",
                 "address": {"country_code": "lk", "country": "Sri Lanka", "state": "Western Province",
                             "county": "Colombo District"}},
                {"place_id": 456, "name": "Malabe", "display_name": "Malabe, another country",
                 "lat": "1", "lon": "1", "address": {"country_code": "us"}},
            ]

    def fake_get(url, params, headers, timeout):
        calls.append((url, params, headers, timeout))
        return GeocodingResponse()

    monkeypatch.setattr("app.components.elia_engine.solar.httpx.get", fake_get)
    results = search_sri_lanka_locations("Malabe Example")
    cached = search_sri_lanka_locations("malabe example")

    assert len(results) == 1
    assert results[0]["latitude"] == pytest.approx(6.9040723)
    assert results[0]["admin1"] == "Western Province"
    assert results[0]["country_code"] == "LK"
    assert cached == results
    assert len(calls) == 1
    assert calls[0][1]["countrycodes"] == "lk"
    assert "ArchAI-Plan-ELIA" in calls[0][2]["User-Agent"]


def test_provider_failure_is_a_typed_unavailable_error(monkeypatch):
    def failed_get(*args, **kwargs):
        raise httpx.ConnectTimeout("offline")

    monkeypatch.setattr("app.components.elia_engine.solar.httpx.get", failed_get)
    with pytest.raises(ELIAError) as failure:
        fetch_live_solar_conditions(-7.12345, 79.12345, "Asia/Colombo")
    assert failure.value.code == "ELIA_SOLAR_API_UNAVAILABLE"
    assert failure.value.status_code == 503
