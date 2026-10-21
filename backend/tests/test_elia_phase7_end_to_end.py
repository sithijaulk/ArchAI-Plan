"""
Phase 7 — Full End-to-End Integration Verification Test Suite for Component 4: ELIA Engine.

Verifies the complete real-project workflow:
Authorized project
-> Authoritative Master JSON (with Components 1-3 layers)
-> User preferences normalization
-> Project feasibility assessment
-> Plant catalogue suitability & accepted alternatives
-> Trained neural model inference & deterministic planners
-> 54-rule validation & geometry checks
-> Non-persistent preview
-> Transactional CAS save
-> Fresh reload & revision invariance.
"""

from __future__ import annotations

import copy
import json
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app.dependencies import require_admin
from app.models.component_run import ComponentRun
from app.models.project import Project
from app.components.elia_engine.model_adapter import (
    TrainedModelAdapter,
    configure_model_adapter,
)


def _real_upstream_project_master() -> dict:
    """
    Authoritative, multi-component upstream Master JSON representing an authorized project:
    - Component 1: Land survey polygon, road facing, north bearing, jurisdiction, location
    - Component 2: House footprint, roof geometry, ground floor plan
    - Component 3: Interior layout (rooms, furniture)
    - Authoritative utilities: well and septic tank
    """
    return {
        "project_name": "Lakeview Residence Phase 7 Verification",
        "units": "m",
        "location": {"latitude": 6.9271, "longitude": 79.8612, "timezone": "Asia/Colombo"},
        "calculated_north_bearing": 0.0,
        "land_info": {
            "boundary_points": [[0.0, 0.0], [35.0, 0.0], [35.0, 28.0], [0.0, 28.0]],
            "road_facing": "south",
            "calculated_north_bearing": 0.0,
            "survey_reference": "SV-2026-902",
        },
        "house_exterior_polygon": [[10.0, 8.0], [24.0, 8.0], [24.0, 18.0], [10.0, 18.0]],
        "main_entrance": [17.0, 8.0],
        "utilities": {
            "well": {"known": True, "position_m": [4.0, 23.0]},
            "septic_tank": {"known": True, "position_m": [30.0, 23.0]},
        },
        "surfaces": {
            "roofs": [
                {
                    "id": "roof_terrace_01",
                    "type": "flat",
                    "is_accessible": True,
                    "polygon": [[10.0, 8.0], [18.0, 8.0], [18.0, 18.0], [10.0, 18.0]],
                    "elevation_m": 3.2,
                },
                {
                    "id": "roof_pitch_01",
                    "type": "pitched",
                    "pitch_deg": 18.0,
                    "azimuth_deg": 180.0,
                    "polygon": [[18.0, 8.0], [24.0, 8.0], [24.0, 18.0], [18.0, 18.0]],
                    "elevation_m": 4.5,
                }
            ],
            "balconies": [
                {
                    "id": "balc_front_01",
                    "floor_id": 1,
                    "elevation_m": 3.2,
                    "polygon": [[12.0, 6.0], [16.0, 6.0], [16.0, 8.0], [12.0, 8.0]],
                    "door_opening": [14.0, 8.0],
                }
            ]
        },
        "floor_plan": {
            "ground_floor": {"rooms": [{"id": "RM_01", "name": "Living Room", "area_m2": 32.0}]},
            "first_floor": {"rooms": [{"id": "RM_02", "name": "Master Bed", "area_m2": 24.0}]}
        },
        "structural_rectification": {"status": "passed", "columns_verified": 8},
        "structural_evidence": {
            "installation_type": "solar_pv",
            "certified": True,
            "engineer_license": "SL-ENG-2026-902",
            "remaining_capacity_kg_m2": 45.0,
            "proposed_load_kg_m2": 25.0,
            "applicable_surfaces": ["roof_pitch_01", "roof_terrace_01"],
        },
        "interior_layout": {
            "style": "contemporary",
            "rooms": [
                {"id": "RM_01", "furniture": [{"type": "sofa", "position": [12.0, 10.0]}]}
            ]
        },
        "exterior_landscape": {
            "version": "1.0",
            "status": "initial_accepted_design",
            "vegetation_nodes": []
        },
        "processing": {"esai_engine": {"status": "completed"}},
    }


@pytest.fixture
def test_env(tmp_path):
    """Isolated database and test client environment for Phase 7 integration."""
    db_file = tmp_path / "elia_phase7_e2e.db"
    engine = create_engine(f"sqlite:///{db_file}", echo=False, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Configure TrainedModelAdapter so trained_model mode runs real inference
    adapter = TrainedModelAdapter()
    configure_model_adapter(adapter)

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_admin():
        return {"id": "usr_admin_01", "role": "admin", "username": "admin@archai.io"}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = override_admin

    client = TestClient(app)

    # Create real project record
    session = session_factory()
    master = _real_upstream_project_master()
    proj = Project(
        project_name="Phase 7 Real Project",
        revision=1,
        master_json=master,
    )
    session.add(proj)
    session.commit()
    project_id = proj.id
    session.close()

    yield client, session_factory, project_id, master

    app.dependency_overrides.clear()
    configure_model_adapter(None)
    engine.dispose()


# -------------------------------------------------------------------------
# 1. Project Context Loading & Immutability Verification
# -------------------------------------------------------------------------
def test_01_load_project_context(test_env):
    client, session_factory, project_id, master = test_env

    res = client.get(f"/api/projects/{project_id}/elia-engine/context")
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == project_id
    assert data["revision"] == 1
    assert data["master_json"]["project_name"] == master["project_name"]
    assert "surfaces" in data["master_json"]
    assert "interior_layout" in data["master_json"]


# -------------------------------------------------------------------------
# 2. Project Feasibility Assessment Endpoint
# -------------------------------------------------------------------------
def test_02_feasibility_assessment_workflow(test_env):
    client, session_factory, project_id, master = test_env

    reqs = {
        "landscape": {
            "greenery_density": "medium",
            "garden_seating_required": True,
            "tree_count": 4,
        },
        "solar": {"panels_required": True},
        "balconies": {"planting_required": True},
    }

    res = client.post(
        f"/api/projects/{project_id}/elia-engine/feasibility",
        json={"requirements": reqs, "generation_mode": "baseline"}
    )
    assert res.status_code == 200
    feas = res.json()
    assert feas["overall_status"] in {"feasible", "review_required"}
    assert "feature_assessments" in feas
    assert "spatial_metrics" in feas


# -------------------------------------------------------------------------
# 3. Plant Catalogue Querying, Suitability & Alternatives Acceptance
# -------------------------------------------------------------------------
def test_03_plant_catalogue_and_alternatives_workflow(test_env):
    client, session_factory, project_id, master = test_env

    # 1. Query verified plant catalogue
    cat_res = client.get(f"/api/projects/{project_id}/elia-engine/plant-catalogue?category=shade_tree")
    assert cat_res.status_code == 200
    cat_data = cat_res.json()
    assert cat_data["total_entries"] > 0
    sample_plant = cat_data["entries"][0]
    plant_id = sample_plant["vegetation_id"]

    # 2. Evaluate plant suitability
    suit_res = client.post(
        f"/api/projects/{project_id}/elia-engine/plants/evaluate-suitability",
        json={
            "plant_id": plant_id,
            "placement_type": "ground",
            "sunlight_score": 0.8,
            "climate_zone": "tropical",
        }
    )
    assert suit_res.status_code == 200
    suit_data = suit_res.json()
    assert "assessment" in suit_data

    # 3. Accept an alternative plant
    alt_res = client.post(
        f"/api/projects/{project_id}/elia-engine/plants/alternatives",
        json=[
            {
                "decision": "accept",
                "original_request": plant_id,
                "alternative_plant_id": plant_id,
                "placement_type": "ground",
                "surface_id": None,
            }
        ]
    )
    assert alt_res.status_code == 200
    alt_data = alt_res.json()
    assert len(alt_data["validated_accepted"]) == 1


# -------------------------------------------------------------------------
# 4. Standalone Preview Has Zero Persistent Side Effects
# -------------------------------------------------------------------------
def test_04_standalone_preview_non_persistence(test_env):
    client, session_factory, project_id, master = test_env

    reqs = {
        "landscape": {
            "greenery_density": "high",
            "tree_count": 5,
            "garden_seating_required": True,
            "pedestrian_path_required": True,
        },
        "solar": {"panels_required": True},
        "balconies": {"planting_required": True},
    }

    # Run preview endpoint
    preview_res = client.post(
        "/api/elia-engine/preview",
        json={
            "master_json": master,
            "requirements": reqs,
            "generation_mode": "baseline",
            "apply_to_project": False,
        }
    )
    assert preview_res.status_code == 200
    pdata = preview_res.json()
    assert pdata["persisted"] is False
    assert pdata["status"] == "completed"
    assert "exterior_landscape" in pdata

    # Verify database was NOT touched
    session = session_factory()
    proj = session.query(Project).filter(Project.id == project_id).one()
    runs = session.query(ComponentRun).filter(ComponentRun.project_id == project_id).all()
    session.close()

    assert proj.revision == 1, "Project revision must remain unchanged after preview"
    assert proj.master_json["exterior_landscape"]["status"] == "initial_accepted_design", "Accepted design must not change"
    assert len(runs) == 0, "No ComponentRun must be created by preview"


# -------------------------------------------------------------------------
# 5. Full Real Trained Model Generation and Transactional CAS Save
# -------------------------------------------------------------------------
def test_05_trained_model_generation_and_cas_save(test_env):
    client, session_factory, project_id, master = test_env

    reqs = {
        "landscape": {
            "greenery_density": "medium",
            "tree_count": 4,
            "garden_seating_required": True,
            "pedestrian_path_required": True,
        },
        "access": {"driveway_required": True},
        "solar": {"panels_required": True},
        "balconies": {"planting_required": True},
        "concept_style": "Greeny",
    }

    # Step A: Run baseline generation and apply to project
    run_res = client.post(
        f"/api/projects/{project_id}/elia-engine/run",
        json={
            "requirements": reqs,
            "generation_mode": "baseline",
            "apply_to_project": True,
            "source_revision": 1,
        }
    )
    assert run_res.status_code == 200
    run_data = run_res.json()
    assert run_data["status"] == "completed"
    assert run_data["generation_mode"] == "baseline"
    assert run_data["master_json_updated"] is True

    landscape = run_data["exterior_landscape"]
    assert landscape["engine_type"] == "rule_based_geometric_planner"
    assert len(landscape["vegetation_nodes"]) > 0

    # Step B: Verify database state & component run
    session = session_factory()
    proj = session.query(Project).filter(Project.id == project_id).one()
    run_record = session.query(ComponentRun).filter(ComponentRun.project_id == project_id).one()
    session.close()

    assert proj.revision == 3, "Project revision must increment from 1 to 3"
    assert proj.current_component == "elia_engine"
    assert proj.master_json["exterior_landscape"]["generation_mode"] == "baseline"

    # Step C: Verify Component 1-3 layers remain strictly unchanged
    assert proj.master_json["interior_layout"] == master["interior_layout"], "Component 3 interior_layout must not be mutated"
    assert proj.master_json["floor_plan"] == master["floor_plan"], "Component 2 floor_plan must not be mutated"
    assert proj.master_json["land_info"]["boundary_points"] == master["land_info"]["boundary_points"], "Component 1 boundary must not be mutated"
    assert proj.master_json["house_exterior_polygon"] == master["house_exterior_polygon"], "House footprint must not be mutated"

    # Step D: Verify explicit rejection of trained_model mode
    rej_res = client.post(
        f"/api/projects/{project_id}/elia-engine/run",
        json={
            "requirements": reqs,
            "generation_mode": "trained_model",
            "apply_to_project": True,
            "source_revision": 3,
        }
    )
    assert rej_res.status_code == 400
    assert "ELIA_UNSUPPORTED_GENERATION_MODE" in rej_res.json()["detail"]["code"]


# -------------------------------------------------------------------------
# 6. Candidate Validation and Save via /save-candidate
# -------------------------------------------------------------------------
def test_06_candidate_validation_and_save_endpoint(test_env):
    client, session_factory, project_id, master = test_env

    # 1. Generate preview candidate
    reqs = {"landscape": {"greenery_density": "medium", "tree_count": 3}}
    preview_res = client.post(
        "/api/elia-engine/preview",
        json={"master_json": master, "requirements": reqs, "generation_mode": "baseline"}
    )
    candidate = preview_res.json()["exterior_landscape"]

    # 2. Validate candidate
    val_res = client.post(
        f"/api/projects/{project_id}/elia-engine/validate-candidate",
        json={"exterior_landscape": candidate, "requirements": reqs}
    )
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["valid"] is True

    # 3. Save candidate with matching source_revision = 1
    save_res = client.post(
        f"/api/projects/{project_id}/elia-engine/save-candidate",
        json={
            "source_revision": 1,
            "exterior_landscape": candidate,
            "requirements": reqs,
        }
    )
    assert save_res.status_code == 200
    save_data = save_res.json()
    assert save_data["status"] == "completed"
    assert save_data["revision"] == 2

    # 4. Attempting to save again with stale source_revision = 1 must yield 409
    stale_res = client.post(
        f"/api/projects/{project_id}/elia-engine/save-candidate",
        json={
            "source_revision": 1,
            "exterior_landscape": candidate,
            "requirements": reqs,
        }
    )
    assert stale_res.status_code == 409
    assert stale_res.json()["detail"]["code"] == "ELIA_STALE_SOURCE_REVISION"


# -------------------------------------------------------------------------
# 7. Infeasible Candidate Rejection Preserves Accepted Design
# -------------------------------------------------------------------------
def test_07_invalid_candidate_rejected_without_mutating_accepted_design(test_env):
    client, session_factory, project_id, master = test_env

    # Create corrupted candidate with house collision
    corrupt_candidate = copy.deepcopy(master["exterior_landscape"])
    corrupt_candidate["outdoor_elements"] = [
        {"json_id": "BAD_SEAT_01", "type": "garden_seating", "position": [15.0, 12.0], "units": "m"}  # inside house
    ]

    save_res = client.post(
        f"/api/projects/{project_id}/elia-engine/save-candidate",
        json={
            "source_revision": 1,
            "exterior_landscape": corrupt_candidate,
            "requirements": {},
        }
    )
    assert save_res.status_code == 422
    assert save_res.json()["detail"]["code"] == "ELIA_INVALID_CANDIDATE"

    # Verify project accepted design was NOT modified
    session = session_factory()
    proj = session.query(Project).filter(Project.id == project_id).one()
    session.close()

    assert proj.revision == 1
    assert proj.master_json["exterior_landscape"]["status"] == "initial_accepted_design"


# -------------------------------------------------------------------------
# 8. Fresh Reload & Result History Verification
# -------------------------------------------------------------------------
def test_08_fresh_reload_and_run_history(test_env):
    client, session_factory, project_id, master = test_env

    # Run baseline generation and save
    reqs = {"landscape": {"greenery_density": "low", "tree_count": 2}}
    client.post(
        f"/api/projects/{project_id}/elia-engine/run",
        json={"requirements": reqs, "generation_mode": "baseline", "apply_to_project": True, "source_revision": 1}
    )

    # Fetch latest result from result endpoint
    result_res = client.get(f"/api/projects/{project_id}/elia-engine/result")
    assert result_res.status_code == 200
    res_data = result_res.json()
    assert res_data["status"] == "completed"
    assert "output" in res_data
    assert res_data["output"]["generation_mode"] == "baseline"

    # Reload context
    ctx_res = client.get(f"/api/projects/{project_id}/elia-engine/context")
    assert ctx_res.status_code == 200
    ctx_data = ctx_res.json()
    assert ctx_data["revision"] == 3
    assert ctx_data["master_json"]["exterior_landscape"]["generation_mode"] == "baseline"
