from copy import deepcopy
import pytest

from app.components.elia_engine.output import build_updated_master
from app.components.elia_engine.exceptions import ELIAError
from app.components.elia_engine.model_adapter import run_model_generation
from app.components.elia_engine.requirements import normalize_requirements
from app.components.elia_engine.schemas import ELIARequirements
from app.components.elia_engine.service import _building_height, run_elia


@pytest.fixture
def master_json():
    return {
        "project_id": "project-elia",
        "project_name": "Courtyard home",
        "units": "m",
        "location": {"latitude": 6.9, "longitude": 79.8, "timezone": "Asia/Colombo"},
        "land_info": {"boundary_points": [[0, 0], [40, 0], [40, 30], [0, 30]],
                   "road_facing": "south", "calculated_north_bearing": 0},
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
                   "driveway_required": True, "vehicle_profiles": [{"vehicle_type": "car", "minimum_turning_radius_m": 5.5}]},
        "landscape": {"garden_required": False},
        "lighting": {"required": False},
        "vertical_greenery": {"mode": "automatic"},
    }


def test_complete_run_returns_explainable_layout_without_mutating_master(master_json, requirements):
    before = deepcopy(master_json)
    exterior, outcome = run_elia(master_json, requirements, "run-1")

    assert master_json == before
    assert outcome == "infeasible", {"validation": exterior["validation_summary"],
                                     "gate": exterior["access"]["gate"], "garage": exterior["access"]["garage"],
                                     "metrics": exterior["metrics"]}
    assert exterior["access"]["gate"]["json_id"] == "GATE_001"
    assert exterior["utility_safety"]["required_separation_ft"] == 50
    assert exterior["environment"]["solar_samples"]
    assert exterior["metrics"]["solar_analysis_completed"]
    assert exterior["access"]["garage"]["json_id"] == "GARAGE_001"
    assert exterior["access"]["driveway"]["pathfinding"] == "A*"
    assert not exterior["validation_summary"]["valid"]
    assert "vehicle_turning_radius_or_width" in exterior["validation_summary"]["violations"]
    assert exterior["validation_summary"]["constraint_satisfaction_rate"] < 1.0
    assert exterior["validation_summary"]["checks_passed"] + len(exterior["validation_summary"]["violations"]) == exterior["validation_summary"]["checks_total"]
    assert exterior["metrics"]["constraint_satisfaction_rate"] == exterior["validation_summary"]["constraint_satisfaction_rate"]
    assert exterior["metrics"]["constraint_violation_count"] == len(exterior["validation_summary"]["violations"])
    assert tuple(exterior["access"]["driveway"]["centerline"][-1]) == tuple(exterior["access"]["garage"]["entry_point"])


def test_updated_master_preserves_prior_layers_structurally(master_json):
    exterior = {"version": "1.0", "vegetation_nodes": []}
    updated = build_updated_master(master_json, exterior, "run-2", "valid")

    assert updated["interior_layout"] == master_json["interior_layout"]
    assert updated["floor_plan"] == master_json["floor_plan"]
    assert updated["processing"]["esai_engine"] == master_json["processing"]["esai_engine"]
    assert updated["exterior_landscape"] == exterior
    assert updated["processing"]["elia_engine"]["outcome"] == "valid"


def test_infeasible_candidate_does_not_replace_accepted_exterior(master_json):
    master_json["exterior_landscape"] = {"accepted_run": "previous"}
    candidate = {"run_id": "candidate", "validation_summary": {"valid": False}}

    updated = build_updated_master(master_json, candidate, "candidate", "infeasible")

    assert updated["exterior_landscape"] == {"accepted_run": "previous"}
    assert updated["processing"]["elia_engine"]["outcome"] == "infeasible"


def test_meter_and_feet_requirement_dimensions_normalize_equivalently(master_json):
    meters = {"units": "m", "access": {"vehicle_profiles": [{"vehicle_type": "car", "length": 4.5,
             "width": 1.8, "minimum_turning_radius": 5.0}]},
              "landscape": {"boundary_wall_height": 2.0}, "lighting": {"preferred_spacing": 5.0}}
    feet = {"units": "ft", "access": {"vehicle_profiles": [{"vehicle_type": "car", "length": 4.5 / 0.3048,
             "width": 1.8 / 0.3048, "minimum_turning_radius": 5.0 / 0.3048}]},
            "landscape": {"boundary_wall_height": 2.0 / 0.3048},
            "lighting": {"preferred_spacing": 5.0 / 0.3048}}

    normalized_m = normalize_requirements(meters, master_json, "m")
    normalized_ft = normalize_requirements(feet, master_json, "m")

    assert normalized_ft["access"]["vehicle_profiles"] == pytest.approx(normalized_m["access"]["vehicle_profiles"])
    assert normalized_ft["landscape"]["boundary_wall_height_m"] == pytest.approx(2.0)
    assert normalized_ft["lighting"]["preferred_spacing_m"] == pytest.approx(5.0)
    defaults_m = normalize_requirements({"units": "m"}, master_json, "m")
    defaults_ft = normalize_requirements({"units": "ft"}, master_json, "m")
    assert defaults_ft["access"]["vehicle_profiles"] == defaults_m["access"]["vehicle_profiles"]


def test_omitted_requirement_units_default_to_meters_for_feet_master(master_json):
    master_json["units"] = "ft"
    request = ELIARequirements(access={"gate_width": 4})
    requirements = request.model_dump(mode="json", exclude_none=True, exclude_unset=True)
    assert "units" not in requirements
    normalized = normalize_requirements(requirements, master_json, "ft")
    explicit_feet = normalize_requirements({"units": "ft", "access": {"gate_width": 4}}, master_json, "ft")

    assert normalized["access"]["gate_width_m"] == pytest.approx(4.0)
    assert explicit_feet["access"]["gate_width_m"] == pytest.approx(1.2192)


def test_request_utility_positions_default_to_meters_with_feet_master(master_json):
    master_json["units"] = "ft"
    # master well=[2,27]ft -> [0.6096, 8.2296]m, septic=[22,27]ft -> [6.7056, 8.2296]m
    # Request must match master (no relocation allowed) and be in meters (no units key = m).
    # Separation = (22-2)*0.3048 = 6.096 m = 20 ft < 50 ft minimum → should FAIL safety check.
    exterior, outcome = run_elia(master_json, {
        "access": {"road_side": "south", "garage_required": False, "driveway_required": False},
        "utilities": {
            "well": {"known": True, "position": [0.6096, 8.2296]},
            "septic_tank": {"known": True, "position": [6.7056, 8.2296]},
        },
    }, "request-utility-units")

    assert exterior["utility_safety"]["status"] == "failed"
    assert exterior["utility_safety"]["checks"][0]["actual_distance_ft"] == pytest.approx(20.0)
    assert outcome in {"valid", "infeasible"}


@pytest.mark.parametrize(("requirements", "code"), [
    ({"location": {"timezone": "Mars/NotAZone"}}, "ELIA_INVALID_TIMEZONE"),
    ({"solar_analysis_date": "2026-02-30"}, "ELIA_INVALID_SOLAR_DATE"),
    ({"solar_analysis_time_range": ["25:00"]}, "ELIA_INVALID_SOLAR_TIME"),
    ({"lighting": {"required": True, "style": "neon"}}, "ELIA_INVALID_LIGHTING_STYLE"),
    ({"lighting": {"required": True, "zones": ["roof"]}}, "ELIA_INVALID_LIGHTING_ZONE"),
    ({"lighting": {"preferred_spacing": 2}}, "ELIA_INVALID_LIGHTING_SPACING"),
    ({"greenery_level": "lush"}, "ELIA_INVALID_GREENERY_DENSITY"),
    ({"landscape_priority": "fast"}, "ELIA_INVALID_LANDSCAPE_PRIORITY"),
])
def test_invalid_solar_and_lighting_preferences_are_typed(master_json, requirements, code):
    with pytest.raises(ELIAError) as error:
        normalize_requirements(requirements, master_json, "m")

    assert error.value.code == code


def test_explicit_meter_house_height_is_not_scaled_for_feet_site():
    assert _building_height({"house_height_m": 6}, 0.3048) == 6
    assert _building_height({"building": {"height_m": 6}}, 0.3048) == 6


def test_trained_model_is_explicitly_unavailable_until_adapter_exists(master_json, requirements):
    with pytest.raises(ELIAError) as error:
        run_model_generation(master_json, requirements, "model-run")

    assert error.value.code == "ELIA_MODEL_UNAVAILABLE"
    assert error.value.status_code == 503


def test_model_validity_flags_do_not_override_house_overlap(master_json):
    class MockAdapter:
        model_version = "mock-v1"

        def infer(self, prepared_input):
            return {
                "schema_version": "1.0", "coordinate_reference": "local meters", "access": {},
                "site_analysis": {}, "utility_safety": {}, "environment": {}, "metrics": {},
                "outdoor_elements": [{"json_id": "SEAT_001", "type": "garden_seating",
                                      "position": [11, 10], "units": "m",
                                      "validation": {"valid": True}}],
                "validation_summary": {"valid": True},
            }

    exterior, outcome = run_model_generation(master_json, {"access": {"driveway_required": False}},
                                             "mock-run", MockAdapter())

    assert outcome == "infeasible"
    assert "fixed_obstacle_overlap:SEAT_001" in exterior["validation_summary"]["violations"]
    assert exterior["outdoor_elements"][0]["validation"]["valid"] is False


def test_malformed_model_output_is_rejected_and_kept_for_run_history(master_json):
    class MockAdapter:
        model_version = "mock-v1"

        def infer(self, prepared_input):
            return {"schema_version": "1.0", "coordinate_reference": "local meters", "access": {},
                    "site_analysis": {}, "utility_safety": {}, "environment": {}, "metrics": {},
                    "outdoor_elements": [{"json_id": "BAD_001", "type": "garden_seating",
                                          "position": [float("nan"), 1], "units": "m"}]}

    with pytest.raises(ELIAError) as error:
        run_model_generation(master_json, {"access": {"driveway_required": False}}, "bad-run", MockAdapter())

    assert error.value.code == "ELIA_INVALID_MODEL_OUTPUT"
    assert error.value.candidate_output["outdoor_elements"][0]["json_id"] == "BAD_001"


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
    assert outcome == "infeasible"
    assert exterior["environment"]["live_solar_conditions"]["irradiance_w_m2"]["shortwave_radiation"] == 500

    def unavailable(latitude, longitude, timezone=None):
        raise ELIAError("ELIA_SOLAR_API_UNAVAILABLE", "Live solar conditions are temporarily unavailable.", 503)

    monkeypatch.setattr(service, "fetch_live_solar_conditions", unavailable)
    exterior, outcome = run_elia(master_json, requirements, "run-live-solar-unavailable")
    assert outcome == "infeasible"
    assert exterior["environment"]["live_solar_conditions"]["status"] == "unavailable"
    assert exterior["environment"]["live_solar_conditions"]["error_code"] == "ELIA_SOLAR_API_UNAVAILABLE"
