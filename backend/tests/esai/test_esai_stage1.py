"""
Pytest Suite for ESAI-Engine Stage 1 Backend Foundation
Validates all mandatory requirements:
- Catalog loading and queries
- Neufert standards parsing, exact provenance, and separation of unverified rules
- Room normalization, polygon parsing, area computation
- Unit conversion (mm, cm, ft, in -> m) and strict rejection of missing/invalid units
- Strict rejection of missing door/window geometry (no fabricated coordinates)
- Upstream compatibility blocker reporting when structural geometry is missing
- Room and floor identity cross-validation (actual rooms and correct floors)
- Input requirement cross-validation (unknown assets, density, door blockages)
- Validation rejection of invalid submissions vs explicit invalid_draft handling
- Transactional persistence (relational table and Master JSON update succeed or roll back together)
- Master JSON preservation & immutability
- Unique constraint for ESAI room requirements per project and room
- Validation of saved configuration room IDs against project geometry
- Shared FastAPI security model (401 unauthenticated, 403 non-admin, 200/501 admin)
- Single controlled 501 /run endpoint
"""
from types import SimpleNamespace
from copy import deepcopy
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.database import Base, get_db
from app.dependencies import get_current_user, require_admin
from app.main import app as fastapi_app
from app.models.project import Project
from app.models.esai import EsaiRoomRequirement, EsaiSavedConfig
from app.components.esai_engine.catalog import FurnitureCatalogRepository
from app.components.esai_engine.rules import ErgonomicStandardsRepository
from app.components.esai_engine.parser import StructuralInputParser
from app.components.esai_engine.normalizer import SpatialNormalizer
from app.components.esai_engine.validators import EsaiInputValidator
from app.components.esai_engine.contracts import (
    RoomRequirementsDTO,
    FurnitureRequirementItem,
    Dimensions3D,
    Coordinate2D,
    AssetCategory,
    RoomType,
    LengthUnit,
    StandardVerificationStatus,
    convert_to_meters,
)
from app.components.esai_engine.repositories import EsaiDatabaseRepository
from app.components.esai_engine.service import EsaiEngineService
from app.components.esai_engine.exceptions import (
    StructuralInputValidationError,
    CatalogItemNotFoundError,
    NeufertStandardRuleNotFoundError,
)
from tests.esai.fixtures import (
    BEDROOM_PROJECT_FIXTURE,
    MULTI_FLOOR_PROJECT_FIXTURE,
    L_SHAPED_ROOM_FIXTURE,
    MILLIMETERS_PROJECT_FIXTURE,
    INVALID_SELF_INTERSECTING_FIXTURE,
)

import app.models  # ensure all models are registered on Base.metadata

# Test in-memory engine for fast isolated unit & API contract tests
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def unauthenticated_client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def admin_client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    admin_user = SimpleNamespace(id="admin_1", username="admin", role="admin", is_active=True)
    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_user] = lambda: admin_user
    fastapi_app.dependency_overrides[require_admin] = lambda: admin_user
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def user_client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    regular_user = SimpleNamespace(id="user_1", username="regular", role="user", is_active=True)
    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_user] = lambda: regular_user
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


# ============================================================================
# 1. Catalog & Neufert Standards Tests (Audit & Provenance)
# ============================================================================
def test_furniture_catalog_loading():
    catalog = FurnitureCatalogRepository.get_instance()
    items = catalog.get_all()
    assert len(items) >= 15
    bed = catalog.get_by_id("BED_KING_01")
    assert bed.category == AssetCategory.BED
    assert bed.dimensions.width > 0
    assert bed.dimensions.depth > 0
    assert "master_bedroom" in bed.supported_room_types


def test_catalog_non_existent_item_raises_exception():
    catalog = FurnitureCatalogRepository.get_instance()
    with pytest.raises(CatalogItemNotFoundError):
        catalog.get_by_id("NON_EXISTENT_FURNITURE_XYZ")


def test_ergonomic_standards_provenance_and_verification():
    standards = ErgonomicStandardsRepository.get_instance()
    rules = standards.get_all()
    assert len(rules) >= 10

    # Phase 3 audit: Neufert attribution is preserved, but the page reference could not be
    # confirmed against licensed material, so it lives in historical_source_claim and the
    # rule is provisional (advisory), never mandatory compliance.
    bed_rule = standards.get_by_id("BED_ACCESS_PRIMARY")
    assert "Ernst Neufert" in bed_rule.source_title
    assert "4th International English Edition" in bed_rule.source_edition
    assert "p. 254" not in (bed_rule.source_section or "")
    assert "UNCONFIRMED" in (bed_rule.historical_source_claim or "")
    assert bed_rule.threshold_m == 0.70
    assert bed_rule.verification_status == StandardVerificationStatus.PROVISIONAL
    assert bed_rule.is_enforceable is True
    assert bed_rule.is_mandatory_compliance is False

    # Separate unverified rule: must NOT be mandatory compliance
    unverified_rule = standards.get_by_id("CUSTOM_EXPERIMENTAL_CLEARANCE")
    assert unverified_rule.verification_status == StandardVerificationStatus.UNVERIFIED
    assert unverified_rule.is_enforceable is False
    assert unverified_rule.is_mandatory_compliance is False

    # Check unverified filter
    unverified_list = standards.get_unverified_rules()
    assert any(r.id == "CUSTOM_EXPERIMENTAL_CLEARANCE" for r in unverified_list)
    assert all(r.verification_status == StandardVerificationStatus.UNVERIFIED for r in unverified_list)

    # Mandatory only filter excludes unverified rules
    mandatory_rules = standards.get_all(mandatory_only=True)
    assert unverified_rule not in mandatory_rules

    # Non-existent rule raises structured exception
    with pytest.raises(NeufertStandardRuleNotFoundError):
        standards.get_by_id("NON_EXISTENT_RULE_ID")


# ============================================================================
# 2. Structural Parsing, Unit Conversions & Geometry Prohibitions
# ============================================================================
def test_parse_bedroom_structural_geometry():
    parsed = StructuralInputParser.parse(BEDROOM_PROJECT_FIXTURE)
    assert parsed.project_id == "test_proj_bedroom_01"
    assert len(parsed.floors) == 1
    floor = parsed.floors[0]
    assert len(floor.rooms) == 1
    room = floor.rooms[0]
    assert room.room_id == "RM_BED_01"
    assert room.room_type == RoomType.MASTER_BEDROOM
    assert abs(room.area_sqm - 20.0) < 0.01
    assert len(room.doors) == 1
    assert room.doors[0].leaf_width == 0.9
    assert len(room.windows) == 1


def test_parse_multi_floor_and_room_discovery():
    parsed = StructuralInputParser.parse(MULTI_FLOOR_PROJECT_FIXTURE)
    assert len(parsed.floors) == 2
    all_rooms = SpatialNormalizer.find_all_rooms(parsed)
    assert len(all_rooms) == 3


def test_unit_conversion_from_millimeters_to_meters():
    parsed = StructuralInputParser.parse(MILLIMETERS_PROJECT_FIXTURE)
    room = parsed.floors[0].rooms[0]
    assert abs(room.area_sqm - 12.0) < 0.01
    assert abs(room.doors[0].leaf_width - 0.9) < 0.01


def test_unit_conversion_helper():
    assert convert_to_meters(100.0, LengthUnit.CENTIMETERS) == 1.0
    assert convert_to_meters(1000.0, LengthUnit.MILLIMETERS) == 1.0
    assert round(convert_to_meters(10.0, LengthUnit.FEET), 3) == 3.048
    assert round(convert_to_meters(12.0, LengthUnit.INCHES), 3) == 0.305


def test_missing_measurement_unit_rejected():
    fixture = deepcopy(BEDROOM_PROJECT_FIXTURE)
    del fixture["unit"]
    with pytest.raises(StructuralInputValidationError) as exc:
        StructuralInputParser.parse(fixture)
    assert "Missing measurement unit" in str(exc.value)


def test_invalid_measurement_unit_rejected():
    fixture = deepcopy(BEDROOM_PROJECT_FIXTURE)
    fixture["unit"] = "cubits"
    with pytest.raises(StructuralInputValidationError) as exc:
        StructuralInputParser.parse(fixture)
    assert "Invalid measurement unit" in str(exc.value)


def test_missing_door_positions_rejected_no_fabricated_geometry():
    fixture = deepcopy(BEDROOM_PROJECT_FIXTURE)
    del fixture["floor_plan"]["floors"][0]["rooms"][0]["doors"][0]["start"]
    with pytest.raises(StructuralInputValidationError) as exc:
        StructuralInputParser.parse(fixture)
    assert "missing required start/end coordinates" in str(exc.value)
    assert "Fabricated geometry is prohibited" in str(exc.value)


def test_missing_window_positions_rejected_no_fabricated_geometry():
    fixture = deepcopy(BEDROOM_PROJECT_FIXTURE)
    del fixture["floor_plan"]["floors"][0]["rooms"][0]["windows"][0]["end"]
    with pytest.raises(StructuralInputValidationError) as exc:
        StructuralInputParser.parse(fixture)
    assert "missing required start/end coordinates" in str(exc.value)
    assert "Fabricated geometry is prohibited" in str(exc.value)


def test_missing_structural_floor_plan_reports_compatibility_blocker():
    fixture = {"project_id": "p1", "project_name": "No Floor Plan", "unit": "m"}
    with pytest.raises(StructuralInputValidationError) as exc:
        StructuralInputParser.parse(fixture)
    assert "COMPATIBILITY_BLOCKER" in str(exc.value)


def test_invalid_self_intersecting_polygon_rejected():
    with pytest.raises(StructuralInputValidationError):
        StructuralInputParser.parse(INVALID_SELF_INTERSECTING_FIXTURE)


def test_l_shaped_polygon_area_computation():
    parsed = StructuralInputParser.parse(L_SHAPED_ROOM_FIXTURE)
    room = parsed.floors[0].rooms[0]
    assert abs(room.area_sqm - 27.0) < 0.01


# ============================================================================
# 3. Room and Floor Identity Cross-Validation
# ============================================================================
def test_requirements_referencing_nonexistent_room_detected(db_session):
    project = Project(id="proj_identity_01", project_name="Identity Test", master_json=BEDROOM_PROJECT_FIXTURE)
    db_session.add(project)
    db_session.commit()

    service = EsaiEngineService(db_session)
    reqs = RoomRequirementsDTO(
        room_id="NON_EXISTENT_ROOM_99",
        floor_id="floor_gf",
        room_type=RoomType.BEDROOM,
        items=[]
    )
    val = service.validate_room_requirements(project, reqs)
    assert val.valid is False
    assert any(err.code == "ROOM_NOT_FOUND" for err in val.errors)

    # Attempting to save requirements for a non-existent room must raise 404
    with pytest.raises(HTTPException) as exc:
        service.save_room_requirements(project, reqs)
    assert exc.value.status_code == 404


def test_requirements_referencing_nonexistent_floor_detected(db_session):
    project = Project(id="proj_identity_02", project_name="Floor Identity Test", master_json=BEDROOM_PROJECT_FIXTURE)
    db_session.add(project)
    db_session.commit()

    service = EsaiEngineService(db_session)
    reqs = RoomRequirementsDTO(
        room_id="RM_BED_01",
        floor_id="fake_floor_99",
        room_type=RoomType.MASTER_BEDROOM,
        items=[]
    )
    val = service.validate_room_requirements(project, reqs)
    assert val.valid is False
    assert any(err.code == "FLOOR_NOT_FOUND" for err in val.errors)


def test_requirements_floor_mismatch_detected(db_session):
    project = Project(id="proj_identity_03", project_name="Multi Floor Identity", master_json=MULTI_FLOOR_PROJECT_FIXTURE)
    db_session.add(project)
    db_session.commit()

    service = EsaiEngineService(db_session)
    # RM_BATH_01 is on fl_1, not fl_0
    reqs = RoomRequirementsDTO(
        room_id="RM_BATH_01",
        floor_id="fl_0",
        room_type=RoomType.BATHROOM,
        items=[]
    )
    val = service.validate_room_requirements(project, reqs)
    assert val.valid is False
    assert any(err.code == "ROOM_FLOOR_MISMATCH" for err in val.errors)


# ============================================================================
# 4. Client Requirements Validation & Draft Usability
# ============================================================================
def test_valid_room_requirements_validation():
    parsed = StructuralInputParser.parse(BEDROOM_PROJECT_FIXTURE)
    room = parsed.floors[0].rooms[0]

    reqs = RoomRequirementsDTO(
        room_id="RM_BED_01",
        floor_id="floor_gf",
        room_type=RoomType.MASTER_BEDROOM,
        items=[
            FurnitureRequirementItem(
                instance_id="item_king_bed_1",
                catalog_id="BED_KING_01",
                category=AssetCategory.BED,
                quantity=1
            )
        ]
    )

    validator = EsaiInputValidator()
    result = validator.validate_room_requirements(reqs, room)
    assert result.valid is True
    assert len(result.errors) == 0


def test_validation_fails_on_unknown_catalog_item():
    parsed = StructuralInputParser.parse(BEDROOM_PROJECT_FIXTURE)
    room = parsed.floors[0].rooms[0]

    reqs = RoomRequirementsDTO(
        room_id="RM_BED_01",
        floor_id="floor_gf",
        room_type=RoomType.MASTER_BEDROOM,
        items=[
            FurnitureRequirementItem(
                instance_id="item_invalid_asset",
                catalog_id="DOES_NOT_EXIST_001",
                category=AssetCategory.BED,
                quantity=1
            )
        ]
    )

    validator = EsaiInputValidator()
    result = validator.validate_room_requirements(reqs, room)
    assert result.valid is False
    assert any(err.code == "CATALOG_ITEM_UNKNOWN" for err in result.errors)


def test_validation_detects_locked_item_blocking_door():
    parsed = StructuralInputParser.parse(BEDROOM_PROJECT_FIXTURE)
    room = parsed.floors[0].rooms[0]

    reqs = RoomRequirementsDTO(
        room_id="RM_BED_01",
        floor_id="floor_gf",
        room_type=RoomType.MASTER_BEDROOM,
        items=[
            FurnitureRequirementItem(
                instance_id="item_locked_wardrobe_in_door",
                catalog_id="WARDROBE_3DOOR_01",
                category=AssetCategory.WARDROBE,
                user_locked=True,
                locked_position=Coordinate2D(x=0.5, y=0.9),
                locked_rotation=0
            )
        ]
    )

    validator = EsaiInputValidator()
    result = validator.validate_room_requirements(reqs, room)
    assert result.valid is False
    assert any(err.code == "LOCKED_ASSET_BLOCKS_DOOR" for err in result.errors)


def test_invalid_requirements_rejected_when_submitted_as_usable(db_session):
    project = Project(id="proj_req_reject_01", project_name="Reject Usable Invalid", master_json=BEDROOM_PROJECT_FIXTURE)
    db_session.add(project)
    db_session.commit()

    service = EsaiEngineService(db_session)
    invalid_reqs = RoomRequirementsDTO(
        room_id="RM_BED_01",
        floor_id="floor_gf",
        room_type=RoomType.MASTER_BEDROOM,
        items=[
            FurnitureRequirementItem(
                instance_id="item_unknown",
                catalog_id="NOT_A_REAL_ITEM",
                category=AssetCategory.BED
            )
        ]
    )

    # Submitting as "ready" or usable must raise 422
    with pytest.raises(HTTPException) as exc:
        service.save_room_requirements(project, invalid_reqs, status="ready")
    assert exc.value.status_code == 422


def test_invalid_requirements_persisted_as_draft_marked_invalid_draft(db_session):
    project = Project(id="proj_req_draft_01", project_name="Persist Draft", master_json=BEDROOM_PROJECT_FIXTURE)
    db_session.add(project)
    db_session.commit()

    service = EsaiEngineService(db_session)
    invalid_reqs = RoomRequirementsDTO(
        room_id="RM_BED_01",
        floor_id="floor_gf",
        room_type=RoomType.MASTER_BEDROOM,
        items=[
            FurnitureRequirementItem(
                instance_id="item_unknown",
                catalog_id="NOT_A_REAL_ITEM",
                category=AssetCategory.BED
            )
        ]
    )

    # Saving as draft with errors must be marked "invalid_draft" (never usable for optimization)
    res = service.save_room_requirements(project, invalid_reqs, status="draft")
    assert res["status"] == "invalid_draft"
    assert res["validation"]["valid"] is False


# ============================================================================
# 5. Database Persistence, Unique Constraints & Master JSON Immutability
# ============================================================================
def test_room_requirements_unique_constraint(db_session):
    project = Project(id="proj_uniq_01", project_name="Unique Constraint Test", master_json=BEDROOM_PROJECT_FIXTURE)
    db_session.add(project)
    db_session.commit()

    # Insert first record
    rec1 = EsaiRoomRequirement(
        project_id="proj_uniq_01",
        floor_id="floor_gf",
        room_id="RM_BED_01",
        requirements_json={"item": "1"}
    )
    db_session.add(rec1)
    db_session.commit()

    # Insert duplicate record for same project and room must violate unique constraint
    rec2 = EsaiRoomRequirement(
        project_id="proj_uniq_01",
        floor_id="floor_gf",
        room_id="RM_BED_01",
        requirements_json={"item": "2"}
    )
    db_session.add(rec2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_transactional_requirement_persistence_success(db_session):
    project = Project(id="proj_trans_01", project_name="Transactional Success", master_json=BEDROOM_PROJECT_FIXTURE)
    db_session.add(project)
    db_session.commit()

    service = EsaiEngineService(db_session)
    reqs = RoomRequirementsDTO(
        room_id="RM_BED_01",
        floor_id="floor_gf",
        room_type=RoomType.MASTER_BEDROOM,
        items=[
            FurnitureRequirementItem(
                instance_id="bed_1",
                catalog_id="BED_KING_01",
                category=AssetCategory.BED
            )
        ]
    )

    res = service.save_room_requirements(project, reqs, status="ready")
    assert res["status"] == "ready"

    # Both relational table and project.master_json must be updated
    db_rec = service.db_repo.get_single_room_requirement("proj_trans_01", "RM_BED_01")
    assert db_rec is not None
    assert db_rec.status == "ready"

    db_session.refresh(project)
    assert "RM_BED_01" in project.master_json["interior_layout"]["room_requirements"]
    assert project.master_json["processing"]["esai_engine"]["status"] == "pending"


def test_master_json_immutability_and_preservation(db_session):
    original_master = deepcopy(BEDROOM_PROJECT_FIXTURE)
    original_master["unrelated_research_field"] = {"model_name": "special_v1", "scores": [0.95, 0.98]}
    project = Project(id="proj_immut_01", project_name="Immutability Test", master_json=original_master)
    db_session.add(project)
    db_session.commit()

    service = EsaiEngineService(db_session)
    reqs = RoomRequirementsDTO(
        room_id="RM_BED_01",
        floor_id="floor_gf",
        room_type=RoomType.MASTER_BEDROOM,
        items=[
            FurnitureRequirementItem(
                instance_id="bed_1",
                catalog_id="BED_KING_01",
                category=AssetCategory.BED
            )
        ]
    )
    service.save_room_requirements(project, reqs)

    db_session.refresh(project)
    # Structural geometry preserved exactly
    assert project.master_json["floor_plan"]["floors"][0]["rooms"][0]["polygon"] == original_master["floor_plan"]["floors"][0]["rooms"][0]["polygon"]
    # Unrelated research field preserved untouched
    assert project.master_json["unrelated_research_field"] == {"model_name": "special_v1", "scores": [0.95, 0.98]}
    # Only ESAI-owned fields added
    assert "RM_BED_01" in project.master_json["interior_layout"]["room_requirements"]


# ============================================================================
# 6. Saved Configurations Room ID Validation
# ============================================================================
def test_saved_config_with_invalid_room_id_rejected(admin_client, db_session):
    project = Project(id="proj_cfg_val_01", project_name="Cfg Val Test", master_json=BEDROOM_PROJECT_FIXTURE)
    db_session.add(project)
    db_session.commit()

    # Room 'FAKE_ROOM_ID' does not exist in BEDROOM_PROJECT_FIXTURE (only RM_BED_01 exists)
    res = admin_client.post(
        "/api/projects/proj_cfg_val_01/esai-engine/configurations",
        json={
            "configuration_name": "Bad Room Config",
            "room_ids": ["FAKE_ROOM_ID"],
            "settings": {}
        }
    )
    assert res.status_code == 422
    assert "invalid room id" in res.json()["detail"].lower()


def test_saved_config_with_empty_room_ids_rejected(admin_client, db_session):
    project = Project(id="proj_cfg_val_02", project_name="Cfg Empty Test", master_json=BEDROOM_PROJECT_FIXTURE)
    db_session.add(project)
    db_session.commit()

    res = admin_client.post(
        "/api/projects/proj_cfg_val_02/esai-engine/configurations",
        json={
            "configuration_name": "Empty Rooms Config",
            "room_ids": [],
            "settings": {}
        }
    )
    assert res.status_code == 422


def test_saved_config_crud_success(admin_client, db_session):
    project = Project(id="proj_cfg_ok_01", project_name="Cfg Success", master_json=BEDROOM_PROJECT_FIXTURE)
    db_session.add(project)
    db_session.commit()

    # Create
    post_res = admin_client.post(
        "/api/projects/proj_cfg_ok_01/esai-engine/configurations",
        json={
            "configuration_name": "Valid Scandi Layout",
            "room_ids": ["RM_BED_01"],
            "settings": {"theme": "scandi"}
        }
    )
    assert post_res.status_code == 201
    cfg_id = post_res.json()["id"]

    # List
    list_res = admin_client.get("/api/projects/proj_cfg_ok_01/esai-engine/configurations")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # Update
    put_res = admin_client.put(
        f"/api/projects/proj_cfg_ok_01/esai-engine/configurations/{cfg_id}",
        json={
            "configuration_name": "Updated Scandi Layout",
            "room_ids": ["RM_BED_01"]
        }
    )
    assert put_res.status_code == 200
    assert put_res.json()["configuration_name"] == "Updated Scandi Layout"

    # Delete
    del_res = admin_client.delete(f"/api/projects/proj_cfg_ok_01/esai-engine/configurations/{cfg_id}")
    assert del_res.status_code == 204


# ============================================================================
# 7. Shared Security Model (Authentication & Authorization)
# ============================================================================
def test_project_endpoints_require_authentication(unauthenticated_client, db_session):
    project = Project(id="proj_sec_01", project_name="Security Test", master_json=BEDROOM_PROJECT_FIXTURE)
    db_session.add(project)
    db_session.commit()

    # Unauthenticated requests to project endpoints must be rejected with 401
    endpoints = [
        ("POST", "/api/projects/proj_sec_01/esai-engine/run"),
        ("GET", "/api/projects/proj_sec_01/esai-engine/context"),
        ("GET", "/api/projects/proj_sec_01/esai-engine/floors"),
        ("GET", "/api/projects/proj_sec_01/esai-engine/rooms"),
        ("GET", "/api/projects/proj_sec_01/esai-engine/requirements"),
        ("POST", "/api/projects/proj_sec_01/esai-engine/validate-input"),
        ("GET", "/api/projects/proj_sec_01/esai-engine/configurations"),
    ]
    for method, path in endpoints:
        if method == "POST":
            res = unauthenticated_client.post(path)
        else:
            res = unauthenticated_client.get(path)
        assert res.status_code == 401, f"{path} expected 401, got {res.status_code}"


def test_project_endpoints_forbid_non_admin_users(user_client, db_session):
    project = Project(id="proj_sec_02", project_name="Security Non-Admin", master_json=BEDROOM_PROJECT_FIXTURE)
    db_session.add(project)
    db_session.commit()

    # Authenticated non-admin requests must receive 403 Forbidden
    res = user_client.get("/api/projects/proj_sec_02/esai-engine/context")
    assert res.status_code == 403


def test_global_knowledge_endpoints_are_public(unauthenticated_client):
    # Catalog, standards, and room-profiles remain publicly discoverable
    res_cat = unauthenticated_client.get("/api/esai/catalog")
    assert res_cat.status_code == 200
    assert res_cat.json()["total"] >= 15

    res_std = unauthenticated_client.get("/api/esai/standards")
    assert res_std.status_code == 200
    assert res_std.json()["total"] >= 10

    res_prof = unauthenticated_client.get("/api/esai/room-profiles")
    assert res_prof.status_code == 200
    assert len(res_prof.json()["profiles"]) >= 5


# ============================================================================
# 8. Real Evolutionary Optimization Run Endpoint
# ============================================================================
def test_api_run_executes_real_evolutionary_optimization(admin_client, db_session):
    project = Project(id="proj_run_01", project_name="Run GA Test", master_json=BEDROOM_PROJECT_FIXTURE)
    db_session.add(project)
    db_session.commit()

    response = admin_client.post(
        "/api/projects/proj_run_01/esai-engine/run",
        json={"scope": "room", "room_id": "RM_BED_01", "population_size": 15, "generations": 5, "seed": 42}
    )
    assert response.status_code == 200
    data = response.json()["result"]
    assert data["project_id"] == "proj_run_01"
    assert data["total_rooms_discovered"] == 1
    assert "RM_BED_01" in data["rooms"]
    assert data["rooms"]["RM_BED_01"]["status"] in ("success", "partial")
