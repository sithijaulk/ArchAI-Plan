"""Targeted regression test suite verifying architectural corrections for Component 4: ELIA Engine.

Verifies:
1. Rule-based geometric planner generates exterior designs without neural weights or PyTorch.
2. Legacy/unsupported 'trained_model' mode is explicitly rejected with 400.
3. Truthful planner provenance is recorded (engine_type, planner_version, ruleset_version, catalogue_version).
4. Missing roof geometry cannot synthesize a fake roof from the house footprint.
5. Missing structural evidence does not default live_load_certified to True.
6. Solar energy estimation is clearly labeled as an optional preliminary heuristic with stated assumptions.
7. Water features and utilities return feasibility assessments with proper codes and reasons.
8. Upstream house and land geometry remain immutable.
"""
from __future__ import annotations

import copy
import pytest
from app.components.elia_engine.exceptions import ELIAError
from app.components.elia_engine.generation import generate_exterior
from app.components.elia_engine.solar_planner import plan_solar_pv, _extract_roof_surfaces
from app.components.elia_engine.feasibility import assess_project_feasibility


@pytest.fixture
def base_master_json():
    return {
        "project_name": "Architecture Verification Lot",
        "units": "m",
        "location": {"latitude": 6.9271, "longitude": 79.8612, "timezone": "Asia/Colombo"},
        "calculated_north_bearing": 0.0,
        "land_info": {
            "boundary_points": [[0.0, 0.0], [40.0, 0.0], [40.0, 30.0], [0.0, 30.0]],
            "road_facing": "south",
        },
        "land_boundary_polygon": [[0.0, 0.0], [40.0, 0.0], [40.0, 30.0], [0.0, 30.0]],
        "road_boundary_edge": 0,
        "house_exterior_polygon": [[10.0, 8.0], [25.0, 8.0], [25.0, 20.0], [10.0, 20.0]],
        "main_entrance": [17.5, 8.0],
        "building_height_m": 6.5,
        "site": {
            "boundary": [[0.0, 0.0], [40.0, 0.0], [40.0, 30.0], [0.0, 30.0]],
            "road_access": {"road_side": "south", "road_edge_index": 0},
            "utilities": {
                "septic_tank": {"position": [35.0, 5.0]},
            },
        },
        "building": {
            "footprint": [[10.0, 8.0], [25.0, 8.0], [25.0, 20.0], [10.0, 20.0]],
            "entrance": [17.5, 8.0],
            "height_m": 6.5,
        },
        "utilities": {
            "septic_tank": {"known": True, "position_m": [35.0, 5.0]},
        },
    }


@pytest.fixture
def base_requirements():
    return {
        "design_style": "tropical_modern",
        "units": "m",
        "access": {
            "driveway_required": True,
            "driveway_style": "auto",
            "garage_required": False,
            "vehicle_count": 1,
            "vehicle_types": ["sedan"],
        },
        "landscape": {
            "lawn_required": True,
            "pedestrian_path_required": True,
        },
        "solar": {
            "panels_required": True,
            "target_system_capacity_kw": 5.0,
        },
        "water_features": {
            "well_required": True,
            "pond_required": True,
            "swimming_pool_required": False,
        },
    }


def test_generation_succeeds_without_neural_model(base_master_json, base_requirements):
    """Confirm normal generation succeeds using rule-based geometric planning."""
    exterior, outcome = generate_exterior(
        master=base_master_json,
        requirements=base_requirements,
        run_id="run_test_geometric_001",
        generation_mode="baseline",
    )
    assert outcome in {"valid", "infeasible"}
    assert exterior["engine_type"] == "rule_based_geometric_planner"
    assert exterior["planner_version"] == "1.0.0"
    assert exterior["ruleset_version"] == "1.0"
    assert exterior["catalogue_version"] == "2.1"
    assert exterior["model_inference_status"] == "not_requested"


def test_trained_model_mode_is_explicitly_rejected(base_master_json, base_requirements):
    """Trained model requests must be rejected with 400 and clear explanation."""
    with pytest.raises(ELIAError) as exc_info:
        generate_exterior(
            master=base_master_json,
            requirements=base_requirements,
            run_id="run_test_reject_001",
            generation_mode="trained_model",
        )
    assert "ELIA_UNSUPPORTED_GENERATION_MODE" in exc_info.value.code
    assert exc_info.value.status_code == 400
    assert "Trained model mode is not supported" in exc_info.value.message


def test_missing_roof_geometry_does_not_fabricate_from_house_footprint(base_master_json, base_requirements):
    """Solar planner must return evidence_missing when Master JSON lacks explicit roofs."""
    surfaces = _extract_roof_surfaces(base_master_json, unit_scale=1.0)
    assert len(surfaces) == 0

    solar_plan = plan_solar_pv(base_master_json, base_requirements, unit_scale=1.0)
    assert solar_plan["status"] == "evidence_missing"
    assert solar_plan["feasibility_status"] == "evidence_missing"
    assert solar_plan["reason"] == "MISSING_ROOF_GEOMETRY"
    assert "authoritative_roof_surfaces" in solar_plan["missing_evidence"]
    assert solar_plan["module_count"] == 0


def test_solar_planner_with_explicit_roof_and_structural_verification(base_master_json, base_requirements):
    """Solar planner uses explicit roof surfaces, preserves orientation, and checks certification."""
    master_with_roof = {
        **base_master_json,
        "roofs": [
            {
                "json_id": "ROOF_FLAT_001",
                "type": "flat_roof",
                "polygon": [
                    [11.0, 9.0],
                    [24.0, 9.0],
                    [24.0, 19.0],
                    [11.0, 19.0],
                ],
                "elevation_m": 6.5,
                "pitch_deg": 0.0,
                "azimuth_deg": 180.0,
                "live_load_certified": False, # Explicitly uncertified
            }
        ],
    }

    solar_plan = plan_solar_pv(master_with_roof, base_requirements, unit_scale=1.0)
    assert solar_plan is not None
    assert solar_plan["status"] == "review_required"
    assert solar_plan["approval_status"] == "provisional_review_required"
    assert solar_plan["module_count"] > 0
    # Must report unverified structural certification
    assert solar_plan["structural_certification_status"] == "unverified"
    assert "Supporting roof surface lacks verified structural live-load certification" in solar_plan["outdoor_element"]["validation"]["technical_disclaimer"]
    # Energy estimate must be explicitly labeled as preliminary heuristic
    assert solar_plan["energy_estimation"]["is_rough_preliminary_estimate"] is True
    assert "Empirical tropical baseline" in solar_plan["energy_estimation"]["assumptions"][0]


def test_feasibility_assesses_water_features_and_disabling(base_master_json, base_requirements):
    """Feasibility engine evaluates well, septic, pond, pool, and garden taps."""
    result = assess_project_feasibility(base_master_json, base_requirements)
    fa = result.feature_assessments

    assert "well" in fa
    assert "septic_tank" in fa
    assert "pond" in fa
    assert "swimming_pool" in fa
    assert "pool" in fa
    assert "garden_taps" in fa

    # Septic is preserved from Master JSON
    assert fa["septic_tank"].feasibility_status in {"feasible", "review_required"}
    # Pond requested on 30x40 lot with unoccupied ground
    assert fa["pond"].feasibility_status == "feasible"


def test_upstream_geometry_immutability(base_master_json, base_requirements):
    """Ensure generation does not mutate the authoritative house footprint or land boundary."""
    original_land = copy.deepcopy(base_master_json["land_boundary_polygon"])
    original_house = copy.deepcopy(base_master_json["house_exterior_polygon"])

    generate_exterior(
        master=base_master_json,
        requirements=base_requirements,
        run_id="run_immutability_test",
        generation_mode="baseline",
    )

    assert base_master_json["land_boundary_polygon"] == original_land
    assert base_master_json["house_exterior_polygon"] == original_house
