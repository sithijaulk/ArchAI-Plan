from __future__ import annotations

import math
from copy import deepcopy
import pytest
from shapely.geometry import Point, Polygon

from app.components.elia_engine.rule_registry import (
    RULE_REGISTRY,
    RuleCategory,
    RuleClass,
    RuleOutcome,
    get_all_rules,
    get_rule,
)
from app.components.elia_engine.rule_evaluator import evaluate_rules
from app.components.elia_engine.parser import parse_exterior_context
from app.components.elia_engine.requirements import normalize_requirements
from app.components.elia_engine.service import run_elia, validate_candidate_exterior
from app.components.elia_engine.rule_repository import vegetation_catalog


@pytest.fixture
def base_master_json():
    return {
        "project_id": "test-rules-prj",
        "project_name": "Versioned Rules Test Site",
        "revision": 2,
        "units": "m",
        "location": {"latitude": 6.9, "longitude": 79.8, "timezone": "Asia/Colombo"},
        "land_info": {
            "boundary_points": [[0, 0], [40, 0], [40, 30], [0, 30]],
            "road_facing": "south",
            "calculated_north_bearing": 0,
        },
        "house_exterior_polygon": [[10, 8], [22, 8], [22, 22], [10, 22]],
        "house_height_m": 6,
        "utilities": {
            "well": {"known": True, "position": [2, 27]},
            "septic_tank": {"known": True, "position": [22, 27]},
        },
        "interior_layout": {"rooms": [{"id": "R1"}]},
        "floor_plan": {"floors": [{"id": "F1"}]},
        "processing": {"esai_engine": {"status": "completed"}},
    }


def test_rule_registry_structure_and_classes():
    """Verify registry completeness across groups A, G, B, R, V, W, X, C and rule classes."""
    all_rules = get_all_rules()
    assert len(all_rules) >= 50
    rule_ids = {r.rule_id for r in all_rules}

    # Verify presence of representative rules from each group
    for expected_id in ["A01", "A06", "G01", "G02", "B01", "B04", "R03", "R04", "V01", "V06", "W01", "X02", "C01", "C08"]:
        assert expected_id in rule_ids, f"Expected rule {expected_id} in registry"

    # Verify classes L, E, P, D exist and have required metadata
    classes_found = {r.rule_class for r in all_rules}
    assert {RuleClass.LEGAL, RuleClass.ENGINEERING, RuleClass.PLANNER, RuleClass.DATA_QUALITY} <= classes_found

    for r in all_rules:
        assert r.rule_id
        assert r.version
        assert r.category in RuleCategory
        assert r.description
        assert r.verification_status
        assert r.missing_data_behavior
        assert r.enforcement_consequence


def test_pending_legal_rule_is_not_enforced_as_universal_law(base_master_json):
    """Pending legal rules (e.g. A06 street line, W01 15m well) require verification and do not hard-block."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern", "landscape": {"garden_required": True}}

    # Base candidate without street line or local gazette
    candidate = {
        "vegetation_nodes": [{"json_id": "tree_1", "position": [5, 5], "canopy_radius_m": 2.0}],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    eval_res = evaluate_rules(candidate, context, base_master_json, reqs)
    r_map = {r["rule_id"]: r for r in eval_res["rule_evaluations"]}

    # A03 (jurisdiction) and A04 (instrument provenance) are unknown/review_required, not hard fail
    assert r_map["A03"]["outcome"] == RuleOutcome.UNKNOWN.value
    assert r_map["A04"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    # A06 is not applicable when no street line is declared
    assert r_map["A06"]["outcome"] == RuleOutcome.NOT_APPLICABLE.value
    # Draft is conditional, not blocked
    assert eval_res["approval_status"] == "conditional_draft_review_required"


def test_full_footprint_fails_where_center_only_placement_would_pass(base_master_json):
    """G02: Center point is inside boundary (x=1.0, y=10.0), but canopy radius (2.0m) crosses boundary (x=-1.0).

    Center-only check would pass, but full footprint must fail!
    """
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}

    # Plant with center at x=1.0, r=2.0 -> left edge at x=-1.0 (outside boundary [0, 40])
    candidate = {
        "vegetation_nodes": [{"json_id": "edge_tree_1", "position": [1.0, 10.0], "canopy_radius_m": 2.0}],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    eval_res = evaluate_rules(candidate, context, base_master_json, reqs)
    r_map = {r["rule_id"]: r for r in eval_res["rule_evaluations"]}

    assert r_map["G02"]["outcome"] == RuleOutcome.FAIL.value
    assert "edge_tree_1" in r_map["G02"]["affected_object_ids"]
    assert "extends across property boundaries" in r_map["G02"]["evidence"]
    assert eval_res["approval_status"] == "blocked"


def test_surface_and_permeability_metrics_remain_separate(base_master_json):
    """G12: Planted soil, permeable paving, impermeable paving, and canopy projection are distinct."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    candidate = {"vegetation_nodes": [], "outdoor_elements": [], "outdoor_lighting": {"nodes": []}, "access": {}}

    eval_res = evaluate_rules(candidate, context, base_master_json, reqs)
    r_map = {r["rule_id"]: r for r in eval_res["rule_evaluations"]}
    assert r_map["G12"]["outcome"] == RuleOutcome.PASS.value
    assert "tracked as independent metrics" in r_map["G12"]["evidence"]


def test_no_roof_geometry_means_no_invented_roof_planting(base_master_json):
    """R03: Attempting to place rooftop planting without verified flat roof polygon in Master JSON fails."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}

    # Candidate attempting rooftop planting without upstream roof geometry
    candidate = {
        "vegetation_nodes": [{
            "json_id": "roof_pot_1",
            "position": [15.0, 15.0],
            "canopy_radius_m": 0.5,
            "supporting_surface_type": "rooftop",
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    eval_res = evaluate_rules(candidate, context, base_master_json, reqs)
    r_map = {r["rule_id"]: r for r in eval_res["rule_evaluations"]}

    assert r_map["R03"]["outcome"] == RuleOutcome.FAIL.value
    assert "accessible_flat_roof_polygon" in r_map["R03"]["missing_inputs"]
    assert "House footprint does not prove flat accessible roof exists" in r_map["R03"]["evidence"]


def test_balcony_geometry_without_approval_remains_conditional_review(base_master_json):
    """B01 & B04: Balcony planting on verified balcony without structural certificate gives review_required,

    preserving viewable draft without falsely claiming structural approval.
    """
    master_with_balcony = deepcopy(base_master_json)
    master_with_balcony["building_exterior"] = {
        "balconies": [{
            "json_id": "balcony_f2_1",
            "floor_id": "F2",
            "elevation_m": 3.2,
            "polygon": [[10, 8], [15, 8], [15, 10], [10, 10]],
        }]
    }

    context = parse_exterior_context(master_with_balcony, default_units="m")
    reqs = {"design_style": "modern"}

    candidate = {
        "vegetation_nodes": [{
            "json_id": "balcony_pot_1",
            "position": [12.0, 9.0],
            "canopy_radius_m": 0.4,
            "supporting_surface_type": "balcony",
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    eval_res = evaluate_rules(candidate, context, master_with_balcony, reqs)
    r_map = {r["rule_id"]: r for r in eval_res["rule_evaluations"]}

    # B01 passes because supporting surface geometry exists
    assert r_map["B01"]["outcome"] == RuleOutcome.PASS.value
    # B02 and B04 require review because structural engineer certificate is absent
    assert r_map["B02"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert r_map["B04"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    # Draft is conditional review, not hard blocked!
    assert eval_res["approval_status"] == "conditional_draft_review_required"


def test_advisory_rooftop_edge_conflict_is_not_mislabeled_statutory_violation():
    """R04: NParks 3-5m advisory guidance is categorized as advisory overseas engineering, not statutory violation."""
    r_r04 = get_rule("R04")
    assert r_r04 is not None
    assert r_r04.rule_class == RuleClass.ENGINEERING
    assert r_r04.verification_status.value == "advisory_overseas"
    assert "advisory" in r_r04.description.lower()
    assert r_r04.enforcement_consequence.value == "flag_review"


def test_maintained_hedge_size_distinct_from_natural_maximum_height():
    """Verify Murraya paniculata maintained height (3.0m) is distinguished from natural maximum height (8.0m)."""
    cat = vegetation_catalog()
    murraya = next((e for e in cat["entries"] if e["vegetation_id"] == "murraya_paniculata"), None)
    assert murraya is not None
    assert murraya.get("maintained_height_m") == 3.0
    assert murraya.get("mature_height_m") == 8.0
    assert "maintained around 2.5–3.5m" in murraya.get("notes", "")


def test_client_assessment_spoofing_does_not_create_a_pass(base_master_json):
    """validate_candidate_exterior recalculates derived assessments and disregards client-supplied flags."""
    spoofed_candidate = {
        "version": "1.0",
        "vegetation_nodes": [
            # Invalid plant: outside land boundary
            {"json_id": "spoofed_tree", "position": [100.0, 100.0], "canopy_radius_m": 2.0}
        ],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
        # Spoofed client summary asserting 100% satisfaction
        "validation_summary": {
            "valid": True,
            "violations": [],
            "checks_passed": 999,
            "checks_total": 999,
            "constraint_satisfaction_rate": 1.0,
        },
        "factors_assessment": {
            "summary": {"satisfied": 7, "unmet": 0, "unknown": 0},
            "status": "satisfied",
        },
        "approval_status": "approved",
    }

    res = validate_candidate_exterior(base_master_json, spoofed_candidate)

    # Server must catch the out-of-boundary violation and reject the client spoof
    assert res["valid"] is False
    assert any("outside_land" in v or "G02" in v for v in res["violations"])
    assert res["canonical_candidate"]["validation_summary"]["valid"] is False
    assert res["approval_status"] == "blocked"


def test_same_applicable_checks_run_across_baseline_and_manual_validation(base_master_json):
    """A08: Baseline generation and manual candidate validation evaluate the same Versioned Rule Registry."""
    reqs = {
        "design_style": "modern",
        "access": {"road_side": "south", "driveway_required": False, "garage_required": False},
        "landscape": {"garden_required": True},
    }

    # 1. Baseline generation
    generated_layout, outcome = run_elia(base_master_json, reqs, "test-symmetric-run")
    assert outcome == "valid"
    assert "rule_evaluations" in generated_layout
    assert "rule_summary" in generated_layout
    assert len(generated_layout["rule_evaluations"]) >= 40

    # 2. Manual candidate validation of the exact generated layout
    val_res = validate_candidate_exterior(base_master_json, generated_layout, reqs)
    assert val_res["valid"] is True
    assert "rule_evaluations" in val_res
    assert len(val_res["rule_evaluations"]) == len(generated_layout["rule_evaluations"])

    # Rule IDs evaluated match identically
    gen_ids = [r["rule_id"] for r in generated_layout["rule_evaluations"]]
    val_ids = [r["rule_id"] for r in val_res["rule_evaluations"]]
    assert gen_ids == val_ids


def test_monetary_functionality_is_never_reintroduced(base_master_json):
    """Verify that no financial keys, cost catalogs, or monetary assessments exist in any ELIA output."""
    reqs = {
        "design_style": "greeny",
        "budget_limit_lkr": 750000,  # obsolete attempt
        "budget_preference": "strict",
    }
    output, _ = run_elia(base_master_json, reqs, "test-no-fin-run")

    # Check root output
    for fin_keyword in ("budget", "price", "cost", "quotation", "lkr", "subtotal"):
        assert not any(fin_keyword in k.lower() for k in output.keys())

    # Check factors assessment
    factors = output.get("factors_assessment", {}).get("factors", [])
    assert not any("budget" in f.get("factor", "").lower() for f in factors)
    assert not any("cost" in f.get("factor", "").lower() for f in factors)

    # Check validated candidate
    val = validate_candidate_exterior(base_master_json, output, reqs)
    canon = val["canonical_candidate"]
    for fin_keyword in ("budget", "price", "cost", "quotation", "lkr", "subtotal"):
        assert not any(fin_keyword in k.lower() for k in canon.keys())


# =========================================================================
# Part 8: Regression Tests for A, B, C, D, E, F
# =========================================================================

def test_elevated_assessments_lifecycle(base_master_json):
    """A: No elevated objects -> not_applicable. Missing guard -> unknown. Prohibited placement -> fail."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}

    # 1. No elevated objects -> B05, B06, B07, B08, B10 are not_applicable
    ground_candidate = {
        "vegetation_nodes": [{"json_id": "tree_1", "position": [5, 5], "canopy_radius_m": 1.0}],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res1 = evaluate_rules(ground_candidate, context, base_master_json, reqs)
    r_map1 = {r["rule_id"]: r for r in res1["rule_evaluations"]}
    for bid in ("B05", "B06", "B07", "B08", "B10"):
        assert r_map1[bid]["applicability"] == "not_applicable"
        assert r_map1[bid]["outcome"] == RuleOutcome.NOT_APPLICABLE.value

    # 2. Elevated planter with missing slab/guardrail geometry in Master JSON -> B05 is UNKNOWN
    elev_candidate = {
        "vegetation_nodes": [{
            "json_id": "balc_pot_1",
            "position": [12, 10],
            "canopy_radius_m": 0.4,
            "supporting_surface_type": "balcony",
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res2 = evaluate_rules(elev_candidate, context, base_master_json, reqs)
    r_map2 = {r["rule_id"]: r for r in res2["rule_evaluations"]}
    assert r_map2["B05"]["outcome"] == RuleOutcome.UNKNOWN.value
    assert "balcony_slab_polygon" in r_map2["B05"]["missing_inputs"]

    # 3. Balcony in Master JSON, but planter placed with prohibited mounting on railing top -> FAIL
    master_with_balcony = deepcopy(base_master_json)
    master_with_balcony["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_f2",
            "elevation_m": 3.0,
            "polygon": [[10, 8], [15, 8], [15, 10], [10, 10]],
            "guardrail": [[10, 8], [15, 8]],
        }]
    }
    context_b = parse_exterior_context(master_with_balcony, default_units="m")
    prohibited_candidate = {
        "vegetation_nodes": [{
            "json_id": "balc_pot_bad",
            "position": [12, 8],
            "canopy_radius_m": 0.3,
            "supporting_surface_type": "balcony",
            "mounting_type": "railing_top",
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res3 = evaluate_rules(prohibited_candidate, context_b, master_with_balcony, reqs)
    r_map3 = {r["rule_id"]: r for r in res3["rule_evaluations"]}
    assert r_map3["B05"]["outcome"] == RuleOutcome.FAIL.value
    assert "balc_pot_bad" in r_map3["B05"]["affected_object_ids"]


def test_wall_assessment_applicability_and_evidence(base_master_json):
    """B: No wall -> not_applicable. Unverified limit -> review_required (never auto-pass <=2.0m). Verified limit -> pass/fail."""
    context = parse_exterior_context(base_master_json, default_units="m")

    # 1. No wall requested or in candidate -> not_applicable
    reqs_no_wall = {"design_style": "modern", "landscape": {}}
    cand_no_wall = {"vegetation_nodes": [], "outdoor_elements": [], "outdoor_lighting": {"nodes": []}, "access": {}}
    res1 = evaluate_rules(cand_no_wall, context, base_master_json, reqs_no_wall)
    r_map1 = {r["rule_id"]: r for r in res1["rule_evaluations"]}
    assert r_map1["X07"]["applicability"] == "not_applicable"
    assert r_map1["X07"]["outcome"] == RuleOutcome.NOT_APPLICABLE.value

    # 2. Wall requested with height 1.8m, but NO verified local jurisdiction threshold -> review_required
    reqs_wall = {"design_style": "modern", "landscape": {"boundary_wall_required": True, "boundary_wall_height_m": 1.8}}
    res2 = evaluate_rules(cand_no_wall, context, base_master_json, reqs_wall)
    r_map2 = {r["rule_id"]: r for r in res2["rule_evaluations"]}
    assert r_map2["X07"]["applicability"] == "applicable"
    assert r_map2["X07"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "local_authority_by_law" in r_map2["X07"]["missing_inputs"]
    assert "unverified advisory guideline" in r_map2["X07"]["evidence"]

    # 3. Verified local authority limit in Master JSON (e.g. 2.0m limit)
    master_with_limit = deepcopy(base_master_json)
    master_with_limit["jurisdiction"] = {"wall_height_limit_m": 2.0}
    # Wall height 1.8m <= 2.0m -> PASS
    res3 = evaluate_rules(cand_no_wall, context, master_with_limit, reqs_wall)
    r_map3 = {r["rule_id"]: r for r in res3["rule_evaluations"]}
    assert r_map3["X07"]["outcome"] == RuleOutcome.PASS.value

    # Wall height 2.4m > 2.0m -> FAIL
    reqs_high_wall = {"design_style": "modern", "landscape": {"boundary_wall_required": True, "boundary_wall_height_m": 2.4}}
    res4 = evaluate_rules(cand_no_wall, context, master_with_limit, reqs_high_wall)
    r_map4 = {r["rule_id"]: r for r in res4["rule_evaluations"]}
    assert r_map4["X07"]["outcome"] == RuleOutcome.FAIL.value


def test_status_aggregation_rules(base_master_json):
    """C: Not_applicable not counted as pass, unresolved checks prevent compliant status, blocking failure blocks."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    cand = {"vegetation_nodes": [], "outdoor_elements": [], "outdoor_lighting": {"nodes": []}, "access": {}}

    res = evaluate_rules(cand, context, base_master_json, reqs)
    # Check that not_applicable count is distinct and not added to pass
    for cat_name, summary in res["category_summaries"].items():
        assert summary["total"] == summary["pass"] + summary["fail"] + summary["unknown"] + summary["review_required"] + summary["not_applicable"]

    # When jurisdiction is missing (A03 unknown), approval status cannot be fully "compliant"
    assert res["approval_status"] == "conditional_draft_review_required"


def test_mandatory_requirements_structured_evaluation(base_master_json):
    """D: C04 detects missing active mandatory requirements without substring search, and distinguishes optional omissions."""
    context = parse_exterior_context(base_master_json, default_units="m")

    # 1. No mandatory requirements -> not_applicable
    reqs_empty = {"design_style": "modern", "access": {"garage_required": False, "driveway_required": False}}
    cand_empty = {"vegetation_nodes": [], "outdoor_elements": [], "outdoor_lighting": {"nodes": []}, "access": {}}
    res1 = evaluate_rules(cand_empty, context, base_master_json, reqs_empty)
    r_map1 = {r["rule_id"]: r for r in res1["rule_evaluations"]}
    assert r_map1["C04"]["applicability"] == "not_applicable"
    assert r_map1["C04"]["outcome"] == RuleOutcome.NOT_APPLICABLE.value

    # 2. Garage mandatory (garage_required=True), but missing from candidate -> FAIL (stable ID 'req_garage_missing')
    reqs_garage = {"design_style": "modern", "access": {"garage_required": True, "garage_capacity": 1}}
    res2 = evaluate_rules(cand_empty, context, base_master_json, reqs_garage)
    r_map2 = {r["rule_id"]: r for r in res2["rule_evaluations"]}
    assert r_map2["C04"]["outcome"] == RuleOutcome.FAIL.value
    assert "req_garage_missing" in r_map2["C04"]["affected_object_ids"]

    # 3. Excluded plant mandatory negative requirement
    reqs_avoid = {"design_style": "modern", "landscape": {"plant_ids_to_avoid": ["poison_ivy_1"]}}
    cand_with_poison = {
        "vegetation_nodes": [{"json_id": "p1", "plant_id": "poison_ivy_1", "position": [5, 5], "canopy_radius_m": 1.0}],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res3 = evaluate_rules(cand_with_poison, context, base_master_json, reqs_avoid)
    r_map3 = {r["rule_id"]: r for r in res3["rule_evaluations"]}
    assert r_map3["C04"]["outcome"] == RuleOutcome.FAIL.value
    assert any("req_excluded_plants_present" in aff for aff in r_map3["C04"]["affected_object_ids"])


def test_lock_preservation_real_comparison(base_master_json):
    """E: Unchanged locked object passes; moved/deleted/replaced locked object fails; duplicate IDs rejected."""
    context = parse_exterior_context(base_master_json, default_units="m")
    locked_tree = {
        "json_id": "tree_lock_1",
        "plant_id": "ixora_sri_lanka",
        "position": [10.0, 5.0],
        "canopy_radius_m": 1.5,
        "locked": True,
    }
    reqs_locked = {
        "design_style": "modern",
        "locked_features": [locked_tree],
    }

    # 1. Unchanged locked object in candidate -> PASS
    cand_pass = {
        "vegetation_nodes": [deepcopy(locked_tree)],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res1 = evaluate_rules(cand_pass, context, base_master_json, reqs_locked)
    r_map1 = {r["rule_id"]: r for r in res1["rule_evaluations"]}
    assert r_map1["C08"]["outcome"] == RuleOutcome.PASS.value
    assert "preserved with identical IDs, positions" in r_map1["C08"]["evidence"]

    # 2. Moved locked object (x=10.0 -> x=10.5) -> FAIL
    cand_moved = deepcopy(cand_pass)
    cand_moved["vegetation_nodes"][0]["position"] = [10.5, 5.0]
    res2 = evaluate_rules(cand_moved, context, base_master_json, reqs_locked)
    r_map2 = {r["rule_id"]: r for r in res2["rule_evaluations"]}
    assert r_map2["C08"]["outcome"] == RuleOutcome.FAIL.value
    assert any("locked_position_changed" in aff for aff in r_map2["C08"]["affected_object_ids"])

    # 3. Deleted locked object -> FAIL
    cand_deleted = {"vegetation_nodes": [], "outdoor_elements": [], "outdoor_lighting": {"nodes": []}, "access": {}}
    res3 = evaluate_rules(cand_deleted, context, base_master_json, reqs_locked)
    r_map3 = {r["rule_id"]: r for r in res3["rule_evaluations"]}
    assert r_map3["C08"]["outcome"] == RuleOutcome.FAIL.value
    assert any("locked_object_deleted" in aff for aff in r_map3["C08"]["affected_object_ids"])

    # 4. Duplicate object IDs in candidate -> FAIL
    cand_dup = {
        "vegetation_nodes": [deepcopy(locked_tree), deepcopy(locked_tree)],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res4 = evaluate_rules(cand_dup, context, base_master_json, reqs_locked)
    r_map4 = {r["rule_id"]: r for r in res4["rule_evaluations"]}
    assert r_map4["C08"]["outcome"] == RuleOutcome.FAIL.value
    assert "Duplicate object IDs" in r_map4["C08"]["evidence"]


def test_generation_and_persistence_symmetry(base_master_json):
    """F: Model output normalization runs common rule evaluation; preview is non-mutating; invalid output preserved."""
    from app.components.elia_engine.model_adapter import validate_model_output

    reqs = {
        "design_style": "modern",
        "access": {"road_side": "south", "driveway_required": False, "garage_required": False},
        "landscape": {"garden_required": True},
    }

    # Synthesize valid model output dictionary
    model_output = {
        "schema_version": "1.0",
        "version": "1.0",
        "run_id": "model-run-123",
        "generation_mode": "trained_model",
        "coordinate_reference": "local Cartesian coordinates in meters; north is clockwise from local +Y toward +X",
        "access": {"gate": None, "garage": None, "driveway": None},
        "vegetation_nodes": [
            {"json_id": "m_tree_1", "position": [5.0, 5.0], "canopy_radius_m": 1.0, "category": "small_tree", "units": "m"}
        ],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "vertical_greenery": {"triggered": False, "elements": []},
    }

    validated_result, outcome = validate_model_output(model_output, base_master_json, reqs)
    # Check that model output received full 54-rule evaluations
    assert "rule_evaluations" in validated_result
    assert "rule_summary" in validated_result
    assert "approval_status" in validated_result
    assert len(validated_result["rule_evaluations"]) >= 40

    # Ensure upstream Master JSON remains unmutated
    assert base_master_json["revision"] == 2
    assert "exterior_landscape" not in base_master_json

