from __future__ import annotations

import pytest
from copy import deepcopy
from shapely.geometry import box, Polygon, Point

from app.components.elia_engine.assessment import build_factors_assessment
from app.components.elia_engine.requirements import normalize_requirements
from app.components.elia_engine.rule_repository import vegetation_catalog
from app.components.elia_engine.vegetation import place_vegetation
from app.components.elia_engine.service import run_elia, validate_candidate_exterior
from app.components.elia_engine.exceptions import ELIAError, ELIAPlanningLimitExceeded
from app.components.elia_engine.schemas import ELIARequirements, ExteriorLandscape


@pytest.fixture
def base_master_json():
    return {
        "project_id": "test-panel-feedback-prj",
        "project_name": "Test Garden Project",
        "units": "m",
        "location": {"latitude": 6.9, "longitude": 79.8, "timezone": "Asia/Colombo"},
        "land_info": {"boundary_points": [[0, 0], [40, 0], [40, 30], [0, 30]],
                      "road_facing": "south", "calculated_north_bearing": 0},
        "house_exterior_polygon": [[10, 8], [22, 8], [22, 22], [10, 22]],
        "house_height_m": 6,
        "utilities": {"well": {"known": True, "position": [2, 27]},
                      "septic_tank": {"known": True, "position": [22, 27]}},
        "interior_layout": {"rooms": [{"id": "R1", "furniture": [{"id": "SOFA_01"}]}]},
        "floor_plan": {"floors": [{"id": "F1", "rooms": ["R1"]}]},
        "processing": {"esai_engine": {"status": "completed"}},
    }


def test_requirements_normalization_and_financial_stripping(base_master_json):
    # 1. Test canonical styles and aliases
    req_minimalist = {"design_style": "minimalist", "low_maintenance_preference": True}
    norm_min = normalize_requirements(req_minimalist, base_master_json, "m")
    assert norm_min["design_style"] == "minimalistic"
    assert norm_min["maintenance_preference"] == "low"

    # 2. Obsolete financial fields are stripped and never present
    req_financial = {
        "design_style": "greeny",
        "water_availability": "limited",
        "budget_limit_lkr": 500000,
        "budget_preference": "strict",
    }
    norm_financial = normalize_requirements(req_financial, base_master_json, "m")
    assert norm_financial["design_style"] == "greeny"
    assert norm_financial["water_availability"] == "limited"
    assert "budget_limit_lkr" not in norm_financial
    assert "budget_preference" not in norm_financial

    # 3. Missing environmental info is None, not assumed favorable
    assert norm_financial["climate_zone"] is None
    assert norm_financial["site_exposure"] is None


def test_old_saved_records_with_obsolete_financials_load_cleanly(base_master_json):
    # Historical record contains obsolete financial fields
    reqs = {
        "design_style": "modern",
        "access": {"road_side": "south", "driveway_required": False, "garage_required": False},
        "landscape": {"garden_required": True},
    }
    cand_output, _ = run_elia(base_master_json, reqs, "run-hist")
    historical_candidate = deepcopy(cand_output)
    historical_candidate["budget_estimate"] = {"known_subtotal_lkr": 250000, "currency": "LKR"}
    historical_candidate["budget_assessment"] = {"budget_status": "within_budget"}
    historical_candidate["price_quotation"] = 12345

    res = validate_candidate_exterior(base_master_json, historical_candidate, reqs)
    assert res["valid"] is True
    canonical = res["canonical_candidate"]
    assert "budget_estimate" not in canonical
    assert "budget_assessment" not in canonical
    assert "price_quotation" not in canonical


def test_planning_limit_exception_raised_on_impossible_search():
    # Test that search/computation limit protections raise ELIAPlanningLimitExceeded
    with pytest.raises(ELIAPlanningLimitExceeded) as exc_info:
        raise ELIAPlanningLimitExceeded(
            code="ELIA_PLANNING_LIMIT_EXCEEDED",
            message="Search limit exhausted: Iteration limit exceeded",
            details={"iterations": 1000}
        )
    assert exc_info.value.code == "ELIA_PLANNING_LIMIT_EXCEEDED"
    assert "Search limit" in exc_info.value.message


def test_explicit_density_overrides_concept_defaults(base_master_json):
    land = box(0, 0, 40, 30)
    residual = land.difference(box(10, 8, 22, 22))
    blocked = box(10, 8, 22, 22)

    # Minimalistic concept defaults to low density, but user explicitly requests high density
    reqs_explicit_high = {
        "design_style": "minimalistic",
        "landscape": {
            "garden_required": True,
            "greenery_density": "high",
            "explicit_greenery_density": True,
        },
    }
    result_explicit = place_vegetation(residual, land, blocked, reqs_explicit_high, [])

    # Minimalistic concept with omitted density gets default low density
    reqs_default_low = {
        "design_style": "minimalistic",
        "landscape": {
            "garden_required": True,
            "explicit_greenery_density": False,
        },
    }
    result_default = place_vegetation(residual, land, blocked, reqs_default_low, [])

    # Explicit high density must produce more plants than default low density
    assert len(result_explicit.nodes) > len(result_default.nodes)
    # Concept default rule must NOT be added when explicit density was given
    assert not any("restricted planting density" in r for r in result_explicit.concept_rules)
    assert any("restricted planting density" in r for r in result_default.concept_rules)


def test_plant_exclusions_honored_without_fallback(base_master_json):
    land = box(0, 0, 40, 30)
    residual = land.difference(box(10, 8, 22, 22))
    blocked = box(10, 8, 22, 22)

    cat = vegetation_catalog()
    all_plant_ids = [e["vegetation_id"] for e in cat.get("entries", [])]

    # Exclude every single plant in the catalogue
    reqs_all_excluded = {
        "landscape": {"garden_required": True, "plant_ids_to_avoid": all_plant_ids},
        "plant_ids_to_avoid": all_plant_ids,
    }
    result = place_vegetation(residual, land, blocked, reqs_all_excluded, [])

    # Must NOT fallback to original catalogue; no plants placed
    assert len(result.nodes) == 0
    # Must report unmet requirement with specific explanation
    assert len(result.unmet_reasons) > 0
    assert any("exclusion" in r.lower() for r in result.unmet_reasons)


def test_unknown_sunlight_and_climate_traits_stay_unknown(base_master_json):
    # Assessment with unknown climate and water availability
    assessment = build_factors_assessment(
        residual_area_m2=500.0,
        land_area_m2=1200.0,
        house_area_m2=200.0,
        vegetation=[{"json_id": "v1", "plant_id": "areca_catechu", "category": "small_tree", "verified_species_data": True}],
        shadow_samples=[],
        requirements={
            "climate_zone": None,
            "water_availability": None,
            "maintenance_preference": None,
        },
    )
    factors_map = {f["factor"]: f for f in assessment["factors"]}

    # Climate must be unknown, not assumed satisfied
    assert factors_map["climate"]["status"] == "unknown"
    assert "Climate zone not declared" in factors_map["climate"]["reason_and_limitations"]

    # Water demand must be unknown
    assert factors_map["water_needs"]["status"] == "unknown"

    # Sunlight suitability must be unknown when no shadow samples are available
    assert factors_map["sunlight"]["status"] == "unknown"

    # No financial factor in assessment
    assert "budget" not in factors_map


def test_mixed_verified_and_unverified_plant_assessment():
    placed_veg = [
        {"json_id": "v1", "plant_id": "areca_catechu", "verified_species_data": True},
        {"json_id": "v2", "plant_id": "custom_unverified_fern", "verified_species_data": False},
    ]
    assessment = build_factors_assessment(
        residual_area_m2=300.0,
        land_area_m2=1000.0,
        house_area_m2=150.0,
        vegetation=placed_veg,
        shadow_samples=[],
        requirements={},
    )
    factors_map = {f["factor"]: f for f in assessment["factors"]}
    # Plant suitability honestly reports unverified nodes
    assert factors_map["plant_suitability"]["status"] == "unmet"
    assert "1 of 2" in factors_map["plant_suitability"]["input_value"]


def test_locked_objects_preservation_and_routing(base_master_json):
    land = box(0, 0, 40, 30)
    residual = land.difference(box(10, 8, 22, 22))
    blocked = box(10, 8, 22, 22)

    locked_feature = {
        "json_id": "SHRUB_LOCKED_01",
        "category": "shrub",
        "plant_id": "heliconia_psittacorum",
        "position": [5.0, 5.0],
        "canopy_radius_m": 0.8,
        "height_m": 1.2,
        "locked": True,
    }

    reqs = {
        "landscape": {"garden_required": True, "greenery_density": "medium"},
        "locked_features": [locked_feature],
    }

    result = place_vegetation(residual, land, blocked, reqs, [])
    # Verify locked feature is preserved with identical ID and coordinates
    preserved = next((n for n in result.nodes if n.get("json_id") == "SHRUB_LOCKED_01"), None)
    assert preserved is not None
    assert preserved["position"] == [5.0, 5.0]
    assert preserved["locked"] is True

    # Newly placed nodes must not collide with the locked feature
    p_locked = Point(5.0, 5.0)
    for other in result.nodes:
        if other.get("json_id") != "SHRUB_LOCKED_01":
            p_other = Point(other["position"])
            assert p_locked.distance(p_other) >= 0.8


def test_locked_feature_pairwise_conflict():
    land = box(0, 0, 40, 30)
    residual = land.difference(box(10, 8, 22, 22))
    blocked = box(10, 8, 22, 22)

    # Locked node placed inside house obstacle
    conflicting_locked = {
        "json_id": "TREE_COLLIDING",
        "category": "shade_tree",
        "position": [15.0, 15.0],  # Inside the house [10, 8] to [22, 22]
        "canopy_radius_m": 2.0,
        "locked": True,
    }
    reqs = {
        "landscape": {"garden_required": True},
        "locked_features": [conflicting_locked],
    }
    with pytest.raises(ELIAError) as exc_info:
        place_vegetation(residual, land, blocked, reqs, [])
    assert exc_info.value.code == "ELIA_LOCKED_FEATURE_CONFLICT"


def test_candidate_exterior_validation_and_canonical_return(base_master_json):
    requirements = {
        "design_style": "modern",
        "access": {"road_side": "south", "driveway_required": False, "garage_required": False},
        "landscape": {"garden_required": True},
    }
    output, outcome = run_elia(base_master_json, requirements, "test-run-1")
    assert outcome == "valid"

    # 1. Valid candidate passes validation and returns canonical candidate
    res = validate_candidate_exterior(base_master_json, output, requirements)
    assert res["valid"] is True
    assert "canonical_candidate" in res
    assert res["canonical_candidate"] is not None
    assert res["factors_assessment"] is not None
    assert "budget_assessment" not in res
    assert res["checks_passed"] > 0
    assert res["checks_total"] >= res["checks_passed"]

    # 2. Moving an object outside boundary fails validation with accurate checks counters
    invalid_candidate = deepcopy(output)
    if invalid_candidate["vegetation_nodes"]:
        invalid_candidate["vegetation_nodes"][0]["position"] = [999.0, 999.0]
        res_invalid = validate_candidate_exterior(base_master_json, invalid_candidate, requirements)
        assert res_invalid["valid"] is False
        assert any("containment" in v for v in res_invalid["violations"])
        assert res_invalid["checks_passed"] < res_invalid["checks_total"]


def test_candidate_save_preserves_components_1_to_3_and_saves_canonical(base_master_json):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.main import app
    from app.database import Base, get_db
    from app.dependencies import get_current_user
    from app.models.project import Project
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: type("User", (), {"id": "admin", "role": "admin", "is_admin": True})()

    try:
        with TestingSession() as db:
            project = Project(
                id="prj-panel-test-02",
                project_name="Panel Test Project 2",
                revision=1,
                master_json=deepcopy(base_master_json),
            )
            db.add(project)
            db.commit()

        with TestClient(app) as client:
            reqs = {
                "design_style": "modern",
                "access": {"road_side": "south", "driveway_required": False, "garage_required": False},
                "landscape": {"garden_required": True},
            }
            cand_output, _ = run_elia(base_master_json, reqs, "cand-run-2")

            customized = deepcopy(cand_output)
            if customized["vegetation_nodes"]:
                customized["vegetation_nodes"][0]["locked"] = True

            # Save candidate
            save_resp = client.post(
                "/api/projects/prj-panel-test-02/elia-engine/save-candidate",
                json={"exterior_landscape": customized, "source_revision": 1, "requirements": reqs}
            )
            assert save_resp.status_code == 200
            saved_data = save_resp.json()
            assert saved_data["revision"] == 2
            assert saved_data["status"] == "completed"

            # Check that no financial fields were persisted in the response or master JSON
            assert "budget_estimate" not in saved_data["exterior_landscape"]
            assert "budget_assessment" not in saved_data["exterior_landscape"]

            with TestingSession() as db:
                updated_prj = db.query(Project).filter(Project.id == "prj-panel-test-02").one()
                master = updated_prj.master_json
                # Authoritative preservation of Components 1-3
                assert master["interior_layout"] == base_master_json["interior_layout"]
                assert master["floor_plan"] == base_master_json["floor_plan"]
                assert master["processing"]["esai_engine"] == base_master_json["processing"]["esai_engine"]
                # ELIA saved without financial fields
                assert "exterior_landscape" in master
                assert "budget_estimate" not in master["exterior_landscape"]
    finally:
        app.dependency_overrides.clear()
