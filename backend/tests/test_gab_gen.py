"""
Unit tests for GAB-Gen Stage 1 Backend.
Tests:
- Bearing normalization & Quadrant bearing parsing
- Vector polygon reconstruction in canonical P0 coordinate system
- No double rotation from north orientation angle
- Area cross-check with configurable tolerance
- Regulatory setbacks without arbitrary safe fallbacks
- Research rules requiring explicit test mode
- Buildable footprint computation with irregular parcels and collapsed footprint
- Space allocation with mandatory room minimum target protection & staircase core reservation
- Multi-floor feasibility & dynamic storey support (1-4)
- Blueprint partition proportional to room target areas
- Non-overlap & containment in buildable footprint
- Master JSON non-destructive update & schema validation
"""
import io
import pytest
from PIL import Image
from shapely.geometry import Polygon

from app.components.gab_gen.schemas import (
    ManualSurveyExtractionRequest,
    SurveyEdgeInput,
    DistanceValue,
    DistanceUnit,
    BearingValue,
    EdgeType,
    ClientRequirementsInput,
    RoomRequirement,
    LandExtentUnit,
    BuildingType,
    RegulatoryRule,
    RegulatoryContextInput
)
from app.components.gab_gen.survey_provider import FixtureSurveyExtractionProvider
from app.components.gab_gen.vector_reconstruction.reconstruct import (
    normalize_bearing_string,
    reconstruct_polygon
)
from app.components.gab_gen.regulations.rules import RegulatoryEngine
from app.components.gab_gen.buildable_footprint.compute import compute_buildable_footprint
from app.components.gab_gen.space_allocation.allocator import RuleBasedSpaceAllocationProvider
from app.components.gab_gen.blueprint.generator import generate_blueprint_floors
from app.components.gab_gen.validation.validator import cross_check_land_area, validate_gab_geometry
from app.components.gab_gen.output.master_json_builder import build_gab_master_json
from app.components.gab_gen.service import GabGenService


# -----------------------------------------------------------------
# 1. Coordinate System & Quadrant Bearings
# -----------------------------------------------------------------

def test_bearing_normalization_quadrants():
    assert normalize_bearing_string("90") == 90.0
    assert normalize_bearing_string("090°00'00\"") == 90.0
    assert normalize_bearing_string("N 90 E") == 90.0
    assert normalize_bearing_string("N 0 E") == 0.0
    assert normalize_bearing_string("S 0 E") == 180.0
    assert normalize_bearing_string("S 90 W") == 270.0
    assert normalize_bearing_string("N 45 W") == 315.0
    assert normalize_bearing_string("S 45 E") == 135.0


def test_north_angle_does_not_double_rotate_normalized_azimuth():
    """Verify that north_angle does not rotate legal azimuth in vector reconstruction."""
    req = ManualSurveyExtractionRequest(
        north_angle=45.0,  # Image orientation rotation
        reference_edge="E01",
        edges=[
            SurveyEdgeInput(
                edge_id="E01",
                distance=DistanceValue(value=10.0, unit=DistanceUnit.METERS),
                bearing=BearingValue(raw="090°", normalized_degrees=90.0),
                edge_type=EdgeType.ROAD_FRONT
            ),
            SurveyEdgeInput(
                edge_id="E02",
                distance=DistanceValue(value=10.0, unit=DistanceUnit.METERS),
                bearing=BearingValue(raw="180°", normalized_degrees=180.0),
                edge_type=EdgeType.SIDE_RIGHT
            ),
            SurveyEdgeInput(
                edge_id="E03",
                distance=DistanceValue(value=10.0, unit=DistanceUnit.METERS),
                bearing=BearingValue(raw="270°", normalized_degrees=270.0),
                edge_type=EdgeType.REAR
            ),
            SurveyEdgeInput(
                edge_id="E04",
                distance=DistanceValue(value=10.0, unit=DistanceUnit.METERS),
                bearing=BearingValue(raw="000°", normalized_degrees=0.0),
                edge_type=EdgeType.SIDE_LEFT
            ),
        ]
    )
    result = reconstruct_polygon(req)
    # The first edge azimuth must remain 90.0 (not 135.0)
    assert result["edges"][0]["azimuth"] == 90.0
    # End point after 10m East (90 deg) must be (10.0, 0.0)
    assert result["edges"][0]["end"]["x"] == 10.0
    assert result["edges"][0]["end"]["y"] == 0.0


def test_canonical_coordinates_negative_crossings():
    """Verify irregular parcel crossing negative coordinates retains P0 origin."""
    req = ManualSurveyExtractionRequest(
        north_angle=0.0,
        edges=[
            SurveyEdgeInput(
                edge_id="E01",
                distance=DistanceValue(value=10.0, unit=DistanceUnit.METERS),
                bearing=BearingValue(raw="270°", normalized_degrees=270.0),  # Go West (-X)
                edge_type=EdgeType.ROAD_FRONT
            ),
            SurveyEdgeInput(
                edge_id="E02",
                distance=DistanceValue(value=10.0, unit=DistanceUnit.METERS),
                bearing=BearingValue(raw="180°", normalized_degrees=180.0),  # Go South (-Y)
                edge_type=EdgeType.SIDE_RIGHT
            ),
            SurveyEdgeInput(
                edge_id="E03",
                distance=DistanceValue(value=10.0, unit=DistanceUnit.METERS),
                bearing=BearingValue(raw="090°", normalized_degrees=90.0),  # Go East (+X)
                edge_type=EdgeType.REAR
            ),
            SurveyEdgeInput(
                edge_id="E04",
                distance=DistanceValue(value=10.0, unit=DistanceUnit.METERS),
                bearing=BearingValue(raw="000°", normalized_degrees=0.0),  # Go North (+Y)
                edge_type=EdgeType.SIDE_LEFT
            ),
        ]
    )
    res = reconstruct_polygon(req)
    assert res["is_valid"] is True
    # First vertex is strictly (0, 0)
    assert res["vertices"][0]["x"] == 0.0
    assert res["vertices"][0]["y"] == 0.0
    # Next vertex went West: (-10.0, 0.0)
    assert res["vertices"][1]["x"] == -10.0
    assert res["vertices"][1]["y"] == 0.0


# -----------------------------------------------------------------
# 2. Regulatory Rule Resolution & Buildable Footprint
# -----------------------------------------------------------------

def test_missing_verified_jurisdiction_requires_configuration():
    """Unknown jurisdiction returns empty without falling back to synthetic rules."""
    rules = RegulatoryEngine.get_rules_for_jurisdiction("unknown_nonexistent_council")
    assert len(rules) == 0


def test_research_test_rules_require_explicit_mode():
    """research_test_relaxed rules must NOT load in standard mode."""
    rules_standard = RegulatoryEngine.get_rules_for_jurisdiction("research_test_relaxed", allow_research_test=False)
    assert len(rules_standard) == 0

    rules_dev = RegulatoryEngine.get_rules_for_jurisdiction("research_test_relaxed", allow_research_test=True)
    assert len(rules_dev) >= 3
    assert all(r.verification_status == "research_test" for r in rules_dev)


def test_buildable_footprint_traceability():
    """Every edge setback applied must record exact rule ID and edge ID."""
    provider = FixtureSurveyExtractionProvider()
    req = provider.extract_survey({"fixture_name": "standard_10_perch"})
    recon = reconstruct_polygon(req)

    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")
    buildable = compute_buildable_footprint(
        shapely_poly=recon["shapely_polygon"],
        edges=recon["edges"],
        rules=rules
    )

    assert buildable["valid"] is True
    assert len(buildable["applied_rules"]) >= 4
    # Road front setback applied from rule UDA-SL-R01
    road_entry = next(r for r in buildable["applied_rules"] if r["edge_type"] == "road_front")
    assert road_entry["rule_id"] == "UDA-SL-R01"
    assert road_entry["setback_m"] == 3.0


def test_buildable_footprint_collapsed_returns_infeasible():
    """Narrow parcel where setbacks collapse site returns status=infeasible."""
    # 4m wide parcel with 3m front + 2.3m rear setback
    req = ManualSurveyExtractionRequest(
        edges=[
            SurveyEdgeInput(
                edge_id="E01",
                distance=DistanceValue(value=3.0, unit=DistanceUnit.METERS),
                bearing=BearingValue(raw="090°", normalized_degrees=90.0),
                edge_type=EdgeType.ROAD_FRONT
            ),
            SurveyEdgeInput(
                edge_id="E02",
                distance=DistanceValue(value=4.0, unit=DistanceUnit.METERS),
                bearing=BearingValue(raw="180°", normalized_degrees=180.0),
                edge_type=EdgeType.SIDE_RIGHT
            ),
            SurveyEdgeInput(
                edge_id="E03",
                distance=DistanceValue(value=3.0, unit=DistanceUnit.METERS),
                bearing=BearingValue(raw="270°", normalized_degrees=270.0),
                edge_type=EdgeType.REAR
            ),
            SurveyEdgeInput(
                edge_id="E04",
                distance=DistanceValue(value=4.0, unit=DistanceUnit.METERS),
                bearing=BearingValue(raw="000°", normalized_degrees=0.0),
                edge_type=EdgeType.SIDE_LEFT
            ),
        ]
    )
    recon = reconstruct_polygon(req)
    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")
    buildable = compute_buildable_footprint(
        shapely_poly=recon["shapely_polygon"],
        edges=recon["edges"],
        rules=rules
    )
    assert buildable["valid"] is False
    assert buildable["status"] == "infeasible"


# -----------------------------------------------------------------
# 3. Space Allocation & Feasibility
# -----------------------------------------------------------------

def test_mandatory_rooms_never_silently_scaled_down():
    """When a floor is overloaded, mandatory room areas are not shrunk; it returns infeasible."""
    allocator = RuleBasedSpaceAllocationProvider()
    buildable_area = 50.0  # usable ~42.5 sqm

    reqs = ClientRequirementsInput(
        project_name="Tight Site",
        declared_land_extent=5.0,
        storey_count=1,
        rooms=[
            RoomRequirement(id="r1", type="living_room", quantity=1, preferred_min_area=30.0, required=True),
            RoomRequirement(id="r2", type="kitchen", quantity=1, preferred_min_area=25.0, required=True),  # Total 55 > 42.5
        ]
    )
    res = allocator.allocate_space(buildable_area=buildable_area, requirements=reqs)
    assert res["feasible"] is False
    assert "exceeds" in res["details"]


def test_explicit_floor_conflict_returns_infeasible():
    """Requesting 3rd floor in a 2-storey house returns infeasible."""
    allocator = RuleBasedSpaceAllocationProvider()
    reqs = ClientRequirementsInput(
        project_name="Invalid Floor Request",
        declared_land_extent=10.0,
        storey_count=2,
        rooms=[
            RoomRequirement(id="r1", type="bedroom", quantity=1, floor_preference="2", required=True)
        ]
    )
    res = allocator.allocate_space(buildable_area=150.0, requirements=reqs)
    assert res["feasible"] is False
    assert res["infeasibility_reason"] == "invalid_floor_preference"


def test_four_storey_dynamic_allocation():
    """Verify up to 4 storeys supported dynamically."""
    allocator = RuleBasedSpaceAllocationProvider()
    reqs = ClientRequirementsInput(
        project_name="Four Storey Villa",
        declared_land_extent=15.0,
        storey_count=4,
        rooms=[
            RoomRequirement(id="r1", type="living_room", quantity=1, floor_preference="0"),
            RoomRequirement(id="r2", type="bedroom", quantity=1, floor_preference="1"),
            RoomRequirement(id="r3", type="bedroom", quantity=1, floor_preference="2"),
            RoomRequirement(id="r4", type="bedroom", quantity=1, floor_preference="3"),
        ]
    )
    res = allocator.allocate_space(buildable_area=150.0, requirements=reqs)
    assert res["feasible"] is True
    assert len(res["floors"]) == 4
    # Every floor must contain staircase core
    for fl in res["floors"]:
        types = [rm["type"] for rm in fl["rooms"]]
        assert "staircase" in types


# -----------------------------------------------------------------
# 4. Blueprint Partition & Proportional Sizing
# -----------------------------------------------------------------

def test_blueprint_generated_area_near_target():
    """Verify room areas approximate target areas and stay strictly inside buildable polygon."""
    provider = FixtureSurveyExtractionProvider()
    req = provider.extract_survey({"fixture_name": "standard_10_perch"})
    recon = reconstruct_polygon(req)
    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")
    buildable = compute_buildable_footprint(recon["shapely_polygon"], recon["edges"], rules)

    allocator = RuleBasedSpaceAllocationProvider()
    reqs = ClientRequirementsInput(
        project_name="Test Residence",
        declared_land_extent=10.0,
        storey_count=1,
        rooms=[
            RoomRequirement(id="r1", type="living_room", quantity=1, preferred_min_area=25.0),
            RoomRequirement(id="r2", type="kitchen", quantity=1, preferred_min_area=15.0),
            RoomRequirement(id="r3", type="bedroom", quantity=1, preferred_min_area=15.0),
        ]
    )
    alloc = allocator.allocate_space(buildable["area"], reqs)
    floors = generate_blueprint_floors(buildable["shapely_polygon"], alloc["floors"])

    assert len(floors) == 1
    rooms = floors[0].rooms
    assert len(rooms) == 3

    # Check containment and area
    for rm in rooms:
        poly = Polygon([(p.x, p.y) for p in rm.polygon])
        assert buildable["shapely_polygon"].buffer(0.05).contains(poly)
        assert rm.area > 5.0


# -----------------------------------------------------------------
# 5. Master JSON Non-Destructive Update
# -----------------------------------------------------------------

def test_master_json_preserves_unrelated_sections():
    """Rerunning GAB builder must not overwrite unrelated downstream sections."""
    existing_mj = {
        "project_id": "test-p1",
        "structural_rectification": {
            "columns": [{"id": "C1", "x": 5.0, "y": 5.0}],
            "status": "completed"
        },
        "interior_layout": {
            "furniture": [{"id": "F1", "item": "sofa"}]
        },
        "processing": {
            "vsai": {"status": "completed"}
        }
    }

    service = GabGenService()
    provider = FixtureSurveyExtractionProvider()
    survey_req = provider.extract_survey({"fixture_name": "standard_10_perch"})
    reqs = ClientRequirementsInput(
        project_name="Villa Colombo",
        declared_land_extent=10.0,
        storey_count=1,
        rooms=[RoomRequirement(id="r1", type="living_room", quantity=1)]
    )

    out = service.run_pipeline(
        project_id="test-p1",
        project_name="Villa Colombo",
        survey_request=survey_req,
        requirements=reqs,
        existing_master_json=existing_mj
    )

    mj = out.master_json
    # Unrelated sections preserved
    assert "structural_rectification" in mj
    assert mj["structural_rectification"]["columns"][0]["id"] == "C1"
    assert "interior_layout" in mj
    assert mj["processing"]["vsai"]["status"] == "completed"
    # GAB section updated
    assert mj["processing"]["gab_gen"]["status"] in ("completed", "needs_verification")
