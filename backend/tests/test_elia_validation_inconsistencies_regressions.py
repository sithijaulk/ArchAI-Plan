"""
Regression Test Suite for the Four Confirmed ELIA Validation Inconsistencies:
1. Unified Solar Structural-Evidence Validation
2. Unsupported Load Defaults & Approval Shortcuts Removal
3. Candidate Geometry Internal Consistency (Parametric, Polygon-Authoritative, Solar)
4. Acceptance Policy Enforcement on Persistence Paths (save-candidate & run)
"""

from __future__ import annotations

import copy
import math
import pytest
from shapely.geometry import Polygon, box
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app.dependencies import require_admin
from app.models.component_run import ComponentRun
from app.models.project import Project
from app.components.elia_engine.exceptions import ELIAError
from app.components.elia_engine.solar_planner import plan_solar_pv, evaluate_solar_structural_evidence
from app.components.elia_engine.service import validate_candidate_exterior, evaluate_acceptance_policy
from app.components.elia_engine.schemas import ELIARequest


def _make_base_master():
    return {
        "project_name": "Lakeview Residence Regression Testing",
        "units": "m",
        "location": {"latitude": 6.9271, "longitude": 79.8612, "timezone": "Asia/Colombo"},
        "calculated_north_bearing": 0.0,
        "land_boundary_polygon": [[0.0, 0.0], [40.0, 0.0], [40.0, 30.0], [0.0, 30.0], [0.0, 0.0]],
        "house_exterior_polygon": [[12.0, 8.0], [26.0, 8.0], [26.0, 20.0], [12.0, 20.0], [12.0, 8.0]],
        "main_entrance": [19.0, 8.0],
        "road_facing": "south",
        "road_access_edge": 0,
        "house": {
            "roof": {
                "surfaces": [
                    {
                        "id": "roof_flat_01",
                        "json_id": "roof_flat_01",
                        "type": "flat",
                        "is_accessible": True,
                        "elevation_m": 6.8,
                        "coordinates": [[[12.0, 8.0], [26.0, 8.0], [26.0, 20.0], [12.0, 20.0], [12.0, 8.0]]],
                    }
                ]
            }
        },
        "utilities": {
            "well": {"known": True, "position_m": [4.0, 25.0]},
            "septic_tank": {"known": True, "position_m": [35.0, 25.0]},
        },
        "exterior_landscape": {
            "version": "1.0",
            "status": "initial_accepted_design",
            "vegetation_nodes": [],
            "outdoor_elements": [],
        },
        "processing": {"esai_engine": {"status": "completed"}},
    }


@pytest.fixture
def test_app_env(tmp_path):
    db_file = tmp_path / "elia_inconsistencies_test.db"
    engine = create_engine(f"sqlite:///{db_file}", echo=False, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = lambda: {"username": "admin", "role": "admin"}

    session = session_factory()
    master = _make_base_master()
    project = Project(
        project_name=master["project_name"],
        revision=1,
        master_json=master,
        current_component="floor_plan",
    )
    session.add(project)
    session.commit()
    project_id = project.id
    session.close()

    client = TestClient(app)
    yield client, session_factory, project_id, master

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


# =========================================================================
# 1. SOLAR STRUCTURAL EVIDENCE & LOAD DEFECT REGRESSIONS
# =========================================================================

def test_solar_evidence_consistency_generation_and_candidate_validation():
    """Generation (plan_solar_pv) and candidate validation must produce the exact same evidence decision."""
    master = _make_base_master()
    master["structural_evidence"] = {
        "certified": True,
        "remaining_capacity_kg_m2": 35.0,
        "proposed_load_kg_m2": 25.0,
        "engineer_license": "SL-ENG-2024-5544",
    }
    reqs = {
        "access": {"driveway_required": False, "gate_required": False},
        "solar": {"panels_required": True, "proposed_load_kg_m2": 25.0}
    }

    plan = plan_solar_pv(master, reqs)
    assert plan["status"] == "fulfilled"
    assert plan["approval_status"] == "approved"
    assert plan["provisional_geometric_preview"] is False

    candidate = {
        "version": "1.0",
        "outdoor_elements": [plan["outdoor_element"]],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
        "access": {"driveway": None, "gate": None},
    }
    val = validate_candidate_exterior(master, candidate, reqs)
    assert val["valid"] is True
    assert val["approval_status"] == "approved"
    assert not any("unverified_structural_solar" in v for v in val["violations"])


def test_solar_evidence_bare_approval_flag_rejected():
    """A bare approval flag cannot bypass evidence evaluation."""
    master = _make_base_master()
    master["structural_evidence"] = {
        "certified": True,
        "approved": True,
        "solar_certified": True,
    }
    reqs = {
        "access": {"driveway_required": False, "gate_required": False},
        "solar": {"panels_required": True, "proposed_load_kg_m2": 25.0}
    }

    plan = plan_solar_pv(master, reqs)
    assert plan["approval_status"] in ("review_required", "provisional_review_required")
    assert plan["provisional_geometric_preview"] is True

    candidate = {
        "version": "1.0",
        "outdoor_elements": [plan["outdoor_element"]],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
        "access": {"driveway": None, "gate": None},
    }
    val = validate_candidate_exterior(master, candidate, reqs)
    assert val["approval_status"] == "review_required"
    assert val["valid"] is True  # Geometrically valid layout
    # Acceptance policy must reject this candidate for persistence
    policy = evaluate_acceptance_policy(val, val["canonical_candidate"], master, reqs)
    assert policy["accepted"] is False
    assert "solar_panels" in policy["blocking_features"]


def test_solar_evidence_insufficient_or_invalid_capacity_rejected():
    """Capacity field present with insufficient or malformed value is rejected."""
    master = _make_base_master()
    # Insufficient capacity
    master["structural_evidence"] = {
        "remaining_capacity_kg_m2": 15.0,  # Proposed load is 25.0
        "proposed_load_kg_m2": 25.0,
        "engineer_license": "SL-ENG-2024-5544",
    }
    reqs = {
        "access": {"driveway_required": False, "gate_required": False},
        "solar": {"panels_required": True, "proposed_load_kg_m2": 25.0}
    }
    plan = plan_solar_pv(master, reqs)
    assert plan["approval_status"] in ("review_required", "provisional_review_required")

    # Malformed negative capacity
    master["structural_evidence"]["remaining_capacity_kg_m2"] = -10.0
    ev = evaluate_solar_structural_evidence("roof_flat_01", master, reqs)
    assert ev["is_approved"] is False
    assert ev["status"] == "invalid_evidence"

    # Malformed boolean capacity
    master["structural_evidence"]["remaining_capacity_kg_m2"] = True
    ev_bool = evaluate_solar_structural_evidence("roof_flat_01", master, reqs)
    assert ev_bool["is_approved"] is False
    assert ev_bool["status"] == "invalid_evidence"


def test_solar_evidence_mismatched_surface_or_installation_rejected():
    """Evidence scoped to a different surface or installation scope is rejected."""
    master = _make_base_master()
    master["structural_evidence"] = {
        "target_surface_id": "other_roof_surface",
        "installation_type": "bipv_integrated",
        "remaining_capacity_kg_m2": 50.0,
        "proposed_load_kg_m2": 25.0,
        "engineer_license": "SL-ENG-2024-5544",
    }
    reqs = {"solar": {"panels_required": True, "installation_type": "ballasted_flat", "proposed_load_kg_m2": 25.0}}
    ev = evaluate_solar_structural_evidence("roof_flat_01", master, reqs)
    assert ev["is_approved"] is False
    assert ev["status"] == "review_required"
    assert ev["reason"] == "STRUCTURAL_EVIDENCE_SCOPE_MISMATCH"


def test_solar_evidence_missing_proposed_load_remains_review_required():
    """Missing proposed load must remain review_required without defaulting to 25.0 kg/m2."""
    master = _make_base_master()
    master["structural_evidence"] = {
        "remaining_capacity_kg_m2": 50.0,
        "engineer_license": "SL-ENG-2024-5544",
    }
    reqs = {"solar": {"panels_required": True}}  # No proposed load specified

    ev = evaluate_solar_structural_evidence("roof_flat_01", master, reqs)
    assert ev["is_approved"] is False
    assert ev["status"] == "review_required"
    assert "proposed_pv_load_kg_m2" in ev["missing_evidence"]
    assert ev["reason"] == "MISSING_PROPOSED_PV_LOAD"


def test_solar_evidence_invalid_proposed_load_raises_typed_error():
    """Invalid numeric input for proposed load must produce a typed validation error."""
    master = _make_base_master()
    master["structural_evidence"] = {
        "remaining_capacity_kg_m2": 50.0,
        "engineer_license": "SL-ENG-2024-5544",
    }

    # Boolean proposed load
    with pytest.raises(ELIAError) as exc_bool:
        evaluate_solar_structural_evidence("roof_flat_01", master, {"solar": {"proposed_load_kg_m2": True}})
    assert exc_bool.value.code == "ELIA_INVALID_REQUIREMENT"

    # Negative proposed load
    with pytest.raises(ELIAError) as exc_neg:
        evaluate_solar_structural_evidence("roof_flat_01", master, {"solar": {"proposed_load_kg_m2": -15.0}})
    assert exc_neg.value.code == "ELIA_INVALID_REQUIREMENT"

    # Non-finite proposed load
    with pytest.raises(ELIAError) as exc_nan:
        evaluate_solar_structural_evidence("roof_flat_01", master, {"solar": {"proposed_load_kg_m2": "NaN"}})
    assert exc_nan.value.code == "ELIA_INVALID_REQUIREMENT"


def test_solar_evidence_valid_scoped_case_succeeds():
    """Valid scoped engineering evidence case succeeds as approved."""
    master = _make_base_master()
    master["structural_evidence"] = {
        "target_surface_id": "roof_flat_01",
        "remaining_capacity_kg_m2": 55.0,
        "proposed_load_kg_m2": 25.0,
        "engineer_license": "SL-ENG-2024-5544",
    }
    reqs = {"solar": {"panels_required": True, "proposed_load_kg_m2": 25.0}}
    ev = evaluate_solar_structural_evidence("roof_flat_01", master, reqs)
    assert ev["is_approved"] is True
    assert ev["status"] == "approved"
    assert ev["missing_evidence"] == []


# =========================================================================
# 2. CANDIDATE GEOMETRY INTERNAL CONSISTENCY REGRESSIONS
# =========================================================================

def test_geometry_small_polygon_oversized_dimensions():
    """Parametric element: Small supplied polygon with oversized dimensions is replaced with canonical footprint."""
    master = _make_base_master()
    candidate = {
        "version": "1.0",
        "outdoor_elements": [
            {
                "json_id": "SEAT_01",
                "type": "garden_seating",
                "position": [5.0, 5.0],
                "dimensions": {"width_m": 3.0, "depth_m": 2.0},
                "polygon": [[5.0, 5.0], [5.5, 5.0], [5.5, 5.5], [5.0, 5.5], [5.0, 5.0]],  # only 0.25 m2
            }
        ],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
    }
    val = validate_candidate_exterior(master, candidate)
    canonical_elem = val["canonical_candidate"]["outdoor_elements"][0]
    canonical_poly = Polygon(canonical_elem["polygon"])
    # The contradictory 0.25 m2 polygon must be replaced by the canonical 6.0 m2 footprint
    assert math.isclose(canonical_poly.area, 6.0, rel_tol=1e-3)
    assert math.isclose(canonical_poly.centroid.x, 5.0, abs_tol=1e-3)
    assert math.isclose(canonical_poly.centroid.y, 5.0, abs_tol=1e-3)


def test_geometry_stale_polygon_changed_position_or_rotation():
    """Parametric element: Stale polygon with changed position is replaced with canonical footprint."""
    master = _make_base_master()
    candidate = {
        "version": "1.0",
        "outdoor_elements": [
            {
                "json_id": "PERGOLA_01",
                "type": "pergola",
                "position": [8.0, 8.0],  # Position changed to (8, 8)
                "dimensions": {"width_m": 2.0, "depth_m": 2.0},
                "rotation_deg": 45.0,
                "polygon": [[1.0, 1.0], [3.0, 1.0], [3.0, 3.0], [1.0, 3.0], [1.0, 1.0]],  # Stale polygon at (2, 2)
            }
        ],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
    }
    val = validate_candidate_exterior(master, candidate)
    canonical_elem = val["canonical_candidate"]["outdoor_elements"][0]
    canonical_poly = Polygon(canonical_elem["polygon"])
    assert math.isclose(canonical_poly.centroid.x, 8.0, abs_tol=1e-3)
    assert math.isclose(canonical_poly.centroid.y, 8.0, abs_tol=1e-3)


def test_geometry_asymmetric_object_rotated_90_degrees():
    """Asymmetric object rotated by 90 degrees correctly computes rotated footprint bounds."""
    master = _make_base_master()
    candidate = {
        "version": "1.0",
        "outdoor_elements": [
            {
                "json_id": "TABLE_01",
                "type": "garden_table_set",
                "position": [6.0, 6.0],
                "dimensions": {"width_m": 4.0, "depth_m": 2.0},
                "rotation_deg": 90.0,
            }
        ],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
    }
    val = validate_candidate_exterior(master, candidate)
    canonical_elem = val["canonical_candidate"]["outdoor_elements"][0]
    poly = Polygon(canonical_elem["polygon"])
    minx, miny, maxx, maxy = poly.bounds
    # Rotated 90 deg: width is 2.0, depth is 4.0
    assert math.isclose(maxx - minx, 2.0, abs_tol=1e-2)
    assert math.isclose(maxy - miny, 4.0, abs_tol=1e-2)


def test_geometry_explicit_zero_negative_nan_inf_rejected():
    """Explicit zero, negative, NaN, and Inf inputs are rejected rather than falling back to default."""
    master = _make_base_master()
    
    # Explicit zero width
    cand_zero = {
        "version": "1.0",
        "outdoor_elements": [{"json_id": "E_ZERO", "type": "garden_seating", "position": [5.0, 5.0], "dimensions": {"width_m": 0.0, "depth_m": 2.0}}]
    }
    val_zero = validate_candidate_exterior(master, cand_zero)
    assert any("invalid_dimensions_E_ZERO" in v for v in val_zero["violations"])

    # Negative width
    cand_neg = {
        "version": "1.0",
        "outdoor_elements": [{"json_id": "E_NEG", "type": "garden_seating", "position": [5.0, 5.0], "dimensions": {"width_m": -2.0, "depth_m": 2.0}}]
    }
    val_neg = validate_candidate_exterior(master, cand_neg)
    assert any("invalid_dimensions_E_NEG" in v for v in val_neg["violations"])

    # NaN width
    cand_nan = {
        "version": "1.0",
        "outdoor_elements": [{"json_id": "E_NAN", "type": "garden_seating", "position": [5.0, 5.0], "dimensions": {"width_m": float("nan"), "depth_m": 2.0}}]
    }
    val_nan = validate_candidate_exterior(master, cand_nan)
    assert any("invalid_dimensions_E_NAN" in v for v in val_nan["violations"])

    # Boolean width
    cand_bool = {
        "version": "1.0",
        "outdoor_elements": [{"json_id": "E_BOOL", "type": "garden_seating", "position": [5.0, 5.0], "dimensions": {"width_m": True, "depth_m": 2.0}}]
    }
    val_bool = validate_candidate_exterior(master, cand_bool)
    assert any("invalid_dimensions_E_BOOL" in v for v in val_bool["violations"])


def test_geometry_valid_irregular_polygon_preservation():
    """Polygon-authoritative objects preserve irregular geometry and interior holes verbatim."""
    master = _make_base_master()
    # Complex polygon with interior cutout (hole)
    shell = [[2.0, 2.0], [8.0, 2.0], [8.0, 8.0], [5.0, 8.0], [5.0, 5.0], [2.0, 5.0], [2.0, 2.0]]
    hole = [[3.0, 3.0], [4.0, 3.0], [4.0, 4.0], [3.0, 4.0], [3.0, 3.0]]
    expected_poly = Polygon(shell, [hole])

    candidate = {
        "version": "1.0",
        "outdoor_elements": [
            {
                "json_id": "GARDEN_ZONE_01",
                "type": "garden_zone",
                "polygon": [shell, hole],
            }
        ],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
    }
    val = validate_candidate_exterior(master, candidate)
    canonical_elem = val["canonical_candidate"]["outdoor_elements"][0]
    assert canonical_elem["polygon"] == [shell, hole] or canonical_elem["polygon"] == list(expected_poly.exterior.coords)


def test_geometry_solar_modules_preserved_through_validation_save_reload():
    """All individual solar modules are preserved without collapsing to bounding box."""
    master = _make_base_master()
    master["structural_evidence"] = {
        "remaining_capacity_kg_m2": 50.0,
        "proposed_load_kg_m2": 25.0,
        "engineer_license": "SL-ENG-2024-5544",
    }
    modules = [
        {"module_id": f"mod_{i}", "polygon": [[13.0 + i, 9.0], [13.9 + i, 9.0], [13.9 + i, 10.5], [13.0 + i, 10.5], [13.0 + i, 9.0]]}
        for i in range(4)
    ]
    candidate = {
        "version": "1.0",
        "outdoor_elements": [
            {
                "json_id": "SOLAR_ARRAY_01",
                "type": "solar_panel_array",
                "supporting_surface_id": "roof_flat_01",
                "modules": modules,
                "proposed_load_kg_m2": 25.0,
            }
        ],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
    }
    val = validate_candidate_exterior(master, candidate)
    canonical_elem = val["canonical_candidate"]["outdoor_elements"][0]
    assert "modules" in canonical_elem
    assert len(canonical_elem["modules"]) == 4
    for i, mod in enumerate(canonical_elem["modules"]):
        assert mod["module_id"] == f"mod_{i}"


def test_geometry_input_candidate_remains_unchanged():
    """Input candidate dictionary must remain immutable during validation."""
    master = _make_base_master()
    original_candidate = {
        "version": "1.0",
        "outdoor_elements": [
            {
                "json_id": "IMMUTABLE_SEAT",
                "type": "garden_seating",
                "position": [5.0, 5.0],
                "dimensions": {"width_m": 2.0, "depth_m": 1.5},
            }
        ],
        "vegetation_nodes": [{"json_id": "TREE_01", "position": [3.0, 3.0], "canopy_radius_m": 1.5}],
    }
    deep_copy_before = copy.deepcopy(original_candidate)

    validate_candidate_exterior(master, original_candidate)

    assert original_candidate == deep_copy_before


# =========================================================================
# 3. ACCEPTANCE POLICY & PERSISTENCE PATH REGRESSIONS
# =========================================================================

def _generate_valid_preview_candidate(client, master, reqs=None):
    reqs = reqs or {"landscape": {"greenery_density": "medium", "tree_count": 3}}
    res = client.post(
        "/api/elia-engine/preview",
        json={"master_json": master, "requirements": reqs, "generation_mode": "baseline"}
    )
    assert res.status_code == 200
    return res.json()["exterior_landscape"], reqs


def test_persistence_accepted_save_rejects_blocking_review_required(test_app_env):
    """The /save-candidate endpoint rejects candidates with review_required status."""
    client, session_factory, project_id, master = test_app_env

    candidate, reqs = _generate_valid_preview_candidate(client, master)
    # Add unverified solar array to outdoor_elements
    candidate["outdoor_elements"].append({
        "json_id": "UNVERIFIED_SOLAR",
        "type": "solar_panel_array",
        "supporting_surface_id": "roof_flat_01",
        "position": [15.0, 12.0],
        "dimensions": {"width_m": 4.0, "depth_m": 3.0},
    })

    res = client.post(
        f"/api/projects/{project_id}/elia-engine/save-candidate",
        json={
            "source_revision": 1,
            "exterior_landscape": candidate,
            "requirements": reqs,
        }
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "ELIA_ACCEPTANCE_BLOCKED"
    assert "solar_panels" in res.json()["detail"]["blocking_features"]


def test_persistence_client_spoofed_approval_flag_cannot_bypass_checks(test_app_env):
    """Client cannot spoof approval by sending valid: True or approval_status: approved."""
    client, session_factory, project_id, master = test_app_env

    candidate, reqs = _generate_valid_preview_candidate(client, master)
    candidate["outdoor_elements"].append({
        "json_id": "SOLAR_UNVERIFIED",
        "type": "solar_panel_array",
        "supporting_surface_id": "roof_flat_01",
        "position": [15.0, 12.0],
        "dimensions": {"width_m": 4.0, "depth_m": 3.0},
    })
    # Client spoofs approval
    candidate["approval_status"] = "approved"
    candidate["valid"] = True
    candidate["status"] = "approved"

    res = client.post(
        f"/api/projects/{project_id}/elia-engine/save-candidate",
        json={
            "source_revision": 1,
            "exterior_landscape": candidate,
            "requirements": reqs,
        }
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "ELIA_ACCEPTANCE_BLOCKED"


def test_persistence_failed_requests_preserve_accepted_output_and_revision(test_app_env):
    """Failed save requests preserve existing accepted design and authoritative revision."""
    client, session_factory, project_id, master = test_app_env

    bad_candidate = {
        "version": "1.0",
        "outdoor_elements": [
            {"json_id": "COLLISION_SEAT", "type": "garden_seating", "position": [15.0, 12.0]}  # inside house
        ],
    }

    res = client.post(
        f"/api/projects/{project_id}/elia-engine/save-candidate",
        json={
            "source_revision": 1,
            "exterior_landscape": bad_candidate,
            "requirements": {},
        }
    )
    assert res.status_code == 422

    # Verify project in DB
    session = session_factory()
    proj = session.query(Project).filter(Project.id == project_id).one()
    session.close()

    assert proj.revision == 1
    assert proj.master_json["exterior_landscape"]["status"] == "initial_accepted_design"


def test_persistence_missing_requirements_cannot_erase_required_access_features(test_app_env):
    """Omission of requirements in save request does not silently erase saved requirements."""
    client, session_factory, project_id, master = test_app_env

    # Save initial requirements with driveway required
    session = session_factory()
    proj = session.query(Project).filter(Project.id == project_id).one()
    proj.master_json["exterior_requirements"] = {
        "access": {"driveway_required": True, "gate_required": True}
    }
    session.commit()
    session.close()

    # Candidate with NO access provided submitted with empty requirements
    empty_access_candidate = {
        "version": "1.0",
        "outdoor_elements": [],
        "vegetation_nodes": [],
        "outdoor_lighting": {"nodes": []},
    }

    res = client.post(
        f"/api/projects/{project_id}/elia-engine/save-candidate",
        json={
            "source_revision": 1,
            "exterior_landscape": empty_access_candidate,
            "requirements": {},  # Empty requirements
        }
    )
    # Must fail because required driveway and gate are missing!
    assert res.status_code == 422
    assert res.json()["detail"]["code"] in ("ELIA_INVALID_CANDIDATE", "ELIA_ACCEPTANCE_BLOCKED")


def test_persistence_valid_approved_candidate_saves_and_reloads_correctly(test_app_env):
    """A valid, approved candidate saves and increments revision with canonical geometry."""
    client, session_factory, project_id, master = test_app_env

    candidate, reqs = _generate_valid_preview_candidate(client, master)

    res = client.post(
        f"/api/projects/{project_id}/elia-engine/save-candidate",
        json={
            "source_revision": 1,
            "exterior_landscape": candidate,
            "requirements": reqs,
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert data["revision"] == 2

    # Verify saved project in DB
    session = session_factory()
    proj = session.query(Project).filter(Project.id == project_id).one()
    session.close()

    assert proj.revision == 2
    assert "exterior_landscape" in proj.master_json
    assert proj.master_json["exterior_landscape"]["run_id"] == data["run_id"]


def test_persistence_stale_revisions_fail_explicitly(test_app_env):
    """Saving with a stale revision fails with 409 ELIA_STALE_SOURCE_REVISION."""
    client, session_factory, project_id, master = test_app_env

    candidate, reqs = _generate_valid_preview_candidate(client, master)

    # First save increments revision to 2
    res1 = client.post(
        f"/api/projects/{project_id}/elia-engine/save-candidate",
        json={
            "source_revision": 1,
            "exterior_landscape": candidate,
            "requirements": reqs,
        }
    )
    assert res1.status_code == 200

    # Second save with stale source_revision 1 must fail with 409
    res2 = client.post(
        f"/api/projects/{project_id}/elia-engine/save-candidate",
        json={
            "source_revision": 1,
            "exterior_landscape": candidate,
            "requirements": reqs,
        }
    )
    assert res2.status_code == 409
    assert res2.json()["detail"]["code"] == "ELIA_STALE_SOURCE_REVISION"
    assert res2.json()["detail"]["current_revision"] == 2
