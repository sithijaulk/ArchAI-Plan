"""
ESAI Engine Phase 3 Comprehensive Verification Suite
Tests:
1. Unified Interior Asset Catalog (50+ assets, variants, finishes, placement modes, clearances)
2. Neufert & Anthropometric Ergonomic Rules Provenance & Audit
3. Room Profiles, Functional Relationships & Deterministic Aesthetic Scoring
4. Preference-to-Catalog Resolver:
   - Two single beds remain two distinct single bed instances (never merged)
   - Triple-sleeper bed preserved as distinct configuration (never converted to 3 single beds)
   - Bathtub exclusion respected (zero bathtub instances)
   - Hot water service requirement preserved
   - TV power/data socket association without fabricated coordinates
   - User locked placements and custom dimensions
   - Master JSON immutability during read-only GA resolution
5. Phase 3 API endpoints with authorization
"""
import os
import sys
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

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
from app.components.esai_engine.catalog import FurnitureCatalogRepository, CatalogAsset
from app.components.esai_engine.rules import ErgonomicStandardsRepository, StandardVerificationStatus
from app.components.esai_engine.room_knowledge import RoomKnowledgeRepository
from app.components.esai_engine.resolver import PreferenceToCatalogResolver
from app.components.esai_engine.service import EsaiEngineService
from app.components.esai_engine.contracts import (
    AssetCategory,
    PlacementMode,
    ServiceType,
    ServiceStatus,
    Dimensions3D,
    Coordinate2D,
)

from tests.esai.fixtures import (
    BEDROOM_PROJECT_FIXTURE,
    MULTI_FLOOR_PROJECT_FIXTURE,
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
def bedroom_project(in_memory_db):
    project = Project(
        project_name="Phase 3 Bedroom Test",
        master_json=deepcopy(BEDROOM_PROJECT_FIXTURE),
        revision=1,
    )
    in_memory_db.add(project)
    in_memory_db.commit()
    in_memory_db.refresh(project)
    return project


@pytest.fixture
def multi_room_project(in_memory_db):
    project = Project(
        project_name="Phase 3 Multi-Room Test",
        master_json=deepcopy(MULTI_FLOOR_PROJECT_FIXTURE),
        revision=1,
    )
    in_memory_db.add(project)
    in_memory_db.commit()
    in_memory_db.refresh(project)
    return project


# ══════════════════════════════════════════════════════════════════════════════
# 1. CATALOG INTEGRITY & ASSET COVERAGE
# ══════════════════════════════════════════════════════════════════════════════

def test_catalog_assets_integrity():
    """Verifies catalog coverage across bed variants, kitchen, bath, finishes, and dimensions."""
    catalog = FurnitureCatalogRepository.get_instance()
    all_items = catalog.get_all()
    assert len(all_items) >= 40, f"Expected 40+ catalog items, found {len(all_items)}"

    # Check distinct bed variants exist with unique IDs and explicit dimensions
    bed_variants = [
        "BED_SINGLE_01",
        "BED_DOUBLE_01",
        "BED_QUEEN_01",
        "BED_KING_01",
        "BED_TWIN_PAIR_01",
        "BED_BUNK_01",
        "BED_TRIPLE_SLEEPER_01",
        "BED_STORAGE_01",
    ]
    for bed_id in bed_variants:
        asset = catalog.get_by_id(bed_id)
        assert asset is not None, f"Bed variant {bed_id} missing from catalog"
        assert asset.dimensions.width > 0
        assert asset.dimensions.depth > 0
        assert asset.dimensions.height > 0
        assert asset.placement_mode == PlacementMode.FLOOR_STANDING
        assert "bedroom" in [r.lower() for r in asset.supported_room_types]

    # Check kitchen fixtures & appliances
    kitchen_assets = ["KITCHEN_SINK_UNIT_01", "COOKTOP_INDUCTION_01", "REFRIGERATOR_FRENCH_DOOR_01", "DISHWASHER_BUILTIN_01"]
    for k_id in kitchen_assets:
        asset = catalog.get_by_id(k_id)
        assert asset is not None, f"Kitchen fixture {k_id} missing"

    # Check bathroom fixtures
    bath_assets = ["BATH_COMMODE_WALLHUNG_01", "BATH_DOUBLE_VANITY_01", "BATH_WALKIN_SHOWER_01", "BATH_BATHTUB_FREESTANDING_01"]
    for b_id in bath_assets:
        asset = catalog.get_by_id(b_id)
        assert asset is not None, f"Bathroom fixture {b_id} missing"

    # Check surface finishes catalog
    finishes = catalog.get_all_finishes()
    assert len(finishes) >= 8, f"Expected 8+ finishes, found {len(finishes)}"
    finish_ids = {f.id for f in finishes}
    assert "FIN_WALL_PAINT_MATTE" in finish_ids
    assert "FIN_FLOOR_OAK_HARDWOOD" in finish_ids
    assert "FIN_CEILING_GYPSUM_COVE" in finish_ids


# ══════════════════════════════════════════════════════════════════════════════
# 2. ERGONOMIC RULES AUDIT & PROVENANCE
# ══════════════════════════════════════════════════════════════════════════════

def test_ergonomic_rules_provenance_and_audit():
    """Ensures verified rules have provenance and unverified rules are never mandatory."""
    rules_repo = ErgonomicStandardsRepository.get_instance()
    all_rules = rules_repo.get_all()
    assert len(all_rules) >= 15, "Expected 15+ ergonomic rules in knowledge base"

    provisional_count = 0
    unverified_count = 0

    for rule in all_rules:
        assert rule.threshold_m > 0
        assert rule.source_title != ""

        if rule.verification_status == StandardVerificationStatus.UNVERIFIED:
            unverified_count += 1
            # Critical requirement: Unverified rules must never be mandatory compliance
            assert not rule.is_mandatory_compliance, f"Unverified rule {rule.id} cannot be mandatory"
        elif rule.verification_status == StandardVerificationStatus.PROVISIONAL:
            provisional_count += 1
            # Provisional rules are advisory only
            assert not rule.is_mandatory_compliance, f"Provisional rule {rule.id} cannot be mandatory"

    assert provisional_count > 0, "Expected audited provisional rules"
    # Category query checks
    bed_rules = rules_repo.get_rules_for_category("bed")
    assert len(bed_rules) > 0


# ══════════════════════════════════════════════════════════════════════════════
# 3. ROOM PROFILES, FUNCTIONAL RELATIONS & AESTHETIC MATRIX
# ══════════════════════════════════════════════════════════════════════════════

def test_room_profiles_and_aesthetic_matrix():
    """Tests room profile retrieval and deterministic aesthetic harmony scoring."""
    knowledge = RoomKnowledgeRepository.get_instance()
    profiles = knowledge.list_profiles()
    assert len(profiles) >= 10, "Expected 10+ normalized room profiles"

    # Profile check for master_bedroom
    mb_profile = knowledge.get_profile("master_bedroom")
    assert mb_profile is not None
    assert "bed" in mb_profile.recommended_assets
    assert "dining_table" in mb_profile.incompatible_assets

    # Aesthetic scoring: Modern with matching oak & neutral palette
    eval_modern = knowledge.evaluate_aesthetic_compatibility(
        style_name="modern",
        palette=["neutral_warm"],
        materials=["wood_oak", "stainless_steel"],
    )
    assert 0.0 <= eval_modern.overall_compatibility_score <= 1.0
    assert eval_modern.style_cohesion_score >= 0.8
    assert eval_modern.material_harmony_score >= 0.8
    assert len(eval_modern.evaluations) > 0


# ══════════════════════════════════════════════════════════════════════════════
# 4. PREFERENCE RESOLVER: BEDROOM RULES (2 SINGLE BEDS, TRIPLE SLEEPER)
# ══════════════════════════════════════════════════════════════════════════════

def test_resolver_two_single_beds_remain_distinct(in_memory_db, bedroom_project):
    """
    CRITICAL PROMPT REQUIREMENT:
    Two single beds mandatory -> must resolve into two distinct single-bed asset instances.
    Never replace with a double bed.
    """
    service = EsaiEngineService(in_memory_db)
    # Save room preferences: bed_type=single, bed_quantity=2, wardrobe=sliding, ceiling_fan=true
    service.save_room_preferences(
        bedroom_project,
        room_id="RM_BED_01",
        preferences_data={
            "room_specific": {
                "bed_type": "single",
                "bed_quantity": 2,
                "wardrobe_type": "sliding",
            },
            "electrical": {
                "charging_station": True,
                "ceiling_fan": True,
            },
            "design_style": "scandinavian",
        },
    )

    resolved = service.resolve_room_design_input(bedroom_project, room_id="RM_BED_01", floor_id="floor_gf")

    # Check bed instances
    bed_instances = [inst for inst in resolved.asset_instances if inst.category == "bed"]
    assert len(bed_instances) == 2, f"Expected 2 distinct bed instances, got {len(bed_instances)}"
    assert bed_instances[0].instance_id != bed_instances[1].instance_id
    assert bed_instances[0].asset_id == "BED_SINGLE_01"
    assert bed_instances[1].asset_id == "BED_SINGLE_01"
    assert bed_instances[0].dimensions.width == pytest.approx(0.95, rel=1e-2)

    # Check wardrobe instance
    wardrobe_instances = [inst for inst in resolved.asset_instances if inst.category == "wardrobe"]
    assert len(wardrobe_instances) == 1

    # Check services (bedside charging + ceiling fan)
    svc_types = {s.service_type for s in resolved.service_requirements}
    assert ServiceType.USB_CHARGING in svc_types or ServiceType.POWER_GENERAL in svc_types
    assert ServiceType.FAN_POINT in svc_types

    # Ensure no coordinates were fabricated (all GA coordinates should remain None)
    for inst in resolved.asset_instances:
        if inst.priority != "user_locked":
            assert inst.locked_coordinates is None


def test_resolver_triple_sleeper_bed_preserved(in_memory_db, bedroom_project):
    """
    CRITICAL PROMPT REQUIREMENT:
    Triple-sleeper bed must be represented as a distinct configuration,
    not silently converted into three single beds.
    """
    service = EsaiEngineService(in_memory_db)
    service.save_room_preferences(
        bedroom_project,
        room_id="RM_BED_01",
        preferences_data={
            "room_specific": {
                "bed_type": "triple_sleeper",
                "bed_quantity": 1,
            },
        },
    )

    resolved = service.resolve_room_design_input(bedroom_project, room_id="RM_BED_01", floor_id="floor_gf")
    bed_instances = [inst for inst in resolved.asset_instances if inst.category == "bed"]

    assert len(bed_instances) == 1, "Triple sleeper must remain 1 instance, not converted into 3 single beds"
    assert bed_instances[0].asset_id == "BED_TRIPLE_SLEEPER_01"
    assert bed_instances[0].subtype == "triple_sleeper"
    assert bed_instances[0].dimensions.height >= 1.7, "Triple sleeper should have bunk height"


# ══════════════════════════════════════════════════════════════════════════════
# 5. PREFERENCE RESOLVER: BATHROOM RULES (BATHTUB EXCLUSION & HOT WATER)
# ══════════════════════════════════════════════════════════════════════════════

def test_resolver_bathroom_bathtub_exclusion_and_hot_water(in_memory_db, multi_room_project):
    """
    CRITICAL PROMPT REQUIREMENT:
    Input: Bathtub excluded, Shower mandatory, Hot water required, Vanity mandatory.
    Expected: No bathtub, shower present, vanity present, hot-water service requirement.
    """
    service = EsaiEngineService(in_memory_db)
    service.save_room_preferences(
        multi_room_project,
        room_id="RM_BATH_01",
        preferences_data={
            "excluded_furniture": ["bathtub"],
            "plumbing": {
                "bathtub_preferred": False,
                "hot_water": True,
                "vanity_basin_type": "single",
                "water_heater_type": "central_solar",
            },
        },
    )

    resolved = service.resolve_room_design_input(multi_room_project, room_id="RM_BATH_01", floor_id="fl_1")

    # Assert NO bathtub exists in resolved instances
    for inst in resolved.asset_instances:
        assert inst.category != "bathtub"
        assert "bathtub" not in inst.asset_id.lower()

    assert "bathtub" in resolved.excluded_categories

    # Assert Shower and Vanity are present
    categories = {inst.category for inst in resolved.asset_instances}
    assert "shower_enclosure" in categories or "shower" in categories
    assert "vanity_unit" in categories or "basin" in categories

    # Assert Hot Water service requirement
    hot_water_svcs = [s for s in resolved.service_requirements if s.service_type == ServiceType.WATER_HOT]
    assert len(hot_water_svcs) >= 1
    assert hot_water_svcs[0].status == ServiceStatus.PROPOSED_NEW
    assert hot_water_svcs[0].requires_professional_verification is True


# ══════════════════════════════════════════════════════════════════════════════
# 6. PREFERENCE RESOLVER: LIVING ROOM & TV SERVICE POINT MAPPING
# ══════════════════════════════════════════════════════════════════════════════

def test_resolver_living_room_tv_and_services(in_memory_db, multi_room_project):
    """
    CRITICAL PROMPT REQUIREMENT:
    TV unit mandatory on selected wall, TV power/data points required, 3-seat sofa mandatory.
    Expected: TV unit with wall preference, associated TV power/data, sofa, no fabricated coordinates.
    """
    service = EsaiEngineService(in_memory_db)
    service.save_room_preferences(
        multi_room_project,
        room_id="RM_LIVING_01",
        preferences_data={
            "room_specific": {
                "seating_type": "three_seat",
                "tv_wall": "North",
            },
            "electrical": {
                "tv_points": True,
            },
        },
    )

    resolved = service.resolve_room_design_input(multi_room_project, room_id="RM_LIVING_01", floor_id="fl_0")

    # Sofa check
    sofa_instances = [inst for inst in resolved.asset_instances if inst.category == "sofa"]
    assert len(sofa_instances) >= 1
    assert sofa_instances[0].dimensions.width >= 2.0

    # TV Unit check
    tv_instances = [inst for inst in resolved.asset_instances if inst.category in ("tv_console", "media_wall")]
    assert len(tv_instances) >= 1
    assert tv_instances[0].preferred_wall == "North"

    # TV electrical / data service requirement check
    tv_services = [s for s in resolved.service_requirements if s.service_type in (ServiceType.TV_POWER, ServiceType.TV_DATA)]
    assert len(tv_services) >= 1
    assert tv_services[0].requires_professional_verification is True


# ══════════════════════════════════════════════════════════════════════════════
# 7. CUSTOM DIMENSIONS, USER LOCKS & MASTER JSON IMMUTABILITY
# ══════════════════════════════════════════════════════════════════════════════

def test_resolver_custom_dimensions_and_locks(in_memory_db, bedroom_project):
    """Verifies that user custom dimensions and locked coordinates are respected."""
    service = EsaiEngineService(in_memory_db)
    initial_master_json = deepcopy(bedroom_project.master_json)
    initial_revision = bedroom_project.revision

    service.save_room_preferences(
        bedroom_project,
        room_id="RM_BED_01",
        preferences_data={
            "room_specific": {
                "bed_type": "queen",
                "bed_quantity": 1,
            },
            "locked_placements": [
                {
                    "item_id": "BED_QUEEN_01",
                    "x": 2.50,
                    "y": 3.10,
                    "rotation": 90.0,
                }
            ],
            "mandatory_furniture": [
                {
                    "id": "DESK_EXEC_01",
                    "quantity": 1,
                    "custom_dimensions": {"width": 1.40, "depth": 0.70, "height": 0.76},
                }
            ],
        },
    )

    resolved = service.resolve_room_design_input(bedroom_project, room_id="RM_BED_01", floor_id="floor_gf")

    # Locked bed check
    bed = next(inst for inst in resolved.asset_instances if inst.category == "bed")
    assert bed.priority == "user_locked"
    assert bed.locked_coordinates is not None
    assert bed.locked_coordinates.x == 2.50
    assert bed.locked_coordinates.y == 3.10
    assert bed.locked_rotation == 90.0

    # Custom desk dimensions check
    desk = next(inst for inst in resolved.asset_instances if inst.category == "desk")
    assert desk.dimensions.width == pytest.approx(1.40)
    assert desk.dimensions.depth == pytest.approx(0.70)

    # Master JSON immutability check for read-only GA resolution
    assert bedroom_project.master_json["floor_plan"]["floors"] == initial_master_json["floor_plan"]["floors"]


# ══════════════════════════════════════════════════════════════════════════════
# 8. API ENDPOINTS VERIFICATION
# ══════════════════════════════════════════════════════════════════════════════

def test_phase3_api_endpoints(in_memory_db, bedroom_project):
    """Tests the new Phase 3 catalog and resolution REST endpoints."""
    fastapi_app.dependency_overrides[get_db] = lambda: in_memory_db
    fastapi_app.dependency_overrides[require_admin] = lambda: {"user_id": "admin_1", "role": "admin"}
    client = TestClient(fastapi_app)

    try:
        # GET /api/esai/catalog/categories
        r1 = client.get("/api/esai/catalog/categories")
        assert r1.status_code == 200
        cats = r1.json().get("categories", [])
        assert "bed" in cats
        assert "wardrobe" in cats

        # GET /api/esai/catalog/items
        r2 = client.get("/api/esai/catalog/items?category=bed")
        assert r2.status_code == 200
        items = r2.json().get("items", [])
        assert len(items) >= 4

        # GET /api/esai/catalog/finishes
        r3 = client.get("/api/esai/catalog/finishes")
        assert r3.status_code == 200
        finishes = r3.json().get("finishes", [])
        assert len(finishes) >= 5

        # GET /api/esai/knowledge/styles
        r4 = client.get("/api/esai/knowledge/styles")
        assert r4.status_code == 200
        styles = r4.json().get("styles", {})
        assert "modern" in styles
        assert "scandinavian" in styles

        # GET /api/esai/knowledge/rules
        r5 = client.get("/api/esai/knowledge/rules?enforceable_only=true")
        assert r5.status_code == 200
        rules = r5.json().get("rules", [])
        assert len(rules) >= 5

        # POST /api/projects/{id}/esai-engine/preferences/rooms/{room_id}/resolve-design-input
        r6 = client.post(
            f"/api/projects/{bedroom_project.id}/esai-engine/preferences/rooms/RM_BED_01/resolve-design-input?floor_id=floor_gf"
        )
        assert r6.status_code == 200
        payload = r6.json().get("resolved", {})
        assert payload["room_id"] == "RM_BED_01"
        assert len(payload["asset_instances"]) > 0
        assert payload["feasibility_status"] in ("feasible", "conditional_warning")

    finally:
        fastapi_app.dependency_overrides.clear()
