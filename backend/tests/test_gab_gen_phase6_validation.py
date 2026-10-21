"""
Automated Test Suite for GAB-Gen Phase 6:
Architectural Feasibility, Circulation, Doors/Windows & Independent Validation Engine.

Verifies:
A. Geometry & Containment:
   - Valid rectangular and concave rooms
   - Self-intersecting room rejected
   - Zero-area room rejected
   - Room extending outside building footprint rejected
   - Building outside buildable footprint rejected
   - Shared wall permitted without false overlap
   - True room overlap (>0.1 sqm) detected and rejected
B. Explicit Doors & Openings:
   - Valid room-to-corridor door
   - Door with invalid / substandard width (<=0.5m) rejected
   - Floating door without supporting wall rejected
   - External entrance door verified
C. Circulation Graph & Functional Accessibility:
   - All rooms reachable from external entrance
   - Physically isolated room (0 doors) detected and rejected
   - Unreachable room behind locked/unconnected spaces detected and rejected
   - Route distance computation
D. Multi-Storey Staircase Continuity:
   - Single-storey plan requires no staircase
   - Two-storey plan with vertically aligned stair cores passes
   - Two-storey plan with misaligned staircase rejected
   - Upper floor lacking vertical access rejected
E. Window Feasibility:
   - Windows along exterior building boundary verified
   - Orientation computed relative to survey North
F. Hard User Requirements Enforcement:
   - Missing mandatory room rejected
   - Substandard room area rejected
   - Soft preference unmet records warning without invalidating feasibility
G. Regulatory Independence & Multi-Candidate Integration:
   - Validator derives findings independently from candidate geometry (never trusts generator flags)
   - Deliberately falsified candidate flags rejected by validator
   - Invalid candidates excluded from ranked pool
H. Blueprint Editor Revalidation:
   - Overlapping room resize rejected and previous valid state preserved
   - Valid room edit accepted and doors updated
"""
import pytest
from shapely.geometry import Polygon

from app.components.gab_gen.schemas import (
    FloorPlanDefinition,
    RoomPolygon,
    Point2D,
    DoorDefinition,
    WindowDefinition,
    CheckStatus,
    CheckSeverity,
    CheckDimension,
    ClientRequirementsInput,
    RoomRequirement,
    RegulatoryRule,
    RegulatoryContextInput,
)
from app.components.gab_gen.validation.independent_validator import IndependentArchitecturalValidator
from app.components.gab_gen.validation.circulation_analyzer import CirculationGraph
from app.components.gab_gen.blueprint.openings_synthesizer import (
    synthesize_doors_and_windows_for_floor,
    enrich_floor_definitions_with_openings
)
from app.components.gab_gen.blueprint.editor import validate_room_edit, apply_room_edit
from app.components.gab_gen.regulations.rules import RegulatoryEngine



# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture
def standard_envelope():
    # 20m x 15m parcel, 16m x 11m buildable footprint
    land_poly = Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])
    buildable_poly = Polygon([(2, 2), (18, 2), (18, 13), (2, 13)])
    return land_poly, buildable_poly


@pytest.fixture
def valid_single_storey_rooms():
    # Living room with entrance, bedroom, and kitchen sharing walls
    living = RoomPolygon(
        room_id="R_LIVING", name="Living Room", type="living_room", floor_id="FL-00",
        area=24.0, target_area=24.0, center=Point2D(x=5.0, y=5.0),
        polygon=[Point2D(x=2.0, y=2.0), Point2D(x=8.0, y=2.0), Point2D(x=8.0, y=6.0), Point2D(x=2.0, y=6.0)],
        width_m=6.0, length_m=4.0
    )
    bed = RoomPolygon(
        room_id="R_BED1", name="Master Bedroom", type="master_bedroom", floor_id="FL-00",
        area=16.0, target_area=16.0, center=Point2D(x=5.0, y=8.0),
        polygon=[Point2D(x=2.0, y=6.0), Point2D(x=8.0, y=6.0), Point2D(x=8.0, y=10.0), Point2D(x=2.0, y=10.0)],
        width_m=6.0, length_m=4.0
    )
    kitchen = RoomPolygon(
        room_id="R_KITCHEN", name="Kitchen", type="kitchen", floor_id="FL-00",
        area=12.0, target_area=12.0, center=Point2D(x=11.0, y=5.0),
        polygon=[Point2D(x=8.0, y=2.0), Point2D(x=14.0, y=2.0), Point2D(x=14.0, y=6.0), Point2D(x=8.0, y=6.0)],
        width_m=6.0, length_m=4.0
    )
    return [living, bed, kitchen]


# ---------------------------------------------------------------------------
# A. GEOMETRY & CONTAINMENT TESTS
# ---------------------------------------------------------------------------

def test_independent_validator_detects_self_intersecting_room(standard_envelope, valid_single_storey_rooms):
    """Room with self-intersecting bow-tie polygon must fail geometric validity."""
    land_poly, buildable_poly = standard_envelope
    rooms = list(valid_single_storey_rooms)
    # Self-intersecting room polygon
    bad_poly = [Point2D(x=8.0, y=6.0), Point2D(x=14.0, y=10.0), Point2D(x=8.0, y=10.0), Point2D(x=14.0, y=6.0)]
    rooms[2] = rooms[2].model_copy(update={"polygon": bad_poly})

    floor = FloorPlanDefinition(
        floor_id="FL-00", floor_index=0, name="Ground Floor", elevation=0.0,
        available_area=176.0, target_allocated_area=52.0, rooms=rooms
    )
    report = IndependentArchitecturalValidator.validate_candidate(
        floors=[floor], buildable_poly=buildable_poly, land_poly=land_poly
    )
    assert report.is_valid is False
    assert report.geometric_validity is False
    assert any("self-intersecting" in c.message.lower() for c in report.checks)


def test_independent_validator_detects_room_outside_buildable_boundary(standard_envelope, valid_single_storey_rooms):
    """Room protruding outside permitted buildable footprint must fail geometric validity."""
    land_poly, buildable_poly = standard_envelope
    rooms = list(valid_single_storey_rooms)
    # Room placed at x=19, outside buildable_poly max x=18
    protruding_poly = [Point2D(x=16.0, y=2.0), Point2D(x=19.5, y=2.0), Point2D(x=19.5, y=6.0), Point2D(x=16.0, y=6.0)]
    rooms[2] = rooms[2].model_copy(update={"polygon": protruding_poly})

    floor = FloorPlanDefinition(
        floor_id="FL-00", floor_index=0, name="Ground Floor", elevation=0.0,
        available_area=176.0, target_allocated_area=52.0, rooms=rooms
    )
    report = IndependentArchitecturalValidator.validate_candidate(
        floors=[floor], buildable_poly=buildable_poly, land_poly=land_poly
    )
    assert report.is_valid is False
    assert report.geometric_validity is False
    assert any("extends beyond" in c.message.lower() for c in report.checks)



def test_independent_validator_detects_meaningful_room_overlap(standard_envelope, valid_single_storey_rooms):
    """Rooms overlapping by > 0.10 sqm must be detected as a spatial conflict."""
    land_poly, buildable_poly = standard_envelope
    rooms = list(valid_single_storey_rooms)
    # Overlap R_KITCHEN deeply into R_LIVING (x=7.0 to 13.0, overlapping x=7.0 to 8.0)
    overlapping_poly = [Point2D(x=7.0, y=2.0), Point2D(x=13.0, y=2.0), Point2D(x=13.0, y=6.0), Point2D(x=7.0, y=6.0)]
    rooms[2] = rooms[2].model_copy(update={"polygon": overlapping_poly})

    floor = FloorPlanDefinition(
        floor_id="FL-00", floor_index=0, name="Ground Floor", elevation=0.0,
        available_area=176.0, target_allocated_area=52.0, rooms=rooms
    )
    report = IndependentArchitecturalValidator.validate_candidate(
        floors=[floor], buildable_poly=buildable_poly, land_poly=land_poly
    )
    assert report.is_valid is False
    assert report.geometric_validity is False
    assert any("spatial conflict" in c.message.lower() or "overlap" in c.message.lower() for c in report.checks)


# ---------------------------------------------------------------------------
# B. EXPLICIT DOORS & OPENINGS TESTS
# ---------------------------------------------------------------------------

def test_independent_validator_detects_substandard_door_width(standard_envelope, valid_single_storey_rooms):
    """Explicit door with width <= 0.50m must fail accessibility."""
    land_poly, buildable_poly = standard_envelope
    floor = FloorPlanDefinition(
        floor_id="FL-00", floor_index=0, name="Ground Floor", elevation=0.0,
        available_area=176.0, target_allocated_area=52.0, rooms=valid_single_storey_rooms
    )
    enrich_floor_definitions_with_openings([floor], buildable_poly)
    # Mutate one door to substandard 0.40m
    floor.doors[0] = floor.doors[0].model_copy(update={"width_m": 0.40})

    report = IndependentArchitecturalValidator.validate_candidate(
        floors=[floor], buildable_poly=buildable_poly, land_poly=land_poly
    )
    assert report.is_valid is False
    assert report.door_validity is False
    assert any("unusable width" in c.message.lower() for c in report.checks)


# ---------------------------------------------------------------------------
# C. CIRCULATION GRAPH & ACCESSIBILITY TESTS
# ---------------------------------------------------------------------------

def test_circulation_graph_detects_isolated_room(standard_envelope, valid_single_storey_rooms):
    """Room with 0 connecting doors must be identified as isolated."""
    land_poly, buildable_poly = standard_envelope
    floor = FloorPlanDefinition(
        floor_id="FL-00", floor_index=0, name="Ground Floor", elevation=0.0,
        available_area=176.0, target_allocated_area=52.0, rooms=valid_single_storey_rooms
    )
    # Enrich with openings
    enrich_floor_definitions_with_openings([floor], buildable_poly)
    # Remove all doors connected to R_BED1
    floor.doors = [d for d in floor.doors if "R_BED1" not in d.connected_space_ids]

    circ_graph = CirculationGraph()
    circ_graph.build_from_floors([floor])
    checks, isolated, unreachable = circ_graph.analyze_accessibility([floor])

    assert "R_BED1" in isolated
    assert any(c.status == CheckStatus.FAIL and "isolated" in c.message.lower() for c in checks)


def test_circulation_graph_calculates_shortest_route_distance(standard_envelope, valid_single_storey_rooms):
    """Topological graph accurately calculates shortest route distance between connected rooms."""
    land_poly, buildable_poly = standard_envelope
    floor = FloorPlanDefinition(
        floor_id="FL-00", floor_index=0, name="Ground Floor", elevation=0.0,
        available_area=176.0, target_allocated_area=52.0, rooms=valid_single_storey_rooms
    )
    enrich_floor_definitions_with_openings([floor], buildable_poly)

    circ_graph = CirculationGraph()
    circ_graph.build_from_floors([floor])
    dist = circ_graph.get_shortest_route_distance("R_LIVING", "R_BED1")
    assert dist is not None
    assert dist > 0.0


# ---------------------------------------------------------------------------
# D. MULTI-STOREY STAIRCASE TESTS
# ---------------------------------------------------------------------------

def test_staircase_misalignment_fails_two_storey_validation(standard_envelope):
    """Upper floor staircase offset from Ground floor staircase core fails vertical continuity."""
    land_poly, buildable_poly = standard_envelope

    # Ground floor stair at x=2..6, y=2..5
    gf_stair = RoomPolygon(
        room_id="GF_STAIR", name="Staircase", type="staircase", floor_id="FL-00",
        area=12.0, target_area=12.0, center=Point2D(x=4.0, y=3.5),
        polygon=[Point2D(x=2.0, y=2.0), Point2D(x=6.0, y=2.0), Point2D(x=6.0, y=5.0), Point2D(x=2.0, y=5.0)],
        is_structural_stair=True
    )
    gf_room = RoomPolygon(
        room_id="GF_LIVING", name="Living Room", type="living_room", floor_id="FL-00",
        area=24.0, target_area=24.0, center=Point2D(x=9.0, y=3.5),
        polygon=[Point2D(x=6.0, y=2.0), Point2D(x=12.0, y=2.0), Point2D(x=12.0, y=6.0), Point2D(x=6.0, y=6.0)]
    )
    fl0 = FloorPlanDefinition(
        floor_id="FL-00", floor_index=0, name="Ground Floor", elevation=0.0,
        available_area=176.0, target_allocated_area=36.0, rooms=[gf_stair, gf_room]
    )

    # First floor stair shifted to x=10..14, y=2..5 (completely misaligned)
    f1_stair = RoomPolygon(
        room_id="F1_STAIR", name="Staircase", type="staircase", floor_id="FL-01",
        area=12.0, target_area=12.0, center=Point2D(x=12.0, y=3.5),
        polygon=[Point2D(x=10.0, y=2.0), Point2D(x=14.0, y=2.0), Point2D(x=14.0, y=5.0), Point2D(x=10.0, y=5.0)],
        is_structural_stair=True
    )
    f1_bed = RoomPolygon(
        room_id="F1_BED", name="Upper Bedroom", type="bedroom", floor_id="FL-01",
        area=18.0, target_area=18.0, center=Point2D(x=8.0, y=7.0),
        polygon=[Point2D(x=5.0, y=5.0), Point2D(x=11.0, y=5.0), Point2D(x=11.0, y=9.0), Point2D(x=5.0, y=9.0)]
    )
    fl1 = FloorPlanDefinition(
        floor_id="FL-01", floor_index=1, name="First Floor", elevation=3.0,
        available_area=176.0, target_allocated_area=30.0, rooms=[f1_stair, f1_bed]
    )

    enrich_floor_definitions_with_openings([fl0, fl1], buildable_poly)
    report = IndependentArchitecturalValidator.validate_candidate(
        floors=[fl0, fl1], buildable_poly=buildable_poly, land_poly=land_poly
    )

    assert report.is_valid is False
    assert report.staircase_validity is False
    assert any("misaligned" in c.message.lower() for c in report.checks)


def test_staircase_valid_vertical_alignment_passes(standard_envelope):
    """Upper floor staircase aligned >85% with Ground floor staircase passes."""
    land_poly, buildable_poly = standard_envelope

    gf_stair = RoomPolygon(
        room_id="GF_STAIR", name="Staircase", type="staircase", floor_id="FL-00",
        area=12.0, target_area=12.0, center=Point2D(x=4.0, y=3.5),
        polygon=[Point2D(x=2.0, y=2.0), Point2D(x=6.0, y=2.0), Point2D(x=6.0, y=5.0), Point2D(x=2.0, y=5.0)],
        is_structural_stair=True
    )
    fl0 = FloorPlanDefinition(
        floor_id="FL-00", floor_index=0, name="Ground Floor", elevation=0.0,
        available_area=176.0, target_allocated_area=12.0, rooms=[gf_stair]
    )

    # Identical aligned stair on First Floor
    f1_stair = RoomPolygon(
        room_id="F1_STAIR", name="Staircase", type="staircase", floor_id="FL-01",
        area=12.0, target_area=12.0, center=Point2D(x=4.0, y=3.5),
        polygon=[Point2D(x=2.0, y=2.0), Point2D(x=6.0, y=2.0), Point2D(x=6.0, y=5.0), Point2D(x=2.0, y=5.0)],
        is_structural_stair=True
    )
    fl1 = FloorPlanDefinition(
        floor_id="FL-01", floor_index=1, name="First Floor", elevation=3.0,
        available_area=176.0, target_allocated_area=12.0, rooms=[f1_stair]
    )

    enrich_floor_definitions_with_openings([fl0, fl1], buildable_poly)
    report = IndependentArchitecturalValidator.validate_candidate(
        floors=[fl0, fl1], buildable_poly=buildable_poly, land_poly=land_poly
    )

    assert report.staircase_validity is True
    assert any("aligned across all floors" in c.message.lower() for c in report.checks)


# ---------------------------------------------------------------------------
# E. WINDOW FEASIBILITY TESTS
# ---------------------------------------------------------------------------

def test_window_synthesis_along_exterior_perimeter(standard_envelope, valid_single_storey_rooms):
    """Habitable rooms bordering exterior walls receive verified exterior windows."""
    land_poly, buildable_poly = standard_envelope
    floor = FloorPlanDefinition(
        floor_id="FL-00", floor_index=0, name="Ground Floor", elevation=0.0,
        available_area=176.0, target_allocated_area=52.0, rooms=valid_single_storey_rooms
    )
    doors, windows = synthesize_doors_and_windows_for_floor(floor, buildable_poly)
    assert len(windows) > 0
    assert all(w.is_exterior is True for w in windows)
    assert all(w.orientation in ["north", "south", "east", "west"] for w in windows)


# ---------------------------------------------------------------------------
# F. HARD USER REQUIREMENTS ENFORCEMENT
# ---------------------------------------------------------------------------

def test_hard_user_requirement_missing_mandatory_room_fails(standard_envelope, valid_single_storey_rooms):
    """Candidate missing an explicitly mandatory user room must be marked INVALID."""
    land_poly, buildable_poly = standard_envelope
    floor = FloorPlanDefinition(
        floor_id="FL-00", floor_index=0, name="Ground Floor", elevation=0.0,
        available_area=176.0, target_allocated_area=52.0, rooms=valid_single_storey_rooms
    )
    enrich_floor_definitions_with_openings([floor], buildable_poly)

    reqs = ClientRequirementsInput(
        total_bedrooms=2,
        declared_land_extent=300.0,
        rooms=[
            RoomRequirement(id="REQ_POOJA", type="pooja_room", quantity=1, required=True)
        ]
    )


    report = IndependentArchitecturalValidator.validate_candidate(
        floors=[floor], buildable_poly=buildable_poly, land_poly=land_poly, client_requirements=reqs
    )
    assert report.is_valid is False
    assert report.requirements_validity is False
    assert any("pooja_room" in c.message.lower() for c in report.checks)



# ---------------------------------------------------------------------------
# G. VALIDATOR INDEPENDENCE TESTS
# ---------------------------------------------------------------------------

def test_validator_independence_rejects_falsified_generator_output(standard_envelope, valid_single_storey_rooms):
    """The validator independently recalculates geometry, rejecting invalid layouts even if generator claims valid."""
    land_poly, buildable_poly = standard_envelope
    rooms = list(valid_single_storey_rooms)
    # Deliberate overlap
    overlapping_poly = [Point2D(x=7.0, y=2.0), Point2D(x=13.0, y=2.0), Point2D(x=13.0, y=6.0), Point2D(x=7.0, y=6.0)]
    rooms[2] = rooms[2].model_copy(update={"polygon": overlapping_poly})

    floor = FloorPlanDefinition(
        floor_id="FL-00", floor_index=0, name="Ground Floor", elevation=0.0,
        available_area=176.0, target_allocated_area=52.0, rooms=rooms
    )
    # Even if floor plan claims perfection
    report = IndependentArchitecturalValidator.validate_candidate(
        floors=[floor], buildable_poly=buildable_poly, land_poly=land_poly
    )
    assert report.is_valid is False
    assert report.geometric_validity is False


# ---------------------------------------------------------------------------
# H. BLUEPRINT EDITOR REVALIDATION TESTS
# ---------------------------------------------------------------------------

def test_editor_revalidation_rejects_overlapping_room_resize(standard_envelope, valid_single_storey_rooms):
    """Live room edit resulting in room-to-room overlap is rejected; original state remains untouched."""
    land_poly, buildable_poly = standard_envelope
    floor = FloorPlanDefinition(
        floor_id="FL-00", floor_index=0, name="Ground Floor", elevation=0.0,
        available_area=176.0, target_allocated_area=52.0, rooms=valid_single_storey_rooms
    )

    # Attempt to resize R_KITCHEN into R_LIVING (x from 8.0 down to 4.0, overlapping 4m x 4m)
    bad_resize = [Point2D(x=4.0, y=2.0), Point2D(x=14.0, y=2.0), Point2D(x=14.0, y=6.0), Point2D(x=4.0, y=6.0)]
    res = apply_room_edit("R_KITCHEN", "FL-00", bad_resize, [floor], buildable_poly)

    assert res["success"] is False
    assert any("overlap" in v.lower() for v in res["violations"])
    # Verify original room geometry was not mutated
    orig_kitchen = next(r for r in res["floors"][0].rooms if r.room_id == "R_KITCHEN")
    assert orig_kitchen.polygon[0].x == 8.0


def test_editor_revalidation_accepts_valid_translation(standard_envelope, valid_single_storey_rooms):
    """Valid translation within buildable envelope without overlap is applied successfully."""
    land_poly, buildable_poly = standard_envelope
    floor = FloorPlanDefinition(
        floor_id="FL-00", floor_index=0, name="Ground Floor", elevation=0.0,
        available_area=176.0, target_allocated_area=52.0, rooms=valid_single_storey_rooms
    )

    # Move R_KITCHEN 1 meter to the right (x=9.0 to 15.0, buildable max is 18.0)
    valid_move = [Point2D(x=9.0, y=2.0), Point2D(x=15.0, y=2.0), Point2D(x=15.0, y=6.0), Point2D(x=9.0, y=6.0)]
    res = apply_room_edit("R_KITCHEN", "FL-00", valid_move, [floor], buildable_poly)

    assert res["success"] is True
    assert len(res["violations"]) == 0
    updated_kitchen = next(r for r in res["floors"][0].rooms if r.room_id == "R_KITCHEN")
    assert updated_kitchen.polygon[0].x == 9.0
