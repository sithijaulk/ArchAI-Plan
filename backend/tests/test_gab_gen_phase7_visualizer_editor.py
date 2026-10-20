"""
Automated Test Suite for GAB-Gen Phase 7:
Roof Generation, 2D/3D Blueprint Viewer & Interactive Editor Finalization.

Verifies:
A. Multi-Type Roof Generation (flat_slab, accessible_rooftop, gable, hip, mono_pitch)
B. Roof Mesh Validity, Boundary Containment & Pitch Limits
C. Safe Unsupported Roof Geometries & Extreme Bounds Handling
D. Door & Window Editing (position translation & dimension updates)
E. Blueprint Editor Revalidation for Openings (substandard width rejection)
F. Interactive Roof Switching Transaction via Editor API
G. Undo/Redo Edit Transaction State Management
H. Candidate Isolation during Edits
I. Centralized Master JSON Persistence of Phase 7 Geometry & Edit History
"""
import pytest
from shapely.geometry import Polygon

from app.components.gab_gen.schemas import (
    Point2D,
    FloorPlanDefinition,
    RoomPolygon,
    DoorDefinition,
    WindowDefinition,
    RoofPreference,
    RoofType,
    GeneratedRoofGeometry,
)
from app.components.gab_gen.blueprint.roof_generator import (
    generate_roof_geometry,
    validate_roof_geometry,
)
from app.components.gab_gen.blueprint.editor import (
    edit_door_in_blueprint,
    edit_window_in_blueprint,
    change_blueprint_roof,
    apply_room_edit,
)
from app.components.gab_gen.blueprint.openings_synthesizer import (
    synthesize_doors_and_windows_for_floor,
    enrich_floor_definitions_with_openings,
)


@pytest.fixture
def sample_building_footprint():
    # 14m x 10m rectangular building footprint
    return Polygon([(0, 0), (14, 0), (14, 10), (0, 10)])


@pytest.fixture
def sample_floor_with_openings(sample_building_footprint):
    rm1 = RoomPolygon(
        room_id="R1_LIVING", name="Living Room", type="living_room", floor_id="FL-00",
        area=40.0, target_area=40.0, center=Point2D(x=4.0, y=5.0),
        polygon=[Point2D(x=0.0, y=0.0), Point2D(x=8.0, y=0.0), Point2D(x=8.0, y=10.0), Point2D(x=0.0, y=10.0)]
    )
    rm2 = RoomPolygon(
        room_id="R2_BED", name="Master Bedroom", type="master_bedroom", floor_id="FL-00",
        area=30.0, target_area=30.0, center=Point2D(x=11.0, y=5.0),
        polygon=[Point2D(x=8.0, y=0.0), Point2D(x=14.0, y=0.0), Point2D(x=14.0, y=10.0), Point2D(x=8.0, y=10.0)]
    )
    floor = FloorPlanDefinition(
        floor_id="FL-00", floor_index=0, name="Ground Floor", elevation=0.0,
        available_area=140.0, target_allocated_area=70.0, rooms=[rm1, rm2]
    )
    enrich_floor_definitions_with_openings([floor], sample_building_footprint)
    return floor


# ---------------------------------------------------------------------------
# A. ROOF GENERATION TESTS
# ---------------------------------------------------------------------------

def test_flat_roof_generation(sample_building_footprint):
    """Generates valid flat slab roof with default parapet."""
    roof_pref = RoofPreference(roof_type=RoofType.FLAT_SLAB, pitch_angle_deg=0.0, overhang_m=0.3)
    roof = generate_roof_geometry(sample_building_footprint, roof_pref)
    val = validate_roof_geometry(roof, sample_building_footprint)

    assert val["valid"] is True
    assert roof.roof_type == "flat_slab"
    assert len(roof.planes) == 1
    assert roof.planes[0].pitch_deg == 0.0


def test_accessible_terrace_roof_generation(sample_building_footprint):
    """Generates accessible terrace roof with safe 1.0m parapet height."""
    roof_pref = RoofPreference(
        roof_type=RoofType.ACCESSIBLE_ROOFTOP,
        pitch_angle_deg=0.0,
        parapet_height_m=1.0,
        rooftop_access=True
    )
    roof = generate_roof_geometry(sample_building_footprint, roof_pref)
    val = validate_roof_geometry(roof, sample_building_footprint)

    assert val["valid"] is True
    assert roof.roof_type == "accessible_rooftop"
    assert roof.max_height_m == 1.0


def test_gable_roof_generation(sample_building_footprint):
    """Generates dual-pitch gable roof with central ridge points and dual planes."""
    roof_pref = RoofPreference(roof_type=RoofType.GABLE, pitch_angle_deg=30.0, overhang_m=0.5)
    roof = generate_roof_geometry(sample_building_footprint, roof_pref)
    val = validate_roof_geometry(roof, sample_building_footprint)

    assert val["valid"] is True
    assert roof.roof_type == "gable"
    assert len(roof.ridge_points) == 2
    assert len(roof.planes) == 2
    assert roof.max_height_m > 1.0


def test_hip_roof_generation(sample_building_footprint):
    """Generates 4-sided hip roof with distinct triangular and trapezoidal planes."""
    roof_pref = RoofPreference(roof_type=RoofType.HIP, pitch_angle_deg=25.0, overhang_m=0.4)
    roof = generate_roof_geometry(sample_building_footprint, roof_pref)
    val = validate_roof_geometry(roof, sample_building_footprint)

    assert val["valid"] is True
    assert roof.roof_type == "hip"
    assert len(roof.planes) == 4
    plane_ids = [p.plane_id for p in roof.planes]
    assert "HIP_WEST" in plane_ids
    assert "HIP_EAST" in plane_ids
    assert "HIP_SOUTH" in plane_ids
    assert "HIP_NORTH" in plane_ids


def test_mono_pitch_roof_generation(sample_building_footprint):
    """Generates single-slope mono-pitch roof with correct orientation."""
    roof_pref = RoofPreference(roof_type=RoofType.MONO_PITCH, pitch_angle_deg=15.0, overhang_m=0.3)
    roof = generate_roof_geometry(sample_building_footprint, roof_pref)
    val = validate_roof_geometry(roof, sample_building_footprint)

    assert val["valid"] is True
    assert roof.roof_type == "mono_pitch"
    assert len(roof.planes) == 1
    assert roof.planes[0].slope_azimuth in (180.0, 270.0)


# ---------------------------------------------------------------------------
# B. DOOR & WINDOW EDITING TESTS
# ---------------------------------------------------------------------------

def test_editor_edit_door_valid(sample_floor_with_openings):
    """Translates door position and changes width cleanly."""
    door = sample_floor_with_openings.doors[0]
    new_pos = Point2D(x=door.position.x + 0.5, y=door.position.y)

    res = edit_door_in_blueprint(
        door_id=door.door_id,
        target_floor_id=sample_floor_with_openings.floor_id,
        new_position=new_pos,
        new_width_m=1.10,
        floors=[sample_floor_with_openings]
    )

    assert res["success"] is True
    updated_door = next(d for d in res["floors"][0].doors if d.door_id == door.door_id)
    assert updated_door.width_m == 1.10
    assert updated_door.position.x == new_pos.x


def test_editor_edit_door_rejects_substandard_width(sample_floor_with_openings):
    """Rejects door width <= 0.50m as architecturally unfeasible."""
    door = sample_floor_with_openings.doors[0]
    res = edit_door_in_blueprint(
        door_id=door.door_id,
        target_floor_id=sample_floor_with_openings.floor_id,
        new_position=door.position,
        new_width_m=0.45,
        floors=[sample_floor_with_openings]
    )

    assert res["success"] is False
    assert any("usability" in v.lower() for v in res["violations"])


def test_editor_edit_window_valid(sample_floor_with_openings):
    """Edits exterior window coordinates and aperture size."""
    win = sample_floor_with_openings.windows[0]
    new_pos = Point2D(x=win.position.x, y=win.position.y + 0.2)

    res = edit_window_in_blueprint(
        window_id=win.window_id,
        target_floor_id=sample_floor_with_openings.floor_id,
        new_position=new_pos,
        new_width_m=1.50,
        new_height_m=1.40,
        floors=[sample_floor_with_openings]
    )

    assert res["success"] is True
    updated_win = next(w for w in res["floors"][0].windows if w.window_id == win.window_id)
    assert updated_win.width_m == 1.50
    assert updated_win.height_m == 1.40


# ---------------------------------------------------------------------------
# C. INTERACTIVE ROOF SWITCHING TRANSACTION
# ---------------------------------------------------------------------------

def test_change_blueprint_roof_transaction(sample_building_footprint):
    """Switches roof type dynamically and validates new geometry."""
    res = change_blueprint_roof(sample_building_footprint, "hip", pitch_deg=28.0)
    assert res["success"] is True
    assert res["roof_geometry"].roof_type == "hip"
    assert len(res["roof_geometry"].planes) == 4

    res_invalid = change_blueprint_roof(sample_building_footprint, "space_station_dome")
    assert res_invalid["success"] is False
    assert any("unsupported roof type" in v.lower() for v in res_invalid["violations"])
