from copy import deepcopy
import pytest

from app.components.elia_engine.output import build_updated_master
from app.components.elia_engine.service import run_elia


@pytest.fixture
def master_json():
    return {
        "project_id": "project-elia",
        "project_name": "Courtyard home",
        "units": "m",
        "location": {"latitude": 6.9, "longitude": 79.8, "timezone": "Asia/Colombo"},
        "land_info": {"boundary_points": [[0, 0], [40, 0], [40, 30], [0, 30]], "road_facing": "south"},
        "house_exterior_polygon": [[10, 8], [22, 8], [22, 22], [10, 22]],
        "house_height_m": 6,
        "utilities": {"well": {"known": True, "position": [2, 27]},
                      "septic_tank": {"known": True, "position": [22, 27]}},
        "interior_layout": {"rooms": [{"id": "R1", "furniture": [{"id": "SOFA_01", "position": [2, 3]}]}]},
        "floor_plan": {"floors": [{"id": "F1", "rooms": ["R1"]}]},
        "processing": {"esai_engine": {"status": "completed"}},
    }


@pytest.fixture
def requirements():
    return {
        "design_style": "modern",
        "units": "m",
        "access": {"road_side": "south", "garage_required": True, "garage_capacity": 1,
                   "driveway_required": True, "vehicle_profiles": [{"vehicle_type": "car", "minimum_turning_radius": 5.5}]},
        "landscape": {"garden_required": False},
        "lighting": {"required": False},
        "vertical_greenery": {"mode": "automatic"},
    }


def test_complete_run_returns_explainable_layout_without_mutating_master(master_json, requirements):
    before = deepcopy(master_json)
    exterior, outcome = run_elia(master_json, requirements, "run-1")

    assert master_json == before
    assert outcome == "valid", {"validation": exterior["validation_summary"],
                                 "gate": exterior["access"]["gate"], "garage": exterior["access"]["garage"],
                                 "metrics": exterior["metrics"]}
    assert exterior["access"]["gate"]["json_id"] == "GATE_001"
    assert exterior["utility_safety"]["required_separation_ft"] == 50
    assert exterior["environment"]["solar_samples"]
    assert exterior["metrics"]["solar_analysis_completed"]
    assert exterior["access"]["garage"]["json_id"] == "GARAGE_001"
    assert exterior["access"]["driveway"]["pathfinding"] == "A*"
    assert exterior["validation_summary"]["valid"]


def test_updated_master_preserves_prior_layers_structurally(master_json):
    exterior = {"version": "1.0", "vegetation_nodes": []}
    updated = build_updated_master(master_json, exterior, "run-2", "valid")

    assert updated["interior_layout"] == master_json["interior_layout"]
    assert updated["floor_plan"] == master_json["floor_plan"]
    assert updated["processing"]["esai_engine"] == master_json["processing"]["esai_engine"]
    assert updated["exterior_landscape"] == exterior
    assert updated["processing"]["elia_engine"]["outcome"] == "valid"


def test_requested_outdoor_features_are_emitted_with_validation(master_json, requirements):
    master_json["main_entrance"] = [10, 15]
    requirements["landscape"] = {"garden_required": True, "lawn_required": True,
                                  "garden_table_set_required": True, "pedestrian_path_required": True,
                                  "garden_path_required": True, "boundary_wall_required": True,
                                  "boundary_wall_height": 1.8}
    requirements["lighting"] = {"required": True, "style": "pathway", "zones": ["gate", "garden"]}
    exterior, _ = run_elia(master_json, requirements, "run-outdoor")

    types = {element["type"] for element in exterior["outdoor_elements"]}
    assert {"garden_zone", "lawn_zone", "garden_table_set", "pedestrian_path", "garden_path", "boundary_wall"} <= types
    requested_paths = [element for element in exterior["outdoor_elements"] if element["type"].endswith("path")]
    assert len(requested_paths) == 2
    assert all(element["validation"]["valid"] for element in requested_paths), [
        (element["type"], element["validation"], element.get("centerline", [])[:2]) for element in requested_paths
    ]
    assert all(node["json_id"].startswith("LIGHT_") for node in exterior["outdoor_lighting"]["nodes"])


def test_live_solar_is_opt_in_and_provider_failure_is_reported_without_fake_data(master_json, requirements, monkeypatch):
    from app.components.elia_engine import service
    from app.components.elia_engine.exceptions import ELIAError

    monkeypatch.setattr(service, "fetch_live_solar_conditions", lambda latitude, longitude, timezone=None: {
        "status": "available", "provider": "Open-Meteo", "irradiance_w_m2": {"shortwave_radiation": 500.0}
    })
    requirements["include_live_solar"] = True
    exterior, outcome = run_elia(master_json, requirements, "run-live-solar")
    assert outcome == "valid"
    assert exterior["environment"]["live_solar_conditions"]["irradiance_w_m2"]["shortwave_radiation"] == 500

    def unavailable(latitude, longitude, timezone=None):
        raise ELIAError("ELIA_SOLAR_API_UNAVAILABLE", "Live solar conditions are temporarily unavailable.", 503)

    monkeypatch.setattr(service, "fetch_live_solar_conditions", unavailable)
    exterior, outcome = run_elia(master_json, requirements, "run-live-solar-unavailable")
    assert outcome == "valid"
    assert exterior["environment"]["live_solar_conditions"]["status"] == "unavailable"
    assert exterior["environment"]["live_solar_conditions"]["error_code"] == "ELIA_SOLAR_API_UNAVAILABLE"
