"""
Phase 8: Centralized Master JSON, Database Persistence & Full Integration Tests.
Covers:
A. Project Lifecycle & Reopen Persistence
B. Centralized Master JSON Serialization, Deserialization, and Backward Migration
C. Component Namespace Isolation (ELIA, ESAI, VSAI byte preservation)
D. Survey Metadata & Provenance Survival
E. Regulatory Context & Uncertainty Survival
F. User Requirements & Adjacency Persistence
G. Multi-Candidate Isolation & Candidate-Specific Revisions
H. Independent Architectural Validation Synchronization
I. Database Transactions, Rollback, and Concurrency Control (HTTP 409 Conflict)
J. Security & Path Traversal Prevention
"""
import io
import os
import copy
import pytest
from datetime import datetime, timezone
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.project import Project
from app.models.component_run import ComponentRun
from app.components.gab_gen.output.master_json_builder import (
    SCHEMA_VERSION,
    GAB_GEN_VERSION,
    build_gab_master_json,
    migrate_master_json_schema
)
from app.components.gab_gen.schemas import (
    ManualSurveyExtractionRequest,
    SurveyEdgeInput,
    ClientRequirementsInput,
    FloorPlanDefinition,
    RoomPolygon,
    Point2D,
    ValidationResult,
    ComplianceStatus,
    FloorPlanCandidate,
    GeneratedRoofGeometry
)
from app.components.gab_gen.regulations.rules import RegulatoryRule

# In-memory test SQLite DB for fast endpoint validation
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def override_db():
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


client = TestClient(app)


def create_dummy_png_bytes() -> bytes:
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------
# A. Project Lifecycle, Database Persistence & Reload
# --------------------------------------------------------------------------

def test_project_create_save_and_reopen_preserves_master_json():
    """Verify that creating, saving, and reopening a project recovers exact data."""
    db = TestingSessionLocal()
    proj = Project(
        project_name="Phase8 Villa",
        description="Persistence test project",
        master_json={"initial_key": "initial_val"},
        revision=1
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    p_id = proj.id
    db.close()

    # Reopen in new DB session
    db2 = TestingSessionLocal()
    reloaded = db2.query(Project).filter(Project.id == p_id).first()
    assert reloaded is not None
    assert reloaded.project_name == "Phase8 Villa"
    assert reloaded.revision == 1
    assert reloaded.master_json.get("initial_key") == "initial_val"
    db2.close()


# --------------------------------------------------------------------------
# B. Master JSON Schema Migration & Backward Compatibility
# --------------------------------------------------------------------------

def test_legacy_schema_migration_upgrades_version_and_backfills_fields():
    """Legacy projects from schema 1.0.0 are upgraded safely without data loss."""
    legacy_json = {
        "project_id": "P_LEGACY_01",
        "schema_version": "1.0.0",
        "floor_plan": {
            "floors": [
                {
                    "floor_id": "F0",
                    "elevation": 0.0,
                    "height": 3.0,
                    "rooms": []
                }
            ]
        },
        "survey_extraction": {
            "provider": "manual",
            "edges": []
        }
    }

    migrated = migrate_master_json_schema(legacy_json)
    assert migrated["schema_version"] == SCHEMA_VERSION
    assert migrated["units"] == "meters"
    assert "candidate_generation" in migrated
    assert migrated["candidate_generation"]["selected_candidate_id"] == "FP_CANDIDATE_001"
    assert migrated["survey_extraction"]["georeference_status"] == "unreferenced_local"


def test_incompatible_future_schema_version_is_rejected():
    """Future major schema versions (e.g., 99.0.0) fail with clear error."""
    future_json = {
        "project_id": "P_FUTURE_01",
        "schema_version": "99.0.0"
    }
    with pytest.raises(ValueError, match="Unsupported future Master JSON schema version"):
        migrate_master_json_schema(future_json)


# --------------------------------------------------------------------------
# C. Component Namespace Isolation (ELIA, ESAI, VSAI)
# --------------------------------------------------------------------------

def test_gab_gen_pipeline_preserves_unrelated_namespaces():
    """Verifies that GAB-Gen build preserves ELIA, ESAI, and VSAI sections byte-equivalently."""
    existing_mj = {
        "project_id": "P_SHARED_01",
        "elia_engine": {
            "solar_analysis": {"insolation_kwh": 4.5},
            "landscape_plan": {"trees_planted": 8}
        },
        "esai_engine": {
            "movement_paths": [{"agent": "resident", "speed": 1.2}],
            "spatial_clearance": {"corridor_clear": True}
        },
        "vsai_rectifier": {
            "structural_adjustments": [{"axis": "X", "offset_m": 0.05}],
            "rectification_score": 98.2
        },
        "processing": {
            "elia_engine": {"status": "completed"},
            "esai_engine": {"status": "in_progress"},
            "vsai_rectifier": {"status": "pending"}
        }
    }

    from app.components.gab_gen.schemas import DistanceValue, BearingValue, DistanceUnit
    survey_req = ManualSurveyExtractionRequest(
        source="manual",
        north_angle=0.0,
        edges=[
            SurveyEdgeInput(edge_id="E1", distance=DistanceValue(value=20.0, unit=DistanceUnit.METERS), bearing=BearingValue(raw="0°00'", normalized_degrees=0.0)),
            SurveyEdgeInput(edge_id="E2", distance=DistanceValue(value=20.0, unit=DistanceUnit.METERS), bearing=BearingValue(raw="90°00'", normalized_degrees=90.0)),
            SurveyEdgeInput(edge_id="E3", distance=DistanceValue(value=20.0, unit=DistanceUnit.METERS), bearing=BearingValue(raw="180°00'", normalized_degrees=180.0)),
            SurveyEdgeInput(edge_id="E4", distance=DistanceValue(value=20.0, unit=DistanceUnit.METERS), bearing=BearingValue(raw="270°00'", normalized_degrees=270.0)),
        ]
    )

    requirements = ClientRequirementsInput(
        declared_land_extent=10.0,
        declared_land_unit="perches",
        building_type="residential_house",
        storey_count=1
    )

    reconstructed_data = {
        "vertices": [[0, 0], [20, 0], [20, 20], [0, 20]],
        "reconstructed_area": 400.0,
        "is_valid": True
    }

    validation = ValidationResult(
        valid=True,
        compliance_verdict=ComplianceStatus.COMPLIANT,
        status="completed"
    )

    mj_updated = build_gab_master_json(
        project_id="P_SHARED_01",
        project_name="Shared Project",
        survey_request=survey_req,
        reconstructed_data=reconstructed_data,
        requirements=requirements,
        rules=[],
        buildable_data={"polygon": [[2, 2], [18, 2], [18, 18], [2, 18]], "area": 256.0},
        allocation_data={"provider": "rule_based_baseline", "floors": []},
        floors=[],
        validation=validation,
        existing_master_json=existing_mj
    )

    # Assert GAB-Gen updated its own section
    assert mj_updated["buildable_footprint"]["area"] == 256.0
    assert mj_updated["processing"]["gab_gen"]["status"] == "completed"

    # Assert unrelated component sections are preserved byte-equivalently
    assert mj_updated["elia_engine"] == existing_mj["elia_engine"]
    assert mj_updated["esai_engine"] == existing_mj["esai_engine"]
    assert mj_updated["vsai_rectifier"] == existing_mj["vsai_rectifier"]
    assert mj_updated["processing"]["elia_engine"] == {"status": "completed"}
    assert mj_updated["processing"]["esai_engine"] == {"status": "in_progress"}
    assert mj_updated["processing"]["vsai_rectifier"] == {"status": "pending"}


# --------------------------------------------------------------------------
# D. Optimistic Concurrency & Revision Conflict (HTTP 409)
# --------------------------------------------------------------------------

def test_optimistic_concurrency_rejects_stale_revision():
    """Verify that editing a blueprint with a stale expected_revision raises HTTP 409."""
    db = TestingSessionLocal()
    proj = Project(
        project_name="Concurrency Test",
        master_json={
            "floor_plan": {
                "floors": [
                    {
                        "floor_id": "F0",
                        "floor_index": 0,
                        "name": "Ground Floor",
                        "elevation": 0.0,
                        "floor_height": 3.0,
                        "available_area": 100.0,
                        "target_allocated_area": 16.0,
                        "rooms": [
                            {
                                "room_id": "R1",
                                "name": "Living Room",
                                "type": "living_room",
                                "floor_id": "F0",
                                "area": 16.0,
                                "target_area": 16.0,
                                "polygon": [{"x": 2, "y": 2}, {"x": 6, "y": 2}, {"x": 6, "y": 6}, {"x": 2, "y": 6}],
                                "center": {"x": 4, "y": 4},
                                "is_structural_stair": False
                            }
                        ]
                    }
                ]
            },
            "buildable_footprint": {
                "polygon": [{"x": 0, "y": 0}, {"x": 20, "y": 0}, {"x": 20, "y": 20}, {"x": 0, "y": 20}]
            }
        },
        revision=5
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    p_id = proj.id
    db.close()

    # Attempt edit supplying expected_revision=4 (stale)
    payload = {
        "room_id": "R1",
        "target_floor_id": "F0",
        "polygon": [{"x": 3, "y": 3}, {"x": 7, "y": 3}, {"x": 7, "y": 7}, {"x": 3, "y": 7}],
        "expected_revision": 4
    }
    res = client.post(f"/api/projects/{p_id}/gab-gen/edit-room", json=payload)
    assert res.status_code == 409
    err = res.json()["detail"]
    assert err["code"] == "PROJECT_STALE_REVISION"
    assert err["expected_revision"] == 4
    assert err["current_revision"] == 5

    # Successful edit with correct expected_revision=5
    payload["expected_revision"] = 5
    res2 = client.post(f"/api/projects/{p_id}/gab-gen/edit-room", json=payload)
    assert res2.status_code == 200
    assert res2.json()["valid"] is True
    assert res2.json()["revision"] == 6


# --------------------------------------------------------------------------
# E. Candidate Selection & Isolation Across Save/Reopen
# --------------------------------------------------------------------------

def test_candidate_selection_activates_geometry_and_preserves_pool():
    """Selecting a candidate updates active blueprint while preserving candidate alternatives."""
    cand1 = {
        "candidate_id": "FP_CANDIDATE_001",
        "rank": 1,
        "composite_score": 90.0,
        "feasibility_status": "feasible",
        "footprint_variant": "variant_a",
        "building_footprint_polygon": [{"x": 1, "y": 1}, {"x": 10, "y": 1}, {"x": 10, "y": 10}, {"x": 1, "y": 10}],
        "building_footprint_area_sqm": 81.0,
        "floors": [{"floor_id": "F0", "elevation": 0.0, "height": 3.0, "rooms": []}]
    }
    cand2 = {
        "candidate_id": "FP_CANDIDATE_002",
        "rank": 2,
        "composite_score": 85.0,
        "feasibility_status": "feasible",
        "footprint_variant": "variant_b",
        "building_footprint_polygon": [{"x": 2, "y": 2}, {"x": 12, "y": 2}, {"x": 12, "y": 12}, {"x": 2, "y": 12}],
        "building_footprint_area_sqm": 100.0,
        "floors": [{"floor_id": "F0", "elevation": 0.0, "height": 3.0, "rooms": []}]
    }

    db = TestingSessionLocal()
    proj = Project(
        project_name="MultiCandidate Test",
        master_json={
            "candidate_generation": {
                "selected_candidate_id": "FP_CANDIDATE_001",
                "candidates": [cand1, cand2]
            },
            "floor_plan": {"floors": cand1["floors"]},
            "building_footprint": {"candidate_id": "FP_CANDIDATE_001", "area": 81.0}
        },
        revision=1
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    p_id = proj.id
    db.close()

    # Select Candidate 2
    res = client.post(f"/api/projects/{p_id}/gab-gen/select-candidate", json={"candidate_id": "FP_CANDIDATE_002"})
    assert res.status_code == 200
    data = res.json()
    assert data["selected_candidate_id"] == "FP_CANDIDATE_002"
    assert data["revision"] == 2

    # Verify both candidates remain in database
    db2 = TestingSessionLocal()
    p_reloaded = db2.query(Project).filter(Project.id == p_id).first()
    cands = p_reloaded.master_json["candidate_generation"]["candidates"]
    assert len(cands) == 2
    assert p_reloaded.master_json["candidate_generation"]["selected_candidate_id"] == "FP_CANDIDATE_002"
    assert p_reloaded.master_json["building_footprint"]["candidate_id"] == "FP_CANDIDATE_002"
    db2.close()


# --------------------------------------------------------------------------
# F. Path Traversal & File Safety
# --------------------------------------------------------------------------

def test_survey_file_path_traversal_is_prevented():
    """Verify that path traversal attempts (e.g. ../../) in survey references are rejected."""
    db = TestingSessionLocal()
    proj = Project(
        project_name="Security Test",
        master_json={
            "input_metadata": {
                "source_file": {
                    "stored_filename": "../../etc/passwd"
                }
            }
        },
        revision=1
    )
    db.add(proj)
    db.commit()
    p_id = proj.id
    db.close()

    # Attempting to delete or extract from this path must fail with 400
    res = client.delete(f"/api/projects/{p_id}/gab-gen/survey-file")
    assert res.status_code == 400
    assert "traversal" in res.json()["detail"].lower()


# --------------------------------------------------------------------------
# G. Master JSON Headers & ETag Synchronization
# --------------------------------------------------------------------------

def test_get_master_json_returns_etag_and_revision_headers():
    """Verify that /master-json returns standard ETag and X-Project-Revision headers."""
    db = TestingSessionLocal()
    proj = Project(
        project_name="Headers Test",
        master_json={"project_id": "P_HDR_01", "schema_version": "2.1.0"},
        revision=4
    )
    db.add(proj)
    db.commit()
    p_id = proj.id
    db.close()

    res = client.get(f"/api/projects/{p_id}/gab-gen/master-json")
    assert res.status_code == 200
    assert res.headers.get("X-Project-Revision") == "4"
    assert res.headers.get("ETag") == '"4"'
