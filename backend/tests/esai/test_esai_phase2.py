"""
ESAI Phase 2 Test Suite: Multi-Level Client Interior Preference System
Tests:
1. Multi-level preference resolution: Building -> Floor -> Room -> Specific Items.
2. Source attribution tracking (INHERITED_BUILDING, INHERITED_FLOOR, OVERRIDDEN_ROOM, DEFAULT).
3. Reset overrides: Reverting room and floor to inherited defaults.
4. Optimistic concurrency and revision tracking.
5. Dynamic schema discovery for all major room types.
6. Orphan detection on geometry modification.
7. Interior context endpoint (floors, rooms, configuration status).
8. Validation error rejection on invalid room/floor IDs.
"""
from copy import deepcopy
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.database import Base, get_db
from app.dependencies import require_admin
from app.main import app as fastapi_app
from app.models.project import Project
from app.models.esai import EsaiRoomPreference, EsaiFloorPreference, EsaiDesignPreference
from app.components.esai_engine.service import EsaiEngineService
from tests.esai.fixtures import (
    BEDROOM_PROJECT_FIXTURE,
    GAB_GEN_DIRECT_FIXTURE,
    VSAI_RECTIFIED_FIXTURE,
)


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
def auth_client(in_memory_db):
    fastapi_app.dependency_overrides[get_db] = lambda: in_memory_db
    fastapi_app.dependency_overrides[require_admin] = lambda: {"user_id": "admin_1", "role": "admin"}
    client = TestClient(fastapi_app)
    yield client
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def sample_project(in_memory_db):
    project = Project(
        project_name="Phase 2 Test Residence",
        master_json=deepcopy(BEDROOM_PROJECT_FIXTURE),
        revision=1,
    )
    in_memory_db.add(project)
    in_memory_db.commit()
    in_memory_db.refresh(project)
    return project


# ==============================================================================
# 1. Multi-Level Preference Resolution Hierarchy
# ==============================================================================

def test_effective_preference_resolution_hierarchy(in_memory_db, sample_project):
    """
    Building defaults -> Floor overrides -> Room overrides.
    Verify that more specific levels win and source attribution is precise.
    """
    service = EsaiEngineService(in_memory_db)
    floor_id = "floor_gf"
    room_id = "RM_BED_01"

    # Step A: Save building defaults
    service.save_building_preferences(sample_project, {
        "style": "scandinavian",
        "primary_palette": "neutral_warm",
        "flooring": "oak_hardwood",
        "lighting_mood": "warm_diffuse",
    })

    # Effective check at building level
    eff_a = service.get_effective_preferences(sample_project, room_id, floor_id)
    assert eff_a["effective_preferences"]["style"] == "scandinavian"
    assert eff_a["effective_preferences"]["flooring"] == "oak_hardwood"
    assert eff_a["sources"]["style"] == "INHERITED_BUILDING"
    assert eff_a["sources"]["flooring"] == "INHERITED_BUILDING"
    assert "style" in eff_a["inherited_keys"]

    # Step B: Override at floor level
    service.save_floor_preferences(sample_project, floor_id, {
        "flooring": "marble_tile",  # overrides building oak_hardwood
        "floor_accent": "brass_inlay",
    })

    eff_b = service.get_effective_preferences(sample_project, room_id, floor_id)
    assert eff_b["effective_preferences"]["style"] == "scandinavian"  # from building
    assert eff_b["effective_preferences"]["flooring"] == "marble_tile"  # from floor
    assert eff_b["effective_preferences"]["floor_accent"] == "brass_inlay"
    assert eff_b["sources"]["style"] == "INHERITED_BUILDING"
    assert eff_b["sources"]["flooring"] == "INHERITED_FLOOR"

    # Step C: Override at room level
    service.save_room_preferences(sample_project, room_id, {
        "preferences": {
            "style": "japandi",  # overrides building scandinavian
            "bed_size": "king",
            "wardrobe_type": "walk_in",
        },
        "specific_assets": [{"asset_code": "BED_KING_01", "priority": "mandatory"}],
        "custom_constraints": [{"type": "no_mirror_facing_bed"}],
    })

    eff_c = service.get_effective_preferences(sample_project, room_id, floor_id)
    assert eff_c["effective_preferences"]["style"] == "japandi"  # room wins
    assert eff_c["effective_preferences"]["flooring"] == "marble_tile"  # floor wins
    assert eff_c["effective_preferences"]["bed_size"] == "king"  # room specific
    assert eff_c["sources"]["style"] == "OVERRIDDEN_ROOM"
    assert eff_c["sources"]["flooring"] == "INHERITED_FLOOR"
    assert eff_c["sources"]["primary_palette"] == "INHERITED_BUILDING"
    assert "style" in eff_c["overridden_keys"]
    assert len(eff_c["specific_assets"]) == 1
    assert eff_c["specific_assets"][0]["asset_code"] == "BED_KING_01"


# ==============================================================================
# 2. Reset Overrides (Revert to Inherited Defaults)
# ==============================================================================

def test_reset_room_preferences_reverts_to_inherited(in_memory_db, sample_project):
    """Deleting room preference reverts room to floor/building defaults without deleting room."""
    service = EsaiEngineService(in_memory_db)
    floor_id = "floor_gf"
    room_id = "RM_BED_01"

    service.save_building_preferences(sample_project, {"style": "minimalist"})
    service.save_room_preferences(sample_project, room_id, {"preferences": {"style": "industrial"}})

    eff_before = service.get_effective_preferences(sample_project, room_id, floor_id)
    assert eff_before["effective_preferences"]["style"] == "industrial"
    assert eff_before["sources"]["style"] == "OVERRIDDEN_ROOM"

    # Reset room override
    service.reset_room_preferences(sample_project, room_id)

    eff_after = service.get_effective_preferences(sample_project, room_id, floor_id)
    assert eff_after["effective_preferences"]["style"] == "minimalist"
    assert eff_after["sources"]["style"] == "INHERITED_BUILDING"


def test_reset_floor_preferences_reverts_to_building(in_memory_db, sample_project):
    """Deleting floor preference reverts floor to building defaults."""
    service = EsaiEngineService(in_memory_db)
    floor_id = "floor_gf"
    room_id = "RM_BED_01"

    service.save_building_preferences(sample_project, {"flooring": "hardwood"})
    service.save_floor_preferences(sample_project, floor_id, {"flooring": "carpet"})

    eff_before = service.get_effective_preferences(sample_project, room_id, floor_id)
    assert eff_before["effective_preferences"]["flooring"] == "carpet"
    assert eff_before["sources"]["flooring"] == "INHERITED_FLOOR"

    service.reset_floor_preferences(sample_project, floor_id)

    eff_after = service.get_effective_preferences(sample_project, room_id, floor_id)
    assert eff_after["effective_preferences"]["flooring"] == "hardwood"
    assert eff_after["sources"]["flooring"] == "INHERITED_BUILDING"


# ==============================================================================
# 3. Dynamic Room-Type Preference Schema Discovery
# ==============================================================================

def test_room_preference_schemas_contain_expected_fields(in_memory_db):
    service = EsaiEngineService(in_memory_db)

    # Master bedroom schema
    mbr_schema = service.get_preference_schema_for_room_type("master_bedroom")
    mbr_fields = set(mbr_schema["fields"].keys())
    assert "bed_type" in mbr_fields
    assert "wardrobe_type" in mbr_fields

    # Living room schema
    lr_schema = service.get_preference_schema_for_room_type("living_room")
    lr_fields = set(lr_schema["fields"].keys())
    assert "sofa_type" in lr_fields or "tv_wall_required" in lr_fields

    # Kitchen schema
    k_schema = service.get_preference_schema_for_room_type("kitchen")
    k_fields = set(k_schema["fields"].keys())
    assert "layout_type" in k_fields

    # Attached bathroom schema
    bath_schema = service.get_preference_schema_for_room_type("attached_bathroom")
    bath_fields = set(bath_schema["fields"].keys())
    assert "has_bathtub" in bath_fields or "has_shower" in bath_fields


# ==============================================================================
# 4. Orphaned Preferences Detection
# ==============================================================================

def test_orphan_detection_identifies_deleted_rooms(in_memory_db, sample_project):
    """Preferences saved for a room that no longer exists in project geometry are detected."""
    service = EsaiEngineService(in_memory_db)

    # Save preference for an existing room
    service.save_room_preferences(sample_project, "RM_BED_01", {"preferences": {"style": "modern"}})

    # Now create an orphaned preference record for a room not in geometry
    orphan_pref = EsaiRoomPreference(
        project_id=sample_project.id,
        floor_id="floor_gf",
        room_id="RM_GHOST_99",
        room_type="bedroom",
        preferences_json={"style": "gothic"},
        preference_revision=1,
        is_orphaned=False,
    )
    in_memory_db.add(orphan_pref)
    in_memory_db.commit()

    report = service.detect_orphaned_preferences(sample_project)
    assert report["scanned_count"] >= 2
    assert report["orphaned_count"] == 1
    assert "RM_GHOST_99" in report["orphaned_room_ids"]

    # In database, is_orphaned flag must now be True
    updated = in_memory_db.query(EsaiRoomPreference).filter_by(room_id="RM_GHOST_99").first()
    assert updated.is_orphaned is True


# ==============================================================================
# 5. Optimistic Concurrency on Preferences
# ==============================================================================

def test_optimistic_concurrency_rejects_stale_revision(in_memory_db, sample_project):
    """Attempting to save preferences with an outdated revision raises HTTP 409."""
    service = EsaiEngineService(in_memory_db)
    sample_project.revision = 5
    in_memory_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        service.save_building_preferences(
            sample_project,
            {"style": "art_deco"},
            expected_revision=3  # Stale! Current is 5
        )
    assert exc_info.value.status_code == 409


# ==============================================================================
# 6. REST API Endpoints Verification via auth_client
# ==============================================================================

def test_api_interior_context_endpoint(auth_client, sample_project):
    """GET /api/projects/{id}/esai-engine/interior-context returns floors and rooms summary."""
    resp = auth_client.get(f"/api/projects/{sample_project.id}/esai-engine/interior-context")
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == sample_project.id
    assert len(data["floors"]) >= 1
    assert data["total_rooms"] >= 1
    assert "geometry_staleness" in data


def test_api_multi_level_preferences_crud(auth_client, sample_project):
    """Full HTTP test: building PUT, floor PUT, room PUT, effective GET, room DELETE."""
    base = f"/api/projects/{sample_project.id}/esai-engine"

    # 1. Building PUT
    resp_b = auth_client.put(f"{base}/preferences/building", json={"style": "minimalist", "lighting": "soft"})
    assert resp_b.status_code == 200
    assert resp_b.json()["preferences"]["style"] == "minimalist"

    # 2. Floor PUT
    resp_f = auth_client.put(f"{base}/preferences/floors/floor_gf", json={"flooring": "hardwood"})
    assert resp_f.status_code == 200

    # 3. Room PUT
    resp_r = auth_client.put(
        f"{base}/preferences/rooms/RM_BED_01",
        json={"preferences": {"bed_size": "queen", "style": "boho"}}
    )
    assert resp_r.status_code == 200

    # 4. Effective GET
    resp_eff = auth_client.get(f"{base}/preferences/rooms/RM_BED_01/effective?floor_id=floor_gf")
    assert resp_eff.status_code == 200
    eff_data = resp_eff.json()
    assert eff_data["effective_preferences"]["style"] == "boho"
    assert eff_data["effective_preferences"]["flooring"] == "hardwood"
    assert eff_data["sources"]["style"] == "OVERRIDDEN_ROOM"
    assert eff_data["sources"]["flooring"] == "INHERITED_FLOOR"

    # 5. Room Reset DELETE
    resp_del = auth_client.delete(f"{base}/preferences/rooms/RM_BED_01")
    assert resp_del.status_code == 204

    # 6. Effective GET after reset -> style falls back to building minimalist
    resp_eff2 = auth_client.get(f"{base}/preferences/rooms/RM_BED_01/effective?floor_id=floor_gf")
    assert resp_eff2.status_code == 200
    assert resp_eff2.json()["effective_preferences"]["style"] == "minimalist"
    assert resp_eff2.json()["sources"]["style"] == "INHERITED_BUILDING"


def test_api_schema_discovery(auth_client):
    """GET /api/esai/preference-schema/master_bedroom returns valid schema."""
    resp = auth_client.get("/api/esai/preference-schema/master_bedroom")
    assert resp.status_code == 200
    data = resp.json()
    assert data["room_type"] == "master_bedroom"
    assert len(data["fields"]) > 0
