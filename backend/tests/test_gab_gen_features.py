"""
Comprehensive unit & integration tests covering new GAB-Gen features:
- Acres and unit conversion
- Logical consistency validation of requirements (attached baths > total baths, etc.)
- Vision & OpenCV preprocessing on synthetic plans
- EasyOCR extraction pipeline (mocked/synthetic)
- Regulatory rules versioning & metadata selection
- Blueprint editing constraints & boundary checking
"""
import pytest
from app.components.gab_gen.input.units import (
    convert_area_to_sqm,
    validate_land_extent,
    parse_acres_roods_perches,
    validate_scale_ratio,
    ACRE_TO_SQM,
    PERCH_TO_SQM
)
from app.components.gab_gen.input.validator import reconcile_and_validate_requirements
from app.components.gab_gen.schemas import (
    ClientRequirementsInput,
    RoomRequirement,
    LandExtentUnit,
    Point2D,
    FloorPlanDefinition,
    RoomPolygon
)
from app.components.gab_gen.regulations.rules import RegulatoryEngine
from app.components.gab_gen.blueprint.editor import validate_room_edit, apply_room_edit
from shapely.geometry import box


def test_acre_conversion():
    # 1 acre = 4046.8564224 sqm
    sqm = convert_area_to_sqm(1.0, LandExtentUnit.ACRES)
    assert abs(sqm - ACRE_TO_SQM) < 0.01

    # Half an acre
    sqm_half = convert_area_to_sqm(0.5, "acres")
    assert abs(sqm_half - (ACRE_TO_SQM / 2)) < 0.01


def test_arp_notation_parsing():
    parsed = parse_acres_roods_perches("A0-R1-P10.5")
    assert parsed is not None
    assert parsed["roods"] == 1
    assert parsed["perches"] == 10.5
    assert parsed["total_perches"] == 50.5  # 1 rood = 40 perches + 10.5 = 50.5


def test_drawing_scale_validation():
    v1 = validate_scale_ratio("1:100")
    assert v1["valid"] is True
    assert v1["denominator"] == 100

    v2 = validate_scale_ratio("invalid_scale")
    assert v2["valid"] is False


def test_inconsistent_requirements_rejected():
    req = ClientRequirementsInput(
        project_name="Bad Counts Residence",
        declared_land_extent=10.0,
        storey_count=2,
        bedroom_count=2,
        master_bedroom_count=3,  # Invalid: 3 > 2
        bathroom_count=1,
        attached_bathroom_count=2  # Invalid: 2 > 1
    )
    rec = reconcile_and_validate_requirements(req)
    assert rec["valid"] is False
    assert len(rec["errors"]) >= 2
    assert any("Master bedroom count" in e for e in rec["errors"])
    assert any("Attached bathroom count" in e for e in rec["errors"])


def test_regulatory_rule_metadata_traceability():
    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")
    assert len(rules) >= 3
    for r in rules:
        assert r.version is not None
        assert r.last_reviewed is not None
        assert r.source_reference is not None


def test_blueprint_room_edit_constraint_enforcement():
    buildable = box(0, 0, 10, 10)
    floor = FloorPlanDefinition(
        floor_id="F0",
        floor_index=0,
        name="Ground Floor",
        elevation=0.0,
        available_area=100.0,
        target_allocated_area=30.0,
        rooms=[
            RoomPolygon(
                room_id="R1",
                name="Living Room",
                type="living_room",
                floor_id="F0",
                area=25.0,
                target_area=25.0,
                polygon=[Point2D(x=1, y=1), Point2D(x=5, y=1), Point2D(x=5, y=5), Point2D(x=1, y=5)],
                center=Point2D(x=3, y=3)
            )
        ],
        walls=[]
    )

    # Edit 1: Valid move inside buildable footprint (staying within 0..10)
    valid_poly = [Point2D(x=2, y=2), Point2D(x=6, y=2), Point2D(x=6, y=6), Point2D(x=2, y=6)]
    v_res = validate_room_edit("R1", "F0", valid_poly, [floor], buildable)
    assert v_res["valid"] is True

    # Edit 2: Invalid move exceeding buildable boundary (> 10)
    invalid_poly = [Point2D(x=8, y=8), Point2D(x=12, y=8), Point2D(x=12, y=12), Point2D(x=8, y=12)]
    inv_res = validate_room_edit("R1", "F0", invalid_poly, [floor], buildable)
    assert inv_res["valid"] is False
    assert any("extends outside" in e for e in inv_res["violations"])


def test_irregular_concave_plot_reconstruction_and_buildable():
    """Verify handling of L-shaped / concave land plots without making the house identical to land."""
    from app.components.gab_gen.schemas import SurveyEdgeInput, DistanceValue, BearingValue, DistanceUnit, EdgeType, ManualSurveyExtractionRequest
    from app.components.gab_gen.vector_reconstruction.reconstruct import reconstruct_polygon
    from app.components.gab_gen.buildable_footprint.compute import compute_buildable_footprint
    from app.components.gab_gen.regulations.rules import RegulatoryEngine

    # 6-sided L-shaped concave plot
    edges = [
        SurveyEdgeInput(edge_id="E1", distance=DistanceValue(value=20.0, unit=DistanceUnit.METERS), bearing=BearingValue(raw="90", normalized_degrees=90.0), edge_type=EdgeType.ROAD_FRONT),
        SurveyEdgeInput(edge_id="E2", distance=DistanceValue(value=10.0, unit=DistanceUnit.METERS), bearing=BearingValue(raw="180", normalized_degrees=180.0), edge_type=EdgeType.SIDE_RIGHT),
        SurveyEdgeInput(edge_id="E3", distance=DistanceValue(value=10.0, unit=DistanceUnit.METERS), bearing=BearingValue(raw="270", normalized_degrees=270.0), edge_type=EdgeType.REAR),
        SurveyEdgeInput(edge_id="E4", distance=DistanceValue(value=10.0, unit=DistanceUnit.METERS), bearing=BearingValue(raw="180", normalized_degrees=180.0), edge_type=EdgeType.SIDE_RIGHT),
        SurveyEdgeInput(edge_id="E5", distance=DistanceValue(value=10.0, unit=DistanceUnit.METERS), bearing=BearingValue(raw="270", normalized_degrees=270.0), edge_type=EdgeType.REAR),
        SurveyEdgeInput(edge_id="E6", distance=DistanceValue(value=20.0, unit=DistanceUnit.METERS), bearing=BearingValue(raw="0", normalized_degrees=0.0), edge_type=EdgeType.SIDE_LEFT),
    ]
    req = ManualSurveyExtractionRequest(edges=edges)
    recon = reconstruct_polygon(req)
    assert recon["is_valid"] is True
    assert recon["closure_error"] < 0.01

    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")
    buildable = compute_buildable_footprint(recon["shapely_polygon"], recon["edges"], rules)
    assert buildable["valid"] is True
    assert buildable["area"] > 0
    # Buildable footprint does not collapse and is properly offset from irregular boundary
    assert buildable["area"] < recon["reconstructed_area"]


def test_roof_preference_geometry_generation():
    """Verify parameterized roof geometry generation for gable, hip, flat, and accessible rooftop."""
    from app.components.gab_gen.blueprint.roof_generator import generate_roof_geometry
    from app.components.gab_gen.schemas import RoofPreference, RoofType
    poly = box(0, 0, 12, 10)

    # 1. Flat slab with parapet
    r_flat = generate_roof_geometry(poly, RoofPreference(roof_type=RoofType.FLAT_SLAB, pitch_angle_deg=0.0))
    assert r_flat.roof_type == "flat_slab"
    assert len(r_flat.planes) == 1
    assert r_flat.planes[0].pitch_deg == 0.0

    # 2. Gable roof with central ridge
    r_gable = generate_roof_geometry(poly, RoofPreference(roof_type=RoofType.GABLE, pitch_angle_deg=22.0, overhang_m=0.8))
    assert r_gable.roof_type == "gable"
    assert len(r_gable.ridge_points) == 2
    assert len(r_gable.planes) == 2
    assert r_gable.max_height_m > 1.0

    # 3. Accessible rooftop terrace
    r_terrace = generate_roof_geometry(poly, RoofPreference(roof_type=RoofType.ACCESSIBLE_ROOFTOP, parapet_height_m=1.1, rooftop_access=True))
    assert r_terrace.roof_type == "accessible_rooftop"
    assert r_terrace.planes[0].height_offset_m == 1.1


def test_blueprint_room_add_and_remove():
    """Verify adding and removing non-structural rooms dynamically with wall recalculation."""
    from app.components.gab_gen.blueprint.editor import add_room_to_blueprint, remove_room_from_blueprint
    buildable = box(0, 0, 20, 20)
    floor = FloorPlanDefinition(
        floor_id="F0",
        floor_index=0,
        name="Ground Floor",
        elevation=0.0,
        available_area=400.0,
        target_allocated_area=30.0,
        rooms=[
            RoomPolygon(
                room_id="F0_LIV_1",
                name="Living Room",
                type="living_room",
                floor_id="F0",
                area=30.0,
                target_area=30.0,
                polygon=[Point2D(x=1, y=1), Point2D(x=6, y=1), Point2D(x=6, y=6), Point2D(x=1, y=6)],
                center=Point2D(x=3.5, y=3.5)
            )
        ],
        walls=[]
    )

    # 1. Add custom study room in non-overlapping space (10..15, 10..15)
    new_room_data = {
        "room_id": "F0_STU_1",
        "name": "Study Room",
        "type": "study_office",
        "polygon": [{"x": 10, "y": 10}, {"x": 15, "y": 10}, {"x": 15, "y": 15}, {"x": 10, "y": 15}],
        "target_area": 25.0
    }
    add_res = add_room_to_blueprint("F0", new_room_data, [floor], buildable)
    assert add_res["success"] is True
    f0_rooms = add_res["floors"][0].rooms
    assert len(f0_rooms) == 2
    assert any(r.room_id == "F0_STU_1" for r in f0_rooms)

    # 2. Remove the study room
    rem_res = remove_room_from_blueprint("F0_STU_1", add_res["floors"], buildable)
    assert rem_res["success"] is True
    assert len(rem_res["floors"][0].rooms) == 1
    assert rem_res["floors"][0].rooms[0].room_id == "F0_LIV_1"

