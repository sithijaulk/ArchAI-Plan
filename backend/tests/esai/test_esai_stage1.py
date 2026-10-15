"""
Pytest Suite for ESAI-Engine Stage 1 Backend Foundation
Validates:
- Catalog loading and queries
- Standards parsing, verification flags, and provenance
- Room normalization, polygon parsing, area computation
- Unit conversion (mm, cm, ft, in -> m)
- Invalid geometry detection
- Input requirement cross-validation (unknown assets, density, door blockages)
- Master JSON preservation & immutability
- ESAI database repository persistence
- API endpoints & controlled 501 /run behavior
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models.project import Project
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

from sqlalchemy.pool import StaticPool
import app.models  # ensure all models are registered on Base.metadata

# Test Database setup (using in-memory SQLite only for isolated backend unit tests)
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
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


# ============================================================================
# 1. Catalog & Standards Tests
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

    # Verify Neufert rule provenance
    bed_rule = standards.get_by_id("BED_ACCESS_PRIMARY")
    assert bed_rule.source_title.startswith("Architects' Data")
    assert bed_rule.threshold_m == 0.70
    assert bed_rule.is_enforceable is True

    # Verify unverified rule handling
    unverified_rule = standards.get_by_id("CUSTOM_EXPERIMENTAL_CLEARANCE")
    assert unverified_rule.is_enforceable is False

    # Check non-existent rule
    with pytest.raises(NeufertStandardRuleNotFoundError):
        standards.get_by_id("NON_EXISTENT_RULE_ID")


# ============================================================================
# 2. Structural Parsing & Unit Conversions
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
    assert abs(room.area_sqm - 20.0) < 0.01  # 5.0m x 4.0m = 20 sqm
    assert len(room.doors) == 1
    assert room.doors[0].leaf_width == 0.9
    assert len(room.windows) == 1


def test_parse_multi_floor_and_room_discovery():
    parsed = StructuralInputParser.parse(MULTI_FLOOR_PROJECT_FIXTURE)
    assert len(parsed.floors) == 2

    all_rooms = SpatialNormalizer.find_all_rooms(parsed)
    assert len(all_rooms) == 3

    kitchens = SpatialNormalizer.find_rooms_by_type(parsed, RoomType.KITCHEN)
    assert len(kitchens) == 1
    assert kitchens[0].room_id == "RM_KITCHEN_01"

    bathrooms = SpatialNormalizer.find_rooms_by_type(parsed, RoomType.BATHROOM)
    assert len(bathrooms) == 1
    assert bathrooms[0].room_id == "RM_BATH_01"


def test_unit_conversion_from_millimeters_to_meters():
    parsed = StructuralInputParser.parse(MILLIMETERS_PROJECT_FIXTURE)
    room = parsed.floors[0].rooms[0]
    # 4000mm x 3000mm should normalize to 4m x 3m = 12 sqm
    assert abs(room.area_sqm - 12.0) < 0.01
    assert abs(room.doors[0].leaf_width - 0.9) < 0.01


def test_unit_conversion_helper():
    assert convert_to_meters(100.0, LengthUnit.CENTIMETERS) == 1.0
    assert convert_to_meters(1000.0, LengthUnit.MILLIMETERS) == 1.0
    assert round(convert_to_meters(10.0, LengthUnit.FEET), 3) == 3.048
    assert round(convert_to_meters(12.0, LengthUnit.INCHES), 3) == 0.305


def test_invalid_self_intersecting_polygon_rejected():
    with pytest.raises(StructuralInputValidationError):
        StructuralInputParser.parse(INVALID_SELF_INTERSECTING_FIXTURE)


def test_l_shaped_polygon_area_computation():
    parsed = StructuralInputParser.parse(L_SHAPED_ROOM_FIXTURE)
    room = parsed.floors[0].rooms[0]
    # L-shape: 6x3 bottom + 3x3 top = 18 + 9 = 27 sqm
    assert abs(room.area_sqm - 27.0) < 0.01


# ============================================================================
# 3. Client Requirements & Input Validation
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
            ),
            FurnitureRequirementItem(
                instance_id="item_nightstand_1",
                catalog_id="NIGHTSTAND_01",
                category=AssetCategory.BEDSIDE_TABLE,
                quantity=2
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

    # Door is at start [0.0, 0.5] end [0.0, 1.4].
    # Place a locked wardrobe directly in front of the door leaf
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


# ============================================================================
# 4. Database Persistence & Repository
# ============================================================================
def test_esai_database_repository_persistence(db_session):
    # Create test project
    project = Project(
        id="proj_test_db_01",
        project_name="Test Persist Project",
        master_json=BEDROOM_PROJECT_FIXTURE
    )
    db_session.add(project)
    db_session.commit()

    repo = EsaiDatabaseRepository(db_session)

    # 1. Upsert requirement
    req_data = {"test_key": "test_value"}
    record = repo.upsert_room_requirement(
        project_id="proj_test_db_01",
        floor_id="floor_gf",
        room_id="RM_BED_01",
        requirements_data=req_data
    )
    assert record.id is not None
    assert record.room_id == "RM_BED_01"

    # Query requirement
    queried = repo.get_single_room_requirement("proj_test_db_01", "RM_BED_01")
    assert queried is not None
    assert queried.requirements_json["test_key"] == "test_value"

    # 2. Saved Config CRUD
    cfg = repo.create_saved_config(
        project_id="proj_test_db_01",
        configuration_name="Minimalist Setup",
        room_ids=["RM_BED_01"],
        settings_data={"density": "minimal"}
    )
    assert cfg.id is not None

    configs = repo.list_saved_configs("proj_test_db_01")
    assert len(configs) == 1
    assert configs[0].configuration_name == "Minimalist Setup"

    # Delete
    deleted = repo.delete_saved_config("proj_test_db_01", cfg.id)
    assert deleted is True
    assert len(repo.list_saved_configs("proj_test_db_01")) == 0


def test_master_json_immutability_on_requirement_save(db_session):
    project = Project(
        id="proj_immutability_01",
        project_name="Preserve Structural Project",
        master_json=BEDROOM_PROJECT_FIXTURE
    )
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
    # Verify structural geometry was preserved
    assert project.master_json["floor_plan"]["floors"][0]["rooms"][0]["polygon"] == [
        [0.0, 0.0],
        [5.0, 0.0],
        [5.0, 4.0],
        [0.0, 4.0]
    ]
    # Verify interior layout was cleanly added
    assert "interior_layout" in project.master_json
    assert "RM_BED_01" in project.master_json["interior_layout"]["room_requirements"]


# ============================================================================
# 5. ESAI API Endpoints & Controlled 501
# ============================================================================
def test_api_run_returns_controlled_501(client, db_session):
    project = Project(
        id="proj_api_01",
        project_name="API Test Project",
        master_json=BEDROOM_PROJECT_FIXTURE
    )
    db_session.add(project)
    db_session.commit()

    response = client.post("/api/projects/proj_api_01/esai-engine/run")
    assert response.status_code == 501
    assert "esai" in response.json()["detail"].lower()


def test_api_context_and_floors_discovery(client, db_session):
    project = Project(
        id="proj_api_02",
        project_name="Context Test Project",
        master_json=MULTI_FLOOR_PROJECT_FIXTURE
    )
    db_session.add(project)
    db_session.commit()

    # Context
    res_ctx = client.get("/api/projects/proj_api_02/esai-engine/context")
    assert res_ctx.status_code == 200
    data = res_ctx.json()
    assert data["total_floors"] == 2
    assert data["total_rooms"] == 3

    # Floors
    res_floors = client.get("/api/projects/proj_api_02/esai-engine/floors")
    assert res_floors.status_code == 200
    assert len(res_floors.json()["floors"]) == 2

    # Single room
    res_room = client.get("/api/projects/proj_api_02/esai-engine/rooms/RM_KITCHEN_01")
    assert res_room.status_code == 200
    assert res_room.json()["room_type"] == "kitchen"


def test_api_global_catalog_and_standards(client):
    res_cat = client.get("/api/esai/catalog")
    assert res_cat.status_code == 200
    assert res_cat.json()["total"] >= 15

    res_std = client.get("/api/esai/standards")
    assert res_std.status_code == 200
    assert res_std.json()["total"] >= 10

    res_profiles = client.get("/api/esai/room-profiles")
    assert res_profiles.status_code == 200
    assert len(res_profiles.json()["profiles"]) >= 5


def test_api_saved_configurations_crud(client, db_session):
    project = Project(
        id="proj_api_cfg",
        project_name="Config Test Project",
        master_json=BEDROOM_PROJECT_FIXTURE
    )
    db_session.add(project)
    db_session.commit()

    # Create config
    post_res = client.post(
        "/api/projects/proj_api_cfg/esai-engine/configurations",
        json={
            "configuration_name": "Family Bed Layout",
            "room_ids": ["RM_BED_01"],
            "settings": {"style": "scandi"}
        }
    )
    assert post_res.status_code == 201
    cfg_id = post_res.json()["id"]

    # List configs
    list_res = client.get("/api/projects/proj_api_cfg/esai-engine/configurations")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # Delete config
    del_res = client.delete(f"/api/projects/proj_api_cfg/esai-engine/configurations/{cfg_id}")
    assert del_res.status_code == 204
