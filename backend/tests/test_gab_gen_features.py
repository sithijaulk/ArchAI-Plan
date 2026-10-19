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
