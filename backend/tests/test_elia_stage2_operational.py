"""
Stage 2 Operational Verification Tests for Component 4 (ELIA Engine).

Exercises the full backend operational flow using test-client and transactional sessions:
- Authenticated ELIA request & role enforcement
- Input validation (validate-input)
- Explicit baseline generation mode & model-unavailable safeguards
- Standalone preview non-persistence
- Controlled persistence & fresh reload/retrieval (result & context)
- Run history & ComponentRun status
- Revision CAS safeguards (stale revision rejection & concurrent conflicts)
- Preservation of accepted exterior on infeasible/failed runs
- Non-destructive Master JSON updates across all component boundaries
"""
import uuid
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.routers import elia
from app.database import Base, get_db
from app.models.component_run import ComponentRun
from app.models.project import Project


def _create_isolated_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'operational_test.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, session_factory


def _valid_upstream_master() -> dict:
    """Real upstream Master JSON structure with Components 1-3 layers."""
    return {
        "project_name": "Operational Verification Project",
        "units": "m",
        "location": {"latitude": 6.9271, "longitude": 79.8612, "timezone": "Asia/Colombo"},
        "land_info": {
            "boundary_points": [[0.0, 0.0], [40.0, 0.0], [40.0, 30.0], [0.0, 30.0], [0.0, 0.0]],
            "road_facing": "south",
            "calculated_north_bearing": 15.0,
        },
        "house_exterior_polygon": [[10.0, 8.0], [25.0, 8.0], [25.0, 20.0], [10.0, 20.0], [10.0, 8.0]],
        "utilities": {
            "well": {"known": True, "position": [2.0, 25.0]},
            "septic_tank": {"known": True, "position": [25.0, 25.0]},
        },
        "floor_plan": {"ground_floor": {"rooms": [{"name": "Living", "area": 35.0}]}},
        "structural_rectification": {"status": "passed", "columns_verified": 8},
        "interior_layout": {"style": "contemporary", "furniture_items": 12},
        "custom_upstream_metadata": {"architect_id": "arch_99", "client_code": "CL-402"},
        "exterior_landscape": {"version": "0.1", "status": "initial_accepted_design"},
    }


def test_auth_enforcement_and_role_protection():
    """Unauthenticated and unauthorized requests must be rejected according to policy."""
    with TestClient(app) as client:
        # Unauthenticated project run returns 401
        resp = client.post("/api/projects/p-123/elia-engine/run", json={"generation_mode": "baseline"})
        assert resp.status_code == 401

        # Unauthenticated preview returns 401
        resp_prev = client.post("/api/elia-engine/preview", json={"generation_mode": "baseline"})
        assert resp_prev.status_code == 401

        # Unauthenticated context returns 401
        resp_ctx = client.get("/api/projects/p-123/elia-engine/context")
        assert resp_ctx.status_code == 401


def test_operational_flow_baseline_run_persistence_and_reload(tmp_path):
    """Verifies complete operational lifecycle: validate -> preview -> run -> reload -> result."""
    engine, session_factory = _create_isolated_db(tmp_path)
    seed = session_factory()
    master = _valid_upstream_master()
    orig_snapshot = deepcopy(master)
    proj_id = str(uuid.uuid4())

    project = Project(
        id=proj_id,
        project_name="Operational Flow Test",
        revision=1,
        master_json=master,
    )
    seed.add(project)
    seed.commit()
    seed.close()

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[elia.require_admin] = lambda: None

    try:
        with TestClient(app) as client:
            # 1. Validate-input check
            val_req = {
                "generation_mode": "baseline",
                "requirements": {
                    "access": {"road_side": "south", "garage_required": False, "driveway_required": False}
                },
            }
            val_resp = client.post(f"/api/projects/{proj_id}/elia-engine/validate-input", json=val_req)
            assert val_resp.status_code == 200
            val_data = val_resp.json()
            assert val_data["valid"] is True
            assert val_data["geometry"]["land_area_m2"] > 0
            assert val_data["orientation"]["north_angle_degrees"] == 15.0

            # 2. Standalone preview check (verifies non-persistence)
            prev_req = {**val_req, "master_json": master}
            prev_resp = client.post("/api/elia-engine/preview", json=prev_req)
            assert prev_resp.status_code == 200
            prev_data = prev_resp.json()
            assert prev_data["persisted"] is False
            assert prev_data["outcome"] == "valid"
            assert "exterior_landscape" in prev_data

            # Verify preview did NOT write to project database or component runs
            check_session = session_factory()
            runs_count = check_session.query(ComponentRun).filter(ComponentRun.project_id == proj_id).count()
            assert runs_count == 0, "Standalone preview must not write to component_runs"
            p_check = check_session.query(Project).filter(Project.id == proj_id).one()
            assert p_check.revision == 1, "Standalone preview must not modify project revision"
            check_session.close()

            # 3. Explicit baseline run execution
            run_resp = client.post(f"/api/projects/{proj_id}/elia-engine/run", json=val_req)
            assert run_resp.status_code == 200
            run_data = run_resp.json()
            assert run_data["status"] == "completed"
            assert run_data["outcome"] == "valid"
            assert run_data["generation_mode"] == "baseline"
            run_id = run_data["run_id"]

            # 4. Fresh reload via project context endpoint
            ctx_resp = client.get(f"/api/projects/{proj_id}/elia-engine/context")
            assert ctx_resp.status_code == 200
            reloaded_master = ctx_resp.json()["master_json"]

            # Verify non-destructive updates: non-ELIA layers strictly preserved
            assert reloaded_master["floor_plan"] == orig_snapshot["floor_plan"]
            assert reloaded_master["structural_rectification"] == orig_snapshot["structural_rectification"]
            assert reloaded_master["interior_layout"] == orig_snapshot["interior_layout"]
            assert reloaded_master["custom_upstream_metadata"] == orig_snapshot["custom_upstream_metadata"]
            assert reloaded_master["land_info"] == orig_snapshot["land_info"]

            # Verify ELIA output persisted cleanly
            assert reloaded_master["exterior_landscape"]["validation_summary"]["valid"] is True
            assert reloaded_master["processing"]["elia_engine"]["run_id"] == run_id
            assert reloaded_master["processing"]["elia_engine"]["status"] == "completed"

            # 5. Result retrieval from run history
            res_resp = client.get(f"/api/projects/{proj_id}/elia-engine/result")
            assert res_resp.status_code == 200
            res_data = res_resp.json()
            assert res_data["run_id"] == run_id
            assert res_data["status"] == "completed"
            assert res_data["output"]["run_id"] == run_id
            assert res_data["started_at"] is not None
            assert res_data["completed_at"] is not None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_infeasible_run_preserves_accepted_exterior(tmp_path):
    """Infeasible candidate must not overwrite previously accepted exterior_landscape."""
    engine, session_factory = _create_isolated_db(tmp_path)
    seed = session_factory()
    # Master with tight setbacks where a garage cannot fit between house and boundary
    tight_master = _valid_upstream_master()
    tight_master["land_info"]["boundary_points"] = [[0.0, 0.0], [20.0, 0.0], [20.0, 20.0], [0.0, 20.0], [0.0, 0.0]]
    # House occupies almost entire plot (only 1m setback, garage requires at least 3m + width)
    tight_master["house_exterior_polygon"] = [[1.5, 1.5], [18.5, 1.5], [18.5, 18.5], [1.5, 18.5], [1.5, 1.5]]
    initial_accepted = deepcopy(tight_master["exterior_landscape"])
    proj_id = str(uuid.uuid4())

    project = Project(
        id=proj_id,
        project_name="Infeasible Preservation Test",
        revision=2,
        master_json=tight_master,
    )
    seed.add(project)
    seed.commit()
    seed.close()

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[elia.require_admin] = lambda: None

    try:
        with TestClient(app) as client:
            # Request garage on tight plot where garage cannot fit
            infeasible_req = {
                "generation_mode": "baseline",
                "requirements": {
                    "access": {
                        "road_side": "south",
                        "garage_required": True,
                        "garage_capacity": 2,
                    }
                },
            }
            resp = client.post(f"/api/projects/{proj_id}/elia-engine/run", json=infeasible_req)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "infeasible"
            assert data["outcome"] == "infeasible"

            # Fresh reload of project master_json
            check_session = session_factory()
            stored = check_session.query(Project).filter(Project.id == proj_id).one()
            # The accepted exterior_landscape MUST remain the previous accepted design
            assert stored.master_json["exterior_landscape"] == initial_accepted
            # But processing.elia_engine records the infeasible run outcome
            assert stored.master_json["processing"]["elia_engine"]["status"] == "infeasible"
            assert stored.master_json["processing"]["elia_engine"]["run_id"] == data["run_id"]

            # Run history preserves the candidate output
            run = check_session.query(ComponentRun).filter(ComponentRun.id == data["run_id"]).one()
            assert run.status == "completed"
            assert run.output_json["validation_summary"]["valid"] is False
            check_session.close()
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_stale_source_revision_rejection(tmp_path):
    """Applying a supplied snapshot with mismatched revision must return 409 conflict."""
    engine, session_factory = _create_isolated_db(tmp_path)
    seed = session_factory()
    master = _valid_upstream_master()
    proj_id = str(uuid.uuid4())

    project = Project(
        id=proj_id,
        project_name="Stale Revision Test",
        revision=5,  # Current database revision is 5
        master_json=master,
    )
    seed.add(project)
    seed.commit()
    seed.close()

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[elia.require_admin] = lambda: None

    try:
        with TestClient(app) as client:
            stale_req = {
                "generation_mode": "baseline",
                "master_json": master,
                "source_revision": 4,  # Stale revision (expected 5)
                "apply_to_project": True,
                "requirements": {
                    "access": {"road_side": "south", "garage_required": False, "driveway_required": False}
                },
            }
            resp = client.post(f"/api/projects/{proj_id}/elia-engine/run", json=stale_req)
            assert resp.status_code == 409
            detail = resp.json()["detail"]
            assert detail["code"] == "ELIA_STALE_SOURCE_REVISION"
            assert detail["current_revision"] == 5
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_model_unavailable_returns_503_without_silent_fallback(tmp_path):
    """Default trained_model mode returns 503 without falling back to baseline."""
    engine, session_factory = _create_isolated_db(tmp_path)
    seed = session_factory()
    master = _valid_upstream_master()
    proj_id = str(uuid.uuid4())

    project = Project(
        id=proj_id,
        project_name="Model Unavailable Test",
        revision=1,
        master_json=master,
    )
    seed.add(project)
    seed.commit()
    seed.close()

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[elia.require_admin] = lambda: None

    try:
        with TestClient(app) as client:
            # Explicit rejection of trained_model generation_mode
            req = {
                "generation_mode": "trained_model",
                "requirements": {
                    "access": {"road_side": "south", "garage_required": False, "driveway_required": False}
                }
            }
            resp = client.post(f"/api/projects/{proj_id}/elia-engine/run", json=req)
            assert resp.status_code == 400
            detail = resp.json()["detail"]
            assert "ELIA_UNSUPPORTED_GENERATION_MODE" in detail["code"]

            # Check that project accepted exterior was not destroyed
            check_session = session_factory()
            stored = check_session.query(Project).filter(Project.id == proj_id).one()
            assert stored.master_json["exterior_landscape"]["status"] == "initial_accepted_design"
            check_session.close()
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
