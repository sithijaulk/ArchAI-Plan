"""
Unit and regression test suite for Component 4 — ELIA Engine focused correction pass.
Tests verification of:
1. Zero solar geometry fabrication (no default height, pitch, azimuth).
2. Non-finite geometry rejection.
3. Feasibility and fulfillment status propagation (evidence_missing != infeasible).
4. Separation of provisional geometric preview from structural approval.
5. Solar evidence consumption and provider handling.
6. Module geometry preservation (modules list, dimensions width_m/length_m, OBB containment).
7. Septic maintenance-access assessment (hose obstruction, tanker distance screening).
8. Unsupported generation mode rejection (no neural inference dependency).
"""

import math
import pytest
from app.components.elia_engine.solar_planner import plan_solar_pv, _extract_roof_surfaces
from app.components.elia_engine.service import run_elia
from app.components.elia_engine.feasibility import assess_project_feasibility
from app.components.elia_engine.exceptions import ELIAError


def _base_master():
    return {
        "units": "m",
        "location": {"latitude": 6.9271, "longitude": 79.8612},
        "land_info": {
            "mathematical_polygon": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [40, 0], [40, 30], [0, 30], [0, 0]]],
            },
            "calculated_north_bearing": 0.0,
            "road_facing": "south",
        },
        "house": {
            "exterior_polygon": [[10, 10], [25, 10], [25, 20], [10, 20], [10, 10]],
            "roof": {
                "surfaces": [
                    {
                        "id": "roof_south",
                        "surface_type": "pitched_roof",
                        "coordinates": [[[10, 10], [25, 10], [25, 15], [10, 15], [10, 10]]],
                        "elevation_m": 4.5,
                        "pitch_degrees": 25.0,
                        "azimuth_degrees": 180.0,
                    }
                ]
            },
        },
    }


# =========================================================================
# 1. REMOVE SOLAR GEOMETRY FABRICATION & VALIDATE FINITENESS
# =========================================================================

def test_missing_roof_elevation_does_not_invent_six_meters():
    master = _base_master()
    # Explicitly remove elevation_m
    del master["house"]["roof"]["surfaces"][0]["elevation_m"]
    reqs = {"solar": {"panels_required": True}}
    
    plan = plan_solar_pv(master, reqs)
    assert plan["status"] == "evidence_missing"
    assert "elevation_m" in plan.get("missing_evidence", [])
    assert plan.get("outdoor_element") is None


def test_missing_roof_pitch_on_pitched_roof_produces_evidence_missing():
    master = _base_master()
    # Explicitly remove pitch_degrees
    del master["house"]["roof"]["surfaces"][0]["pitch_degrees"]
    reqs = {"solar": {"panels_required": True}}
    
    plan = plan_solar_pv(master, reqs)
    assert plan["status"] == "evidence_missing"
    assert "roof_pitch_degrees" in plan.get("missing_evidence", [])


def test_missing_roof_azimuth_on_pitched_roof_produces_evidence_missing():
    master = _base_master()
    del master["house"]["roof"]["surfaces"][0]["azimuth_degrees"]
    reqs = {"solar": {"panels_required": True}}
    
    plan = plan_solar_pv(master, reqs)
    assert plan["status"] == "evidence_missing"
    assert "roof_orientation_azimuth" in plan.get("missing_evidence", [])


def test_explicit_flat_metadata_records_flatness_provenance():
    master = _base_master()
    master["house"]["roof"]["surfaces"][0] = {
        "id": "roof_flat",
        "surface_type": "flat_roof",
        "coordinates": [[[10, 10], [25, 10], [25, 15], [10, 15], [10, 10]]],
        "elevation_m": 4.0,
        "is_flat": True,
        "pitch_degrees": 0.0,
        "azimuth_degrees": 180.0,
    }
    surfaces = _extract_roof_surfaces(master)
    assert len(surfaces) == 1
    assert surfaces[0]["flatness_provenance"] == "explicit_metadata"
    assert surfaces[0]["is_flat"] is True


def test_non_finite_roof_coordinates_are_rejected():
    master = _base_master()
    master["house"]["roof"]["surfaces"][0]["coordinates"] = [
        [[10, 10], [float("nan"), 10], [25, 15], [10, 15], [10, 10]]
    ]
    with pytest.raises(ELIAError) as exc_info:
        _extract_roof_surfaces(master)
    assert "Non-finite" in str(exc_info.value) or "finite" in str(exc_info.value).lower()


def test_non_finite_roof_pitch_is_rejected():
    master = _base_master()
    master["house"]["roof"]["surfaces"][0]["pitch_degrees"] = float("inf")
    with pytest.raises(ELIAError) as exc_info:
        _extract_roof_surfaces(master)
    assert "Non-finite" in str(exc_info.value) or "finite" in str(exc_info.value).lower()


# =========================================================================
# 2. STATUS PROPAGATION: EVIDENCE_MISSING != INFEASIBLE
# =========================================================================

def test_missing_roof_geometry_reports_evidence_missing_not_infeasible():
    master = _base_master()
    # Completely remove roof
    del master["house"]["roof"]
    reqs = {"solar": {"panels_required": True}}
    
    plan = plan_solar_pv(master, reqs)
    assert plan["status"] == "evidence_missing"
    assert plan["feasibility_status"] == "evidence_missing"
    assert plan["status"] != "infeasible"
    assert "authoritative_roof_surfaces" in plan.get("missing_evidence", []) or "roof_surface_polygons" in plan.get("missing_evidence", [])


def test_unsupported_requested_surface_gives_actionable_error():
    master = _base_master()
    reqs = {
        "solar": {
            "panels_required": True,
            "preferred_roof_surface_id": "non_existent_surface_id",
        }
    }
    plan = plan_solar_pv(master, reqs)
    assert plan["status"] == "infeasible"
    assert "REQUESTED_ROOF_SURFACE_NOT_FOUND" in plan["reason"]
    assert "roof_south" in plan.get("supported_alternatives", [])


# =========================================================================
# 3. SEPARATE GEOMETRIC PREVIEW FROM ACCEPTED STRUCTURAL APPROVAL
# =========================================================================

def test_uncertified_solar_is_provisional_preview_not_fulfilled():
    master = _base_master()
    # No structural evidence in master
    reqs = {"solar": {"panels_required": True}}
    
    plan = plan_solar_pv(master, reqs)
    assert plan["status"] == "review_required"
    assert plan["approval_status"] == "provisional_review_required"
    assert plan["provisional_geometric_preview"] is True
    assert plan["valid"] is False
    assert plan["structural_certification_status"] == "unverified"
    assert "structural_load_certification" in plan.get("missing_evidence", [])


def test_bare_boolean_structural_flag_does_not_bypass_certification():
    master = _base_master()
    # Provide a bare boolean without verifiable professional report / allowance
    master["structural_evidence"] = {"certified": True}
    reqs = {"solar": {"panels_required": True}}
    
    plan = plan_solar_pv(master, reqs)
    # Must still reject bare boolean
    assert plan["approval_status"] == "provisional_review_required"
    assert plan["valid"] is False
    assert plan["structural_certification_status"] == "unverified"


def test_verified_structural_evidence_allows_full_approval():
    master = _base_master()
    master["structural_evidence"] = {
        "certified": True,
        "remaining_capacity_kg_m2": 50.0,
        "proposed_load_kg_m2": 25.0,
        "solar_load_certified": True,
        "roof_allowance_kg_m2": 200.0,
        "engineer_license": "SL-ENG-2024-9988",
    }
    reqs = {"solar": {"panels_required": True, "proposed_load_kg_m2": 25.0}}
    
    plan = plan_solar_pv(master, reqs)
    assert plan["status"] == "fulfilled"
    assert plan["approval_status"] == "approved"
    assert plan["provisional_geometric_preview"] is False
    assert plan["valid"] is True
    assert plan["structural_certification_status"] == "certified"


# =========================================================================
# 4. SOLAR ARRAY GEOMETRY: MODULE FOOTPRINTS & DIMENSIONS
# =========================================================================

def test_solar_array_preserves_individual_modules():
    master = _base_master()
    reqs = {"solar": {"panels_required": True, "target_kw": 4.0}}
    
    plan = plan_solar_pv(master, reqs)
    array = plan.get("outdoor_element")
    assert array is not None
    assert "modules" in array
    modules = array["modules"]
    assert len(modules) > 0
    
    for mod in modules:
        assert "id" in mod
        assert "coordinates" in mod
        assert "center" in mod
        assert "elevation_m" in mod
        assert "dimensions" in mod
        assert "width_m" in mod["dimensions"]
        assert "length_m" in mod["dimensions"]
        assert mod["dimensions"]["length_m"] > 0
        assert mod["tilt_degrees"] == 25.0
        assert mod["azimuth_degrees"] == 180.0


def test_array_dimensions_contain_width_and_length():
    master = _base_master()
    reqs = {"solar": {"panels_required": True, "target_kw": 2.5}}
    
    plan = plan_solar_pv(master, reqs)
    dims = plan["outdoor_element"]["dimensions"]
    assert "width_m" in dims
    assert "length_m" in dims
    assert dims["width_m"] > 0
    assert dims["length_m"] > 0


# =========================================================================
# 5. SOLAR EVIDENCE CONSUMPTION
# =========================================================================

def test_plan_solar_pv_consumes_live_solar_evidence():
    master = _base_master()
    reqs = {"solar": {"panels_required": True}}
    live_solar = {
        "source": "Open-Meteo",
        "irradiance": {"direct_normal_irradiance": 850.0, "global_horizontal_irradiance": 920.0},
        "sun_position": {"azimuth": 178.5, "elevation": 62.0},
        "status": "available",
    }
    solar_samples = [
        {"time": "09:00", "azimuth": 110.0, "elevation": 42.0},
        {"time": "12:00", "azimuth": 180.0, "elevation": 75.0},
        {"time": "15:00", "azimuth": 250.0, "elevation": 38.0},
    ]
    
    plan = plan_solar_pv(master, reqs, solar_samples=solar_samples, live_solar=live_solar)
    assert plan["solar_evidence_consumed"]["live_solar_available"] is True
    assert plan["solar_evidence_consumed"]["solar_samples_count"] == 3


# =========================================================================
# 6. SEPTIC MAINTENANCE-ACCESS ASSESSMENT
# =========================================================================

def test_septic_maintenance_access_detects_structural_obstruction():
    master = _base_master()
    # Place septic tank in back yard (y=25) so direct line to road (y=0) intersects house (y=10..20)
    master["floor_plan"] = {
        "ground_floor": {
            "utilities": {
                "septic_tank": {"position": {"x": 15, "y": 25}},
            }
        }
    }
    
    result = assess_project_feasibility(master, {})
    septic_res = result.feature_assessments.get("septic_tank")
    assert septic_res is not None
    assert septic_res.feasibility_status == "review_required"
    assert "SEPTIC_HOSE_CORRIDOR_OBSTRUCTED_BY_STRUCTURE" in septic_res.reason_codes
    assert "vacuum_tanker_parking_position" in septic_res.missing_evidence


def test_septic_maintenance_access_long_distance_requires_auxiliary_pumping():
    master = _base_master()
    # Place septic tank far from road (> 30m)
    master["floor_plan"] = {
        "ground_floor": {
            "utilities": {
                "septic_tank": {"position": {"x": 35, "y": 28}},
            }
        }
    }
    result = assess_project_feasibility(master, {})
    septic_res = result.feature_assessments.get("septic_tank")
    assert septic_res is not None
    assert septic_res.feasibility_status == "review_required"
    assert "SEPTIC_ACCESS_DISTANCE_HIGH" in septic_res.reason_codes


# =========================================================================
# 7. SERVICE & UNSUPPORTED MODE REJECTION
# =========================================================================

def test_unsupported_neural_mode_is_rejected():
    master = _base_master()
    reqs = {}
    with pytest.raises(ELIAError) as exc_info:
        run_elia(master, reqs, run_id="run_test_001", generation_mode="neural_diffusion_model")
    assert "UNSUPPORTED_GENERATION_MODE" in exc_info.value.code or "Unsupported" in str(exc_info.value)


# =========================================================================
# 8. SOLAR EVIDENCE DRIVEN ROOF SELECTION & SEPTIC ROUTING CASES
# =========================================================================

def test_solar_samples_tilt_surface_selection_between_east_and_west():
    """Verify that empirical/incident solar samples directly affect roof surface selection."""
    master = _base_master()
    # Provide two symmetric roofs: one facing East (azimuth 90), one facing West (azimuth 270)
    master["house"]["roof"]["surfaces"] = [
        {
            "id": "roof_east",
            "surface_type": "pitched_roof",
            "coordinates": [[[10, 10], [17, 10], [17, 20], [10, 20], [10, 10]]],
            "elevation_m": 4.5,
            "pitch_degrees": 25.0,
            "azimuth_degrees": 90.0,
        },
        {
            "id": "roof_west",
            "surface_type": "pitched_roof",
            "coordinates": [[[18, 10], [25, 10], [25, 20], [18, 20], [18, 10]]],
            "elevation_m": 4.5,
            "pitch_degrees": 25.0,
            "azimuth_degrees": 270.0,
        },
    ]
    reqs = {"solar": {"panels_required": True}}

    # Case A: Morning-weighted solar samples (sun from East)
    morning_samples = [
        {"time": "08:00", "azimuth": 90.0, "elevation": 30.0},
        {"time": "10:00", "azimuth": 95.0, "elevation": 55.0},
    ]
    plan_morning = plan_solar_pv(master, reqs, solar_samples=morning_samples)
    assert plan_morning["target_surface_id"] == "roof_east", (
        f"Morning solar samples must select East roof, got {plan_morning['target_surface_id']}"
    )

    # Case B: Afternoon-weighted solar samples (sun from West)
    afternoon_samples = [
        {"time": "14:00", "azimuth": 265.0, "elevation": 55.0},
        {"time": "16:00", "azimuth": 270.0, "elevation": 30.0},
    ]
    plan_afternoon = plan_solar_pv(master, reqs, solar_samples=afternoon_samples)
    assert plan_afternoon["target_surface_id"] == "roof_west", (
        f"Afternoon solar samples must select West roof, got {plan_afternoon['target_surface_id']}"
    )


def test_septic_service_access_straight_line_clear():
    """Verify that a septic tank in front of the house has clear straight-line access."""
    master = _base_master()
    # Place septic tank in front yard (y=4, road south at y=0, house at y=10..20)
    master["floor_plan"] = {
        "ground_floor": {
            "utilities": {
                "septic_tank": {"position": {"x": 15, "y": 4}},
            }
        }
    }
    result = assess_project_feasibility(master, {})
    septic_res = result.feature_assessments.get("septic_tank")
    assert septic_res is not None
    assert septic_res.feasibility_status == "feasible"
    assert "EXISTING_SEPTIC_PRESERVED" in septic_res.reason_codes


def test_septic_service_access_side_corridor_feasible_when_reach_sufficient():
    """Verify that an obstructed septic tank is marked feasible if a side corridor is within reach."""
    master = _base_master()
    # Place septic tank behind house at (16, 21), house is [10, 10]..[25, 20]
    master["floor_plan"] = {
        "ground_floor": {
            "utilities": {
                "septic_tank": {"position": {"x": 16, "y": 21}},
            }
        }
    }
    # With a hose reach of 35.0m, routing around the house is feasible
    reqs = {"water_features": {"max_vacuum_hose_reach_m": 35.0}}
    result = assess_project_feasibility(master, reqs)
    septic_res = result.feature_assessments.get("septic_tank")
    assert septic_res is not None
    assert septic_res.feasibility_status == "feasible"
    assert "SEPTIC_SIDE_CORRIDOR_ACCESSIBLE" in septic_res.reason_codes
    assert "W05" in septic_res.applicable_rule_ids


def test_septic_service_access_side_corridor_exceeding_reach_requires_review():
    """Verify that an obstructed septic tank whose side corridor exceeds reach requires review."""
    master = _base_master()
    # Place septic tank behind house at (16, 21), routing distance is ~26-28m
    master["floor_plan"] = {
        "ground_floor": {
            "utilities": {
                "septic_tank": {"position": {"x": 16, "y": 21}},
            }
        }
    }
    # Reach of 15.0m is not sufficient to reach around the house
    reqs = {"water_features": {"max_vacuum_hose_reach_m": 15.0}}
    result = assess_project_feasibility(master, reqs)
    septic_res = result.feature_assessments.get("septic_tank")
    assert septic_res is not None
    assert septic_res.feasibility_status == "review_required"
    assert "SEPTIC_ROUTE_EXCEEDS_REACH" in septic_res.reason_codes


# =========================================================================
# 9. ADVANCED STRUCTURAL ACCEPTANCE, REVISED THRESHOLDS & SCOPE MATCHING
# =========================================================================

def test_structural_evidence_baseline_code_allowance_150_retains_review_required():
    """150 kg/m2 is the statutory maintenance live load baseline; without surplus margin, review is required."""
    master = _base_master()
    master["structural_evidence"] = {
        "certified": True,
        "roof_allowance_kg_m2": 150.0,
        "engineer_license": "SL-ENG-2024-9988",
    }
    reqs = {"solar": {"panels_required": True}}
    plan = plan_solar_pv(master, reqs)
    assert plan["status"] == "review_required"
    assert plan["approval_status"] == "provisional_review_required"
    assert plan["provisional_geometric_preview"] is True
    assert plan["valid"] is False
    assert plan["structural_certification_status"] == "unverified"


def test_structural_evidence_proposed_load_exceeds_remaining_capacity_rejected():
    """When a specific proposed load (35 kg/m2) exceeds certified remaining capacity (20 kg/m2), review is required."""
    master = _base_master()
    master["structural_evidence"] = {
        "certified": True,
        "remaining_capacity_kg_m2": 20.0,
        "engineer_license": "SL-ENG-2024-9988",
    }
    reqs = {"solar": {"panels_required": True, "proposed_load_kg_m2": 35.0}}
    plan = plan_solar_pv(master, reqs)
    assert plan["status"] == "review_required"
    assert plan["approval_status"] == "provisional_review_required"
    assert plan["provisional_geometric_preview"] is True
    assert plan["valid"] is False


def test_structural_evidence_mismatched_installation_type_retains_review_required():
    """Structural signoff for one installation type (e.g. BIPV) cannot certify a different installation type (ballasted)."""
    master = _base_master()
    master["structural_evidence"] = {
        "certified": True,
        "roof_allowance_kg_m2": 250.0,
        "engineer_license": "SL-ENG-2024-9988",
        "installation_type": "bipv",
    }
    reqs = {"solar": {"panels_required": True, "installation_type": "ballasted"}}
    plan = plan_solar_pv(master, reqs)
    assert plan["status"] == "review_required"
    assert plan["approval_status"] == "provisional_review_required"
    assert plan["provisional_geometric_preview"] is True


# =========================================================================
# 10. SEPTIC REACH VALIDATION & COMPLETE OBSTRUCTION
# =========================================================================

def test_septic_invalid_non_finite_hose_reach_rejected():
    """Non-finite (NaN or Inf) or negative vacuum hose reach inputs are rejected with ELIA_INVALID_REQUIREMENT."""
    master = _base_master()
    master["floor_plan"] = {
        "ground_floor": {
            "utilities": {
                "septic_tank": {"position": {"x": 16, "y": 21}},
            }
        }
    }
    with pytest.raises(ELIAError) as exc_nan:
        assess_project_feasibility(master, {"water_features": {"max_vacuum_hose_reach_m": float("nan")}})
    assert exc_nan.value.code == "ELIA_INVALID_REQUIREMENT"

    with pytest.raises(ELIAError) as exc_neg:
        assess_project_feasibility(master, {"water_features": {"max_vacuum_hose_reach_m": -15.0}})
    assert exc_neg.value.code == "ELIA_INVALID_REQUIREMENT"


def test_septic_blocked_route_without_side_corridor_retains_review_required():
    """When house spans the entire width of parcel, no side corridor exists; review_required is preserved."""
    master = _base_master()
    # House spans full x width [0..40] from y=10 to y=20
    master["house"]["exterior_polygon"] = [[0, 10], [40, 10], [40, 20], [0, 20], [0, 10]]
    master["floor_plan"] = {
        "ground_floor": {
            "utilities": {
                "septic_tank": {"position": {"x": 20, "y": 25}},
            }
        }
    }
    result = assess_project_feasibility(master, {})
    septic_res = result.feature_assessments.get("septic_tank")
    assert septic_res is not None
    assert septic_res.feasibility_status == "review_required"
    assert "SEPTIC_HOSE_CORRIDOR_OBSTRUCTED_BY_STRUCTURE" in septic_res.reason_codes


# =========================================================================
# 11. CANDIDATE VALIDATION: SOLAR APPROVAL, TAMPERING, & ROTATED OBBs
# =========================================================================

def test_validate_candidate_rejects_uncertified_solar_array():
    """Candidate containing solar array on uncertified roof is rejected by backend validator and acceptance policy."""
    from app.components.elia_engine.service import validate_candidate_exterior, evaluate_acceptance_policy
    master = _base_master()
    # Master has no structural certification
    candidate = {
        "access": {"gate": None, "garage": None, "driveway": None},
        "outdoor_elements": [
            {
                "json_id": "SOLAR_001",
                "type": "solar_panel_array",
                "supporting_surface_id": "roof_south",
                "position": [17.5, 12.5],
                "dimensions": {"width_m": 5.0, "length_m": 3.0},
                "polygon": [[15, 11], [20, 11], [20, 14], [15, 14], [15, 11]],
            }
        ],
    }
    res = validate_candidate_exterior(master, candidate)
    assert res["approval_status"] in ("review_required", "provisional_review_required")
    policy = evaluate_acceptance_policy(res, res.get("canonical_candidate", candidate), master)
    assert policy["accepted"] is False
    assert "solar_panels" in policy["blocking_features"]


def test_validate_candidate_rejects_tampered_flags_with_collision():
    """Server recalculates validity independently; client-supplied valid=True is ignored on collision."""
    from app.components.elia_engine.service import validate_candidate_exterior
    master = _base_master()
    # Candidate places seating inside house [10..25, 10..20], but claims valid=True, approval_status='approved'
    candidate = {
        "valid": True,
        "approval_status": "approved",
        "outdoor_elements": [
            {
                "json_id": "SEAT_TAMPERED",
                "type": "garden_seating",
                "position": [15.0, 15.0],  # inside house
                "dimensions": {"width_m": 2.0, "length_m": 1.5},
            }
        ],
    }
    res = validate_candidate_exterior(master, candidate)
    assert res["valid"] is False
    assert any("outdoor_element_intersects_obstacles" in v for v in res["violations"])


def test_validate_candidate_enforces_catalogue_dimension_limits():
    """Resizing beyond catalogue limits (e.g. 25m width table or 15m canopy radius) is rejected."""
    from app.components.elia_engine.service import validate_candidate_exterior
    master = _base_master()
    # Out-of-bounds furniture
    candidate_furniture = {
        "outdoor_elements": [
            {
                "json_id": "HUGE_TABLE",
                "type": "garden_table_set",
                "position": [5.0, 5.0],
                "dimensions": {"width_m": 25.0, "length_m": 2.0},  # 25m exceeds 10m catalogue limit
            }
        ],
    }
    res_f = validate_candidate_exterior(master, candidate_furniture)
    assert res_f["valid"] is False
    assert any("dimension_limits_exceeded" in v for v in res_f["violations"])

    # Out-of-bounds tree canopy radius
    candidate_tree = {
        "vegetation_nodes": [
            {
                "json_id": "GIANT_TREE",
                "position": [5.0, 5.0],
                "canopy_radius_m": 15.0,  # exceeds 10m limit
            }
        ],
    }
    res_t = validate_candidate_exterior(master, candidate_tree)
    assert res_t["valid"] is False
    assert any("invalid_canopy_radius" in v for v in res_t["violations"])


def test_validate_candidate_preserves_rotated_asymmetric_obb():
    """Asymmetric feature (3m x 1m) rotated 90 degrees rotates its footprint correctly."""
    from app.components.elia_engine.service import validate_candidate_exterior
    from shapely.geometry import Polygon
    master = _base_master()
    # Table positioned at (5, 5), width=3, length=1, rotated 90 degrees
    # At 0 degrees: x from 3.5 to 6.5 (extent 3), y from 4.5 to 5.5 (extent 1)
    # At 90 degrees: x from 4.5 to 5.5 (extent 1), y from 3.5 to 6.5 (extent 3)
    candidate = {
        "outdoor_elements": [
            {
                "json_id": "ROTATED_TABLE",
                "type": "garden_table_set",
                "position": [5.0, 5.0],
                "dimensions": {"width_m": 3.0, "length_m": 1.0},
                "rotation_deg": 90.0,
            }
        ],
    }
    res = validate_candidate_exterior(master, candidate)
    assert res["valid"] is True
    elem = res["canonical_candidate"]["outdoor_elements"][0]
    poly = Polygon(elem["polygon"])
    bounds = poly.bounds  # minx, miny, maxx, maxy
    assert round(bounds[2] - bounds[0], 2) == 1.0, f"Rotated width along x must be 1.0m, got {bounds[2] - bounds[0]}"
    assert round(bounds[3] - bounds[1], 2) == 3.0, f"Rotated length along y must be 3.0m, got {bounds[3] - bounds[1]}"


