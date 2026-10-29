"""
ESAI Phase 1 Validation Test Suite
Exhaustively tests all Phase 1 Acceptance Criteria:
1. GAB-GEN -> ESAI direct workflow without Component 2 (Workflow A)
2. GAB-GEN -> VSAI -> ESAI rectified workflow (Workflow B)
3. Room-type normalization (family_living_area, dining_area, attached/common bathroom, study_office)
4. Preservation of source_room_type and distinguishable bathroom types
5. Explicit handling of unknown room types (no silent conversion to OTHER)
6. Floor and Room ID preservation
7. Wall extraction and Opening completeness tracking (no fabricated geometry)
8. Geometry fingerprinting: stability against unrelated Master JSON changes & detection of stale geometry
9. Transactional persistence & optimistic concurrency (revision conflict rejection)
10. Preservation of other components' Master JSON data
11. Design preferences persistence and retrieval
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
from app.models.esai import EsaiRoomRequirement, EsaiDesignPreference
from app.components.esai_engine.parser import StructuralInputParser, normalize_room_type
from app.components.esai_engine.geometry import compute_geometry_fingerprint
from app.components.esai_engine.contracts import (
    RoomType,
    LengthUnit,
    RoomRequirementsDTO,
    FurnitureRequirementItem,
    AssetCategory,
)
from app.components.esai_engine.service import EsaiEngineService
from tests.esai.fixtures import (
    BEDROOM_PROJECT_FIXTURE,
    GAB_GEN_DIRECT_FIXTURE,
    VSAI_RECTIFIED_FIXTURE,
    UNKNOWN_ROOM_TYPE_FIXTURE,
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


# ==============================================================================
# SECTION 3: ROOM-TYPE NORMALIZATION TESTS
# ==============================================================================

def test_room_type_normalization_maps_gab_types_correctly():
    """Ensure upstream room types from GAB-GEN map to specific, distinct RoomTypes."""
    # Living types
    rt, src, unsupp = normalize_room_type("family_living_area")
    assert rt == RoomType.FAMILY_LIVING_AREA
    assert src == "family_living_area"
    assert not unsupp

    rt, src, unsupp = normalize_room_type("living_area")
    assert rt == RoomType.LIVING_ROOM
    assert not unsupp

    # Dining types
    rt, src, unsupp = normalize_room_type("dining_area")
    assert rt == RoomType.DINING_AREA
    assert not unsupp

    # Study / office
    rt, src, unsupp = normalize_room_type("study_office")
    assert rt == RoomType.STUDY_OFFICE
    assert not unsupp

    rt, src, unsupp = normalize_room_type("Study / Office")
    assert rt == RoomType.STUDY_OFFICE
    assert not unsupp


def test_bathroom_types_remain_distinguishable():
    """Ensure attached_bathroom, common_bathroom, and toilet do NOT collapse into generic bathroom."""
    rt_att, _, _ = normalize_room_type("attached_bathroom")
    rt_com, _, _ = normalize_room_type("common_bathroom")
    rt_toilet, _, _ = normalize_room_type("toilet")
    rt_bath, _, _ = normalize_room_type("bathroom")

    assert rt_att == RoomType.ATTACHED_BATHROOM
    assert rt_com == RoomType.COMMON_BATHROOM
    assert rt_toilet == RoomType.TOILET
    assert rt_bath == RoomType.BATHROOM

    # All 4 must be distinct enum values
    distinct_types = {rt_att, rt_com, rt_toilet, rt_bath}
    assert len(distinct_types) == 4


def test_unknown_room_type_handled_explicitly():
    """Unknown room type preserves source string and sets is_unsupported=True and UNKNOWN enum."""
    rt, src, unsupp = normalize_room_type("secret_bunker_level_2")
    assert rt == RoomType.UNKNOWN
    assert src == "secret_bunker_level_2"
    assert unsupp is True


def test_unknown_room_type_in_project_geometry_emits_validation_warning():
    """Parsing project with unknown room type succeeds, preserving ID and emitting warning."""
    structural = StructuralInputParser.parse(UNKNOWN_ROOM_TYPE_FIXTURE)
    assert len(structural.floors) == 1
    room = structural.floors[0].rooms[0]
    assert room.room_id == "RM_UNKNOWN_01"
    assert room.room_type == RoomType.UNKNOWN
    assert room.source_room_type == "cryogenic_vault"
    assert room.is_unsupported_type is True

    # Validate structural input
    from app.components.esai_engine.validators import EsaiInputValidator
    validator = EsaiInputValidator()
    result = validator.validate_structural_input(structural)
    unsupp_warnings = [w for w in result.warnings if w.code == "UNSUPPORTED_ROOM_TYPE"]
    assert len(unsupp_warnings) == 1
    assert "cryogenic_vault" in unsupp_warnings[0].message


# ==============================================================================
# SECTION 4 & 5: WORKFLOW A (GAB-GEN DIRECT) & GEOMETRY PARSING
# ==============================================================================

def test_workflow_a_gab_gen_direct_geometry():
    """Workflow A: GAB-Gen direct geometry without VSAI works cleanly."""
    doc = deepcopy(GAB_GEN_DIRECT_FIXTURE)
    structural = StructuralInputParser.parse(doc)

    assert structural.project_id == "test_gab_direct_01"
    assert structural.unit == LengthUnit.METERS
    assert structural.geometry_source == "gab_gen"
    assert len(structural.floors) == 1

    floor = structural.floors[0]
    assert floor.floor_id == "F0"
    assert floor.floor_name == "Ground Floor"
    assert len(floor.rooms) == 5

    # Check wall extraction
    assert len(floor.walls) == 1
    wall = floor.walls[0]
    assert wall.id == "W_EXT_01"
    assert wall.thickness == 0.225
    assert wall.wall_type == "exterior"
    assert "RM_FAM_LIV" in wall.related_room_ids

    # Check rooms
    fam_liv = next(r for r in floor.rooms if r.room_id == "RM_FAM_LIV")
    assert fam_liv.room_type == RoomType.FAMILY_LIVING_AREA
    assert fam_liv.source_room_type == "family_living_area"
    assert fam_liv.area_sqm == 25.0
    # Doors were not in GAB output: must be marked data unavailable, NOT fabricated!
    assert fam_liv.doors_data_available is False
    assert len(fam_liv.doors) == 0
    assert "doors" in fam_liv.missing_upstream_fields


def test_opening_completeness_distinction():
    """Distinction between absent door data vs explicitly zero doors is preserved."""
    # Room without doors key
    doc_absent = deepcopy(GAB_GEN_DIRECT_FIXTURE)
    structural_absent = StructuralInputParser.parse(doc_absent)
    rm_absent = structural_absent.floors[0].rooms[0]
    assert rm_absent.doors_data_available is False

    # Room with explicit empty doors list
    doc_empty = deepcopy(GAB_GEN_DIRECT_FIXTURE)
    doc_empty["floor_plan"]["floors"][0]["rooms"][0]["doors"] = []
    structural_empty = StructuralInputParser.parse(doc_empty)
    rm_empty = structural_empty.floors[0].rooms[0]
    assert rm_empty.doors_data_available is True
    assert len(rm_empty.doors) == 0


# ==============================================================================
# SECTION 6: WORKFLOW B (VSAI RECTIFIED GEOMETRY)
# ==============================================================================

def test_workflow_b_vsai_rectified_geometry():
    """Workflow B: when VSAI is completed, ESAI uses structural_rectification.floor_plan."""
    doc = deepcopy(VSAI_RECTIFIED_FIXTURE)
    structural = StructuralInputParser.parse(doc)

    assert structural.geometry_source == "vsai_rectifier"
    assert len(structural.floors) == 1
    floor = structural.floors[0]
    assert floor.floor_id == "F0_RECTIFIED"
    assert len(floor.rooms) == 1
    assert floor.rooms[0].room_id == "RM_VSAI_CORRECTED"
    assert floor.rooms[0].room_type == RoomType.MASTER_BEDROOM


def test_workflow_b_optional_falls_back_when_vsai_pending():
    """If VSAI is pending or incomplete, ESAI falls back to GAB-GEN floor_plan without error."""
    doc = deepcopy(VSAI_RECTIFIED_FIXTURE)
    doc["processing"]["vsai_rectifier"]["status"] = "pending"
    structural = StructuralInputParser.parse(doc)

    assert structural.geometry_source == "gab_gen"
    assert structural.floors[0].floor_id == "F0"
    assert structural.floors[0].rooms[0].room_id == "RM_GAB_ORIGINAL"


# ==============================================================================
# SECTION 8: GEOMETRY FINGERPRINTING & STALE DATA DETECTION
# ==============================================================================

def test_geometry_fingerprint_stability_against_unrelated_changes():
    """Unrelated changes (notes, exterior landscape, preferences) do NOT alter geometry fingerprint."""
    doc1 = deepcopy(BEDROOM_PROJECT_FIXTURE)
    structural1 = StructuralInputParser.parse(doc1)
    fp1 = compute_geometry_fingerprint(structural1)

    # Mutate unrelated fields
    doc2 = deepcopy(doc1)
    doc2["notes"] = "Client requested modern style"
    doc2["exterior_landscape"] = {"trees": [{"type": "oak", "x": 10.0, "y": 5.0}]}
    doc2["client_requirements"] = {"preferred_colors": ["beige", "teal"]}
    structural2 = StructuralInputParser.parse(doc2)
    fp2 = compute_geometry_fingerprint(structural2)

    assert fp1 == fp2, "Fingerprint must not change when unrelated metadata changes."


def test_geometry_fingerprint_changes_on_structural_modification():
    """Structural geometry change (e.g. vertex coordinates) DOES change the fingerprint."""
    doc1 = deepcopy(BEDROOM_PROJECT_FIXTURE)
    structural1 = StructuralInputParser.parse(doc1)
    fp1 = compute_geometry_fingerprint(structural1)

    doc2 = deepcopy(doc1)
    # Move room vertex from 5.0 to 6.0
    doc2["floor_plan"]["floors"][0]["rooms"][0]["polygon"][1] = [6.0, 0.0]
    doc2["floor_plan"]["floors"][0]["rooms"][0]["polygon"][2] = [6.0, 4.0]
    structural2 = StructuralInputParser.parse(doc2)
    fp2 = compute_geometry_fingerprint(structural2)

    assert fp1 != fp2, "Fingerprint must change when room geometry changes."


def test_staleness_detection_service(in_memory_db):
    """EsaiEngineService detects when upstream geometry changes after requirements were saved."""
    service = EsaiEngineService(in_memory_db)
    project = Project(
        project_name="Staleness Test Project",
        master_json=deepcopy(BEDROOM_PROJECT_FIXTURE),
        revision=1
    )
    in_memory_db.add(project)
    in_memory_db.commit()

    # Save room requirements (stores geometry_fingerprint)
    reqs = RoomRequirementsDTO(
        room_id="RM_BED_01",
        floor_id="floor_gf",
        room_type=RoomType.MASTER_BEDROOM,
        items=[
            FurnitureRequirementItem(
                instance_id="req_bed_1",
                catalog_id="BED_KING_01",
                category=AssetCategory.BED
            )
        ]
    )
    service.save_room_requirements(project, reqs)

    # Initial check: must be up to date
    stale_status = service.check_geometry_staleness(project)
    assert stale_status["is_stale"] is False
    assert stale_status["status"] == "up_to_date"

    # Upstream geometry modified (e.g. wall shifted)
    mj = deepcopy(project.master_json)
    mj["floor_plan"]["floors"][0]["rooms"][0]["polygon"][1] = [7.0, 0.0]
    mj["floor_plan"]["floors"][0]["rooms"][0]["polygon"][2] = [7.0, 4.0]
    project.master_json = mj
    in_memory_db.commit()

    # Staleness check must now flag as stale!
    stale_status_after = service.check_geometry_staleness(project)
    assert stale_status_after["is_stale"] is True
    assert stale_status_after["status"] == "stale"
    assert "Authoritative structural geometry has changed" in stale_status_after["message"]


# ==============================================================================
# SECTION 9: TRANSACTION SAFETY & OPTIMISTIC CONCURRENCY
# ==============================================================================

def test_optimistic_concurrency_conflict_rejected(in_memory_db):
    """Attempting to save requirements with a stale expected_revision raises 409 Conflict."""
    service = EsaiEngineService(in_memory_db)
    project = Project(
        project_name="Concurrency Project",
        master_json=deepcopy(BEDROOM_PROJECT_FIXTURE),
        revision=5
    )
    in_memory_db.add(project)
    in_memory_db.commit()

    reqs = RoomRequirementsDTO(
        room_id="RM_BED_01",
        floor_id="floor_gf",
        room_type=RoomType.MASTER_BEDROOM,
        items=[
            FurnitureRequirementItem(
                instance_id="req_bed_1",
                catalog_id="BED_KING_01",
                category=AssetCategory.BED
            )
        ]
    )

    # Supply outdated revision (expected 4, current is 5)
    with pytest.raises(HTTPException) as exc_info:
        service.save_room_requirements(project, reqs, expected_revision=4)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "PROJECT_STALE_REVISION"


def test_transactional_persistence_preserves_other_components_data(in_memory_db):
    """Saving requirements does NOT overwrite land_info, buildable_footprint, or exterior_landscape."""
    service = EsaiEngineService(in_memory_db)
    master = deepcopy(BEDROOM_PROJECT_FIXTURE)
    master["land_info"] = {"survey_number": "123/A", "area_sqft": 4500.0}
    master["exterior_landscape"] = {"greenery_ratio": 0.35}
    master["buildable_footprint"] = {"polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]}

    project = Project(
        project_name="Preservation Project",
        master_json=master,
        revision=1
    )
    in_memory_db.add(project)
    in_memory_db.commit()

    reqs = RoomRequirementsDTO(
        room_id="RM_BED_01",
        floor_id="floor_gf",
        room_type=RoomType.MASTER_BEDROOM,
        items=[
            FurnitureRequirementItem(
                instance_id="req_bed_1",
                catalog_id="BED_KING_01",
                category=AssetCategory.BED
            )
        ]
    )
    service.save_room_requirements(project, reqs)

    # Verify that project.master_json retained all non-ESAI sections
    saved_mj = project.master_json
    assert saved_mj["land_info"] == {"survey_number": "123/A", "area_sqft": 4500.0}
    assert saved_mj["exterior_landscape"] == {"greenery_ratio": 0.35}
    assert saved_mj["buildable_footprint"] == {"polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]}
    # And interior_layout was cleanly updated
    assert "RM_BED_01" in saved_mj["interior_layout"]["room_requirements"]


# ==============================================================================
# SECTION 13: DESIGN PREFERENCES (PHASE 2 EXTENSION POINTS)
# ==============================================================================

def test_design_preferences_persistence_and_retrieval(in_memory_db):
    """Can save and retrieve building/project-level design preferences without budget fields."""
    service = EsaiEngineService(in_memory_db)
    project = Project(
        project_name="Preferences Project",
        master_json=deepcopy(BEDROOM_PROJECT_FIXTURE),
        revision=1
    )
    in_memory_db.add(project)
    in_memory_db.commit()

    prefs_payload = {
        "style": "minimalist",
        "primary_palette": "warm_earth_tones",
        "flooring": "hardwood",
        "lighting_mood": "ambient_warm"
    }

    result = service.save_design_preferences(project, prefs_payload)
    assert result["preferences"]["style"] == "minimalist"
    assert result["geometry_fingerprint"] is not None

    # Retrieve via service
    retrieved = service.get_design_preferences(project.id)
    assert retrieved is not None
    assert retrieved["preferences"]["flooring"] == "hardwood"

    # Verify Master JSON has interior_layout.preferences
    assert project.master_json["interior_layout"]["preferences"]["style"] == "minimalist"


# ==============================================================================
# API ENDPOINT TESTS FOR NEW PHASE 1 ROUTES
# ==============================================================================

def test_api_staleness_endpoint(auth_client, in_memory_db):
    """GET /api/projects/{id}/esai-engine/staleness returns staleness status."""
    project = Project(
        project_name="API Staleness Project",
        master_json=deepcopy(BEDROOM_PROJECT_FIXTURE),
        revision=1
    )
    in_memory_db.add(project)
    in_memory_db.commit()

    resp = auth_client.get(f"/api/projects/{project.id}/esai-engine/staleness")
    assert resp.status_code == 200
    data = resp.json()
    assert "is_stale" in data
    assert "geometry_fingerprint" in data


def test_api_preferences_endpoint(auth_client, in_memory_db):
    """PUT and GET /api/projects/{id}/esai-engine/preferences works with authorization."""
    project = Project(
        project_name="API Prefs Project",
        master_json=deepcopy(BEDROOM_PROJECT_FIXTURE),
        revision=1
    )
    in_memory_db.add(project)
    in_memory_db.commit()

    prefs = {"interior_style": "scandinavian", "wall_finish": "matte_white"}
    put_resp = auth_client.put(f"/api/projects/{project.id}/esai-engine/preferences", json=prefs)
    assert put_resp.status_code == 200
    assert put_resp.json()["preferences"]["interior_style"] == "scandinavian"

    get_resp = auth_client.get(f"/api/projects/{project.id}/esai-engine/preferences")
    assert get_resp.status_code == 200
    assert get_resp.json()["preferences"]["preferences"]["wall_finish"] == "matte_white"
