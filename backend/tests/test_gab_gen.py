"""
Unit tests for GAB-Gen Stage 1 Backend.
Tests:
- Bearing normalization
- Vector polygon reconstruction
- Area cross-check
- Regulatory setbacks
- Buildable footprint computation
- Space allocation & multi-floor feasibility
- Non-overlap & containment
- Master JSON structure & schema validation
"""
import pytest
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
    BuildingType
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
from app.components.gab_gen.service import GabGenService


def test_bearing_normalization():
    assert normalize_bearing_string("90") == 90.0
    assert normalize_bearing_string("090°00'00\"") == 90.0
    assert normalize_bearing_string("N 90 E") == 90.0
    assert normalize_bearing_string("S 0 E") == 180.0
    assert normalize_bearing_string("S 90 W") == 270.0


def test_fixture_vector_reconstruction():
    provider = FixtureSurveyExtractionProvider()
    req = provider.extract_survey({"fixture_name": "standard_10_perch"})
    
    result = reconstruct_polygon(req)
    assert result["is_valid"] is True
    assert result["closure_error"] < 0.1
    # 14.5 * 17.44 ≈ 252.88 sqm (~10 perches)
    assert 240.0 < result["reconstructed_area"] < 265.0
    assert len(result["vertices"]) == 4


def test_area_cross_check():
    # 10 perches = 252.93 sqm
    check = cross_check_land_area(declared_area_sqm=252.93, reconstructed_area_sqm=252.88, tolerance_percent=15.0)
    assert check["exceeds_tolerance"] is False
    assert check["area_difference_percent"] < 1.0

    # Large mismatch
    mismatch = cross_check_land_area(declared_area_sqm=500.0, reconstructed_area_sqm=252.88, tolerance_percent=15.0)
    assert mismatch["exceeds_tolerance"] is True


def test_buildable_footprint():
    provider = FixtureSurveyExtractionProvider()
    req = provider.extract_survey({"fixture_name": "standard_10_perch"})
    recon = reconstruct_polygon(req)
    
    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")
    assert len(rules) >= 3

    buildable = compute_buildable_footprint(
        shapely_poly=recon["shapely_polygon"],
        edges=recon["edges"],
        rules=rules
    )
    assert buildable["valid"] is True
    assert 0 < buildable["area"] < recon["reconstructed_area"]
    # Buildable must be contained within land polygon
    assert recon["shapely_polygon"].contains(buildable["shapely_polygon"])


def test_space_allocator_multi_storey():
    allocator = RuleBasedSpaceAllocationProvider()
    buildable_area = 120.0  # sqm
    
    reqs = ClientRequirementsInput(
        project_name="Test Residence",
        declared_land_extent=10.0,
        storey_count=2,
        rooms=[
            RoomRequirement(id="rm1", type="living_room", quantity=1),
            RoomRequirement(id="rm2", type="kitchen", quantity=1),
            RoomRequirement(id="rm3", type="master_bedroom", quantity=1),
            RoomRequirement(id="rm4", type="bedroom", quantity=2),
            RoomRequirement(id="rm5", type="bathroom", quantity=2),
        ]
    )

    allocation = allocator.allocate_space(buildable_area=buildable_area, requirements=reqs)
    assert allocation["feasible"] is True
    assert len(allocation["floors"]) == 2
    # Verify staircase zone created for multi-storey
    g_rooms = [r["type"] for r in allocation["floors"][0]["rooms"]]
    f_rooms = [r["type"] for r in allocation["floors"][1]["rooms"]]
    assert "staircase" in g_rooms
    assert "staircase" in f_rooms


def test_infeasible_programme():
    allocator = RuleBasedSpaceAllocationProvider()
    tiny_buildable = 20.0  # very small
    
    reqs = ClientRequirementsInput(
        project_name="Mansion on Tiny Lot",
        declared_land_extent=1.0,
        storey_count=1,
        rooms=[
            RoomRequirement(id="rm1", type="living_room", quantity=2, preferred_min_area=40.0),
            RoomRequirement(id="rm2", type="bedroom", quantity=4, preferred_min_area=25.0),
        ]
    )
    res = allocator.allocate_space(buildable_area=tiny_buildable, requirements=reqs)
    assert res["feasible"] is False
    assert res["infeasibility_reason"] == "insufficient_buildable_area"


def test_end_to_end_service_pipeline():
    service = GabGenService()
    provider = FixtureSurveyExtractionProvider()
    survey_req = provider.extract_survey({"fixture_name": "standard_10_perch"})

    reqs = ClientRequirementsInput(
        project_name="Villa Colombo",
        declared_land_extent=10.0,
        declared_land_unit=LandExtentUnit.PERCHES,
        storey_count=2,
        rooms=[
            RoomRequirement(id="r1", type="living_room", quantity=1),
            RoomRequirement(id="r2", type="kitchen", quantity=1),
            RoomRequirement(id="r3", type="master_bedroom", quantity=1),
            RoomRequirement(id="r4", type="bedroom", quantity=1),
            RoomRequirement(id="r5", type="bathroom", quantity=2),
        ]
    )

    output = service.run_pipeline(
        project_id="test-p1",
        project_name="Villa Colombo",
        survey_request=survey_req,
        requirements=reqs,
        jurisdiction="sri_lanka_uda_standard"
    )

    assert output.status in ("completed", "needs_verification")
    mj = output.master_json
    assert mj["project_id"] == "test-p1"
    assert "source_land_polygon" in mj["land_info"]
    assert "buildable_footprint" in mj
    assert len(mj["floor_plan"]["floors"]) == 2
    # Ensure source legal polygon is separate from buildable footprint
    assert mj["land_info"]["source_land_polygon"] != mj["buildable_footprint"]["polygon"]
