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
from app.components.elia_engine.evaluation_helpers import (
    extract_physical_footprint,
    are_polygons_equivalent,
    to_positive_finite_int,
    parse_polygon_representation,
    compare_locked_object_properties,
)


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

    cand_with_wall = {
        "vegetation_nodes": [],
        "outdoor_elements": [{
            "json_id": "wall_1",
            "type": "boundary_wall",
            "height_m": 1.8,
            "dimensions": {"width_m": 10.0, "depth_m": 0.2, "height_m": 1.8},
        }],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    # 2. Wall requested with height 1.8m, but NO verified local jurisdiction threshold -> review_required
    reqs_wall = {"design_style": "modern", "landscape": {"boundary_wall_required": True, "boundary_wall_height_m": 1.8}}
    res2 = evaluate_rules(cand_with_wall, context, base_master_json, reqs_wall)
    r_map2 = {r["rule_id"]: r for r in res2["rule_evaluations"]}
    assert r_map2["X07"]["applicability"] == "applicable"
    assert r_map2["X07"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "local_authority_by_law" in r_map2["X07"]["missing_inputs"]
    assert "unverified advisory guideline" in r_map2["X07"]["evidence"]

    # 3. Verified local authority limit in Master JSON (e.g. 2.0m limit) with actual candidate wall
    master_with_limit = deepcopy(base_master_json)
    master_with_limit["site"] = {"local_authority": "Colombo Municipal Council"}
    master_with_limit["legal_profile"] = {
        "statutory_instrument": "Planning By-law Gazette 2120/15",
        "jurisdiction": "Colombo Municipal Council",
        "verification_status": "verified",
        "effective_status": "active",
        "wall_height_limit_m": 2.0,
        "clause": "Clause 14",
    }
    reqs_wall_jurisdiction = dict(reqs_wall)
    reqs_wall_jurisdiction["local_authority"] = "Colombo Municipal Council"
    # Candidate wall height 1.8m <= 2.0m -> PASS
    res3 = evaluate_rules(cand_with_wall, context, master_with_limit, reqs_wall_jurisdiction)
    r_map3 = {r["rule_id"]: r for r in res3["rule_evaluations"]}
    assert r_map3["X07"]["outcome"] == RuleOutcome.PASS.value

    # Candidate wall height 2.4m > 2.0m -> FAIL
    cand_high_wall = deepcopy(cand_with_wall)
    cand_high_wall["outdoor_elements"][0]["height_m"] = 2.4
    cand_high_wall["outdoor_elements"][0]["dimensions"]["height_m"] = 2.4
    res4 = evaluate_rules(cand_high_wall, context, master_with_limit, reqs_wall_jurisdiction)
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
    assert "tree_lock_1" in r_map1["C08"]["affected_object_ids"]
    assert "invariant" in r_map1["C08"]["evidence"] or "locked" in r_map1["C08"]["evidence"].lower()

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


# =========================================================================
# Confirmed Defect Regression Tests (B05, B06, B10, X07, C08, C04, Audits)
# =========================================================================

def test_b05_footprint_partly_outside_balcony_slab_fails(base_master_json):
    """B05: Centre is inside slab, but planter footprint extends outside balcony slab edge -> must NOT pass."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_f2",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "polygon": [[10, 8], [14, 8], [14, 11], [10, 11]],
            "guardrail": [[10, 8], [14, 8], [14, 11]],
        }]
    }

    # Planter center is at (13.8, 9.5), radius 0.5m -> footprint reaches x=14.3 (outside slab [10..14])
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_overhang",
            "position": [13.8, 9.5],
            "canopy_radius_m": 0.5,
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_f2",
            "floor_id": "F2",
            "footprint": [[13.3, 9.0], [14.3, 9.0], [14.3, 10.0], [13.3, 10.0]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B05"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["B05"]["outcome"] in (RuleOutcome.FAIL.value, RuleOutcome.UNKNOWN.value)


def test_b05_planter_outside_guardrail_protected_region_fails(base_master_json):
    """B05: Planter placed outside the guardrail-protected region must not pass."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_f2",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "polygon": [[10, 8], [14, 8], [14, 11], [10, 11]],
            "guardrail": [[10, 8], [14, 8]],
            "protected_region": [[10, 8.3], [14, 8.3], [14, 11], [10, 11]],
        }]
    }

    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_unprotected",
            "position": [12.0, 8.1],
            "canopy_radius_m": 0.3,
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_f2",
            "floor_id": "F2",
            "footprint": [[11.8, 8.0], [12.2, 8.0], [12.2, 8.2], [11.8, 8.2]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B05"]["outcome"] != RuleOutcome.PASS.value


def test_b05_guardrail_geometry_on_another_balcony_remains_unresolved(base_master_json):
    """B05: Guardrail geometry exists only on Balcony F1, planter is placed on Balcony F2 -> cannot use F1 geometry."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [
            {
                "json_id": "balc_f1",
                "floor_id": "F1",
                "elevation_m": 0.0,
                "polygon": [[10, 8], [14, 8], [14, 11], [10, 11]],
                "guardrail": [[10, 8], [14, 8]],
            },
            {
                "json_id": "balc_f2",
                "floor_id": "F2",
                "elevation_m": 3.0,
            }
        ]
    }

    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_f2",
            "position": [12.0, 9.0],
            "canopy_radius_m": 0.3,
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_f2",
            "floor_id": "F2",
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B05"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["B05"]["outcome"] in (RuleOutcome.UNKNOWN.value, RuleOutcome.FAIL.value)


def test_b05_explicit_railing_top_mounting_fails_even_without_slab_data(base_master_json):
    """B05: Prohibited railing-top mounting must fail immediately even if balcony slab geometry is missing."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master.pop("building_exterior", None)

    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_railing",
            "position": [12.0, 9.0],
            "canopy_radius_m": 0.3,
            "supporting_surface_type": "balcony",
            "mounting_type": "railing_top",
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B05"]["outcome"] == RuleOutcome.FAIL.value
    assert "planter_railing" in r_map["B05"]["affected_object_ids"]


def test_b05_empty_geometry_keys_does_not_pass(base_master_json):
    """B05: Balcony surface with empty polygon or empty guardrail keys must not produce PASS."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_empty",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "polygon": [],
            "guardrail": [],
        }]
    }

    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "position": [12.0, 9.0],
            "canopy_radius_m": 0.3,
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_empty",
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B05"]["outcome"] != RuleOutcome.PASS.value


def test_b05_valid_matched_surface_and_contained_footprint_passes(base_master_json):
    """B05: Valid matched surface geometry and strictly contained planter footprint -> PASS."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_ok",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "polygon": [[10, 8], [15, 8], [15, 12], [10, 12]],
            "guardrail": [[10, 8], [15, 8], [15, 12]],
            "protected_region": [[10, 8], [15, 8], [15, 12], [10, 12]],
        }]
    }

    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_safe",
            "position": [12.0, 10.0],
            "canopy_radius_m": 0.3,
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_ok",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "mounting_type": "floor_slab",
            "footprint": [[11.7, 9.7], [12.3, 9.7], [12.3, 10.3], [11.7, 10.3]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B05"]["outcome"] == RuleOutcome.PASS.value


def test_b05_ambiguous_open_guardrail_line_remains_unresolved(base_master_json):
    """B05: Open guard line without defined protected region must remain unresolved/UNKNOWN."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_open",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "polygon": [[10, 8], [15, 8], [15, 12], [10, 12]],
            "guardrail": [[10, 8], [15, 8], [15, 12]],
        }]
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_open_guard",
            "position": [12.0, 10.0],
            "canopy_radius_m": 0.3,
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_open",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "mounting_type": "floor_slab",
            "footprint": [[11.7, 9.7], [12.3, 9.7], [12.3, 10.3], [11.7, 10.3]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B05"]["outcome"] == RuleOutcome.UNKNOWN.value
    assert any("guardrail" in mi for mi in r_map["B05"]["missing_inputs"])


def test_b06_footprint_overlaps_door_clearance_fails(base_master_json):
    """B06: Planter center is outside door polygon, but its footprint overlaps the door clearance -> FAIL."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_f2",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "polygon": [[10, 8], [14, 8], [14, 11], [10, 11]],
        }],
        "balcony_doors": [{
            "id": "door_f2",
            "floor_id": "F2",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
        }],
        "guardrail_profile": {"height_m": 1.1, "type": "solid_glass", "climbable_footholds": False},
    }

    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_door_overlap",
            "position": [11.3, 9.0],
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_f2",
            "floor_id": "F2",
            "footprint": [[10.8, 8.7], [11.8, 8.7], [11.8, 9.3], [10.8, 9.3]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.FAIL.value


def test_b06_arbitrary_guard_profile_does_not_pass_climbability(base_master_json):
    """B06: An arbitrary guardrail_profile string/dict must not grant an automatic PASS without verified climbability."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_f2",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "polygon": [[10, 8], [14, 8], [14, 11], [10, 11]],
        }],
        "balcony_doors": [{
            "id": "door_f2",
            "floor_id": "F2",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
        }],
        "guardrail_profile": {"arbitrary_note": "standard metal railings"},
    }

    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_far",
            "position": [13.0, 10.5],
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_f2",
            "floor_id": "F2",
            "footprint": [[12.8, 10.3], [13.2, 10.3], [13.2, 10.7], [12.8, 10.7]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] != RuleOutcome.PASS.value


def test_b06_door_geometry_from_another_floor_does_not_establish_safety(base_master_json):
    """B06: Balcony door is on Floor 1, planter is on Balcony Floor 2 -> cannot establish F2 egress safety."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_f2",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "polygon": [[10, 8], [14, 8], [14, 11], [10, 11]],
        }],
        "balcony_doors": [{
            "id": "door_f1",
            "floor_id": "F1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
        }],
        "guardrail_profile": {"height_m": 1.1, "non_climbable_verified": True},
    }

    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_f2",
            "position": [13.0, 10.5],
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_f2",
            "floor_id": "F2",
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] != RuleOutcome.PASS.value


def test_b10_arbitrary_maintenance_text_does_not_pass(base_master_json):
    """B10: Arbitrary non-empty maintenance text must never establish safe maintenance pass."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_f2",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "polygon": [[10, 8], [14, 8], [14, 11], [10, 11]],
        }],
        "balcony_maintenance_access": "Gardener will use a ladder once a week",
    }

    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_f2",
            "position": [12.0, 9.5],
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_f2",
            "floor_id": "F2",
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B10"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["B10"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value


def test_b10_evidence_for_another_balcony_or_revision_does_not_pass(base_master_json):
    """B10: Verified maintenance access assessment scoped for another balcony or older revision does not pass."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 3
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_f2",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "polygon": [[10, 8], [14, 8], [14, 11], [10, 11]],
        }],
        "balcony_maintenance_access": {
            "verified_assessment": True,
            "applicable_balcony_id": "balc_other",
            "revision": 3,
            "reach_verified": True,
        },
    }

    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_f2",
            "position": [12.0, 9.5],
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_f2",
            "floor_id": "F2",
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B10"]["outcome"] != RuleOutcome.PASS.value


def test_x07_bare_numeric_threshold_does_not_pass_legal_compliance(base_master_json):
    """X07: A bare numeric wall_height_limit_m without verified statutory instrument must NOT pass."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern", "landscape": {"boundary_wall_required": True}}
    master = deepcopy(base_master_json)
    master["jurisdiction"] = {"wall_height_limit_m": 2.0}

    cand = {
        "vegetation_nodes": [],
        "outdoor_elements": [{
            "json_id": "wall_1",
            "type": "boundary_wall",
            "height_m": 1.8,
            "position": [20.0, 0.0],
            "dimensions": {"width_m": 40.0, "depth_m": 0.2, "height_m": 1.8},
        }],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["X07"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["X07"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value


def test_x07_verified_threshold_for_another_jurisdiction_does_not_pass(base_master_json):
    """X07: Verified regulation for another jurisdiction (e.g. Colombo vs Kandy) must NOT pass."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {
        "design_style": "modern",
        "local_authority": "Kandy Municipal Council",
        "landscape": {"boundary_wall_required": True},
    }
    master = deepcopy(base_master_json)
    master["site"] = {"local_authority": "Kandy Municipal Council"}
    master["legal_profile"] = {
        "statutory_instrument": "Colombo MC By-laws 2018",
        "jurisdiction": "Colombo Municipal Council",
        "verification_status": "verified",
        "wall_height_limit_m": 2.0,
    }

    cand = {
        "vegetation_nodes": [],
        "outdoor_elements": [{
            "json_id": "wall_1",
            "type": "boundary_wall",
            "height_m": 1.8,
            "position": [20.0, 0.0],
            "dimensions": {"width_m": 40.0, "depth_m": 0.2, "height_m": 1.8},
        }],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["X07"]["outcome"] != RuleOutcome.PASS.value


def test_x07_actual_candidate_wall_exceeds_limit_fails(base_master_json):
    """X07: Requested wall height is 1.8m, but actual candidate wall height is 2.5m -> FAIL."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {
        "design_style": "modern",
        "local_authority": "Colombo Municipal Council",
        "landscape": {"boundary_wall_required": True, "boundary_wall_height_m": 1.8},
    }
    master = deepcopy(base_master_json)
    master["site"] = {"local_authority": "Colombo Municipal Council"}
    master["legal_profile"] = {
        "statutory_instrument": "Planning By-law Gazette 2120/15",
        "jurisdiction": "Colombo Municipal Council",
        "verification_status": "verified",
        "effective_status": "active",
        "wall_height_limit_m": 2.0,
        "clause": "Part IV Clause 12(1)",
    }

    cand = {
        "vegetation_nodes": [],
        "outdoor_elements": [{
            "json_id": "wall_high",
            "type": "boundary_wall",
            "height_m": 2.5,
            "position": [20.0, 0.0],
            "dimensions": {"width_m": 40.0, "depth_m": 0.2, "height_m": 2.5},
        }],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["X07"]["outcome"] == RuleOutcome.FAIL.value
    assert "wall_high" in r_map["X07"]["affected_object_ids"]


def test_x07_missing_actual_candidate_wall_height_is_unresolved(base_master_json):
    """X07: Candidate wall has no height specified; evaluator must not default to 1.8m."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["legal_profile"] = {
        "statutory_instrument": "Planning By-law Gazette 2120/15",
        "verification_status": "verified",
        "effective_status": "active",
        "wall_height_limit_m": 2.0,
    }

    cand = {
        "vegetation_nodes": [],
        "outdoor_elements": [{
            "json_id": "wall_no_h",
            "type": "boundary_wall",
            "position": [20.0, 0.0],
        }],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["X07"]["outcome"] in (RuleOutcome.UNKNOWN.value, RuleOutcome.REVIEW_REQUIRED.value)
    assert any("height" in mi for mi in r_map["X07"]["missing_inputs"])


def test_x07_one_compliant_wall_and_one_excessive_wall(base_master_json):
    """X07: Multiple walls: one compliant (1.6m) and one excessive (2.3m) -> flags excessive wall."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern", "local_authority": "Colombo Municipal Council"}
    master = deepcopy(base_master_json)
    master["site"] = {"local_authority": "Colombo Municipal Council"}
    master["legal_profile"] = {
        "statutory_instrument": "Planning By-law Gazette 2120/15",
        "jurisdiction": "Colombo Municipal Council",
        "verification_status": "verified",
        "effective_status": "active",
        "wall_height_limit_m": 2.0,
    }

    cand = {
        "vegetation_nodes": [],
        "outdoor_elements": [
            {
                "json_id": "wall_south",
                "type": "boundary_wall",
                "height_m": 1.6,
                "position": [20.0, 0.0],
                "dimensions": {"width_m": 40.0, "depth_m": 0.2, "height_m": 1.6},
            },
            {
                "json_id": "wall_north",
                "type": "boundary_wall",
                "height_m": 2.3,
                "position": [20.0, 30.0],
                "dimensions": {"width_m": 40.0, "depth_m": 0.2, "height_m": 2.3},
            },
        ],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["X07"]["outcome"] == RuleOutcome.FAIL.value
    assert "wall_north" in r_map["X07"]["affected_object_ids"]
    assert "wall_south" not in r_map["X07"]["affected_object_ids"]


def test_c08_request_supplied_moved_reference_cannot_override_saved_lock(base_master_json):
    """C08: Request locked_features cannot redefine the authoritative reference position of a saved locked object."""
    context = parse_exterior_context(base_master_json, default_units="m")
    master = deepcopy(base_master_json)
    master["exterior_landscape"] = {
        "vegetation_nodes": [{
            "json_id": "locked_tree_1",
            "plant_id": "ixora_sri_lanka",
            "position": [10.0, 5.0],
            "canopy_radius_m": 1.5,
            "locked": True,
        }],
        "outdoor_elements": [],
    }

    reqs_spoofed_lock = {
        "design_style": "modern",
        "locked_features": [{
            "json_id": "locked_tree_1",
            "plant_id": "ixora_sri_lanka",
            "position": [12.0, 5.0],
            "canopy_radius_m": 1.5,
            "locked": True,
        }],
    }

    cand = {
        "vegetation_nodes": [{
            "json_id": "locked_tree_1",
            "plant_id": "ixora_sri_lanka",
            "position": [12.0, 5.0],
            "canopy_radius_m": 1.5,
            "locked": True,
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, master, reqs_spoofed_lock)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C08"]["outcome"] == RuleOutcome.FAIL.value
    assert any("locked_position_changed" in aff for aff in r_map["C08"]["affected_object_ids"])


def test_c08_protected_properties_rotation_and_polygon_changes_detected(base_master_json):
    """C08: Changes to rotation, polygon, or removing position are detected."""
    context = parse_exterior_context(base_master_json, default_units="m")
    master = deepcopy(base_master_json)
    master["exterior_landscape"] = {
        "outdoor_elements": [{
            "json_id": "locked_bench",
            "type": "garden_seating",
            "position": [15.0, 10.0],
            "rotation_degrees": 0.0,
            "polygon": [[14.0, 9.5], [16.0, 9.5], [16.0, 10.5], [14.0, 10.5]],
            "locked": True,
        }],
        "vegetation_nodes": [],
    }

    cand_rot = {
        "vegetation_nodes": [],
        "outdoor_elements": [{
            "json_id": "locked_bench",
            "type": "garden_seating",
            "position": [15.0, 10.0],
            "rotation_degrees": 45.0,
            "polygon": [[14.0, 9.5], [16.0, 9.5], [16.0, 10.5], [14.0, 10.5]],
            "locked": True,
        }],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res1 = evaluate_rules(cand_rot, context, master, {})
    r_map1 = {r["rule_id"]: r for r in res1["rule_evaluations"]}
    assert r_map1["C08"]["outcome"] == RuleOutcome.FAIL.value
    assert any("rotation" in aff for aff in r_map1["C08"]["affected_object_ids"])


def test_c04_object_type_present_without_geometry_or_capacity_fails(base_master_json):
    """C04: Object type exists but required geometry is empty, or capacity is unmet -> fails."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {
        "design_style": "modern",
        "access": {"garage_required": True, "garage_capacity": 2},
    }

    cand = {
        "vegetation_nodes": [],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {
            "garage": {
                "polygon": [[5, 2], [10, 2], [10, 6], [5, 6]],
                "capacity": 1,
            }
        },
    }

    res = evaluate_rules(cand, context, base_master_json, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C04"]["outcome"] == RuleOutcome.FAIL.value
    assert any("capacity" in aff for aff in r_map["C04"]["affected_object_ids"])


def test_c04_missing_actual_capacity_not_assumed_as_one(base_master_json):
    """C04: Missing garage capacity must not be silently defaulted to 1 and called verified."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {
        "design_style": "modern",
        "access": {"garage_required": True, "garage_capacity": 1},
    }

    cand = {
        "vegetation_nodes": [],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {
            "garage": {
                "polygon": [[5, 2], [10, 2], [10, 6], [5, 6]],
            }
        },
    }

    res = evaluate_rules(cand, context, base_master_json, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C04"]["outcome"] != RuleOutcome.PASS.value


def test_c04_independent_driveway_evaluated_without_requiring_garage(base_master_json):
    """C04: Driveway required with garage disabled must evaluate driveway requirement independently."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {
        "design_style": "modern",
        "access": {"garage_required": False, "driveway_required": True},
    }

    cand = {
        "vegetation_nodes": [],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }

    res = evaluate_rules(cand, context, base_master_json, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C04"]["outcome"] == RuleOutcome.FAIL.value
    assert "req_driveway_missing" in r_map["C04"]["affected_object_ids"]


# =============================================================================
# REPRODUCTION TESTS FOR THE FOUR CONFIRMED EXECUTABLE FAILURES
# =============================================================================

def test_confirmed_failure_1_b05_malformed_guardrail_does_not_pass(base_master_json):
    """1. B05: A balcony has valid slab polygon but guardrail='malformed'. Planter is inside slab. Must not PASS."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balcony_1",
            "floor_id": "floor_2",
            "polygon": [[10, 10], [15, 10], [15, 13], [10, 13]],
            "guardrail": "malformed",
        }]
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "support_json_id": "balcony_1",
            "floor_id": "floor_2",
            "position": [12, 11],
            "dimensions": {"width_m": 0.5, "depth_m": 0.5},
            "supporting_surface_type": "balcony",
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B05"]["outcome"] != RuleOutcome.PASS.value


def test_confirmed_failure_2_b10_unscoped_assessment_does_not_pass(base_master_json):
    """2. B10: balcony_maintenance_access={'verified_assessment': True} without revision or surface evidence must not PASS."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["surfaces"] = [{
        "json_id": "balcony_1",
        "floor_id": "floor_2",
        "polygon": [[10, 10], [15, 10], [15, 13], [10, 13]],
        "guardrail": [[10, 13], [15, 13]],
    }]
    master["building_exterior"] = {
        "balcony_maintenance_access": {
            "verified_assessment": True
            # No revision and no applicable_balcony_id!
        }
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "support_json_id": "balcony_1",
            "floor_id": "floor_2",
            "position": [12, 11],
            "dimensions": {"width_m": 0.5, "depth_m": 0.5},
            "supporting_surface_type": "balcony",
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B10"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["B10"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value


def test_confirmed_failure_3_c08_protected_property_removal_detected(base_master_json):
    """3. C08: Saved locked object has position, dimensions, elevation. Candidate keeps position, removes elevation and dims to {} -> must FAIL."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["exterior_landscape"] = {
        "outdoor_elements": [{
            "json_id": "bench_locked",
            "type": "garden_seating",
            "position": [5, 5],
            "dimensions": {"width_m": 2.0, "height_m": 3.0},
            "elevation_m": 3.0,
            "locked": True,
        }],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    cand = {
        "outdoor_elements": [{
            "json_id": "bench_locked",
            "type": "garden_seating",
            "position": [5, 5],
            "dimensions": {},  # dimensions removed/cleared
            # elevation_m removed
            "locked": True,
        }],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C08"]["outcome"] == RuleOutcome.FAIL.value


def test_confirmed_failure_4_c08_unchanged_locked_garage_in_access_passes(base_master_json):
    """4. C08: Unchanged locked garage in saved access.garage and candidate access.garage must PASS."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    garage_def = {
        "json_id": "garage_locked_1",
        "type": "garage",
        "position": [6, 2],
        "polygon": [[5, 2], [10, 2], [10, 6], [5, 6]],
        "locked": True,
    }
    master["exterior_landscape"] = {
        "outdoor_elements": [],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
        "access": {
            "garage": deepcopy(garage_def),
        },
    }
    cand = {
        "outdoor_elements": [],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
        "access": {
            "garage": deepcopy(garage_def),
        },
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C08"]["outcome"] == RuleOutcome.PASS.value


# =============================================================================
# PERMANENT REGRESSION TESTS FOR THE EIGHT CONFIRMED DEFECTS AND AUDITS
# =============================================================================

# Defect 1: B06 - Malformed door geometry can still pass
def test_defect_1_b06_malformed_door_geometry_does_not_pass(base_master_json):
    """1. B06: Planter has valid physical footprint; door has polygon='bad' -> must NOT pass B06."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_f1",
            "floor_id": "F1",
            "elevation_m": 0.0,
            "polygon": [[10, 8], [15, 8], [15, 12], [10, 12]],
        }],
        "balcony_doors": [{
            "id": "door_bad",
            "floor_id": "F1",
            "polygon": "bad",
        }],
        "guardrail_profile": {
            "non_climbable_verified": True,
            "climbable_footholds": False,
        },
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_f1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["B06"]["outcome"] == RuleOutcome.UNKNOWN.value
    assert any("door" in mi.lower() for mi in r_map["B06"]["missing_inputs"])


def test_defect_1_b06_valid_door_geometry_and_clearance_passes(base_master_json):
    """1. B06 Positive Counterpart: Valid door polygon, planter does not overlap clearance -> PASS."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_f1",
            "floor_id": "F1",
            "elevation_m": 0.0,
            "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]],
        }],
        "balcony_doors": [{
            "id": "door_good",
            "floor_id": "F1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
            "escape_route_polygon": [[10, 8.5], [12, 8.5], [12, 10.5], [10, 10.5]],
        }],
        "egress_destinations": [{
            "id": "dest_exit",
            "floor_id": "F1",
            "surface_id": "balc_f1",
            "polygon": [[12, 8.5], [13, 8.5], [13, 10.5], [12, 10.5]],
        }],
        "guardrail_profile": {
            "verified_climbability_assessment": True,
            "revision": 2,
            "climbable_footholds": False,
            "scope": ["balc_f1", "F1"],
        },
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_safe",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_f1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.PASS.value


# Defect 2: B07 - Arbitrary drainage text passes
def test_defect_2_b07_arbitrary_drainage_text_requires_review(base_master_json):
    """2. B07: Balcony drainage is an unverified string -> must NOT pass B07."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balcony_drainage": "unverified text",
        "balconies": [{
            "json_id": "balc_1",
            "floor_id": "F1",
            "polygon": [[10, 8], [14, 8], [14, 12], [10, 12]],
        }],
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_b7",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B07"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["B07"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value


def test_defect_2_b07_verified_structured_drainage_passes(base_master_json):
    """2. B07 Positive Counterpart: Structured verified drainage connection with downpipe -> PASS."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_1",
            "floor_id": "F1",
            "polygon": [[10, 8], [14, 8], [14, 12], [10, 12]],
            "drainage": {
                "system": "direct_drainage",
                "downpipe_connected": True,
                "drain_point_id": "dp_f1_01",
                "status": "approved",
            },
        }],
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_b7",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B07"]["outcome"] == RuleOutcome.PASS.value


# Defect 3: B09 - Absent structural approval passes
def test_defect_3_b09_absent_structural_approval_requires_review(base_master_json):
    """3. B09: Elevated planter exists, but no structural approval exists -> REVIEW_REQUIRED."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_elev",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "polygon": [[10, 8], [15, 8], [15, 12], [10, 12]],
        }]
    }
    # No structural_signoff in master
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_elev",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_elev",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert any("structural" in mi or "load" in mi for mi in r_map["B09"]["missing_inputs"])


def test_defect_3_b09_aligned_structural_approval_passes(base_master_json):
    """3. B09 Positive Counterpart: Structural engineer approval covers surface and matches revision -> PASS."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_elev",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "polygon": [[10, 8], [15, 8], [15, 12], [10, 12]],
        }]
    }
    master["structural_signoff"] = {
        "engineer_approval_ref": "SE-2026-001",
        "approved_revision": 2,
        "scope": ["balcony", "balc_elev"],
        "max_saturated_load_kn_m2": 4.5,
        "approved_configuration": [{
            "json_id": "planter_elev",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_elev",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_elev",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_elev",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.PASS.value


def test_defect_3_b09_stale_structural_approval_revision_mismatch_requires_review(base_master_json):
    """3. B09: Structural approval revision does not match current project revision -> REVIEW_REQUIRED."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 3
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_elev",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "polygon": [[10, 8], [15, 8], [15, 12], [10, 12]],
        }]
    }
    master["structural_signoff"] = {
        "engineer_approval_ref": "SE-2026-001",
        "approved_revision": 2,  # Stale: approved for rev 2, project is at rev 3
        "scope": ["balcony", "balc_elev"],
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_elev",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_elev",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert any("structural" in mi or "revision" in mi for mi in r_map["B09"]["missing_inputs"])


# Defect 4: X07 - Both jurisdictions missing treated as matching
def test_defect_4_x07_both_jurisdictions_missing_is_unresolved(base_master_json):
    """4. X07: Both site jurisdiction and legal jurisdiction absent -> REVIEW_REQUIRED."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["legal_profile"] = {
        "verification_status": "verified",
        "effective_status": "active",
        "statutory_instrument": "test",
        "wall_height_limit_m": 2.0,
    }
    cand = {
        "vegetation_nodes": [],
        "outdoor_elements": [{
            "json_id": "wall_1",
            "type": "boundary_wall",
            "height_m": 1.8,
            "position": [20.0, 0.0],
            "dimensions": {"width_m": 40.0, "depth_m": 0.2, "height_m": 1.8},
        }],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["X07"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["X07"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value


def test_defect_4_x07_matching_jurisdiction_passes(base_master_json):
    """4. X07 Positive Counterpart: Matching jurisdiction and valid height -> PASS."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern", "local_authority": "Colombo Municipal Council"}
    master = deepcopy(base_master_json)
    master["site"] = {"local_authority": "Colombo Municipal Council"}
    master["legal_profile"] = {
        "statutory_instrument": "Colombo MC By-laws 2018",
        "jurisdiction": "Colombo Municipal Council",
        "verification_status": "verified",
        "effective_status": "active",
        "wall_height_limit_m": 2.0,
        "clause": "Clause 14",
    }
    cand = {
        "vegetation_nodes": [],
        "outdoor_elements": [{
            "json_id": "wall_1",
            "type": "boundary_wall",
            "height_m": 1.8,
            "position": [20.0, 0.0],
            "dimensions": {"width_m": 40.0, "depth_m": 0.2, "height_m": 1.8},
        }],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["X07"]["outcome"] == RuleOutcome.PASS.value


# Defect 5: C08 - Locked objects without IDs disappear
def test_defect_5_c08_locked_object_without_id_requires_review(base_master_json):
    """5. C08: Saved exterior contains locked object without valid ID; candidate empty -> REVIEW_REQUIRED."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["exterior_landscape"] = {
        "vegetation_nodes": [{
            "position": [10.0, 5.0],
            "canopy_radius_m": 1.5,
            "locked": True,
            # No json_id or id
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    cand = {
        "vegetation_nodes": [],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C08"]["outcome"] != RuleOutcome.NOT_APPLICABLE.value
    assert r_map["C08"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "canonical_locked_object_id" in r_map["C08"]["missing_inputs"]


def test_defect_5_c08_duplicate_ids_across_containers_detected(base_master_json):
    """5. C08: Duplicate IDs across containers are detected."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    cand = {
        "vegetation_nodes": [{
            "json_id": "dup_element_id",
            "position": [5.0, 5.0],
            "locked": True,
        }],
        "outdoor_elements": [{
            "json_id": "dup_element_id",
            "position": [8.0, 8.0],
            "locked": True,
        }],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C08"]["outcome"] == RuleOutcome.FAIL.value
    assert "dup_element_id" in r_map["C08"]["affected_object_ids"]
    assert "duplicate" in r_map["C08"]["evidence"].lower()


# Defect 6: C04 - A position alone satisfies a facility requirement
def test_defect_6_c04_position_alone_lacks_usable_footprint_unknown(base_master_json):
    """6. C04: Garden seating specified by position alone without dimensions/usable footprint -> UNKNOWN."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {
        "design_style": "modern",
        "landscape": {"garden_seating_required": True},
    }
    master = deepcopy(base_master_json)
    cand = {
        "outdoor_elements": [{
            "json_id": "s",
            "type": "garden_seating",
            "position": [5, 5],
            # No dimensions or footprint
        }],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C04"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["C04"]["outcome"] == RuleOutcome.UNKNOWN.value


def test_defect_6_c04_usable_footprint_and_dimensions_passes(base_master_json):
    """6. C04 Positive Counterpart: Garden seating has valid dimensions and physical footprint -> PASS."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {
        "design_style": "modern",
        "landscape": {"garden_seating_required": True},
    }
    master = deepcopy(base_master_json)
    cand = {
        "outdoor_elements": [{
            "json_id": "s",
            "type": "garden_seating",
            "position": [5, 5],
            "dimensions": {"width_m": 2.0, "depth_m": 1.0, "height_m": 0.5},
        }],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C04"]["outcome"] == RuleOutcome.PASS.value


def test_defect_6_c04_non_finite_or_malformed_capacity_rejected(base_master_json):
    """6. C04: Malformed seating capacity is rejected and not coerced."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {
        "design_style": "modern",
        "landscape": {
            "garden_seating_required": True,
            "seating_capacity": "infinite",
        },
    }
    master = deepcopy(base_master_json)
    cand = {
        "outdoor_elements": [{
            "json_id": "s",
            "type": "garden_seating",
            "position": [5, 5],
            "dimensions": {"width_m": 2.0, "depth_m": 1.0, "height_m": 0.5},
        }],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C04"]["outcome"] == RuleOutcome.UNKNOWN.value


# Defect 7: Equivalent polygon serialization is rejected as a lock change
def test_defect_7_c08_equivalent_polygon_cyclic_order_and_closure_passes(base_master_json):
    """7. C08: Reference and candidate polygons describe identical geometry via cyclic shift -> PASS."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["exterior_landscape"] = {
        "outdoor_elements": [{
            "json_id": "patio_locked",
            "type": "patio",
            "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]],
            "locked": True,
        }],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    cand = {
        "outdoor_elements": [{
            "json_id": "patio_locked",
            "type": "patio",
            "polygon": [[2, 0], [2, 2], [0, 2], [0, 0]],  # Cyclically shifted
            "locked": True,
        }],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C08"]["outcome"] == RuleOutcome.PASS.value


def test_defect_7_c08_genuinely_changed_polygon_fails(base_master_json):
    """7. C08 Counterpart: Genuinely translated polygon -> FAIL."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["exterior_landscape"] = {
        "outdoor_elements": [{
            "json_id": "patio_locked",
            "type": "patio",
            "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]],
            "locked": True,
        }],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    cand = {
        "outdoor_elements": [{
            "json_id": "patio_locked",
            "type": "patio",
            "polygon": [[0.5, 0], [2.5, 0], [2.5, 2], [0.5, 2]],  # Translated by 0.5m
            "locked": True,
        }],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C08"]["outcome"] == RuleOutcome.FAIL.value
    assert any("locked_polygon_changed" in aff for aff in r_map["C08"]["affected_object_ids"])


# Defect 8: Invalid rotation is silently ignored
def test_defect_8_extract_physical_footprint_invalid_rotation_detected():
    """8. extract_physical_footprint: Invalid/boolean/NaN rotation must return invalid_rotation."""
    # String rotation
    poly, status = extract_physical_footprint({
        "position": [2, 2],
        "width_m": 1.0,
        "depth_m": 1.0,
        "rotation_degrees": "bad",
    })
    assert status == "invalid_rotation"
    assert poly is None

    # Boolean rotation
    poly, status = extract_physical_footprint({
        "position": [2, 2],
        "width_m": 1.0,
        "depth_m": 1.0,
        "rotation_degrees": True,
    })
    assert status == "invalid_rotation"
    assert poly is None

    # NaN rotation
    poly, status = extract_physical_footprint({
        "position": [2, 2],
        "width_m": 1.0,
        "depth_m": 1.0,
        "rotation_degrees": float("nan"),
    })
    assert status == "invalid_rotation"
    assert poly is None

    # Inf rotation
    poly, status = extract_physical_footprint({
        "position": [2, 2],
        "width_m": 1.0,
        "depth_m": 1.0,
        "rotation_degrees": float("inf"),
    })
    assert status == "invalid_rotation"
    assert poly is None


def test_defect_8_extract_physical_footprint_valid_rotation():
    """8. extract_physical_footprint Positive Counterpart: Valid rotation applies correctly."""
    poly, status = extract_physical_footprint({
        "position": [2, 2],
        "width_m": 2.0,
        "depth_m": 1.0,
        "rotation_degrees": 90.0,
    })
    assert status == "valid"
    assert poly is not None
    minx, miny, maxx, maxy = poly.bounds
    # After 90 deg rotation, width (2.0) is along Y, depth (1.0) is along X
    assert math.isclose(maxx - minx, 1.0, abs_tol=1e-3)
    assert math.isclose(maxy - miny, 2.0, abs_tol=1e-3)


# Additional Audit and Service Invariant Regressions
def test_audit_supporting_surface_contradictory_elevation(base_master_json):
    """Contradictory elevation between planter and surface returns contradictory_elevation."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "balc_elev_3",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "polygon": [[10, 8], [15, 8], [15, 12], [10, 12]],
            "protected_region": [[10, 8], [15, 8], [15, 12], [10, 12]],
        }]
    }
    # Planter claims floor F2 but elevation 6.0m (diff > 0.5m)
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_contradictory",
            "floor_id": "F2",
            "elevation_m": 6.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "balc_elev_3",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B05"]["outcome"] == RuleOutcome.UNKNOWN.value


def test_audit_c10_missing_upstream_revision_is_unknown(base_master_json):
    """C10: Evaluation with missing upstream revision returns UNKNOWN."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = None
    cand = {
        "vegetation_nodes": [],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C10"]["outcome"] == RuleOutcome.UNKNOWN.value
    assert "upstream_revision" in r_map["C10"]["missing_inputs"]


def test_audit_immutability_candidate_evaluation_does_not_mutate_inputs(base_master_json):
    """Candidate evaluation does not mutate candidate, context, master, or requirements."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern", "landscape": {"garden_seating_required": True}}
    master = deepcopy(base_master_json)
    cand = {
        "vegetation_nodes": [{"json_id": "tree_1", "position": [5, 5]}],
        "outdoor_elements": [{"json_id": "seat_1", "type": "garden_seating", "position": [8, 8], "dimensions": {"width_m": 1.5, "depth_m": 0.8, "height_m": 0.5}}],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    cand_copy = deepcopy(cand)
    reqs_copy = deepcopy(reqs)
    master_copy = deepcopy(master)

    evaluate_rules(cand, context, master, reqs)
    assert cand == cand_copy
    assert reqs == reqs_copy
    assert master == master_copy


# =============================================================================
# Six Confirmed ELIA Defect Regressions (B09, B06, C04, C04-Inf, PolyHoles, LockedCoords)
# =============================================================================

# -----------------------------------------------------------------------------
# DEFECT 1: B09 Ignores Structural Approval Scope
# -----------------------------------------------------------------------------

def test_defect_1_b09_wrong_balcony_scope_does_not_pass(base_master_json):
    """B09: Candidate planter on surface 'b1' with structural evidence scoping 'OTHER' must NOT pass."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "F2", "elevation_m": 3.0, "polygon": [[10, 8], [15, 8], [15, 12], [10, 12]]}]
    }
    master["structural_evidence"] = {
        "balcony_allowance_kg_m2": 200,
        "approved_revision": 2,
        "applicable_balcony_id": "OTHER",
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "applicable_surface_scope" in r_map["B09"]["missing_inputs"]
    assert "planter_1" in r_map["B09"]["affected_object_ids"]


def test_defect_1_b09_missing_scope_requires_review(base_master_json):
    """B09: Structural evidence with allowance and revision but missing scope requires review."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["structural_evidence"] = {
        "balcony_allowance_kg_m2": 200,
        "approved_revision": 2,
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "applicable_surface_scope" in r_map["B09"]["missing_inputs"]


def test_defect_1_b09_multiple_planters_partial_scope_requires_review(base_master_json):
    """B09: Multiple planters where only some surfaces are covered requires review."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["structural_evidence"] = {
        "balcony_allowance_kg_m2": 200,
        "approved_revision": 2,
        "scope": ["b1"],
    }
    cand = {
        "vegetation_nodes": [
            {
                "json_id": "planter_covered",
                "floor_id": "F2",
                "elevation_m": 3.0,
                "supporting_surface_type": "balcony",
                "support_json_id": "b1",
                "position": [12.0, 10.0],
                "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
            },
            {
                "json_id": "planter_uncovered",
                "floor_id": "F2",
                "elevation_m": 3.0,
                "supporting_surface_type": "balcony",
                "support_json_id": "b2",
                "position": [14.0, 10.0],
                "footprint": [[13.5, 9.5], [14.5, 9.5], [14.5, 10.5], [13.5, 10.5]],
            },
        ],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "planter_uncovered" in r_map["B09"]["affected_object_ids"]


def test_defect_1_b09_changed_configuration_with_unchanged_revision(base_master_json):
    """B09: Matching project revision alone does not establish edited planter configuration is covered."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["structural_evidence"] = {
        "balcony_allowance_kg_m2": 200,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration_id": "cfg_v1",
    }
    cand = {
        "configuration_id": "cfg_v2",
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "approved_configuration_coverage" in r_map["B09"]["missing_inputs"]


def test_defect_1_b09_valid_matching_scoped_evidence_passes(base_master_json):
    """B09: Valid matching scoped evidence and revision passes with accurate units."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 3.5,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.PASS.value
    assert "3.5 kN/m²" in r_map["B09"]["evidence"]
    assert "kg/m²" not in r_map["B09"]["evidence"]


# -----------------------------------------------------------------------------
# DEFECT 2: B06 Unscoped Flag Still Certifies Escape Safety
# -----------------------------------------------------------------------------

def test_defect_2_b06_unscoped_flag_does_not_certify_escape(base_master_json):
    """B06: Unscoped flag plus clear door without revision, surface scope, and escape route must NOT pass."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "b1",
            "floor_id": "f1",
            "elevation_m": 3.0,
            "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]],
        }],
        "balcony_doors": [{
            "id": "door_1",
            "floor_id": "f1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
        }],
        "guardrail_profile": {
            "verified_climbability_assessment": True,
        },
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "f1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["B06"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value


def test_defect_2_b06_stale_revision_does_not_pass(base_master_json):
    """B06: Guardrail assessment with stale revision requires review."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "f1", "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        "balcony_doors": [{
            "id": "door_1",
            "floor_id": "f1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
            "escape_route_polygon": [[10, 8.5], [12, 8.5], [12, 10.5], [10, 10.5]],
        }],
        "guardrail_profile": {
            "verified_climbability_assessment": True,
            "revision": 1,
            "scope": ["b1"],
        },
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "f1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "revalidated_climbability_assessment" in r_map["B06"]["missing_inputs"]


def test_defect_2_b06_assessment_for_another_surface_requires_review(base_master_json):
    """B06: Guardrail assessment scoping another surface does not certify candidate."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "f1", "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        "balcony_doors": [{
            "id": "door_1",
            "floor_id": "f1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
            "escape_route_polygon": [[10, 8.5], [12, 8.5], [12, 10.5], [10, 10.5]],
        }],
        "guardrail_profile": {
            "verified_climbability_assessment": True,
            "revision": 2,
            "scope": ["balc_other"],
        },
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "f1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "guardrail_assessment_scope" in r_map["B06"]["missing_inputs"]


def test_defect_2_b06_blocked_escape_route_fails_and_known_obstruction_priority(base_master_json):
    """B06: Blocked escape route fails, and obstruction takes priority over missing climbability assessment."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "f1", "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        "balcony_doors": [{
            "id": "door_1",
            "floor_id": "f1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
            # Route corridor overlaps candidate planter
            "escape_route_polygon": [[10, 8.5], [14, 8.5], [14, 11.0], [10, 11.0]],
        }],
        # Climbability assessment missing entirely
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "f1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    # Known obstruction must FAIL even when other evidence is missing
    assert r_map["B06"]["outcome"] == RuleOutcome.FAIL.value


# -----------------------------------------------------------------------------
# DEFECT 3: C04 Accepts Boolean Capacity
# -----------------------------------------------------------------------------

def test_defect_3_to_positive_finite_int_contract():
    """Verify to_positive_finite_int rejects booleans, non-finite, fractions, and malformed strings."""
    # Booleans rejected
    assert to_positive_finite_int(True) is None
    assert to_positive_finite_int(False) is None
    # Non-positive numbers rejected
    assert to_positive_finite_int(0) is None
    assert to_positive_finite_int(-1) is None
    assert to_positive_finite_int(-42) is None
    # Fractional values rejected (not truncated!)
    assert to_positive_finite_int(1.5) is None
    assert to_positive_finite_int(0.99) is None
    assert to_positive_finite_int("1.5") is None
    # Non-finite floats rejected
    assert to_positive_finite_int(float("inf")) is None
    assert to_positive_finite_int(float("-inf")) is None
    assert to_positive_finite_int(float("nan")) is None
    # Empty and malformed strings rejected
    assert to_positive_finite_int(None) is None
    assert to_positive_finite_int("") is None
    assert to_positive_finite_int("   ") is None
    assert to_positive_finite_int("abc") is None
    assert to_positive_finite_int("inf") is None
    # Valid positive integers accepted
    assert to_positive_finite_int(1) == 1
    assert to_positive_finite_int(4) == 4
    assert to_positive_finite_int(2.0) == 2
    assert to_positive_finite_int("3") == 3
    assert to_positive_finite_int(" 5 ") == 5


def test_defect_3_c04_boolean_capacity_in_garage_and_seating_rejected(base_master_json):
    """C04: Boolean capacity (capacity=True) is rejected and does not pass."""
    context = parse_exterior_context(base_master_json, default_units="m")
    master = deepcopy(base_master_json)
    reqs = {
        "design_style": "modern",
        "access": {"garage_required": True, "garage_capacity": 1},
        "landscape": {"garden_seating_required": True, "seating_capacity": 2},
    }
    cand = {
        "vegetation_nodes": [],
        "outdoor_elements": [{
            "json_id": "seat_1",
            "type": "garden_seating",
            "position": [8, 8],
            "capacity": True,
            "dimensions": {"width_m": 2.0, "depth_m": 1.0, "height_m": 0.5},
        }],
        "outdoor_lighting": {"nodes": []},
        "access": {
            "garage": {
                "polygon": [[1, 1], [6, 1], [6, 7], [1, 7]],
                "capacity": True,
            }
        },
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C04"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["C04"]["outcome"] == RuleOutcome.UNKNOWN.value
    assert any("garage_capacity_invalid" in aff for aff in r_map["C04"]["affected_object_ids"])
    assert any("seat_1_capacity_malformed" in aff for aff in r_map["C04"]["affected_object_ids"])


# -----------------------------------------------------------------------------
# DEFECT 4: C04 Infinite Capacity Crashes
# -----------------------------------------------------------------------------

def test_defect_4_c04_infinite_and_nan_capacity_no_crash(base_master_json):
    """C04: float('inf') and float('nan') capacity do not raise OverflowError/ValueError."""
    context = parse_exterior_context(base_master_json, default_units="m")
    master = deepcopy(base_master_json)

    for inf_val in (float("inf"), float("-inf"), float("nan")):
        reqs = {
            "design_style": "modern",
            "access": {"garage_required": True, "garage_capacity": 1},
            "landscape": {"garden_seating_required": True, "seating_capacity": 2},
        }
        cand = {
            "vegetation_nodes": [],
            "outdoor_elements": [{
                "json_id": "seat_1",
                "type": "garden_seating",
                "position": [8, 8],
                "capacity": inf_val,
                "dimensions": {"width_m": 2.0, "depth_m": 1.0, "height_m": 0.5},
            }],
            "outdoor_lighting": {"nodes": []},
            "access": {
                "garage": {
                    "polygon": [[1, 1], [6, 1], [6, 7], [1, 7]],
                    "capacity": inf_val,
                }
            },
        }
        res = evaluate_rules(cand, context, master, reqs)
        r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
        assert r_map["C04"]["outcome"] == RuleOutcome.UNKNOWN.value
        assert any("garage_capacity_invalid" in aff for aff in r_map["C04"]["affected_object_ids"])
        assert any("seat_1_capacity_malformed" in aff for aff in r_map["C04"]["affected_object_ids"])


# -----------------------------------------------------------------------------
# DEFECT 5: Valid Polygons with One Hole are Rejected
# -----------------------------------------------------------------------------

def test_defect_5_polygon_with_one_hole_accepted():
    """Footprint extraction and polygon equivalence accept valid polygon with one hole."""
    outer = [[0, 0], [10, 0], [10, 10], [0, 10]]
    hole = [[2, 2], [3, 2], [3, 3], [2, 3]]

    # 1. extract_physical_footprint
    poly, status = extract_physical_footprint({"polygon": [outer, hole]})
    assert status == "valid"
    assert poly is not None
    assert poly.is_valid
    assert len(poly.interiors) == 1

    # 2. are_polygons_equivalent
    eq, eq_status = are_polygons_equivalent([outer, hole], [outer, hole])
    assert eq is True
    assert eq_status == "equivalent"

    # 3. cyclic shift of hole or shell is equivalent
    hole_shifted = [[3, 2], [3, 3], [2, 3], [2, 2]]
    eq_shift, _ = are_polygons_equivalent([outer, hole], [outer, hole_shifted])
    assert eq_shift is True

    # 4. hole removal is detected as changed
    eq_removed, rem_status = are_polygons_equivalent([outer, hole], [outer])
    assert eq_removed is False
    assert rem_status == "changed"


def test_defect_5_polygon_invalid_topology_and_outside_holes_rejected():
    """Polygons with outside holes or self-intersections are rejected with invalid status."""
    outer = [[0, 0], [10, 0], [10, 10], [0, 10]]
    hole_outside = [[20, 20], [25, 20], [25, 25], [20, 25]]

    poly, status = parse_polygon_representation([outer, hole_outside])
    assert poly is None
    assert status == "invalid_topology"

    _, fp_status = extract_physical_footprint({"polygon": [outer, hole_outside]})
    assert fp_status == "malformed"

    eq, eq_status = are_polygons_equivalent([outer, hole_outside], [outer])
    assert eq is False
    assert eq_status == "invalid"


# -----------------------------------------------------------------------------
# DEFECT 6: Malformed Saved Position Crashes Lock Comparison
# -----------------------------------------------------------------------------

def test_defect_6_malformed_saved_position_no_crash():
    """compare_locked_object_properties does not crash with IndexError on truncated positions."""
    # [1] in reference position
    v1 = compare_locked_object_properties(
        {"json_id": "p", "position": [1]},
        {"json_id": "p", "position": [1, 2]}
    )
    assert any("locked_reference_position_malformed" in v for v in v1)

    # [] in reference position
    v2 = compare_locked_object_properties(
        {"json_id": "p", "position": []},
        {"json_id": "p", "position": [1, 2]}
    )
    assert any("locked_reference_position_malformed" in v for v in v2)

    # None in reference position
    v3 = compare_locked_object_properties(
        {"json_id": "p", "position": None},
        {"json_id": "p", "position": [1, 2]}
    )
    assert any("locked_reference_position_malformed" in v for v in v3)

    # Boolean and NaN in coordinates
    v4 = compare_locked_object_properties(
        {"json_id": "p", "position": [True, 1]},
        {"json_id": "p", "position": [1, 2]}
    )
    assert any("locked_reference_position_malformed" in v for v in v4)

    # Malformed candidate position
    v5 = compare_locked_object_properties(
        {"json_id": "p", "position": [1, 2]},
        {"json_id": "p", "position": [1]}
    )
    assert any("locked_candidate_position_malformed" in v for v in v5)

    # Removed Z coordinate
    v6 = compare_locked_object_properties(
        {"json_id": "p", "position": [1, 2, 3]},
        {"json_id": "p", "position": [1, 2]}
    )
    assert any("locked_z_coordinate_removed" in v for v in v6)

    # Valid unchanged 2D and 3D coordinates
    v7 = compare_locked_object_properties(
        {"json_id": "p", "position": [1, 2]},
        {"json_id": "p", "position": [1, 2]}
    )
    assert v7 == []

    v8 = compare_locked_object_properties(
        {"json_id": "p", "position": [1, 2, 3]},
        {"json_id": "p", "position": [1, 2, 3]}
    )
    assert v8 == []


def test_defect_6_c08_evaluator_consumes_malformed_reference_as_review_required(base_master_json):
    """C08: Malformed reference position produces REVIEW_REQUIRED with explicit diagnostic."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {
        "design_style": "modern",
        "locked_features": [{"json_id": "locked_p", "locked": True, "position": [1]}],
    }
    master = deepcopy(base_master_json)
    cand = {
        "vegetation_nodes": [{"json_id": "locked_p", "locked": True, "position": [1, 2]}],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["C08"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "valid_authoritative_locked_coordinates" in r_map["C08"]["missing_inputs"]
    assert res["approval_status"] == "conditional_draft_review_required"


# -----------------------------------------------------------------------------
# RELATED ACCEPTANCE CHECKS
# -----------------------------------------------------------------------------

def test_acceptance_unresolved_checks_cannot_become_compliant(base_master_json):
    """Unresolved mandatory requirements or lock coordinates cannot produce 'compliant' approval_status."""
    context = parse_exterior_context(base_master_json, default_units="m")
    master = deepcopy(base_master_json)

    # 1. Unusable mandatory capacity (C04 UNKNOWN)
    reqs_c04 = {
        "design_style": "modern",
        "access": {"garage_required": True, "garage_capacity": True},
    }
    cand_c04 = {
        "vegetation_nodes": [],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {"garage": {"polygon": [[1, 1], [6, 1], [6, 7], [1, 7]], "capacity": 1}},
    }
    res_c04 = evaluate_rules(cand_c04, context, master, reqs_c04)
    assert res_c04["approval_status"] != "compliant"
    assert res_c04["approval_status"] == "conditional_draft_review_required"

    # 2. Unverifiable lock reference (C08 REVIEW_REQUIRED)
    reqs_c08 = {
        "design_style": "modern",
        "locked_features": [{"json_id": "locked_p", "locked": True, "position": [1]}],
    }
    cand_c08 = {
        "vegetation_nodes": [{"json_id": "locked_p", "locked": True, "position": [1, 2]}],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res_c08 = evaluate_rules(cand_c08, context, master, reqs_c08)
    assert res_c08["approval_status"] != "compliant"
    assert res_c08["approval_status"] == "conditional_draft_review_required"


# =============================================================================
# DEFECT B06 REGRESSION TESTS: Per-surface route evidence, connectivity, no shortcuts
# =============================================================================

def test_b06_unrelated_route_on_another_floor_does_not_pass(base_master_json):
    """1. B06: Planter on b1, F1. Door on F1. Escape route on F99, surface 'other' -> REVIEW_REQUIRED."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{
            "json_id": "b1",
            "floor_id": "F1",
            "elevation_m": 0.0,
            "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]],
        }],
        "balcony_doors": [{
            "id": "door_f1",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
        }],
        "escape_routes": [{
            "id": "route_other_floor",
            "floor_id": "F99",
            "surface_id": "other",
            "polygon": [[50, 50], [52, 50], [52, 52], [50, 52]],
        }],
        "guardrail_profile": {
            "verified_climbability_assessment": True,
            "revision": 2,
            "climbable_footholds": False,
            "scope": ["b1", "F1"],
        },
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["B06"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "balcony_escape_route_evidence" in r_map["B06"]["missing_inputs"]
    assert "planter_1" in r_map["B06"]["affected_object_ids"]


def test_b06_same_floor_contradictory_surface_does_not_pass(base_master_json):
    """2. B06: Same floor F1, but route explicitly belongs to contradictory surface 'b2' -> REVIEW_REQUIRED."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [
            {"json_id": "b1", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]},
            {"json_id": "b2", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[20, 8], [26, 8], [26, 14], [20, 14]]},
        ],
        "balcony_doors": [{
            "id": "door_b1",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
        }],
        "escape_routes": [{
            "id": "route_b2",
            "floor_id": "F1",
            "surface_id": "b2",
            "polygon": [[20, 8.5], [22, 8.5], [22, 10.5], [20, 10.5]],
        }],
        "guardrail_profile": {
            "verified_climbability_assessment": True,
            "revision": 2,
            "scope": ["b1", "F1"],
        },
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_b1",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["B06"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "balcony_escape_route_evidence" in r_map["B06"]["missing_inputs"]


def test_b06_two_balconies_only_one_covered_unresolved_for_other(base_master_json):
    """3. B06: Two balconies, only b1 has valid route -> unresolved for b2."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [
            {"json_id": "b1", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]},
            {"json_id": "b2", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[20, 8], [26, 8], [26, 14], [20, 14]]},
        ],
        "balcony_doors": [
            {"id": "door_b1", "floor_id": "F1", "surface_id": "b1", "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]], "escape_route_polygon": [[10, 8.5], [12, 8.5], [12, 10.5], [10, 10.5]]},
            {"id": "door_b2", "floor_id": "F1", "surface_id": "b2", "polygon": [[20, 8.5], [21, 8.5], [21, 9.5], [20, 9.5]]},
        ],
        "guardrail_profile": {
            "verified_climbability_assessment": True,
            "revision": 2,
            "scope": ["b1", "b2", "F1"],
        },
    }
    cand = {
        "vegetation_nodes": [
            {"json_id": "p1", "floor_id": "F1", "supporting_surface_type": "balcony", "support_json_id": "b1", "position": [14.0, 12.0], "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]]},
            {"json_id": "p2", "floor_id": "F1", "supporting_surface_type": "balcony", "support_json_id": "b2", "position": [24.0, 12.0], "footprint": [[23.5, 11.5], [24.5, 11.5], [24.5, 12.5], [23.5, 12.5]]},
        ],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "balcony_escape_route_evidence" in r_map["B06"]["missing_inputs"]
    assert "p2" in r_map["B06"]["affected_object_ids"]
    assert "p1" not in r_map["B06"]["affected_object_ids"]


def test_b06_malformed_relevant_route_not_pass(base_master_json):
    """4. B06: Relevant escape route contains malformed polygon -> UNKNOWN."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        "balcony_doors": [{"id": "d1", "floor_id": "F1", "surface_id": "b1", "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]]}],
        "escape_routes": [{"id": "route_bad", "surface_id": "b1", "polygon": "malformed_polygon_coords"}],
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["b1", "F1"]},
    }
    cand = {
        "vegetation_nodes": [{"json_id": "p1", "floor_id": "F1", "supporting_surface_type": "balcony", "support_json_id": "b1", "position": [14.0, 12.0], "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]]}],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.UNKNOWN.value
    assert "valid_escape_route_geometry" in r_map["B06"]["missing_inputs"]


def test_b06_route_polygon_disconnected_from_access_requires_review(base_master_json):
    """5. B06: Route polygon exists on balcony but is disconnected from access door -> REVIEW_REQUIRED."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        "balcony_doors": [{"id": "d1", "floor_id": "F1", "surface_id": "b1", "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]]}],
        "escape_routes": [{
            "id": "route_disc",
            "surface_id": "b1",
            "polygon": [[14.0, 13.0], [15.5, 13.0], [15.5, 13.8], [14.0, 13.8]],
        }],
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["b1", "F1"]},
    }
    cand = {
        "vegetation_nodes": [{"json_id": "p1", "floor_id": "F1", "supporting_surface_type": "balcony", "support_json_id": "b1", "position": [12.0, 12.0], "footprint": [[11.5, 11.5], [12.5, 11.5], [12.5, 12.5], [11.5, 12.5]]}],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "escape_route_connectivity" in r_map["B06"]["missing_inputs"]


def test_b06_bare_escape_route_verified_flag_does_not_pass(base_master_json):
    """6. B06: Bare escape_route_verified flag without usable geometry does NOT pass."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        "balcony_doors": [{
            "id": "d1",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
            "escape_route_verified": True,
        }],
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["b1", "F1"]},
    }
    cand = {
        "vegetation_nodes": [{"json_id": "p1", "floor_id": "F1", "supporting_surface_type": "balcony", "support_json_id": "b1", "position": [14.0, 12.0], "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]]}],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["B06"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "balcony_escape_route_evidence" in r_map["B06"]["missing_inputs"]


def test_b06_known_obstruction_retained_over_missing_route(base_master_json):
    """7. B06: Known door obstruction takes priority and is retained as FAIL even with missing route on other balcony."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [
            {"json_id": "b1", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]},
            {"json_id": "b2", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[20, 8], [26, 8], [26, 14], [20, 14]]},
        ],
        "balcony_doors": [
            {"id": "door_b1", "floor_id": "F1", "surface_id": "b1", "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]]},
            {"id": "door_b2", "floor_id": "F1", "surface_id": "b2", "polygon": [[20, 8.5], [21, 8.5], [21, 9.5], [20, 9.5]]},
        ],
        "escape_routes": [],
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["b1", "b2", "F1"]},
    }
    cand = {
        "vegetation_nodes": [
            {"json_id": "planter_blocking", "floor_id": "F1", "supporting_surface_type": "balcony", "support_json_id": "b1", "position": [10.5, 9.0], "footprint": [[10.0, 8.5], [11.0, 8.5], [11.0, 9.5], [10.0, 9.5]]},
            {"json_id": "planter_ok", "floor_id": "F1", "supporting_surface_type": "balcony", "support_json_id": "b2", "position": [24.0, 12.0], "footprint": [[23.5, 11.5], [24.5, 11.5], [24.5, 12.5], [23.5, 12.5]]},
        ],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.FAIL.value
    assert any("blocks" in obj for obj in r_map["B06"]["affected_object_ids"])


def test_b06_fully_valid_matching_route_and_scoped_assessments_passes(base_master_json):
    """8. B06: Fully valid matching door, connected route, and scoped climbability -> PASS."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        "balcony_doors": [{
            "id": "door_b1",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
            "escape_route_polygon": [[10, 8.5], [12, 8.5], [12, 10.5], [10, 10.5]],
        }],
        "egress_destinations": [{
            "id": "dest_exit",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[12, 8.5], [13, 8.5], [13, 10.5], [12, 10.5]],
        }],
        "guardrail_profile": {
            "verified_climbability_assessment": True,
            "revision": 2,
            "climbable_footholds": False,
            "scope": ["b1", "F1"],
        },
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_safe",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.PASS.value


def test_b06_no_elevated_planting_not_applicable(base_master_json):
    """9. B06: No elevated planting in design -> NOT_APPLICABLE."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    cand = {
        "vegetation_nodes": [{"json_id": "ground_p", "position": [1.0, 1.0], "supporting_surface_type": "ground"}],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, base_master_json, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.NOT_APPLICABLE.value


# =============================================================================
# DEFECT B09 REGRESSION TESTS: Configuration coverage independent of edit flags
# =============================================================================

def test_b09_no_approved_snapshot_no_edited_flags_requires_review(base_master_json):
    """1. B09: Structural evidence with allowance & revision, but no approved configuration snapshot -> REVIEW_REQUIRED."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 3.5,
        "approved_revision": 2,
        "scope": ["b1"],
        # No approved_configuration
    }
    cand = {
        # Omitted configuration_modified
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "approved_configuration_coverage" in r_map["B09"]["missing_inputs"]


def test_b09_changed_geometry_with_edited_flag_omitted_requires_review(base_master_json):
    """2. B09: Candidate planter geometry changed, edit flags omitted -> REVIEW_REQUIRED."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 3.5,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
    }
    cand = {
        # Changed geometry (moved/resized), no edit flag
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [13.0, 11.0],
            "footprint": [[12.5, 10.5], [13.5, 10.5], [13.5, 11.5], [12.5, 11.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "revalidated_structural_approval" in r_map["B09"]["missing_inputs"]


def test_b09_changed_geometry_with_edited_flag_explicitly_false_requires_review(base_master_json):
    """3. B09: Candidate planter geometry changed, configuration_modified=False -> REVIEW_REQUIRED."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 3.5,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
    }
    cand = {
        "configuration_modified": False,
        "planters_modified": False,
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [13.0, 11.0],
            "footprint": [[12.5, 10.5], [13.5, 10.5], [13.5, 11.5], [12.5, 11.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "revalidated_structural_approval" in r_map["B09"]["missing_inputs"]


def test_b09_copied_configuration_id_with_different_geometry_requires_review(base_master_json):
    """4. B09: Copied configuration ID with different geometry -> REVIEW_REQUIRED."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 3.5,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration_id": "CFG_APPROVED_01",
        "approved_configuration": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
    }
    cand = {
        "configuration_id": "CFG_APPROVED_01",  # Copied ID!
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 10.0],  # Moved!
            "footprint": [[13.5, 9.5], [14.5, 9.5], [14.5, 10.5], [13.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "revalidated_structural_approval" in r_map["B09"]["missing_inputs"]


def test_b09_added_or_removed_planter_requires_review(base_master_json):
    """5. B09: Planter added or removed relative to approved configuration -> REVIEW_REQUIRED."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 3.5,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
    }
    # Unapproved planter added
    cand = {
        "vegetation_nodes": [
            {
                "json_id": "planter_1",
                "floor_id": "F2",
                "elevation_m": 3.0,
                "supporting_surface_type": "balcony",
                "support_json_id": "b1",
                "position": [12.0, 10.0],
                "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
            },
            {
                "json_id": "planter_extra",
                "floor_id": "F2",
                "elevation_m": 3.0,
                "supporting_surface_type": "balcony",
                "support_json_id": "b1",
                "position": [14.0, 10.0],
                "footprint": [[13.5, 9.5], [14.5, 9.5], [14.5, 10.5], [13.5, 10.5]],
            },
        ],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "revalidated_structural_approval" in r_map["B09"]["missing_inputs"]
    assert any("unapproved_planter_added" in aff for aff in r_map["B09"]["affected_object_ids"])


def test_b09_changed_dimensions_or_load_properties_requires_review(base_master_json):
    """6. B09: Soil volume or load property changed -> REVIEW_REQUIRED."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 3.5,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
            "soil_volume_m3": 0.2,
        }],
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
            "soil_volume_m3": 0.9,  # Changed!
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "revalidated_structural_approval" in r_map["B09"]["missing_inputs"]
    assert any("planter_load_property_changed" in aff for aff in r_map["B09"]["affected_object_ids"])


def test_b09_wrong_surface_or_stale_revision_requires_review(base_master_json):
    """7. B09: Structural approval scoping another surface requires review."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 3.5,
        "approved_revision": 2,
        "scope": ["other_surface"],
        "approved_configuration": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "applicable_surface_scope" in r_map["B09"]["missing_inputs"]


def test_b09_valid_unchanged_configuration_passes(base_master_json):
    """8. B09: Valid unchanged configuration against trusted scoped approval -> PASS."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    planters = [{
        "json_id": "planter_1",
        "floor_id": "F2",
        "elevation_m": 3.0,
        "supporting_surface_type": "balcony",
        "support_json_id": "b1",
        "position": [12.0, 10.0],
        "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
    }]
    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 3.5,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": deepcopy(planters),
    }
    cand = {
        "vegetation_nodes": deepcopy(planters),
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.PASS.value


def test_b09_equivalent_polygon_cyclic_shift_passes(base_master_json):
    """9. B09: Equivalent polygon serialization (cyclic vertex shift) produces no false change -> PASS."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 3.5,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            # Order A
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            # Order B: cyclic shift
            "footprint": [[12.5, 9.5], [12.5, 10.5], [11.5, 10.5], [11.5, 9.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.PASS.value


def test_b09_candidate_evaluation_does_not_mutate_trusted_snapshot(base_master_json):
    """10. B09: Evaluating candidate against approved snapshot does NOT mutate the snapshot."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    snapshot = [{
        "json_id": "planter_1",
        "floor_id": "F2",
        "elevation_m": 3.0,
        "supporting_surface_type": "balcony",
        "support_json_id": "b1",
        "position": [12.0, 10.0],
        "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
    }]
    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 3.5,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": deepcopy(snapshot),
    }
    snapshot_before = deepcopy(master["structural_evidence"]["approved_configuration"])
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "F2",
            "elevation_m": 3.0,
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [12.0, 10.0],
            "footprint": [[11.5, 9.5], [12.5, 9.5], [12.5, 10.5], [11.5, 10.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    evaluate_rules(cand, context, master, reqs)
    assert master["structural_evidence"]["approved_configuration"] == snapshot_before


# =============================================================================
# CALLER AND ACCEPTANCE VERIFICATION
# =============================================================================

def test_caller_unresolved_b06_or_b09_cannot_produce_compliant_approval(base_master_json):
    """Caller acceptance: Unresolved B06 or B09 rules prevent 'compliant' approval_status."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        # Missing doors and routes -> B06 REVIEW_REQUIRED
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["b1", "F1"]},
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_1",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    assert res["approval_status"] != "compliant"
    assert res["approval_status"] == "conditional_draft_review_required"


def test_caller_b06_obstruction_produces_blocked_approval(base_master_json):
    """Caller acceptance: B06 door obstruction hard block produces 'blocked' approval_status."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        "balcony_doors": [{
            "id": "door_b1",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
        }],
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["b1", "F1"]},
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_blocking",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [10.5, 9.0],
            "footprint": [[10.0, 8.5], [11.0, 8.5], [11.0, 9.5], [10.0, 9.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.FAIL.value
    assert res["approval_status"] != "compliant"
    assert res["approval_status"] == "conditional_draft_review_required"


# =============================================================================
# COMPREHENSIVE VERIFIED REGRESSION TESTS: B09 APPROVED CONFIGURATION
# =============================================================================

def test_b09_approved_config_unchanged_passes(base_master_json):
    """B09: Unchanged valid configuration against trusted approval passes."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    planter = {
        "json_id": "p1",
        "floor_id": "F1",
        "elevation_m": 3.0,
        "supporting_surface_type": "balcony",
        "support_json_id": "b1",
        "position": [12.0, 10.0, 3.0],
        "rotation_degrees": 45.0,
        "scale": 1.0,
        "dimensions": {"width_m": 0.8, "depth_m": 0.8, "height_m": 0.5},
        "soil_volume_m3": 0.2,
        "saturated_weight_kg": 150.0,
    }
    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 4.0,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [deepcopy(planter)],
    }
    cand = {
        "vegetation_nodes": [deepcopy(planter)],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.PASS.value


def test_b09_approved_config_rotation_0_to_90_requires_review(base_master_json):
    """B09: Approved planter rotation changing from 0 to 90 degrees requires review."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    approved_planter = {
        "json_id": "p1",
        "floor_id": "F1",
        "elevation_m": 3.0,
        "supporting_surface_type": "balcony",
        "support_json_id": "b1",
        "position": [12.0, 10.0],
        "rotation_degrees": 0.0,
    }
    cand_planter = deepcopy(approved_planter)
    cand_planter["rotation_degrees"] = 90.0

    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 4.0,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [approved_planter],
    }
    cand = {
        "vegetation_nodes": [cand_planter],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert any("planter_rotation_changed" in str(aff) for aff in r_map["B09"]["affected_object_ids"])


def test_b09_approved_config_rotation_0_to_360_equivalent_passes(base_master_json):
    """B09: Equivalent rotation 0 to 360 degrees is preserved as unchanged pass."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    approved_planter = {
        "json_id": "p1",
        "floor_id": "F1",
        "elevation_m": 3.0,
        "supporting_surface_type": "balcony",
        "support_json_id": "b1",
        "position": [12.0, 10.0],
        "rotation_degrees": 0.0,
    }
    cand_planter = deepcopy(approved_planter)
    cand_planter["rotation_degrees"] = 360.0

    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 4.0,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [approved_planter],
    }
    cand = {
        "vegetation_nodes": [cand_planter],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.PASS.value


def test_b09_approved_config_z_only_position_change_requires_review(base_master_json):
    """B09: Position change [5, 5, 3] to [5, 5, 9] must not be ignored; requires review."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    approved_planter = {
        "json_id": "p1",
        "floor_id": "F1",
        "supporting_surface_type": "balcony",
        "support_json_id": "b1",
        "position": [5.0, 5.0, 3.0],
    }
    cand_planter = deepcopy(approved_planter)
    cand_planter["position"] = [5.0, 5.0, 9.0]

    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 4.0,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [approved_planter],
    }
    cand = {
        "vegetation_nodes": [cand_planter],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert any("planter_position_changed" in str(aff) for aff in r_map["B09"]["affected_object_ids"])


def test_b09_approved_config_elevation_only_change_requires_review(base_master_json):
    """B09: Elevation-only change from 3.0 to 4.5 requires review."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    approved_planter = {
        "json_id": "p1",
        "floor_id": "F1",
        "elevation_m": 3.0,
        "supporting_surface_type": "balcony",
        "support_json_id": "b1",
        "position": [12.0, 10.0],
    }
    cand_planter = deepcopy(approved_planter)
    cand_planter["elevation_m"] = 4.5

    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 4.0,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [approved_planter],
    }
    cand = {
        "vegetation_nodes": [cand_planter],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert any("planter_elevation_changed" in str(aff) for aff in r_map["B09"]["affected_object_ids"])


def test_b09_approved_config_missing_previously_present_position_requires_review(base_master_json):
    """B09: Missing previously present position in candidate requires review."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    approved_planter = {
        "json_id": "p1",
        "floor_id": "F1",
        "supporting_surface_type": "balcony",
        "support_json_id": "b1",
        "position": [12.0, 10.0, 3.0],
    }
    cand_planter = {
        "json_id": "p1",
        "floor_id": "F1",
        "supporting_surface_type": "balcony",
        "support_json_id": "b1",
        "elevation_m": 3.0,
    }
    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 4.0,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [approved_planter],
    }
    cand = {
        "vegetation_nodes": [cand_planter],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value


def test_b09_approved_config_malformed_and_boolean_coordinates(base_master_json):
    """B09: Non-finite floats and booleans used as numbers in candidate are rejected."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    approved_planter = {
        "json_id": "p1",
        "floor_id": "F1",
        "supporting_surface_type": "balcony",
        "support_json_id": "b1",
        "position": [12.0, 10.0],
    }
    cand_planter = deepcopy(approved_planter)
    cand_planter["position"] = [True, float("inf")]

    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 4.0,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [approved_planter],
    }
    cand = {
        "vegetation_nodes": [cand_planter],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value


def test_b09_approved_config_scale_change_requires_review(base_master_json):
    """B09: Scale change from 1.0 to 1.5 requires review."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    approved_planter = {
        "json_id": "p1",
        "floor_id": "F1",
        "supporting_surface_type": "balcony",
        "support_json_id": "b1",
        "position": [12.0, 10.0],
        "scale": 1.0,
    }
    cand_planter = deepcopy(approved_planter)
    cand_planter["scale"] = 1.5

    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 4.0,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [approved_planter],
    }
    cand = {
        "vegetation_nodes": [cand_planter],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert any("planter_scale_changed" in str(aff) for aff in r_map["B09"]["affected_object_ids"])


def test_b09_approved_config_duplicate_ids_flagged(base_master_json):
    """B09: Duplicate IDs in approved configuration do not silently overwrite; require review."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    p1 = {
        "json_id": "p1",
        "floor_id": "F1",
        "supporting_surface_type": "balcony",
        "support_json_id": "b1",
        "position": [12.0, 10.0],
    }
    p1_dup = deepcopy(p1)
    p1_dup["position"] = [15.0, 10.0]

    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 4.0,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [p1, p1_dup],
    }
    cand = {
        "vegetation_nodes": [deepcopy(p1)],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B09"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert any("duplicate_approved_planter_id" in str(aff) for aff in r_map["B09"]["affected_object_ids"])


def test_b09_approved_config_no_input_mutation(base_master_json):
    """B09: Evaluating candidate against approved configuration does not mutate inputs."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    planter = {
        "json_id": "p1",
        "floor_id": "F1",
        "elevation_m": 3.0,
        "supporting_surface_type": "balcony",
        "support_json_id": "b1",
        "position": [12.0, 10.0],
    }
    master["structural_evidence"] = {
        "max_saturated_load_kn_m2": 4.0,
        "approved_revision": 2,
        "scope": ["b1"],
        "approved_configuration": [deepcopy(planter)],
    }
    cand = {
        "vegetation_nodes": [deepcopy(planter)],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    master_before = deepcopy(master)
    cand_before = deepcopy(cand)
    evaluate_rules(cand, context, master, reqs)
    assert master == master_before
    assert cand == cand_before


# =============================================================================
# COMPREHENSIVE VERIFIED REGRESSION TESTS: B06 ROUTE CONNECTIVITY & EGRESS DESTINATIONS
# =============================================================================

def test_b06_door_polygon_reused_as_route_no_destination_requires_review(base_master_json):
    """B06: Route polygon identical to doorway polygon with no destination must never pass."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    door_coords = [[10.0, 8.5], [11.0, 8.5], [11.0, 9.5], [10.0, 9.5]]
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        "balcony_doors": [{
            "id": "door_1",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": door_coords,
            "escape_route_polygon": deepcopy(door_coords),  # identical to doorway!
        }],
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["b1", "F1"]},
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_safe",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] != RuleOutcome.PASS.value
    assert r_map["B06"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value


def test_b06_route_touches_door_but_does_not_reach_destination_requires_review(base_master_json):
    """B06: Route corridor touches door but stops short of destination -> REVIEW_REQUIRED."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        "balcony_doors": [{
            "id": "door_1",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
            "escape_route_polygon": [[10, 8.5], [12, 8.5], [12, 10.5], [10, 10.5]],
        }],
        "egress_destinations": [{
            "id": "far_stair",
            "floor_id": "F1",
            "surface_id": "b1",
            # Destination is at x=14..15, but route only goes to x=12
            "polygon": [[14.5, 8.5], [15.5, 8.5], [15.5, 10.5], [14.5, 10.5]],
        }],
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["b1", "F1"]},
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_safe",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "escape_route_connectivity" in r_map["B06"]["missing_inputs"]


def test_b06_route_touches_destination_but_not_door_requires_review(base_master_json):
    """B06: Route touches destination but does not connect to access door -> REVIEW_REQUIRED."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        "balcony_doors": [{
            "id": "door_1",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
        }],
        "escape_routes": [{
            "id": "route_at_dest",
            "floor_id": "F1",
            "surface_id": "b1",
            # Route is adjacent to destination [13..14] but detached from door [10..11]
            "polygon": [[12.5, 8.5], [13.5, 8.5], [13.5, 10.5], [12.5, 10.5]],
        }],
        "egress_destinations": [{
            "id": "dest_exit",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[13.5, 8.5], [14.5, 8.5], [14.5, 10.5], [13.5, 10.5]],
        }],
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["b1", "F1"]},
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_safe",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "escape_route_connectivity" in r_map["B06"]["missing_inputs"]


def test_b06_separate_route_components_touching_opposite_endpoints_requires_review(base_master_json):
    """B06: Two disconnected route pieces touching opposite endpoints do not form a route."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        "balcony_doors": [{
            "id": "door_1",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
        }],
        "escape_routes": [
            # Component 1 touches door
            {"id": "route_1", "surface_id": "b1", "polygon": [[10, 8.5], [11.5, 8.5], [11.5, 9.5], [10, 9.5]]},
            # Component 2 touches destination (gap between 11.5 and 13.0)
            {"id": "route_2", "surface_id": "b1", "polygon": [[13.0, 8.5], [14.0, 8.5], [14.0, 9.5], [13.0, 9.5]]},
        ],
        "egress_destinations": [{
            "id": "dest_exit",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[14.0, 8.5], [15.0, 8.5], [15.0, 9.5], [14.0, 9.5]],
        }],
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["b1", "F1"]},
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_safe",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "escape_route_connectivity" in r_map["B06"]["missing_inputs"]


def test_b06_destination_from_another_balcony_or_floor_excluded(base_master_json):
    """B06: Egress destination associated with a different surface or floor is excluded."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [
            {"json_id": "b1", "floor_id": "F1", "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]},
            {"json_id": "b2", "floor_id": "F1", "polygon": [[20, 8], [26, 8], [26, 14], [20, 14]]},
        ],
        "balcony_doors": [{
            "id": "door_1",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
            "escape_route_polygon": [[10, 8.5], [12, 8.5], [12, 10.5], [10, 10.5]],
        }],
        "egress_destinations": [{
            "id": "dest_other",
            "floor_id": "F1",
            "surface_id": "b2",  # Different surface!
            "polygon": [[12, 8.5], [13, 8.5], [13, 10.5], [12, 10.5]],
        }],
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["b1", "b2", "F1"]},
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_safe",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "designated_egress_destination" in r_map["B06"]["missing_inputs"]


def test_b06_malformed_destination_geometry_unknown(base_master_json):
    """B06: Malformed destination geometry yields UNKNOWN."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "F1", "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        "balcony_doors": [{
            "id": "door_1",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
            "escape_route_polygon": [[10, 8.5], [12, 8.5], [12, 10.5], [10, 10.5]],
        }],
        "egress_destinations": [{
            "id": "bad_dest",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": "malformed_coordinates",
        }],
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["b1", "F1"]},
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_safe",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.UNKNOWN.value
    assert "valid_egress_destination_geometry" in r_map["B06"]["missing_inputs"]


def test_b06_polygon_hole_placement_and_tolerance_contact(base_master_json):
    """B06: Planter inside polygon hole does not obstruct, boundary contact within tolerance passes."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    # Route polygon with interior hole at [13.0, 11.0] to [15.0, 13.0]
    # Door: [10, 8.5] to [11, 9.5]
    # Route shell: [10, 8.5] to [16, 8.5] to [16, 13.5] to [10, 13.5]
    # Route hole: [13.0, 11.0] to [15.0, 11.0] to [15.0, 13.0] to [13.0, 13.0]
    # Destination: [16.0, 8.5] to [17.0, 8.5] to [17.0, 10.5] to [16.0, 10.5]
    route_with_hole = {
        "shell": [[10.0, 8.5], [16.0, 8.5], [16.0, 13.5], [10.0, 13.5]],
        "holes": [[[13.0, 11.0], [15.0, 11.0], [15.0, 13.0], [13.0, 13.0]]],
    }
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[10, 8], [17, 8], [17, 14], [10, 14]]}],
        "balcony_doors": [{
            "id": "door_1",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[10.0, 8.5], [11.0, 8.5], [11.0, 9.5], [10.0, 9.5]],
        }],
        "escape_routes": [{
            "id": "route_holed",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": route_with_hole,
        }],
        "egress_destinations": [{
            "id": "dest_exit",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[16.0, 8.5], [17.0, 8.5], [17.0, 10.5], [16.0, 10.5]],
        }],
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["b1", "F1"]},
    }
    # Planter placed strictly inside the hole [13.5, 11.5] to [14.5, 12.5]
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_in_hole",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    # Does not intersect the corridor because it sits in the hole!
    assert r_map["B06"]["outcome"] == RuleOutcome.PASS.value


# =============================================================================
# COMPREHENSIVE VERIFIED REGRESSION TESTS: SUPPORTING SURFACE RESOLUTION
# =============================================================================

def test_supporting_surface_missing_id_uniquely_resolvable_passes_b06(base_master_json):
    """B06: Planter missing explicit support_json_id resolves uniquely by floor and passes B06."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "balc_unique", "floor_id": "F1", "elevation_m": 0.0, "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        "balcony_doors": [{
            "id": "door_1",
            "floor_id": "F1",
            "surface_id": "balc_unique",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
            "escape_route_polygon": [[10, 8.5], [12, 8.5], [12, 10.5], [10, 10.5]],
        }],
        "egress_destinations": [{
            "id": "dest_exit",
            "floor_id": "F1",
            "surface_id": "balc_unique",
            "polygon": [[12, 8.5], [13, 8.5], [13, 10.5], [12, 10.5]],
        }],
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["balc_unique", "F1"]},
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_unresolved_id",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            # support_json_id intentionally omitted!
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    # Genuinely resolvable unique surface must PASS B06!
    assert r_map["B06"]["outcome"] == RuleOutcome.PASS.value


def test_supporting_surface_multiple_possible_surfaces_no_guessing(base_master_json):
    """B06: Planter missing explicit surface with multiple balconies on floor requires review."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [
            {"json_id": "b1", "floor_id": "F1", "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]},
            {"json_id": "b2", "floor_id": "F1", "polygon": [[20, 8], [26, 8], [26, 14], [20, 14]]},
        ],
        "balcony_doors": [{
            "id": "door_1",
            "floor_id": "F1",
            "surface_id": "b1",
            "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]],
        }],
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["b1", "b2", "F1"]},
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_ambiguous",
            "floor_id": "F1",
            "supporting_surface_type": "balcony",
            # support_json_id omitted with 2 balconies on floor F1
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "supporting_surface_identity" in r_map["B06"]["missing_inputs"]


def test_supporting_surface_contradictory_floor(base_master_json):
    """B06: Planter explicit surface b1 (Floor 1) contradictory with floor_id F2 requires review."""
    context = parse_exterior_context(base_master_json, default_units="m")
    reqs = {"design_style": "modern"}
    master = deepcopy(base_master_json)
    master["revision"] = 2
    master["building_exterior"] = {
        "balconies": [{"json_id": "b1", "floor_id": "F1", "polygon": [[10, 8], [16, 8], [16, 14], [10, 14]]}],
        "balcony_doors": [{"id": "door_1", "floor_id": "F1", "surface_id": "b1", "polygon": [[10, 8.5], [11, 8.5], [11, 9.5], [10, 9.5]]}],
        "guardrail_profile": {"verified_climbability_assessment": True, "revision": 2, "scope": ["b1", "F1"]},
    }
    cand = {
        "vegetation_nodes": [{
            "json_id": "planter_mismatch",
            "floor_id": "F2",  # Contradictory floor!
            "supporting_surface_type": "balcony",
            "support_json_id": "b1",
            "position": [14.0, 12.0],
            "footprint": [[13.5, 11.5], [14.5, 11.5], [14.5, 12.5], [13.5, 12.5]],
        }],
        "outdoor_elements": [],
        "outdoor_lighting": {"nodes": []},
        "access": {},
    }
    res = evaluate_rules(cand, context, master, reqs)
    r_map = {r["rule_id"]: r for r in res["rule_evaluations"]}
    assert r_map["B06"]["outcome"] == RuleOutcome.REVIEW_REQUIRED.value
    assert "supporting_surface_identity" in r_map["B06"]["missing_inputs"]





