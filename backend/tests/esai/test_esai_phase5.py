"""
Phase 5 Automated Test Suite: Safe Master JSON Persistence, Revision Control & Selective Regeneration
Verifies:
1. Upstream Master JSON preservation (geometry, Vastu, ELIA landscape, custom extensions).
2. Two-stage generation and atomic persistence.
3. Selective room-level regeneration (unrelated rooms and floors remain untouched).
4. Selective floor-level regeneration.
5. Building-level regeneration with partial failure policy.
6. Geometry staleness conflict detection & rejection.
7. Preference staleness conflict detection & rejection.
8. Optimistic concurrency and design revision conflict rejection.
9. Invalid / infeasible layout save rejection.
10. Valid alternative selection & atomic layout activation.
11. Complete MEP and surface finishes persistence inside Master JSON.
12. Staleness audit API and reporting.
13. Full REST API integration (/run, /designs/save, /regenerate, /select-alternative, /designs/staleness).
"""
from copy import deepcopy
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.dependencies import require_admin
from app.main import app as fastapi_app
from app.models.project import Project
from app.models.esai import EsaiRoomPreference
from app.components.esai_engine.contracts import (
    Coordinate2D,
    Dimensions3D,
    GeneratedBuildingDesignDTO,
    GeneratedRoomDesignDTO,
    PlacedFixturePointDTO,
)
from app.components.esai_engine.exceptions import (
    AlternativeNotFoundError,
    DesignRevisionConflictError,
    GeometryStalenessError,
    InvalidDesignSaveError,
    PreferenceStalenessError,
)
from app.components.esai_engine.optimizer.genetic_optimizer import OptimizationConfig
from app.components.esai_engine.service import EsaiEngineService
from tests.esai.fixtures import BEDROOM_PROJECT_FIXTURE, MULTI_FLOOR_PROJECT_FIXTURE


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def in_memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def admin_client(in_memory_db):
    fastapi_app.dependency_overrides[get_db] = lambda: in_memory_db
    fastapi_app.dependency_overrides[require_admin] = lambda: {"id": "admin_test", "role": "admin"}
    client = TestClient(fastapi_app)
    yield client
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def rich_master_project(in_memory_db):
    """
    Project with all upstream sections:
    - Component 1 floor_plan
    - Component 2 structural_rectification
    - Component 4 exterior_landscape
    - Custom extension metadata
    - Phase 2 preferences
    """
    mj = deepcopy(BEDROOM_PROJECT_FIXTURE)
    mj["structural_rectification"] = {
        "status": "rectified",
        "vastu_score": 88.5,
        "rectifications_applied": ["shifted_entrance_northeast"],
    }
    mj["exterior_landscape"] = {
        "version": "1.0",
        "site_analysis": {"orientation": "north"},
        "outdoor_elements": [{"id": "TREE_01", "type": "shade_tree", "position": [1.0, 1.0]}],
    }
    mj["custom_bim_metadata"] = {"ifc_guid": "1234-abcd-5678-efgh", "lod": 300}
    mj["interior_layout"] = {
        "preferences": {
            "style": "scandinavian",
            "circulation_priority": "standard",
        },
        "room_requirements": {
            "RM_BED_01": {"room_id": "RM_BED_01", "status": "approved"}
        }
    }

    project = Project(
        id="proj_phase5_rich",
        project_name="Phase 5 Rich Master JSON Project",
        master_json=mj,
        revision=1,
    )
    in_memory_db.add(project)
    in_memory_db.commit()
    in_memory_db.refresh(project)
    return project


@pytest.fixture
def multi_room_project(in_memory_db):
    """Multi-room, multi-floor project for selective regeneration testing."""
    mj = deepcopy(MULTI_FLOOR_PROJECT_FIXTURE)
    mj["interior_layout"] = {
        "preferences": {"style": "modern"},
    }
    project = Project(
        id="proj_phase5_multi",
        project_name="Phase 5 Multi-Room Project",
        master_json=mj,
        revision=1,
    )
    in_memory_db.add(project)
    in_memory_db.commit()
    in_memory_db.refresh(project)
    return project


# ── 1. Master JSON Structural Preservation & Immutability ────────────────────

def test_master_json_preservation_and_immutability(in_memory_db, rich_master_project):
    """
    Verifies that saving an ESAI interior layout strictly preserves:
    - Floor plan structural geometry
    - Component 2 Vastu structural rectification
    - Component 4 ELIA exterior landscape
    - Unknown valid extension metadata
    - Phase 2 preferences and Phase 1 room requirements
    """
    service = EsaiEngineService(in_memory_db)
    cfg = OptimizationConfig(population_size=15, num_generations=5, seed=42)

    # 1. Capture exact snapshots of non-ESAI sections
    orig_mj = deepcopy(rich_master_project.master_json)
    orig_floor_plan = deepcopy(orig_mj["floor_plan"])
    orig_rectification = deepcopy(orig_mj["structural_rectification"])
    orig_landscape = deepcopy(orig_mj["exterior_landscape"])
    orig_custom = deepcopy(orig_mj["custom_bim_metadata"])
    orig_prefs = deepcopy(orig_mj["interior_layout"]["preferences"])
    orig_reqs = deepcopy(orig_mj["interior_layout"]["room_requirements"])

    # 2. Run generation and save
    gen_result = service.run_generation(rich_master_project, scope="room", target_room_id="RM_BED_01", config=cfg)
    assert gen_result.status == "success"

    save_res = service.save_design(rich_master_project, gen_result, scope="room", target_room_id="RM_BED_01")
    assert save_res.success is True
    assert save_res.design_revision == 1

    # 3. Reload fresh project from database
    in_memory_db.refresh(rich_master_project)
    saved_mj = rich_master_project.master_json

    # 4. Assert 100% preservation of all non-ESAI sections
    assert saved_mj["floor_plan"] == orig_floor_plan
    assert saved_mj["structural_rectification"] == orig_rectification
    assert saved_mj["exterior_landscape"] == orig_landscape
    assert saved_mj["custom_bim_metadata"] == orig_custom

    # 5. Assert preservation of Phase 1 and Phase 2 data
    assert saved_mj["interior_layout"]["preferences"] == orig_prefs
    assert saved_mj["interior_layout"]["room_requirements"] == orig_reqs

    # 6. Assert ESAI interior_layout design was cleanly populated
    assert "designs" in saved_mj["interior_layout"]
    assert "RM_BED_01" in saved_mj["interior_layout"]["designs"]["rooms"]
    saved_bed = saved_mj["interior_layout"]["designs"]["rooms"]["RM_BED_01"]
    assert saved_bed["room_id"] == "RM_BED_01"
    assert saved_bed["generation_status"] == "success"
    assert len(saved_bed["furniture"]) > 0

    # 7. Assert processing section status
    assert saved_mj["processing"]["esai_engine"]["status"] == "completed"
    assert saved_mj["processing"]["esai_engine"]["design_revision"] == 1


# ── 2. Two-Stage Generation and Persistence ──────────────────────────────────

def test_two_stage_generation_and_persistence(in_memory_db, rich_master_project):
    """
    Stage A (run_generation) does NOT mutate projects.master_json.
    Stage B (save_design) atomically commits into Master JSON.
    """
    service = EsaiEngineService(in_memory_db)
    cfg = OptimizationConfig(population_size=15, num_generations=5, seed=42)

    # Snapshot before Stage A
    rev_before = rich_master_project.revision
    mj_before = deepcopy(rich_master_project.master_json)

    # Stage A: Generate
    gen_result = service.run_generation(rich_master_project, scope="room", target_room_id="RM_BED_01", config=cfg)
    assert gen_result.status == "success"

    # Assert DB Master JSON has NOT changed after Stage A
    in_memory_db.refresh(rich_master_project)
    assert rich_master_project.revision == rev_before
    assert "designs" not in (rich_master_project.master_json.get("interior_layout") or {})

    # Stage B: Persist
    save_res = service.save_design(rich_master_project, gen_result, scope="room", target_room_id="RM_BED_01")
    assert save_res.success is True

    # Assert DB Master JSON IS updated after Stage B
    in_memory_db.refresh(rich_master_project)
    assert rich_master_project.revision > rev_before
    assert "designs" in rich_master_project.master_json["interior_layout"]
    assert "RM_BED_01" in rich_master_project.master_json["interior_layout"]["designs"]["rooms"]


# ── 3. Selective Room-Level Regeneration ─────────────────────────────────────

def test_room_selective_regeneration_preserves_unrelated_rooms(in_memory_db, multi_room_project):
    """
    Regenerating Room A must leave Room B's design, timestamp, and assets untouched.
    """
    service = EsaiEngineService(in_memory_db)
    cfg = OptimizationConfig(population_size=15, num_generations=5, seed=42)

    # 1. Initial generation of both Living Room and Kitchen
    init_res = service.run_generation(multi_room_project, scope="building", config=cfg)
    service.save_design(multi_room_project, init_res, scope="building")

    in_memory_db.refresh(multi_room_project)
    rooms_before = deepcopy(multi_room_project.master_json["interior_layout"]["designs"]["rooms"])
    assert "RM_LIVING_01" in rooms_before
    assert "RM_KITCHEN_01" in rooms_before

    kitchen_snapshot = deepcopy(rooms_before["RM_KITCHEN_01"])
    living_snapshot_timestamp = rooms_before["RM_LIVING_01"]["generation_timestamp"]

    # 2. Selectively regenerate ONLY RM_LIVING_01 with a different seed
    cfg_new = OptimizationConfig(population_size=20, num_generations=15, seed=101)
    regen_res = service.regenerate(
        multi_room_project,
        scope="room",
        target_room_id="RM_LIVING_01",
        config=cfg_new,
        auto_save=True,
    )
    assert regen_res["persistence"].success is True

    # 3. Reload from DB and verify isolation
    in_memory_db.refresh(multi_room_project)
    rooms_after = multi_room_project.master_json["interior_layout"]["designs"]["rooms"]

    # Living room must be updated
    assert rooms_after["RM_LIVING_01"]["design_revision"] > rooms_before["RM_LIVING_01"]["design_revision"]

    # Kitchen room must be EXACTLY identical (byte-for-byte / field-for-field)
    assert rooms_after["RM_KITCHEN_01"] == kitchen_snapshot


# ── 4. Selective Floor-Level Regeneration ────────────────────────────────────

def test_floor_selective_regeneration_preserves_unrelated_floors(in_memory_db, multi_room_project):
    """
    Regenerating Floor 0 must leave Floor 1's saved designs untouched.
    """
    service = EsaiEngineService(in_memory_db)
    cfg = OptimizationConfig(population_size=20, num_generations=15, seed=42)

    # 1. Generate & save entire building
    init_res = service.run_generation(multi_room_project, scope="building", config=cfg)
    service.save_design(multi_room_project, init_res, scope="building")

    in_memory_db.refresh(multi_room_project)
    saved_rooms = deepcopy(multi_room_project.master_json["interior_layout"]["designs"]["rooms"])
    bath_snapshot = deepcopy(saved_rooms["RM_BATH_01"])  # RM_BATH_01 is on fl_1

    # 2. Regenerate ONLY floor 0 (fl_0: living room and kitchen)
    service.regenerate(multi_room_project, scope="floor", target_floor_id="fl_0", config=cfg, auto_save=True)

    # 3. Reload and verify fl_1 bathroom is untouched
    in_memory_db.refresh(multi_room_project)
    updated_rooms = multi_room_project.master_json["interior_layout"]["designs"]["rooms"]
    assert updated_rooms["RM_BATH_01"] == bath_snapshot


# ── 5. Geometry Staleness Detection & Conflict Rejection ─────────────────────

def test_geometry_staleness_detection_rejects_saving_old_design(in_memory_db, rich_master_project):
    """
    If project geometry changes in Master JSON after layout generation,
    attempting to save the old design must be rejected with GeometryStalenessError.
    """
    service = EsaiEngineService(in_memory_db)
    cfg = OptimizationConfig(population_size=15, num_generations=5, seed=42)

    # 1. Generate design against initial geometry
    gen_result = service.run_generation(rich_master_project, scope="room", target_room_id="RM_BED_01", config=cfg)

    # 2. Upstream geometry changes (e.g. wall shifted in floor_plan)
    mj_copy = deepcopy(rich_master_project.master_json)
    mj_copy["floor_plan"]["floors"][0]["rooms"][0]["polygon"] = [
        [0.0, 0.0], [7.0, 0.0], [7.0, 5.0], [0.0, 5.0]
    ]  # Changed room dimensions from 5x4.2 to 7x5
    rich_master_project.master_json = mj_copy
    rich_master_project.revision += 1
    in_memory_db.commit()

    # 3. Attempt to save the old design -> Must raise GeometryStalenessError
    with pytest.raises(GeometryStalenessError) as exc_info:
        service.save_design(rich_master_project, gen_result, scope="room", target_room_id="RM_BED_01")

    assert "Floor plan geometry has changed since generation" in str(exc_info.value)
    assert exc_info.value.code == "GEOMETRY_STALENESS_CONFLICT"


# ── 6. Preference Staleness Detection & Conflict Rejection ───────────────────

def test_preference_staleness_detection_rejects_saving_old_design(in_memory_db, rich_master_project):
    """
    If room preferences change after layout generation, attempting to save
    the old design must be rejected with PreferenceStalenessError.
    """
    service = EsaiEngineService(in_memory_db)
    cfg = OptimizationConfig(population_size=15, num_generations=5, seed=42)

    # 1. Save initial room preference (preference_revision = 1)
    service.save_room_preferences(
        project=rich_master_project,
        room_id="RM_BED_01",
        preferences_data={"bed_type": "double", "wardrobe_required": True},
    )

    # 2. Generate design (incorporates preference_revision = 1)
    gen_result = service.run_generation(rich_master_project, scope="room", target_room_id="RM_BED_01", config=cfg)

    # 3. Client updates preferences in the meantime (e.g. changed to king bed -> preference_revision = 2)
    service.save_room_preferences(
        project=rich_master_project,
        room_id="RM_BED_01",
        preferences_data={"bed_type": "king", "wardrobe_required": True},
    )

    # 4. Attempt to save old design generated with preference revision 1
    with pytest.raises(PreferenceStalenessError) as exc_info:
        service.save_design(rich_master_project, gen_result, scope="room", target_room_id="RM_BED_01")

    assert "Room preferences for 'RM_BED_01' have changed" in str(exc_info.value)
    assert exc_info.value.code == "PREFERENCE_STALENESS_CONFLICT"


# ── 7. Design Revision & Optimistic Concurrency Conflict Rejection ───────────

def test_concurrency_and_design_revision_conflict_rejection(in_memory_db, rich_master_project):
    """
    If two users or processes save designs concurrently, the second save
    with stale expected_design_revision must be rejected with DesignRevisionConflictError.
    """
    service = EsaiEngineService(in_memory_db)
    cfg = OptimizationConfig(population_size=15, num_generations=5, seed=42)

    # User 1 & User 2 both start from design_revision = 0
    gen_res = service.run_generation(rich_master_project, scope="room", target_room_id="RM_BED_01", config=cfg)

    # User 1 saves successfully (design_revision becomes 1)
    service.save_design(rich_master_project, gen_res, scope="room", target_room_id="RM_BED_01", expected_design_revision=0)

    # User 2 attempts to save with expected_design_revision = 0 -> Conflict!
    with pytest.raises(DesignRevisionConflictError) as exc_info:
        service.save_design(rich_master_project, gen_res, scope="room", target_room_id="RM_BED_01", expected_design_revision=0)

    assert "Concurrent design update conflict" in str(exc_info.value)
    assert exc_info.value.code == "DESIGN_REVISION_CONFLICT"


# ── 8. Invalid Layout Save Rejection ─────────────────────────────────────────

def test_invalid_layout_save_rejection(in_memory_db, rich_master_project):
    """
    A design with hard-constraint violations or status='infeasible' cannot be saved as valid.
    """
    service = EsaiEngineService(in_memory_db)

    # Create mock invalid room design
    bad_room = GeneratedRoomDesignDTO(
        room_id="RM_BED_01",
        room_name="Bedroom",
        room_type="bedroom",
        floor_id="fl_0",
        status="infeasible",
        hard_constraints_passed=False,
        polygon=[Coordinate2D(x=0, y=0), Coordinate2D(x=5, y=0), Coordinate2D(x=5, y=4), Coordinate2D(x=0, y=4)],
        area_sqm=20.0,
        ceiling_height_m=2.8,
        diagnostics=["Asset overlaps door swing clearance zone"],
    )

    with pytest.raises(InvalidDesignSaveError) as exc_info:
        service.save_design(rich_master_project, bad_room, scope="room", target_room_id="RM_BED_01")

    assert "hard-constraint violations" in str(exc_info.value)
    assert exc_info.value.code == "INVALID_DESIGN_SAVE_ERROR"


# ── 9. Alternative Selection and Atomic Layout Activation ────────────────────

def test_alternative_selection_and_atomic_switch(in_memory_db, rich_master_project):
    """
    Allows activating a valid alternative layout for a room.
    Updates active furniture, cabinetry, MEP, and increments design revision.
    """
    service = EsaiEngineService(in_memory_db)
    cfg = OptimizationConfig(population_size=20, num_generations=8, alternatives_count=2, seed=42)

    # 1. Generate and save design with 2 alternatives
    gen_result = service.run_generation(rich_master_project, scope="room", target_room_id="RM_BED_01", config=cfg)
    service.save_design(rich_master_project, gen_result, scope="room", target_room_id="RM_BED_01")

    # 2. Inspect alternatives
    alts = service.get_room_alternatives(rich_master_project, "RM_BED_01")
    assert len(alts) >= 1
    alt_to_select = str(alts[0]["alternative_index"])

    # 3. Select alternative
    switch_res = service.select_alternative(
        project=rich_master_project,
        room_id="RM_BED_01",
        alternative_id=alt_to_select,
    )
    assert switch_res.success is True
    assert switch_res.active_alternative_id == alt_to_select
    assert switch_res.design_revision == 2

    # 4. Verify Master JSON has the updated active alternative ID
    in_memory_db.refresh(rich_master_project)
    saved_room = rich_master_project.master_json["interior_layout"]["designs"]["rooms"]["RM_BED_01"]
    assert saved_room["active_alternative_id"] == alt_to_select
    assert saved_room["design_revision"] == 2

    # 5. Selecting non-existent alternative raises AlternativeNotFoundError
    with pytest.raises(AlternativeNotFoundError):
        service.select_alternative(rich_master_project, "RM_BED_01", "non_existent_alt_999")


# ── 10. Complete MEP and Surface Finishes Persistence ────────────────────────

def test_complete_mep_and_finishes_persistence(in_memory_db, rich_master_project):
    """
    Verifies that lighting, electrical points, plumbing, and wall/floor/ceiling finishes
    are fully preserved inside the Master JSON room layout structure.
    """
    service = EsaiEngineService(in_memory_db)
    cfg = OptimizationConfig(population_size=15, num_generations=5, seed=42)

    gen_result = service.run_generation(rich_master_project, scope="room", target_room_id="RM_BED_01", config=cfg)
    service.save_design(rich_master_project, gen_result, scope="room", target_room_id="RM_BED_01")

    in_memory_db.refresh(rich_master_project)
    saved_bed = rich_master_project.master_json["interior_layout"]["designs"]["rooms"]["RM_BED_01"]

    # MEP & Service points
    assert "lighting" in saved_bed
    assert len(saved_bed["lighting"]) > 0
    assert "electrical_points" in saved_bed
    assert len(saved_bed["electrical_points"]) > 0
    assert "service_requirements" in saved_bed

    # Finishes
    assert "wall_finishes" in saved_bed
    assert "floor_finishes" in saved_bed
    assert "ceiling_finishes" in saved_bed

    # Categories
    assert "furniture" in saved_bed
    assert "cabinetry" in saved_bed
    assert "appliances" in saved_bed
    assert "sanitary_fixtures" in saved_bed
    assert "decorations" in saved_bed

    # Validation & Revisions
    assert "validation" in saved_bed
    assert saved_bed["validation"]["hard_constraints_passed"] is True
    assert "alternatives" in saved_bed
    assert "generation_metadata" in saved_bed


# ── 11. Staleness Audit API ──────────────────────────────────────────────────

def test_staleness_audit_reporting(in_memory_db, rich_master_project):
    """
    Audits saved interior designs against authoritative geometry fingerprint and
    preference revisions, identifying rooms requiring regeneration.
    """
    service = EsaiEngineService(in_memory_db)
    cfg = OptimizationConfig(population_size=15, num_generations=5, seed=42)

    # 1. Before saving: room has no saved design
    report_0 = service.check_design_staleness(rich_master_project)
    assert report_0.rooms["RM_BED_01"].has_saved_design is False
    assert report_0.rooms["RM_BED_01"].is_stale is False

    # 2. Save design
    gen_result = service.run_generation(rich_master_project, scope="room", target_room_id="RM_BED_01", config=cfg)
    service.save_design(rich_master_project, gen_result, scope="room", target_room_id="RM_BED_01")

    # 3. Clean check: fresh and up-to-date
    report_1 = service.check_design_staleness(rich_master_project)
    assert report_1.rooms["RM_BED_01"].has_saved_design is True
    assert report_1.rooms["RM_BED_01"].is_stale is False
    assert report_1.is_any_room_stale is False

    # 4. Geometry changes -> becomes stale
    mj = deepcopy(rich_master_project.master_json)
    mj["floor_plan"]["floors"][0]["rooms"][0]["polygon"] = [
        [0.0, 0.0], [6.0, 0.0], [6.0, 4.0], [0.0, 4.0]
    ]
    rich_master_project.master_json = mj
    in_memory_db.commit()

    report_2 = service.check_design_staleness(rich_master_project)
    assert report_2.rooms["RM_BED_01"].is_stale is True
    assert report_2.rooms["RM_BED_01"].geometry_stale is True
    assert report_2.is_any_room_stale is True


# ── 12. Full REST API Integration ────────────────────────────────────────────

def test_api_run_auto_save_and_persistence_endpoints(admin_client, rich_master_project):
    """
    Verifies Phase 5 REST endpoints through FastAPI test client:
    - POST /run with auto_save=true
    - GET /designs
    - GET /designs/rooms/{room_id}
    - GET /designs/rooms/{room_id}/alternatives
    - POST /designs/rooms/{room_id}/select-alternative
    - POST /regenerate
    - GET /designs/staleness
    """
    pid = rich_master_project.id

    # 1. POST /run with auto_save=true
    run_resp = admin_client.post(
        f"/api/projects/{pid}/esai-engine/run",
        json={
            "scope": "room",
            "room_id": "RM_BED_01",
            "auto_save": True,
            "generations": 5,
            "population_size": 15,
            "seed": 42,
        },
    )
    assert run_resp.status_code == 200, run_resp.text
    run_data = run_resp.json()
    assert run_data["result"]["status"] == "success"
    assert run_data["persistence"]["success"] is True
    assert run_data["persistence"]["design_revision"] == 1

    # 2. GET /designs
    designs_resp = admin_client.get(f"/api/projects/{pid}/esai-engine/designs")
    assert designs_resp.status_code == 200
    designs_data = designs_resp.json()
    assert designs_data["design_revision"] == 1
    assert "RM_BED_01" in designs_data["rooms"]

    # 3. GET /designs/rooms/{room_id}
    room_resp = admin_client.get(f"/api/projects/{pid}/esai-engine/designs/rooms/RM_BED_01")
    assert room_resp.status_code == 200
    room_data = room_resp.json()
    assert room_data["room_id"] == "RM_BED_01"
    assert len(room_data["furniture"]) > 0

    # 4. GET /designs/rooms/{room_id}/alternatives
    alt_resp = admin_client.get(f"/api/projects/{pid}/esai-engine/designs/rooms/RM_BED_01/alternatives")
    assert alt_resp.status_code == 200
    alt_data = alt_resp.json()
    assert "alternatives" in alt_data

    # 5. POST /designs/rooms/{room_id}/select-alternative if alternative exists
    if alt_data["total"] > 0:
        target_alt = str(alt_data["alternatives"][0]["alternative_index"])
        sel_resp = admin_client.post(
            f"/api/projects/{pid}/esai-engine/designs/rooms/RM_BED_01/select-alternative",
            json={"alternative_id": target_alt},
        )
        assert sel_resp.status_code == 200
        sel_data = sel_resp.json()
        assert sel_data["success"] is True
        assert sel_data["design_revision"] == 2

    # 6. POST /regenerate
    regen_resp = admin_client.post(
        f"/api/projects/{pid}/esai-engine/regenerate",
        json={
            "scope": "room",
            "room_id": "RM_BED_01",
            "auto_save": True,
            "generations": 5,
            "population_size": 15,
            "seed": 101,
        },
    )
    assert regen_resp.status_code == 200
    regen_data = regen_resp.json()
    assert regen_data["auto_saved"] is True
    assert regen_data["persistence"]["success"] is True

    # 7. GET /designs/staleness
    stale_resp = admin_client.get(f"/api/projects/{pid}/esai-engine/designs/staleness")
    assert stale_resp.status_code == 200
    stale_data = stale_resp.json()
    assert "report" in stale_data
    assert stale_data["report"]["rooms"]["RM_BED_01"]["has_saved_design"] is True

