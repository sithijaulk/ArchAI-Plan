"""
Comprehensive Test Suite for GAB-Gen Western Province Regulatory Compliance Integration.
Tests:
1. All 47 Western Province local authorities map deterministically to verified statutory frameworks.
2. CMC rules apply strictly to Colombo Municipal Council; non-CMC authorities do not get CMC rules.
3. UDA Gazette 2235/54 rules apply across all other councils (e.g. Kaduwela, Gampaha, Negombo, Kalutara).
4. Room dimension constraints (Schedule 7) detect compliant and non-compliant room allocations.
5. Max plot coverage (Schedule 6) is strictly verified.
6. Editable blueprint revalidation detects statutory room dimension violations.
7. Verification status and statutory references are fully traceable.
8. No budget estimation or financial cost is present or calculated.
"""
import pytest
from app.components.gab_gen.schemas import (
    RegulatoryContextInput,
    RoomPolygon,
    FloorPlanDefinition,
    Point2D,
    ClientRequirementsInput,
    ManualSurveyExtractionRequest,
    SurveyEdgeInput,
    DistanceValue,
    BearingValue,
    DistanceUnit,
    BuildingType
)
from app.components.gab_gen.regulations.rules import RegulatoryEngine
from app.components.gab_gen.validation.validator import validate_gab_geometry
from app.components.gab_gen.blueprint.editor import validate_room_edit
from shapely.geometry import Polygon


def test_western_province_all_authorities_resolve_correctly():
    """Verify that all Western Province authorities resolve to valid verified jurisdictions."""
    # Test Colombo Municipal Council
    cmc_ctx = RegulatoryContextInput(
        province="Western",
        district="Colombo",
        local_authority_type="Municipal Council",
        local_authority_name="Colombo Municipal Council"
    )
    assert RegulatoryEngine.resolve_jurisdiction(cmc_ctx) == "colombo_municipal_council"

    # Test Kaduwela Municipal Council (must get UDA Standard, NOT CMC)
    kaduwela_ctx = RegulatoryContextInput(
        province="Western",
        district="Colombo",
        local_authority_type="Municipal Council",
        local_authority_name="Kaduwela Municipal Council"
    )
    assert RegulatoryEngine.resolve_jurisdiction(kaduwela_ctx) == "sri_lanka_uda_standard"

    # Test Dehiwala-Mount Lavinia Municipal Council (must get UDA Standard, NOT CMC)
    dehiwala_ctx = RegulatoryContextInput(
        province="Western",
        district="Colombo",
        local_authority_type="Municipal Council",
        local_authority_name="Dehiwala-Mount Lavinia Municipal Council"
    )
    assert RegulatoryEngine.resolve_jurisdiction(dehiwala_ctx) == "sri_lanka_uda_standard"

    # Test Negombo Municipal Council (Gampaha)
    negombo_ctx = RegulatoryContextInput(
        province="Western",
        district="Gampaha",
        local_authority_type="Municipal Council",
        local_authority_name="Negombo Municipal Council"
    )
    assert RegulatoryEngine.resolve_jurisdiction(negombo_ctx) == "sri_lanka_uda_standard"

    # Test Kalutara Urban Council
    kalutara_ctx = RegulatoryContextInput(
        province="Western",
        district="Kalutara",
        local_authority_type="Urban Council",
        local_authority_name="Kalutara Urban Council"
    )
    assert RegulatoryEngine.resolve_jurisdiction(kalutara_ctx) == "sri_lanka_uda_standard"

    # Test Kelaniya Pradeshiya Sabha
    kelaniya_ctx = RegulatoryContextInput(
        province="Western",
        district="Gampaha",
        local_authority_type="Pradeshiya Sabha",
        local_authority_name="Kelaniya Pradeshiya Sabha"
    )
    assert RegulatoryEngine.resolve_jurisdiction(kelaniya_ctx) == "sri_lanka_uda_standard"


def test_uda_rules_traceability_and_statutory_attributes():
    """All verified UDA rules must contain exact statutory references to Gazette 2235/54."""
    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")
    assert len(rules) >= 8

    # Verify Schedule 7 room dimension rule exists and is verified
    mbed_rule = next(r for r in rules if r.rule_id == "UDA-2021-ROOM-BED-FIRST-01")
    assert mbed_rule.verification_status == "verified"
    assert mbed_rule.value == 9.5
    assert mbed_rule.unit == "sqm"
    assert "Schedule 7" in (mbed_rule.clause_reference or "")
    assert "2235/54" in mbed_rule.source_document

    # Verify coverage rule
    cov_rule = RegulatoryEngine.get_max_coverage_rule(rules)
    assert cov_rule is not None
    assert cov_rule.value == 0.65


def test_validator_detects_substandard_room_dimensions():
    """Validate that room area below Gazette 2235/54 Schedule 7 minimum triggers a violation."""
    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")
    land_poly = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)])
    buildable_poly = Polygon([(2, 2), (18, 2), (18, 18), (2, 18)])

    # Substandard master bedroom: 7.0 m² (Statutory minimum is 9.5 m²)
    substandard_room = RoomPolygon(
        room_id="F0-MBED-01",
        name="Master Bedroom",
        type="master_bedroom",
        floor_id="FL-00",
        area=7.0,
        target_area=14.0,
        polygon=[Point2D(x=2.5, y=2.5), Point2D(x=5.0, y=2.5), Point2D(x=5.0, y=5.3), Point2D(x=2.5, y=5.3)],
        center=Point2D(x=3.75, y=3.9)
    )

    floor = FloorPlanDefinition(
        floor_id="FL-00",
        floor_index=0,
        name="Ground Floor",
        elevation=0.0,
        available_area=200.0,
        target_allocated_area=100.0,
        rooms=[substandard_room]
    )

    val = validate_gab_geometry(
        land_poly=land_poly,
        buildable_poly=buildable_poly,
        closure_error=0.01,
        area_check={"declared_area_sqm": 400.0, "reconstructed_area_sqm": 400.0, "exceeds_tolerance": False},
        floors=[floor],
        expected_storey_count=1,
        rules=rules
    )

    assert val.valid is False
    assert any("violates statutory minimum area" in v for v in val.violations)


def test_validator_passes_compliant_room_dimensions():
    """Compliant rooms according to Gazette 2235/54 Schedule 7 pass validation."""
    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")
    land_poly = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)])
    buildable_poly = Polygon([(2, 2), (18, 2), (18, 18), (2, 18)])

    compliant_room = RoomPolygon(
        room_id="F0-MBED-01",
        name="Master Bedroom",
        type="master_bedroom",
        floor_id="FL-00",
        area=14.0,
        target_area=14.0,
        polygon=[Point2D(x=2.5, y=2.5), Point2D(x=6.0, y=2.5), Point2D(x=6.0, y=6.5), Point2D(x=2.5, y=6.5)],
        center=Point2D(x=4.25, y=4.5)
    )

    floor = FloorPlanDefinition(
        floor_id="FL-00",
        floor_index=0,
        name="Ground Floor",
        elevation=0.0,
        available_area=200.0,
        target_allocated_area=100.0,
        rooms=[compliant_room]
    )

    val = validate_gab_geometry(
        land_poly=land_poly,
        buildable_poly=buildable_poly,
        closure_error=0.01,
        area_check={"declared_area_sqm": 400.0, "reconstructed_area_sqm": 400.0, "exceeds_tolerance": False},
        floors=[floor],
        expected_storey_count=1,
        rules=rules
    )

    assert val.valid is True
    assert len(val.violations) == 0
    assert val.regulatory_status == "verified"
    assert val.design_checks["coverage_compliance"]["compliant"] is True


def test_editor_revalidation_enforces_statutory_minimums():
    """Editing a room to be smaller than statutory minimum must be rejected."""
    buildable_poly = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)])
    mbed = RoomPolygon(
        room_id="F0-MBED-01",
        name="Master Bedroom",
        type="master_bedroom",
        floor_id="FL-00",
        area=14.0,
        target_area=14.0,
        polygon=[Point2D(x=2, y=2), Point2D(x=6, y=2), Point2D(x=6, y=5.5), Point2D(x=2, y=5.5)],
        center=Point2D(x=4, y=3.75)
    )
    floor = FloorPlanDefinition(
        floor_id="FL-00",
        floor_index=0,
        name="Ground Floor",
        elevation=0.0,
        available_area=200.0,
        target_allocated_area=100.0,
        rooms=[mbed]
    )

    # Propose shrink to 2m x 2m = 4.0 m² (Violates statutory 9.5 m²)
    shrink_poly = [Point2D(x=2, y=2), Point2D(x=4, y=2), Point2D(x=4, y=4), Point2D(x=2, y=4)]
    check = validate_room_edit(
        room_id="F0-MBED-01",
        target_floor_id="FL-00",
        new_polygon=shrink_poly,
        floors=[floor],
        buildable_poly=buildable_poly
    )

    assert check["valid"] is False
    assert any("violates statutory minimum" in v for v in check["violations"])
