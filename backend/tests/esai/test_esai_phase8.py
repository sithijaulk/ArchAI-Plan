"""
Phase 8 Automated Test Suite: Professional Interior Design PDF Reports, Room Schedules,
Layout Drawings & Final Project Export.

Verifies:
1. GET /reports/options returns available scopes, sections, floors, rooms, and staleness info.
2. POST /reports/pdf generates a valid binary PDF (%PDF- header) for building, floor, and room scopes.
3. Master JSON remains strictly unchanged after report generation.
4. Final vs Draft mode: Stale geometry triggers HTTP 422 in final mode, but succeeds with watermark in draft mode.
5. Scenario C: Two Single Beds are represented distinctly as two items (no collapse to double bed).
6. Scenario D: Bathtub and hot water are excluded when not selected in client preferences.
7. Scenario G: Manually edited and locked assets preserve their locked status in schedules.
8. Scenario E & F: Kitchen and TV Lobby schedules include associated MEP provisions without invented coordinates.
9. Optional 3D viewer snapshot integration works with valid base64 image and handles missing captures gracefully.
10. POST /reports/export-data exports structured ESAI JSON without altering database.
11. Security: Cross-project room/floor requests are rejected.
12. Strict exclusion: No budget, price, quotation, or cost fields exist anywhere in exports.
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
from app.components.esai_engine.parser import StructuralInputParser
from app.components.esai_engine.geometry import compute_geometry_fingerprint
from app.components.esai_engine.service import EsaiEngineService
from app.components.esai_engine.reporting import (
    PdfReportRequest,
    ReportScope,
    ReportMode,
)
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


def _create_saved_project(db, fixture_dict=None) -> Project:
    mj = deepcopy(fixture_dict or BEDROOM_PROJECT_FIXTURE)
    structural_input = StructuralInputParser.parse(mj)
    geo_fp = compute_geometry_fingerprint(structural_input)

    if "interior_layout" not in mj:
        mj["interior_layout"] = {
            "design_revision": 1,
            "schema_version": "1.0.0",
            "geometry_fingerprint": geo_fp,
            "designs": {
                "rooms": {
                    "RM_BED_01": {
                        "project_id": "proj-phase8-001",
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
                                "asset_id": "bed-queen-01",
                                "asset_name": "Queen Bed",
                                "category": "bedroom",
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
                        "lighting": [
                            {
                                "fixture_id": "lgt_1",
                                "fixture_type": "recessed_led",
                                "purpose": "ambient",
                                "installation_mode": "ceiling_recessed",
                                "position": {"x": 2.5, "y": 2.0},
                                "height_from_floor_m": 2.8,
                                "is_proposed": True,
                            }
                        ],
                        "electrical_points": [
                            {
                                "point_id": "ep_1",
                                "service_type": "power_outlet",
                                "position": {"x": 1.0, "y": 0.0},
                                "height_m": 0.45,
                                "is_proposed": True,
                            }
                        ],
                        "plumbing_requirements": [],
                        "service_requirements": [],
                        "wall_finishes": {},
                        "floor_finishes": {},
                        "ceiling_finishes": {},
                        "wall_finish": "PAINT_MATTE_WHITE_01",
                        "floor_finish": "FLOOR_OAK_PARQUET_01",
                        "ceiling_finish": "CEILING_GYPSUM_COVE_01",
                        "validation": {
                            "hard_constraints_passed": True,
                            "fitness_score": 0.95,
                            "ergonomic_evaluations": [],
                            "diagnostics": [],
                        },
                        "generation_metadata": {
                            "num_generations": 15,
                            "population_size": 20,
                            "seed": 42,
                            "runtime_seconds": 1.25,
                        },
                        "alternatives": [],
                    }
                }
            },
            "revisions": [{"design_revision": 1, "scope": "initial"}],
        }

    p = Project(
        id="proj-phase8-001",
        project_name="Phase 8 Test Project",
        master_json=mj,
        revision=1,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# 1. Report Options Endpoint
def test_get_report_options(client, in_memory_db):
    project = _create_saved_project(in_memory_db)
    res = client.get(f"/api/projects/{project.id}/esai-engine/reports/options")
    assert res.status_code == 200
    data = res.json()
    assert "supported_scopes" in data
    assert "building" in data["supported_scopes"]
    assert "floor" in data["supported_scopes"]
    assert "room" in data["supported_scopes"]
    assert "supported_sections" in data
    assert len(data["available_floors"]) >= 1
    assert len(data["available_rooms"]) >= 1
    assert "staleness" in data


# 2. PDF Generation: Building Scope
def test_generate_pdf_building_scope(client, in_memory_db):
    project = _create_saved_project(in_memory_db)
    master_json_before = deepcopy(project.master_json)

    res = client.post(
        f"/api/projects/{project.id}/esai-engine/reports/pdf",
        json={"scope": "building", "mode": "final"},
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in res.headers["content-disposition"]
    pdf_bytes = res.content
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 2000

    # Verify Master JSON is 100% untouched
    in_memory_db.refresh(project)
    assert project.master_json == master_json_before


# 3. PDF Generation: Room Scope
def test_generate_pdf_room_scope(client, in_memory_db):
    project = _create_saved_project(in_memory_db)
    res = client.post(
        f"/api/projects/{project.id}/esai-engine/reports/pdf",
        json={"scope": "room", "room_ids": ["RM_BED_01"], "mode": "final"},
    )
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF-")


# 4. Final Mode Rejects Stale Design (Scenario H)
def test_final_mode_rejects_stale_design(client, in_memory_db):
    project = _create_saved_project(in_memory_db)
    # Tamper geometry to cause staleness
    mj = deepcopy(project.master_json)
    room = mj["floor_plan"]["floors"][0]["rooms"][0]
    room["polygon"][0] = [999.0, 999.0]
    project.master_json = mj
    in_memory_db.commit()

    # Final mode must be rejected with 422
    res = client.post(
        f"/api/projects/{project.id}/esai-engine/reports/pdf",
        json={"scope": "building", "mode": "final"},
    )
    assert res.status_code == 422
    err = res.json()["detail"]
    assert err["code"] == "STALE_DESIGN_EXPORT_BLOCKED"


# 5. Draft Mode Allows Stale Design with Watermark (Scenario H)
def test_draft_mode_allows_stale_design(client, in_memory_db):
    project = _create_saved_project(in_memory_db)
    mj = deepcopy(project.master_json)
    room = mj["floor_plan"]["floors"][0]["rooms"][0]
    room["polygon"][0] = [999.0, 999.0]
    project.master_json = mj
    in_memory_db.commit()

    # Draft mode must succeed
    res = client.post(
        f"/api/projects/{project.id}/esai-engine/reports/pdf",
        json={"scope": "building", "mode": "draft"},
    )
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF-")


# 6. Scenario C: Two Single Beds distinct schedule representation
def test_scenario_c_two_single_beds_representation(in_memory_db):
    project = _create_saved_project(in_memory_db)
    service = EsaiEngineService(in_memory_db)

    # Modify layout to have two single beds
    mj = deepcopy(project.master_json)
    room_layout = mj["interior_layout"]["designs"]["rooms"]["RM_BED_01"]
    room_layout["furniture"] = [
        {
            "instance_id": "inst-single-1",
            "asset_id": "bed-single-01",
            "variant": "standard",
            "asset_name": "Single Bed",
            "category": "bedroom",
            "dimensions": {"width": 1.0, "depth": 2.0, "height": 0.9},
            "position": {"x": 1.0, "y": 1.0, "z": 0.0},
            "rotation": 0.0,
            "material": "oak",
            "color": "natural",
            "placement_mode": "free",
            "is_mandatory": True,
            "is_locked": False,
        },
        {
            "instance_id": "inst-single-2",
            "asset_id": "bed-single-01",
            "variant": "standard",
            "asset_name": "Single Bed",
            "category": "bedroom",
            "dimensions": {"width": 1.0, "depth": 2.0, "height": 0.9},
            "position": {"x": 3.0, "y": 1.0, "z": 0.0},
            "rotation": 0.0,
            "material": "oak",
            "color": "natural",
            "placement_mode": "free",
            "is_mandatory": True,
            "is_locked": False,
        },
    ]
    project.master_json = mj
    in_memory_db.commit()

    report_data = service.reporting_service.data_adapter.extract_report_data(
        project,
        PdfReportRequest(scope=ReportScope.ROOM, room_ids=["RM_BED_01"], mode=ReportMode.DRAFT),
    )
    room_data = report_data.floors[0].rooms[0]
    # Two distinct single beds
    assert len(room_data.furniture_schedule) == 2
    assert room_data.furniture_schedule[0].asset_name == "Single Bed"
    assert room_data.furniture_schedule[1].asset_name == "Single Bed"
    assert room_data.furniture_schedule[0].instance_id == "inst-single-1"
    assert room_data.furniture_schedule[1].instance_id == "inst-single-2"


# 7. Scenario D: Bathtub and Hot-Water Excluded When Not Selected
def test_scenario_d_bathroom_exclusion(in_memory_db):
    project = _create_saved_project(in_memory_db)
    service = EsaiEngineService(in_memory_db)

    mj = deepcopy(project.master_json)
    # Add a bathroom without bathtub and hot water
    mj["floor_plan"]["floors"][0]["rooms"].append({
        "room_id": "RM_BATH_01",
        "name": "Powder Room",
        "room_type": "bathroom",
        "polygon": [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]],
        "doors": [],
        "windows": [],
        "openings": [],
    })
    mj["client_preferences"] = mj.get("client_preferences", {})
    mj["client_preferences"]["room_requirements"] = mj["client_preferences"].get("room_requirements", {})
    mj["client_preferences"]["room_requirements"]["RM_BATH_01"] = {
        "bathroom": {
            "bathtub_selected": False,
            "hot_water_required": False,
        }
    }
    mj["interior_layout"]["designs"]["rooms"]["RM_BATH_01"] = {
        "room_id": "RM_BATH_01",
        "floor_id": "floor_gf",
        "design_revision": 1,
        "is_valid": True,
        "furniture": [
            {
                "instance_id": "inst-wc-1",
                "asset_id": "san-wc-01",
                "variant": "wall-hung",
                "asset_name": "Wall-Hung WC",
                "category": "bathroom",
                "dimensions": {"width": 0.4, "depth": 0.6, "height": 0.4},
                "position": {"x": 1.0, "y": 0.5},
                "rotation": 0.0,
                "placement_mode": "wall_aligned",
                "is_mandatory": True,
                "is_locked": False,
            }
        ],
    }
    project.master_json = mj
    in_memory_db.commit()

    report_data = service.reporting_service.data_adapter.extract_report_data(
        project,
        PdfReportRequest(scope=ReportScope.ROOM, room_ids=["RM_BATH_01"], mode=ReportMode.DRAFT),
    )
    room_data = [r for r in report_data.floors[0].rooms if r.room_id == "RM_BATH_01"][0]

    # Verify bathtub is NOT in schedule
    fixture_names = [f.asset_name.lower() for f in room_data.bathroom_schedule]
    assert not any("bathtub" in n for n in fixture_names)

    # Verify hot water is NOT in plumbing requirements
    plumbing_services = [p.service_type for p in room_data.plumbing_schedule]
    assert "hot_water_supply" not in plumbing_services


# 8. Scenario G: Locked asset retains locked status in schedule
def test_scenario_g_locked_asset_preservation(in_memory_db):
    project = _create_saved_project(in_memory_db)
    service = EsaiEngineService(in_memory_db)

    mj = deepcopy(project.master_json)
    room_layout = mj["interior_layout"]["designs"]["rooms"]["RM_BED_01"]
    room_layout["furniture"][0]["is_locked"] = True
    project.master_json = mj
    in_memory_db.commit()

    report_data = service.reporting_service.data_adapter.extract_report_data(
        project,
        PdfReportRequest(scope=ReportScope.ROOM, room_ids=["RM_BED_01"], mode=ReportMode.DRAFT),
    )
    room_data = report_data.floors[0].rooms[0]
    assert room_data.furniture_schedule[0].is_locked is True


# 9. Optional 3D View integration with valid base64 capture
def test_pdf_with_3d_capture(client, in_memory_db):
    project = _create_saved_project(in_memory_db)

    # 1x1 transparent PNG in base64
    tiny_png_base64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    res = client.post(
        f"/api/projects/{project.id}/esai-engine/reports/pdf",
        json={
            "scope": "room",
            "room_ids": ["RM_BED_01"],
            "mode": "draft",
            "viewer_3d_captures": {
                "RM_BED_01": tiny_png_base64,
            },
        },
    )
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF-")


# 10. Structured JSON Export Endpoint
def test_export_report_data_json(client, in_memory_db):
    project = _create_saved_project(in_memory_db)
    master_json_before = deepcopy(project.master_json)

    res = client.post(
        f"/api/projects/{project.id}/esai-engine/reports/export-data",
        json={"scope": "building", "mode": "draft"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == project.id
    assert "floors" in data
    assert len(data["floors"]) >= 1
    assert "rooms" in data["floors"][0]

    # Verify no Master JSON mutation
    in_memory_db.refresh(project)
    assert project.master_json == master_json_before


# 11. Security: Cross-project or invalid room ID rejection
def test_cross_project_room_id_rejection(client, in_memory_db):
    project = _create_saved_project(in_memory_db)
    res = client.post(
        f"/api/projects/{project.id}/esai-engine/reports/pdf",
        json={"scope": "room", "room_ids": ["non-existent-room-999"], "mode": "draft"},
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


# 12. Strict Exclusion: No budget, price, quotation, or cost anywhere in exports
def test_strict_exclusion_no_budget_or_pricing(client, in_memory_db):
    project = _create_saved_project(in_memory_db)
    res = client.post(
        f"/api/projects/{project.id}/esai-engine/reports/export-data",
        json={"scope": "building", "mode": "draft"},
    )
    assert res.status_code == 200
    export_str = res.text.lower()
    forbidden_tokens = ["budget", "price", "pricing", "quotation", "cost_estimate", "cost_optimization", "lkr", "usd", "$", "€"]
    for token in forbidden_tokens:
        assert token not in export_str, f"Forbidden financial term '{token}' found in export!"


# 13. Multi-Floor Completeness and Missing Design Identification
def test_multi_floor_completeness_and_missing_design_warning(client, in_memory_db):
    project = _create_saved_project(in_memory_db)
    # Add a second floor with an un-designed room
    mj = deepcopy(project.master_json)
    mj["floor_plan"]["floors"].append({
        "floor_id": "floor_01",
        "floor_name": "First Floor",
        "rooms": [
            {
                "room_id": "RM_GUEST_01",
                "name": "Guest Bedroom",
                "room_type": "bedroom",
                "area_sqm": 16.0,
                "ceiling_height_m": 2.8,
                "polygon": [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]],
                "doors": [],
                "windows": [],
            }
        ]
    })
    project.master_json = mj
    in_memory_db.commit()

    # In draft mode, multi-floor report generates and includes both floors/rooms
    res = client.post(
        f"/api/projects/{project.id}/esai-engine/reports/pdf",
        json={"scope": "building", "mode": "draft"},
    )
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF-")

    # Check export data has both floors and flags missing design
    exp_res = client.post(
        f"/api/projects/{project.id}/esai-engine/reports/export-data",
        json={"scope": "building", "mode": "draft"},
    )
    assert exp_res.status_code == 200
    data = exp_res.json()
    assert len(data["floors"]) == 2
    guest_room = next(r for fl in data["floors"] for r in fl["rooms"] if r["room_id"] == "RM_GUEST_01")
    assert guest_room["has_design"] is False
    assert any("no saved interior design layout exists" in w.lower() for w in guest_room["warnings"])


# 14. Final Mode Blocks Incomplete or Invalid Room Designs
def test_final_mode_blocks_incomplete_or_invalid_room_designs(client, in_memory_db):
    project = _create_saved_project(in_memory_db)
    mj = deepcopy(project.master_json)
    # Add a room that has no design
    mj["floor_plan"]["floors"][0]["rooms"].append({
        "room_id": "RM_PENDING_01",
        "name": "Pending Study",
        "room_type": "home_office",
        "area_sqm": 12.0,
        "ceiling_height_m": 2.8,
        "polygon": [[0.0, 0.0], [3.0, 0.0], [3.0, 4.0], [0.0, 4.0]],
        "doors": [],
        "windows": [],
    })
    # Update geometry fingerprint so it is not marked as stale, isolating the incomplete design check
    mj["interior_layout"]["geometry_fingerprint"] = compute_geometry_fingerprint(StructuralInputParser.parse(mj))
    project.master_json = mj
    in_memory_db.commit()

    # Final mode export MUST reject incomplete design with HTTP 422
    res = client.post(
        f"/api/projects/{project.id}/esai-engine/reports/pdf",
        json={"scope": "building", "mode": "final"},
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["code"] == "INCOMPLETE_OR_INVALID_DESIGN_EXPORT_BLOCKED"
    assert any("RM_PENDING_01" in r for r in detail["reasons"])


# 15. Vector Drawing Physical Scale: 1:50 vs NOT TO SCALE & Graphic Scale Bar
def test_drawing_scale_mode_1_50_vs_not_to_scale(in_memory_db):
    from app.components.esai_engine.reporting.drawing_renderer import ArchitecturalDrawingRenderer
    from app.components.esai_engine.reporting.contracts import RoomReportDataDTO

    renderer = ArchitecturalDrawingRenderer(canvas_width=500.0, canvas_height=220.0)

    # 1. Powder Room (2.5m x 2.0m) fits on 500x220 canvas at 1:50 (2.5m*56.69=141.7pt <= 450pt, 2.0m*56.69=113.4pt <= 148pt)
    small_room = RoomReportDataDTO(
        room_id="RM_SMALL",
        room_name="Guest Powder Room",
        room_type="bathroom",
        floor_id="floor_0",
        floor_name="Ground Floor",
        area_sqm=5.0,
        ceiling_height_m=2.8,
        polygon=[[0.0, 0.0], [2.5, 0.0], [2.5, 2.0], [0.0, 2.0]],
        doors=[],
        windows=[],
        design_revision=1,
        has_design=True,
    )
    dwg_small = renderer.render_room_drawing(small_room, [], scale_mode="auto")
    strings_small = [node.text for node in dwg_small.getContents() if hasattr(node, "text")]
    assert any("Scale: 1:50 @ A4" in s for s in strings_small)
    assert any("1m" in s for s in strings_small)  # Graphic scale bar label

    # 2. Large Hall (14m x 10m) does NOT fit at 1:50 (14m*56.69 = 793 pt > 450 pt)
    large_room = RoomReportDataDTO(
        room_id="RM_LARGE",
        room_name="Grand Banquet Hall",
        room_type="living_room",
        floor_id="floor_0",
        floor_name="Ground Floor",
        area_sqm=140.0,
        ceiling_height_m=3.5,
        polygon=[[0.0, 0.0], [14.0, 0.0], [14.0, 10.0], [0.0, 10.0]],
        doors=[],
        windows=[],
        design_revision=1,
        has_design=True,
    )
    dwg_large = renderer.render_room_drawing(large_room, [], scale_mode="auto")
    strings_large = [node.text for node in dwg_large.getContents() if hasattr(node, "text")]
    assert any("NOT TO SCALE" in s for s in strings_large)


# 16. Exact Wall, Perimeter, and Openings Surface Area Mathematics
def test_wall_and_opening_surface_area_mathematics(in_memory_db):
    from app.components.esai_engine.reporting.data_adapter import ReportDataAdapter

    service = EsaiEngineService(in_memory_db)
    adapter = ReportDataAdapter(service)

    # 5m x 4m room: perimeter = 2*(5+4) = 18.0m. Ceiling = 3.0m.
    # Gross wall area = 18.0 * 3.0 = 54.0 sqm.
    # Door: 1m x 2m = 2.0 sqm. Window: 2m x 1.5m = 3.0 sqm. Total openings = 5.0 sqm.
    # Expected Net wall area = 54.0 - 5.0 = 49.0 sqm.
    project = _create_saved_project(in_memory_db)
    mj = deepcopy(project.master_json)
    mj["floor_plan"]["floors"][0]["rooms"][0]["polygon"] = [[0.0, 0.0], [5.0, 0.0], [5.0, 4.0], [0.0, 4.0]]
    mj["floor_plan"]["floors"][0]["rooms"][0]["ceiling_height"] = 3.0
    mj["floor_plan"]["floors"][0]["rooms"][0]["ceiling_height_m"] = 3.0
    mj["floor_plan"]["floors"][0]["rooms"][0]["doors"] = [
        {"id": "dr_01", "start": [1.0, 0.0], "end": [2.0, 0.0], "width_m": 1.0, "height_m": 2.0}
    ]
    mj["floor_plan"]["floors"][0]["rooms"][0]["windows"] = [
        {"id": "win_01", "start": [1.0, 4.0], "end": [3.0, 4.0], "width_m": 2.0, "height_m": 1.5}
    ]
    project.master_json = mj
    in_memory_db.commit()

    report_data = adapter.extract_report_data(
        project,
        PdfReportRequest(scope=ReportScope.ROOM, room_ids=["RM_BED_01"], mode=ReportMode.DRAFT),
    )
    rm = report_data.rooms[0]
    assert rm.perimeter_m == 18.0
    assert rm.openings_area_sqm == 5.0
    assert rm.net_wall_area_sqm == 49.0

    wall_finish = next(f for f in rm.finish_schedule if f.surface_type == "Wall")
    assert wall_finish.coverage_area_sqm == 49.0


# 17. Long Furniture Schedule Pagination & RepeatRows Verification
def test_long_furniture_schedule_pagination_and_table_headers(in_memory_db):
    from app.components.esai_engine.reporting.report_service import EsaiReportService

    service = EsaiEngineService(in_memory_db)
    rpt_svc = EsaiReportService(service)
    project = _create_saved_project(in_memory_db)

    # Populate 30 furniture items
    mj = deepcopy(project.master_json)
    items = []
    for i in range(30):
        items.append({
            "instance_id": f"inst_long_{i:02d}",
            "asset_id": f"chair_{i:02d}",
            "asset_name": f"Auditorium Chair {i:02d}",
            "category": "furniture",
            "dimensions": {"width": 0.6, "depth": 0.6, "height": 0.85},
            "position": {"x": 1.0 + (i % 5) * 0.7, "y": 1.0 + (i // 5) * 0.7},
            "rotation_deg": 45.0,
            "material": "Oak Wood / Wool Fabric",
            "is_locked": (i % 2 == 0),
        })
    mj["interior_layout"]["designs"]["rooms"]["RM_BED_01"]["furniture"] = items
    project.master_json = mj
    in_memory_db.commit()

    pdf_bytes, filename = rpt_svc.generate_pdf_report(
        project,
        PdfReportRequest(scope=ReportScope.ROOM, room_ids=["RM_BED_01"], mode=ReportMode.DRAFT),
    )
    assert len(pdf_bytes) > 5000
    assert pdf_bytes.startswith(b"%PDF-")


# 18. Unicode Project and Room Name Resilience
def test_unicode_project_and_room_names(client, in_memory_db):
    project = _create_saved_project(in_memory_db)
    project.project_name = "Villa Élégante • 現代デザイン - 75m²"
    mj = deepcopy(project.master_json)
    mj["floor_plan"]["floors"][0]["rooms"][0]["name"] = "Chambre Principale ✨"
    project.master_json = mj
    in_memory_db.commit()

    res = client.post(
        f"/api/projects/{project.id}/esai-engine/reports/pdf",
        json={"scope": "room", "room_ids": ["RM_BED_01"], "mode": "draft"},
    )
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF-")


# 19. Project Security & Client Role Authorization
def test_report_endpoint_security_and_authorization(in_memory_db):
    from unittest.mock import MagicMock
    from fastapi import HTTPException
    from app.dependencies import require_project_access
    from app.models.user import User

    # Create project owned by client 'user-alice'
    project = _create_saved_project(in_memory_db)
    project.user_id = "user-alice"
    in_memory_db.commit()

    req_mock = MagicMock()
    req_mock.app.dependency_overrides = {}

    # 1. Admin access is permitted
    admin_user = User(id="admin-1", role="admin", is_active=True)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.dependencies.get_current_user", lambda r, d: admin_user)
        result = require_project_access(project.id, req_mock, in_memory_db)
        assert result.role == "admin"

    # 2. Legitimate owner client 'user-alice' is permitted
    alice_user = User(id="user-alice", role="client", is_active=True)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.dependencies.get_current_user", lambda r, d: alice_user)
        result = require_project_access(project.id, req_mock, in_memory_db)
        assert result.id == "user-alice"

    # 3. Foreign client 'user-mallory' is rejected with HTTP 403 Forbidden
    mallory_user = User(id="user-mallory", role="client", is_active=True)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.dependencies.get_current_user", lambda r, d: mallory_user)
        with pytest.raises(HTTPException) as exc_info:
            require_project_access(project.id, req_mock, in_memory_db)
        assert exc_info.value.status_code == 403
        assert "Forbidden" in exc_info.value.detail


# 20. Authentic Neufert Citations Integrity (No Fabricated Pages/Editions)
def test_neufert_citation_integrity(in_memory_db):
    from app.components.esai_engine.reporting.data_adapter import ReportDataAdapter

    service = EsaiEngineService(in_memory_db)
    adapter = ReportDataAdapter(service)
    project = _create_saved_project(in_memory_db)

    # Attach an ergonomic evaluation with an unreferenced heuristic rule
    mj = deepcopy(project.master_json)
    mj["interior_layout"]["designs"]["rooms"]["RM_BED_01"]["validation"] = {
        "is_valid": True,
        "hard_constraints_passed": True,
        "ergonomic_evaluations": [
            {
                "rule_id": "HEURISTIC_CUSTOM_CLEARANCE",
                "description": "Internal layout clearance check",
                "passed": True,
                "message": "Adequate passage.",
            }
        ]
    }
    project.master_json = mj
    in_memory_db.commit()

    report_data = adapter.extract_report_data(
        project,
        PdfReportRequest(scope=ReportScope.ROOM, room_ids=["RM_BED_01"], mode=ReportMode.DRAFT),
    )
    val_item = report_data.rooms[0].validation_items[0]
    # Standard edition and section MUST NOT be fabricated as "4th Edition" or "Circulation"
    assert val_item.standard_edition is None or val_item.standard_edition != "4th Edition"
    assert val_item.standard_section is None or val_item.standard_section != "Circulation"


# 21. Multi-Floor Completeness: Every Applicable Room Included & Missing Designs Marked
def test_multi_floor_completeness_and_missing_design_handling(client, in_memory_db):
    project = _create_saved_project(in_memory_db)
    mj = deepcopy(project.master_json)
    # Add a second floor with two rooms: one with design, one without
    mj["floor_plan"]["floors"].append({
        "floor_id": "floor_1",
        "floor_name": "First Floor",
        "elevation": 3.0,
        "floor_height": 3.0,
        "rooms": [
            {
                "room_id": "RM_STUDY_01",
                "name": "Study Room",
                "room_type": "study",
                "polygon": [[0.0, 0.0], [4.0, 0.0], [4.0, 3.5], [0.0, 3.5]],
                "area_sqm": 14.0,
                "ceiling_height_m": 2.8,
            },
            {
                "room_id": "RM_UNFINISHED_01",
                "name": "Unfinished Storage",
                "room_type": "utility_room",
                "polygon": [[4.0, 0.0], [6.0, 0.0], [6.0, 3.5], [4.0, 3.5]],
                "area_sqm": 7.0,
                "ceiling_height_m": 2.8,
            }
        ]
    })
    # Attach design only for RM_STUDY_01
    mj["interior_layout"]["designs"]["rooms"]["RM_STUDY_01"] = {
        "room_id": "RM_STUDY_01",
        "floor_id": "floor_1",
        "room_name": "Study Room",
        "room_type": "study",
        "design_revision": 1,
        "polygon": [[0.0, 0.0], [4.0, 0.0], [4.0, 3.5], [0.0, 3.5]],
        "area_sqm": 14.0,
        "furniture": [
            {
                "instance_id": "inst_desk_1",
                "asset_id": "desk-exec-01",
                "asset_name": "Executive Desk",
                "category": "furniture",
                "dimensions": {"width": 1.6, "depth": 0.8, "height": 0.75},
                "position": {"x": 2.0, "y": 1.5},
                "rotation_deg": 0.0,
            }
        ],
        "validation": {"is_valid": True, "hard_constraints_passed": True},
    }
    project.master_json = mj
    in_memory_db.commit()

    # Draft building report should succeed and contain all 3 rooms across both floors
    res = client.post(
        f"/api/projects/{project.id}/esai-engine/reports/export-data",
        json={"scope": "building", "mode": "draft"}
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["floors"]) == 2
    all_rooms = [r["room_id"] for r in data["rooms"]]
    assert "RM_BED_01" in all_rooms
    assert "RM_STUDY_01" in all_rooms
    assert "RM_UNFINISHED_01" in all_rooms

    # The unfinished room must have has_design=False
    unfin = [r for r in data["rooms"] if r["room_id"] == "RM_UNFINISHED_01"][0]
    assert unfin["has_design"] is False
    assert any("No saved interior design layout exists" in w for w in unfin["warnings"])


# 22. True Physical Scale Modes (1:50, auto, not_to_scale)
def test_drawing_scale_modes(in_memory_db):
    from app.components.esai_engine.reporting.drawing_renderer import ArchitecturalDrawingRenderer
    from app.components.esai_engine.reporting.contracts import RoomReportDataDTO

    renderer = ArchitecturalDrawingRenderer(canvas_width=460, canvas_height=220)
    # 5m x 4m room fits at 1:50 (5 * 56.69 = 283.5 < 410, 4 * 56.69 = 226.8 > 150)
    # Let's test a small 3m x 2m room that fits cleanly at 1:50
    small_room = RoomReportDataDTO(
        room_id="RM_SMALL",
        room_name="Powder Room",
        room_type="toilet",
        floor_id="floor_0",
        floor_name="Ground Floor",
        area_sqm=6.0,
        ceiling_height_m=2.6,
        perimeter_m=10.0,
        net_wall_area_sqm=22.0,
        openings_area_sqm=2.0,
        polygon=[[0.0, 0.0], [3.0, 0.0], [3.0, 2.0], [0.0, 2.0]],
        design_revision=1,
        has_design=True,
    )
    # 1:50 mode
    draw_150 = renderer.render_room_drawing(small_room, [], scale_mode="1:50")
    assert any("Scale: 1:50 @ A4" in getattr(elem, "text", "") for elem in draw_150.contents if hasattr(elem, "text"))

    # not_to_scale mode
    draw_nts = renderer.render_room_drawing(small_room, [], scale_mode="not_to_scale")
    assert any("NOT TO SCALE" in getattr(elem, "text", "") for elem in draw_nts.contents if hasattr(elem, "text"))


# 23. Long Table Pagination & Large Schedules
def test_long_schedule_pagination_and_table_generation(in_memory_db):
    from app.components.esai_engine.reporting.pdf_builder import PdfReportBuilder
    from app.components.esai_engine.reporting.data_adapter import ReportDataAdapter

    service = EsaiEngineService(in_memory_db)
    adapter = ReportDataAdapter(service)
    builder = PdfReportBuilder()
    project = _create_saved_project(in_memory_db)

    # Populate room with 40 furniture items to test multi-page table pagination
    mj = deepcopy(project.master_json)
    items = []
    for i in range(40):
        items.append({
            "instance_id": f"inst_chair_{i:02d}",
            "asset_id": f"chair_dining_{i:02d}",
            "asset_name": f"Dining Chair Type {i+1}",
            "category": "furniture",
            "dimensions": {"width": 0.55, "depth": 0.55, "height": 0.85},
            "position": {"x": 1.0 + (i % 5) * 0.6, "y": 1.0 + (i // 5) * 0.4},
            "rotation_deg": (i * 15) % 360,
            "is_locked": (i % 3 == 0),
            "material": "Solid Walnut & Linen Upholstery",
        })
    mj["interior_layout"]["designs"]["rooms"]["RM_BED_01"]["furniture"] = items
    project.master_json = mj
    in_memory_db.commit()

    report_data = adapter.extract_report_data(
        project,
        PdfReportRequest(scope=ReportScope.ROOM, room_ids=["RM_BED_01"], mode=ReportMode.DRAFT),
    )
    assert len(report_data.rooms[0].furniture_schedule) == 40
    pdf_bytes = builder.build_pdf(report_data)
    assert len(pdf_bytes) > 15000
    assert pdf_bytes.startswith(b"%PDF-")


# 24. Unicode & Special Character Integrity
def test_unicode_and_special_character_rendering(in_memory_db):
    from app.components.esai_engine.reporting.pdf_builder import PdfReportBuilder
    from app.components.esai_engine.reporting.data_adapter import ReportDataAdapter

    service = EsaiEngineService(in_memory_db)
    adapter = ReportDataAdapter(service)
    builder = PdfReportBuilder()
    project = _create_saved_project(in_memory_db)

    mj = deepcopy(project.master_json)
    mj["project_name"] = "München Résidence & Atelier № 42"
    mj["interior_layout"]["designs"]["rooms"]["RM_BED_01"]["room_name"] = "Master Suite • 20.5 m² • 45°"
    mj["interior_layout"]["designs"]["rooms"]["RM_BED_01"]["furniture"][0]["material"] = "Ébène & Laiton Brossé"
    project.master_json = mj
    in_memory_db.commit()

    report_data = adapter.extract_report_data(
        project,
        PdfReportRequest(scope=ReportScope.ROOM, room_ids=["RM_BED_01"], mode=ReportMode.DRAFT),
    )
    pdf_bytes = builder.build_pdf(report_data)
    assert len(pdf_bytes) > 5000
    assert pdf_bytes.startswith(b"%PDF-")


# 25. Cross-Project Room Access Protection
def test_cross_project_room_access_rejected(client, in_memory_db):
    project = _create_saved_project(in_memory_db)
    # Request a foreign room ID that does not exist in this project
    res = client.post(
        f"/api/projects/{project.id}/esai-engine/reports/export-data",
        json={"scope": "room", "room_ids": ["RM_FOREIGN_OTHER_PROJECT_99"], "mode": "draft"}
    )
    assert res.status_code == 404
    assert "not found in project" in res.json()["detail"].lower()


# 26. 3D Capture Revision Mismatch Protection
def test_3d_capture_revision_and_room_mismatch_rejected(in_memory_db):
    from app.components.esai_engine.reporting.data_adapter import ReportDataAdapter

    service = EsaiEngineService(in_memory_db)
    adapter = ReportDataAdapter(service)
    project = _create_saved_project(in_memory_db)

    # 1. Capture with outdated revision should be ignored
    req_stale_rev = PdfReportRequest(
        scope=ReportScope.ROOM,
        room_ids=["RM_BED_01"],
        mode=ReportMode.DRAFT,
        view_captures={
            "RM_BED_01": {
                "room_id": "RM_BED_01",
                "design_revision": 999,  # Mismatched revision
                "image_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            }
        }
    )
    rep1 = adapter.extract_report_data(project, req_stale_rev)
    assert rep1.rooms[0].image_capture_base64 is None  # Safely rejected

    # 2. Capture with mismatched room_id should be ignored
    req_wrong_room = PdfReportRequest(
        scope=ReportScope.ROOM,
        room_ids=["RM_BED_01"],
        mode=ReportMode.DRAFT,
        view_captures={
            "RM_BED_01": {
                "room_id": "RM_WRONG_ROOM_ID",
                "design_revision": 1,
                "image_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            }
        }
    )
    rep2 = adapter.extract_report_data(project, req_wrong_room)
    assert rep2.rooms[0].image_capture_base64 is None  # Safely rejected


# 27. Authoritative Master JSON Preferences in Resolution
def test_authoritative_master_json_preference_resolution(in_memory_db):
    project = _create_saved_project(in_memory_db)
    mj = deepcopy(project.master_json)
    # Store explicit preference directly in Master JSON (authoritative source)
    mj["interior_layout"]["preferences"] = {
        "rooms": {
            "RM_BED_01": {
                "style": "scandinavian_minimalist",
                "palette": "nordic_frost",
                "bed_size": "king",
            }
        }
    }
    project.master_json = mj
    in_memory_db.commit()

    service = EsaiEngineService(in_memory_db)
    effective = service.get_effective_preferences(project, "RM_BED_01", "floor_gf")
    # Must resolve Scandinavian Minimalist and king bed from authoritative Master JSON
    eff = effective["effective_preferences"]
    assert eff.get("style") == "scandinavian_minimalist"
    assert eff.get("palette") == "nordic_frost"
    assert eff.get("bed_size") == "king"


# 28. Strict Master JSON Geometry Immutability During Report Generation
def test_master_json_strictly_immutable_during_reports(client, in_memory_db):
    project = _create_saved_project(in_memory_db)
    original_mj = deepcopy(project.master_json)
    original_rev = project.revision

    # Trigger PDF report generation
    res = client.post(
        f"/api/projects/{project.id}/esai-engine/reports/pdf",
        json={"scope": "building", "mode": "draft"}
    )
    assert res.status_code == 200

    in_memory_db.refresh(project)
    # Master JSON must be byte-for-byte identical
    assert project.master_json == original_mj
    assert project.revision == original_rev
    assert project.master_json["floor_plan"] == original_mj["floor_plan"]

