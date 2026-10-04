from fastapi.testclient import TestClient

from app.main import app
from app.routers import elia


def test_elia_reference_endpoints_are_registered_and_rules_are_available():
    with TestClient(app) as client:
        response = client.get("/api/elia-engine/rules")
        assert response.status_code == 200
        assert response.json()["utility_rules"]["well_septic_min_distance"] == {"value": 50, "unit": "ft"}
        paths = app.openapi()["paths"]
        assert "/api/projects/{project_id}/elia-engine/run" in paths
        assert "/api/projects/{project_id}/elia-engine/context" in paths
        assert "/api/projects/{project_id}/elia-engine/validate-input" in paths
        assert "/api/projects/{project_id}/elia-engine/solar/current" in paths
        assert "/api/elia-engine/locations/search" in paths
        assert "/api/elia-engine/preview" in paths


def test_project_elia_run_requires_existing_authentication():
    with TestClient(app) as client:
        response = client.post("/api/projects/private-project/elia-engine/run", json={})
    assert response.status_code == 401


def test_project_current_solar_uses_master_location_and_provider(monkeypatch):
    class Project:
        id = "p1"
        master_json = {"location": {"latitude": 6.9, "longitude": 79.8, "timezone": "Asia/Colombo"}}

    class Query:
        def filter(self, *args):
            return self

        def first(self):
            return Project()

    class Database:
        def query(self, model):
            return Query()

    calls = []
    monkeypatch.setattr(elia, "fetch_live_solar_conditions", lambda *args: calls.append(args) or {"status": "available"})
    result = elia.get_project_live_solar("p1", latitude=None, longitude=None, timezone=None,
                                         db=Database(), _admin=None)

    assert result["status"] == "available"
    assert calls == [(6.9, 79.8, "Asia/Colombo")]


def test_sri_lanka_search_includes_provider_and_attribution(monkeypatch):
    monkeypatch.setattr(elia, "search_sri_lanka_locations", lambda name: [{"name": name, "country_code": "LK"}])
    result = elia.search_elia_locations(name="Malabe", _admin=None)
    assert result["provider"] == "OpenStreetMap Nominatim"
    assert result["attribution"] == "© OpenStreetMap contributors"
    assert result["results"][0]["name"] == "Malabe"
