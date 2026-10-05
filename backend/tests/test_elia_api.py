from fastapi.testclient import TestClient
import pytest
from types import SimpleNamespace
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.routers import elia
from app.database import Base, get_db
from app.dependencies import get_current_user
from app.models.component_run import ComponentRun
from app.models.project import Project
from app.components.elia_engine.schemas import ELIARequest


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


def test_project_crud_and_master_json_require_admin_authentication():
    with TestClient(app) as client:
        responses = [
            client.post("/api/projects", json={"project_name": "private"}),
            client.get("/api/projects"),
            client.get("/api/projects/private-project"),
            client.put("/api/projects/private-project", json={"project_name": "changed"}),
            client.delete("/api/projects/private-project"),
            client.get("/api/projects/private-project/master-json"),
        ]

    assert [response.status_code for response in responses] == [401] * len(responses)


def test_project_endpoints_forbid_non_admin_authenticated_users():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="user")
    try:
        with TestClient(app) as client:
            response = client.get("/api/projects")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_preview_reports_model_unavailable_without_falling_back_to_baseline():
    app.dependency_overrides[elia.require_admin] = lambda: None
    payload = {
        "master_json": {
            "units": "m", "location": {"latitude": 6.9, "longitude": 79.8},
            "land_info": {"mathematical_polygon": [[0, 0], [30, 0], [30, 20], [0, 20]],
                          "calculated_north_bearing": 10},
            "house_exterior_polygon": [[10, 5], [20, 5], [20, 15], [10, 15]],
        },
        "requirements": {"access": {"driveway_required": False}},
    }
    try:
        with TestClient(app) as client:
            response = client.post("/api/elia-engine/preview", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ELIA_MODEL_UNAVAILABLE"
    assert response.json()["detail"]["generation_status"] == "model_unavailable"


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


def test_validate_input_reports_missing_inherited_road_access(monkeypatch):
    project = SimpleNamespace(id="p1", master_json={
        "units": "m", "location": {"latitude": 6.9, "longitude": 79.8},
        "north_angle": 0,
        "land_boundary_polygon": [[0, 0], [30, 0], [30, 20], [0, 20]],
        "house_exterior_polygon": [[10, 5], [20, 5], [20, 15], [10, 15]],
    })
    monkeypatch.setattr(elia, "_project_or_404", lambda *args: project)

    with pytest.raises(Exception) as error:
        elia.validate_elia_input("p1", ELIARequest(generation_mode="baseline"), db=None, _admin=None)

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "ELIA_MISSING_ROAD_ACCESS"


def test_sri_lanka_search_includes_provider_and_attribution(monkeypatch):
    monkeypatch.setattr(elia, "search_sri_lanka_locations", lambda name: [{"name": name, "country_code": "LK"}])
    result = elia.search_elia_locations(name="Malabe", _admin=None)
    assert result["provider"] == "OpenStreetMap Nominatim"
    assert result["attribution"] == "© OpenStreetMap contributors"
    assert result["results"][0]["name"] == "Malabe"


def test_baseline_http_endpoints_use_inherited_orientation_and_meter_defaults(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'baseline-api.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    seed = sessions()
    master = {
        "units": "ft",
        "location": {"latitude": 6.9, "longitude": 79.8, "timezone": "Asia/Colombo"},
        "land_info": {
            "mathematical_polygon": [[0, 0], [100, 0], [100, 80], [0, 80]],
            "road_facing": "south",
            "calculated_north_bearing": 90,
        },
        "house_exterior_polygon": [[20, 20], [50, 20], [50, 50], [20, 50]],
        "upstream_component": {"retained": True},
    }
    project = Project(project_name="Baseline API test", revision=1, master_json=master)
    seed.add(project)
    seed.commit()
    project_id = project.id
    seed.close()

    def override_db():
        session = sessions()
        try:
            yield session
        finally:
            session.close()

    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[elia.require_admin] = lambda: None
    request_body = {
        "generation_mode": "baseline",
        "requirements": {"access": {"road_side": "south", "garage_required": False,
                                      "driveway_required": False, "gate_width": 4}},
    }
    preview_body = {**request_body, "master_json": master}
    try:
        with TestClient(app) as client:
            validated = client.post(f"/api/projects/{project_id}/elia-engine/validate-input", json=request_body)
            preview = client.post("/api/elia-engine/preview", json=preview_body)
            no_lights_run = client.post(f"/api/projects/{project_id}/elia-engine/run", json=request_body)
            lit_preview = client.post("/api/elia-engine/preview", json={
                **preview_body,
                "requirements": {**request_body["requirements"], "lighting": {
                    "required": True, "style": "architectural", "zones": ["garden"],
                    "preferred_spacing": 4,
                }},
            })
            stored = client.get(f"/api/projects/{project_id}")
            master_response = client.get(f"/api/projects/{project_id}/master-json")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()

    assert validated.status_code == 200, validated.text
    assert validated.json()["normalized_requirements"]["access"]["gate_width_m"] == 4.0
    assert validated.json()["orientation"]["north_angle_degrees"] == 90
    assert preview.status_code == 200, preview.text
    assert preview.json()["exterior_landscape"]["access"]["gate"]["width"] == 4.0
    assert preview.json()["exterior_landscape"]["environment"]["north_angle"] == 90
    assert preview.json()["exterior_landscape"]["outdoor_lighting"]["nodes"] == []
    assert no_lights_run.status_code == 200, no_lights_run.text
    assert no_lights_run.json()["generation_mode"] == "baseline"
    assert no_lights_run.json()["exterior_landscape"]["outdoor_lighting"]["nodes"] == []
    history = sessions()
    stored_run = history.query(ComponentRun).filter(ComponentRun.id == no_lights_run.json()["run_id"]).one()
    assert stored_run.input_json["effective_requirement_units"] == "m"
    assert stored_run.input_json["requirement_units_explicit"] is False
    history.close()
    assert lit_preview.status_code == 200, lit_preview.text
    light_nodes = lit_preview.json()["exterior_landscape"]["outdoor_lighting"]["nodes"]
    assert light_nodes and all(node["zone"] == "garden" and node["type"] == "wall_light" for node in light_nodes)
    assert stored.json()["master_json"]["upstream_component"] == {"retained": True}
    assert master_response.headers["X-Project-Revision"] == str(stored.json()["revision"])
