"""
Phase 7 Automated Test Suite: Interactive Interior Customization, Furniture Editing, Locking & Safe Selective Regeneration
Verifies:
1. Live validation endpoint (/validate-edit) correctly identifies valid placements.
2. Rejection of out-of-bounds placements (FURNITURE_OUTSIDE_ROOM).
3. Rejection of door swing blockages (DOOR_ACCESS_BLOCKED).
4. Rejection of mutual furniture collisions (ASSET_COLLISION).
5. Transactional manual edit save (/designs/rooms/{id}) updates Master JSON, increments revision, and commits atomically.
6. Optimistic concurrency conflict rejection (HTTP 409) on stale design revision.
7. Invalid placement save rejection (HTTP 422) with zero Master JSON mutation.
8. Asset persistent locking (/lock) and unlocking (/unlock).
9. Selective GA regeneration of unlocked items (/regenerate-unlocked) strictly preserves locked assets at exact coordinates and rotations.
10. Rejection of mandatory asset removal (e.g. bed from bedroom).
"""
from copy import deepcopy
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.dependencies import require_admin
from app.main import app as fastapi_app
from app.models.project import Project
from tests.esai.fixtures import BEDROOM_PROJECT_FIXTURE


@pytest.fixture
def in_memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(in_memory_db):
    def override_get_db():
        try:
            yield in_memory_db
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[require_admin] = lambda: {"user_id": "admin-tester", "role": "admin"}
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def seeded_project(in_memory_db):
    mj = deepcopy(BEDROOM_PROJECT_FIXTURE)
    mj["interior_layout"] = {
        "design_revision": 1,
        "schema_version": "1.0.0",
        "geometry_fingerprint": "mock_fp_001",
        "designs": {
            "rooms": {
                "RM_BED_01": {
                    "project_id": "proj-phase7-001",
                    "floor_id": "floor_gf",
                    "room_id": "RM_BED_01",
                    "room_name": "Master Bedroom",
                    "room_type": "master_bedroom",
                    "geometry_revision": 1,
                    "design_revision": 1,
                    "polygon": [[0.0, 0.0], [5.0, 0.0], [5.0, 4.0], [0.0, 4.0]],
                    "area_sqm": 20.0,
                    "ceiling_height_m": 2.8,
                    "furniture": [
                        {
                            "instance_id": "inst_bed_1",
                            "asset_id": "BED_QUEEN_STORAGE_01",
                            "asset_name": "Queen Bed",
                            "category": "bed",
                            "dimensions": {"width": 1.6, "depth": 2.0, "height": 1.1},
                            "position": {"x": 2.5, "y": 2.5},
                            "rotation_deg": 0.0,
                            "placement_mode": "floor_standing",
                            "is_locked": False,
                            "is_mandatory": True,
                        }
                    ],
                    "cabinetry": [],
                    "appliances": [],
                    "sanitary_fixtures": [],
                    "decorations": [],
                    "lighting": [],
                    "electrical_points": [],
                    "plumbing_requirements": [],
                    "service_requirements": [],
                    "wall_finishes": {},
                    "floor_finishes": {},
                    "ceiling_finishes": {},
                    "wall_finish": "PAINT_MATTE_WHITE_01",
                    "floor_finish": "FLOOR_OAK_PARQUET_01",
                    "ceiling_finish": "CEILING_GYPSUM_COVE_01",
                    "validation": {"hard_constraints_passed": True, "diagnostics": []},
                    "alternatives": [],
                }
            }
        },
        "revisions": [
            {"design_revision": 1, "scope": "initial"}
        ]
    }
    project = Project(
        id="proj-phase7-001",
        project_name="Phase 7 Test Project",
        master_json=mj,
        revision=1,
    )
    in_memory_db.add(project)
    in_memory_db.commit()
    in_memory_db.refresh(project)
    return project


def test_validate_room_edit_valid(client, seeded_project):
    """Verifies that a valid arrangement inside the room returns is_valid=True."""
    payload = {
        "room_id": "RM_BED_01",
        "floor_id": "floor_gf",
        "furniture": [
            {
                "instance_id": "inst_bed_1",
                "asset_id": "BED_QUEEN_STORAGE_01",
                "asset_name": "Queen Bed",
                "category": "bed",
                "dimensions": {"width": 1.6, "depth": 2.0, "height": 1.1},
                "position": {"x": 2.5, "y": 2.0},
                "rotation_deg": 0.0,
                "placement_mode": "floor_standing",
                "is_locked": False,
                "is_mandatory": True,
            },
            {
                "instance_id": "inst_table_1",
                "asset_id": "BEDSIDE_TABLE_01",
                "asset_name": "Bedside Table",
                "category": "bedside_table",
                "dimensions": {"width": 0.5, "depth": 0.45, "height": 0.55},
                "position": {"x": 3.8, "y": 2.0},
                "rotation_deg": 0.0,
                "placement_mode": "floor_standing",
                "is_locked": False,
                "is_mandatory": False,
            }
        ]
    }
    resp = client.post(f"/api/projects/{seeded_project.id}/esai-engine/designs/rooms/RM_BED_01/validate-edit", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["hard_constraints_passed"] is True
    assert data["overlap_area_sqm"] < 0.01
    assert data["out_of_bounds_area_sqm"] < 0.01


def test_validate_room_edit_out_of_bounds(client, seeded_project):
    """Verifies that furniture placed outside the room boundaries is rejected."""
    payload = {
        "room_id": "RM_BED_01",
        "floor_id": "floor_gf",
        "furniture": [
            {
                "instance_id": "inst_bed_oob",
                "asset_id": "BED_QUEEN_STORAGE_01",
                "asset_name": "Queen Bed",
                "category": "bed",
                "dimensions": {"width": 1.6, "depth": 2.0, "height": 1.1},
                "position": {"x": 20.0, "y": 25.0},  # Far outside room
                "rotation_deg": 0.0,
            }
        ]
    }
    resp = client.post(f"/api/projects/{seeded_project.id}/esai-engine/designs/rooms/RM_BED_01/validate-edit", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["hard_constraints_passed"] is False
    codes = [d["code"] for d in data["diagnostics"]]
    assert "FURNITURE_OUTSIDE_ROOM" in codes


def test_validate_room_edit_door_blocked(client, seeded_project):
    """Verifies that furniture placed directly on the door swing clearance is flagged."""
    # Door is at (0.0, 0.5) to (0.0, 1.4)
    payload = {
        "room_id": "RM_BED_01",
        "floor_id": "floor_gf",
        "furniture": [
            {
                "instance_id": "inst_bed_1",
                "asset_id": "BED_QUEEN_STORAGE_01",
                "asset_name": "Queen Bed",
                "category": "bed",
                "dimensions": {"width": 1.6, "depth": 2.0, "height": 1.1},
                "position": {"x": 2.5, "y": 2.5},
                "rotation_deg": 0.0,
            },
            {
                "instance_id": "inst_wardrobe_door",
                "asset_id": "WARDROBE_3DOOR_01",
                "asset_name": "Wardrobe",
                "category": "wardrobe",
                "dimensions": {"width": 1.5, "depth": 0.6, "height": 2.2},
                "position": {"x": 0.4, "y": 0.9},  # Blocking door swing zone
                "rotation_deg": 0.0,
            }
        ]
    }
    resp = client.post(f"/api/projects/{seeded_project.id}/esai-engine/designs/rooms/RM_BED_01/validate-edit", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["hard_constraints_passed"] is False
    codes = [d["code"] for d in data["diagnostics"]]
    assert "DOOR_ACCESS_BLOCKED" in codes


def test_validate_room_edit_collision(client, seeded_project):
    """Verifies that mutual furniture collision is detected and rejected."""
    payload = {
        "room_id": "RM_BED_01",
        "floor_id": "floor_gf",
        "furniture": [
            {
                "instance_id": "inst_bed_1",
                "asset_id": "BED_QUEEN_STORAGE_01",
                "asset_name": "Queen Bed",
                "category": "bed",
                "dimensions": {"width": 1.6, "depth": 2.0, "height": 1.1},
                "position": {"x": 2.5, "y": 2.5},
                "rotation_deg": 0.0,
            },
            {
                "instance_id": "inst_bed_2",
                "asset_id": "BED_SINGLE_01",
                "asset_name": "Single Bed",
                "category": "bed",
                "dimensions": {"width": 1.0, "depth": 2.0, "height": 0.9},
                "position": {"x": 2.7, "y": 2.6},  # Direct collision with Queen Bed
                "rotation_deg": 0.0,
            }
        ]
    }
    resp = client.post(f"/api/projects/{seeded_project.id}/esai-engine/designs/rooms/RM_BED_01/validate-edit", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["hard_constraints_passed"] is False
    codes = [d["code"] for d in data["diagnostics"]]
    assert "ASSET_COLLISION" in codes


def test_save_room_edit_transactional(client, seeded_project, in_memory_db):
    """Verifies that valid edits are saved transactionally and update Master JSON revision."""
    payload = {
        "room_id": "RM_BED_01",
        "floor_id": "floor_gf",
        "expected_design_revision": 1,
        "furniture": [
            {
                "instance_id": "inst_bed_custom_1",
                "asset_id": "BED_QUEEN_STORAGE_01",
                "asset_name": "Queen Bed",
                "category": "bed",
                "dimensions": {"width": 1.6, "depth": 2.0, "height": 1.1},
                "position": {"x": 2.5, "y": 2.5},
                "rotation_deg": 90.0,
                "placement_mode": "floor_standing",
                "is_locked": True,
                "is_mandatory": True,
                "material": "MAT_OAK_LIGHT",
                "color": "#e0d0c0",
            }
        ],
        "wall_finish": "PAINT_SATIN_BEIGE_01",
        "floor_finish": "FLOOR_OAK_PARQUET_01",
    }
    resp = client.patch(f"/api/projects/{seeded_project.id}/esai-engine/designs/rooms/RM_BED_01", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["design_revision"] == 2

    # Verify persisted directly in database Master JSON
    in_memory_db.refresh(seeded_project)
    interior_layout = seeded_project.master_json["interior_layout"]
    assert interior_layout["design_revision"] == 2
    saved_bed = interior_layout["designs"]["rooms"]["RM_BED_01"]
    assert saved_bed["furniture"][0]["instance_id"] == "inst_bed_custom_1"
    assert saved_bed["furniture"][0]["rotation_deg"] == 90.0
    assert saved_bed["furniture"][0]["is_locked"] is True
    assert saved_bed["wall_finish"] == "PAINT_SATIN_BEIGE_01"


def test_save_room_edit_concurrency_conflict(client, seeded_project):
    """Verifies that sending an obsolete design revision returns HTTP 409."""
    payload = {
        "room_id": "RM_BED_01",
        "floor_id": "floor_gf",
        "expected_design_revision": 999,  # Obsolete
        "furniture": [
            {
                "instance_id": "inst_bed_1",
                "asset_id": "BED_QUEEN_STORAGE_01",
                "asset_name": "Queen Bed",
                "category": "bed",
                "dimensions": {"width": 1.6, "depth": 2.0, "height": 1.1},
                "position": {"x": 2.5, "y": 2.5},
                "rotation_deg": 0.0,
            }
        ]
    }
    resp = client.patch(f"/api/projects/{seeded_project.id}/esai-engine/designs/rooms/RM_BED_01", json=payload)
    assert resp.status_code == 409


def test_save_room_edit_invalid_rejected(client, seeded_project, in_memory_db):
    """Verifies that invalid geometry edits are rejected with HTTP 422 and do not mutate DB."""
    prev_rev = seeded_project.master_json["interior_layout"]["design_revision"]
    payload = {
        "room_id": "RM_BED_01",
        "floor_id": "floor_gf",
        "furniture": [
            {
                "instance_id": "inst_bed_collision_1",
                "asset_id": "BED_QUEEN_STORAGE_01",
                "asset_name": "Queen Bed",
                "category": "bed",
                "dimensions": {"width": 1.6, "depth": 2.0, "height": 1.1},
                "position": {"x": 2.5, "y": 2.5},
                "rotation_deg": 0.0,
            },
            {
                "instance_id": "inst_bed_collision_2",
                "asset_id": "BED_SINGLE_01",
                "asset_name": "Single Bed",
                "category": "bed",
                "dimensions": {"width": 1.0, "depth": 2.0, "height": 0.9},
                "position": {"x": 2.5, "y": 2.5},  # Complete overlap
                "rotation_deg": 0.0,
            }
        ]
    }
    resp = client.patch(f"/api/projects/{seeded_project.id}/esai-engine/designs/rooms/RM_BED_01", json=payload)
    assert resp.status_code == 422

    # Confirm database unchanged
    in_memory_db.refresh(seeded_project)
    assert seeded_project.master_json["interior_layout"]["design_revision"] == prev_rev


def test_toggle_asset_lock(client, seeded_project, in_memory_db):
    """Verifies locking and unlocking an asset instance."""
    # Find existing asset instance
    room_data = seeded_project.master_json["interior_layout"]["designs"]["rooms"]["RM_BED_01"]
    asset_id = room_data["furniture"][0]["instance_id"]

    # Lock asset
    lock_resp = client.post(
        f"/api/projects/{seeded_project.id}/esai-engine/designs/rooms/RM_BED_01/lock",
        json={"instance_id": asset_id, "is_locked": True, "lock_type": "all"}
    )
    assert lock_resp.status_code == 200
    lock_data = lock_resp.json()
    assert lock_data["is_locked"] is True
    assert lock_data["design_revision"] == 2

    in_memory_db.refresh(seeded_project)
    saved_furniture = seeded_project.master_json["interior_layout"]["designs"]["rooms"]["RM_BED_01"]["furniture"]
    target = next(a for a in saved_furniture if a["instance_id"] == asset_id)
    assert target["is_locked"] is True

    # Unlock asset
    unlock_resp = client.post(
        f"/api/projects/{seeded_project.id}/esai-engine/designs/rooms/RM_BED_01/unlock",
        json={"instance_id": asset_id, "is_locked": False}
    )
    assert unlock_resp.status_code == 200
    unlock_data = unlock_resp.json()
    assert unlock_data["is_locked"] is False
    assert unlock_data["design_revision"] == 3


def test_mandatory_bedroom_bed_removal_rejected(client, seeded_project):
    """Verifies that removing mandatory bed from bedroom is rejected."""
    payload = {
        "room_id": "RM_BED_01",
        "floor_id": "floor_gf",
        "furniture": [
            {
                "instance_id": "inst_wardrobe_only",
                "asset_id": "WARDROBE_3DOOR_01",
                "asset_name": "Wardrobe",
                "category": "wardrobe",
                "dimensions": {"width": 1.5, "depth": 0.6, "height": 2.2},
                "position": {"x": 2.0, "y": 2.5},
                "rotation_deg": 0.0,
            }
        ]
    }
    resp = client.post(f"/api/projects/{seeded_project.id}/esai-engine/designs/rooms/RM_BED_01/validate-edit", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["hard_constraints_passed"] is False
    codes = [d["code"] for d in data["diagnostics"]]
    assert "MANDATORY_ASSET_REMOVAL" in codes


def test_regenerate_unlocked_preserves_locked_assets(client, seeded_project, in_memory_db):
    """Verifies that selective regeneration preserves locked assets at exact coordinates and orientations."""
    # 1. Lock the existing bed at exact coordinates
    lock_resp = client.post(
        f"/api/projects/{seeded_project.id}/esai-engine/designs/rooms/RM_BED_01/lock",
        json={"instance_id": "inst_bed_1", "is_locked": True}
    )
    assert lock_resp.status_code == 200
    current_rev = lock_resp.json()["design_revision"]

    # 2. Trigger selective regeneration of unlocked assets
    regen_resp = client.post(
        f"/api/projects/{seeded_project.id}/esai-engine/designs/rooms/RM_BED_01/regenerate-unlocked",
        json={"expected_design_revision": current_rev}
    )
    assert regen_resp.status_code == 200, regen_resp.text
    data = regen_resp.json()
    assert data["success"] is True
    assert data["design_revision"] == current_rev + 1

    # Check preserved bed in response
    new_furniture = data["saved_design"]["furniture"]
    preserved_bed = next((a for a in new_furniture if a["instance_id"] == "inst_bed_1"), None)
    assert preserved_bed is not None
    assert preserved_bed["is_locked"] is True
    assert preserved_bed["position"]["x"] == 2.5
    assert preserved_bed["position"]["y"] == 2.5
    assert preserved_bed["rotation_deg"] == 0.0

