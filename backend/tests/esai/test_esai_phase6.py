"""
Phase 6 Automated Test Suite: Realistic 3D Scene Visualization Data Pipeline
Verifies:
1. Retrieval of authoritative architectural geometry (floors, rooms, walls, doors, windows, elevations).
2. Retrieval of saved interior design layouts from projects.master_json['interior_layout'].
3. Preserves real floor and room IDs (no fabricated or hardcoded IDs).
4. Floor/room filtering options.
5. Geometry and design revision metadata + staleness report.
6. Centralized Master JSON is strictly preserved (read-only query, no mutations).
7. Non-existent project returns 404.
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
from tests.esai.fixtures import GAB_GEN_DIRECT_FIXTURE, MULTI_FLOOR_PROJECT_FIXTURE


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


def test_scene_data_endpoint_structure(client, in_memory_db):
    """
    Verifies GET /api/projects/{id}/esai-engine/scene returns authoritative geometry
    and saved interior design layout data with correct structure and types.
    """
    proj = Project(
        id="proj-scene-001",
        project_name="Scene Test Project",
        master_json=deepcopy(MULTI_FLOOR_PROJECT_FIXTURE),
        revision=1,
    )
    in_memory_db.add(proj)
    in_memory_db.commit()

    resp = client.get(f"/api/projects/{proj.id}/esai-engine/scene")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["project_id"] == proj.id
    assert data["project_name"] == proj.project_name
    assert "floors" in data
    assert len(data["floors"]) >= 2
    assert "saved_designs" in data
    assert "staleness" in data
    assert data["geometry_revision"] == 1

    # Verify floor IDs and room IDs match authoritative geometry
    floor_ids = [f["floor_id"] for f in data["floors"]]
    assert "fl_0" in floor_ids
    assert "fl_1" in floor_ids

    ground_floor = next(f for f in data["floors"] if f["floor_id"] == "fl_0")
    assert len(ground_floor["rooms"]) == 2
    room_ids = [r["room_id"] for r in ground_floor["rooms"]]
    assert "RM_LIVING_01" in room_ids
    assert "RM_KITCHEN_01" in room_ids


def test_scene_data_floor_and_room_filtering(client, in_memory_db):
    """
    Verifies that floor_id and room_id query parameters accurately filter the scene data.
    """
    proj = Project(
        id="proj-scene-002",
        project_name="Filter Test Project",
        master_json=deepcopy(MULTI_FLOOR_PROJECT_FIXTURE),
        revision=1,
    )
    in_memory_db.add(proj)
    in_memory_db.commit()

    # Filter by floor_id
    resp = client.get(f"/api/projects/{proj.id}/esai-engine/scene?floor_id=fl_1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["floors"]) == 1
    assert data["floors"][0]["floor_id"] == "fl_1"

    # Filter by room_id
    resp = client.get(f"/api/projects/{proj.id}/esai-engine/scene?room_id=RM_BATH_01")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["floors"]) == 1
    assert len(data["floors"][0]["rooms"]) == 1
    assert data["floors"][0]["rooms"][0]["room_id"] == "RM_BATH_01"


def test_scene_data_uses_flat_gab_rooms_when_floor_list_is_empty(client, in_memory_db):
    """
    GAB-Gen also publishes a flat floor_plan.rooms view. Keep that geometry usable
    by ESAI when an upstream Master JSON has an empty floors list.
    """
    master_json = deepcopy(GAB_GEN_DIRECT_FIXTURE)
    master_json["floor_plan"]["rooms"] = [
        room
        for floor in master_json["floor_plan"]["floors"]
        for room in floor["rooms"]
    ]
    master_json["floor_plan"]["floors"] = []
    project = Project(
        id="proj-scene-flat-gab",
        project_name="Flat GAB Geometry",
        master_json=master_json,
        revision=1,
    )
    in_memory_db.add(project)
    in_memory_db.commit()

    response = client.get(f"/api/projects/{project.id}/esai-engine/scene")

    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["floors"]) == 1
    assert data["floors"][0]["floor_id"] == "F0"
    assert len(data["floors"][0]["rooms"]) == 5


def test_scene_data_read_only_master_json_integrity(client, in_memory_db):
    """
    Verifies that retrieving scene data NEVER mutates the projects.master_json.
    """
    orig_json = deepcopy(MULTI_FLOOR_PROJECT_FIXTURE)
    proj = Project(
        id="proj-scene-003",
        project_name="Read Only Test",
        master_json=deepcopy(orig_json),
        revision=1,
    )
    in_memory_db.add(proj)
    in_memory_db.commit()

    resp = client.get(f"/api/projects/{proj.id}/esai-engine/scene")
    assert resp.status_code == 200

    in_memory_db.refresh(proj)
    assert proj.master_json == orig_json, "Scene data query must be strictly read-only"


def test_scene_data_nonexistent_project_404(client):
    """
    Verifies that requesting scene data for a non-existent project returns 404.
    """
    resp = client.get("/api/projects/non-existent-99999/esai-engine/scene")
    assert resp.status_code == 404
