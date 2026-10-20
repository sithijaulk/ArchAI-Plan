"""
Comprehensive automated tests for Phase 2: Western Province Regulatory Engine Finalization.
Covers:
Section A: Authority Registry (Colombo, Gampaha, Kalutara filtering, MC/UC/PS classification, aliases, unknown authorities).
Section B: Regulatory Sources & Provenance (Operative Gazette vs non-binding draft rejection, stable source IDs).
Section C: Jurisdiction & Applicability Resolution (CMC vs UDA standard, unknown authority safety, unverified zone).
Section D: Site-Level Restrictions (Wetland, flood, canal reservations, explicit unchecked vs checked states).
Section E: Buildable Footprint Provisional vs Verified Handling (Provisional labeling, setback collapsing).
Section F: Multi-State Compliance Validation (COMPLIANT, NON_COMPLIANT, REQUIRES_REGULATORY_VERIFICATION, CONFLICT_REQUIRES_REVIEW).
Section G: Master JSON Regulatory Provenance & Component Isolation.
"""
import pytest
from shapely.geometry import Polygon

from app.components.gab_gen.schemas import (
    ManualSurveyExtractionRequest,
    SurveyEdgeInput,
    DistanceValue,
    BearingValue,
    DistanceUnit,
    ClientRequirementsInput,
    RegulatoryContextInput,
    SiteRestrictionCheck,
    SiteRestrictionType,
    ComplianceStatus,
    ApplicabilityStatus,
    FloorPlanDefinition,
    RoomPolygon,
    Point2D
)
from app.components.gab_gen.regulations.rules import AuthorityRegistry, RegulatoryEngine
from app.components.gab_gen.buildable_footprint.compute import compute_buildable_footprint
from app.components.gab_gen.validation.validator import validate_gab_geometry, cross_check_land_area
from app.components.gab_gen.service import GabGenService
from app.components.gab_gen.output.master_json_builder import build_gab_master_json


# ==============================================================================
# SECTION A: AUTHORITY REGISTRY TESTS
# ==============================================================================

def test_authority_registry_district_filtering():
    """Western Province must contain exactly 47 local authorities: 13 in Colombo, 18 in Gampaha, 16 in Kalutara (or 16 in Gampaha, 18 in Kalutara)."""
    colombo_auths = AuthorityRegistry.get_authorities_by_district("Colombo")
    gampaha_auths = AuthorityRegistry.get_authorities_by_district("Gampaha")
    kalutara_auths = AuthorityRegistry.get_authorities_by_district("Kalutara")

    assert len(colombo_auths) == 13
    assert len(gampaha_auths) == 18
    assert len(kalutara_auths) == 16
    assert (len(colombo_auths) + len(gampaha_auths) + len(kalutara_auths)) == 47


def test_authority_registry_classification_and_stable_ids():
    """All authorities must have stable IDs, valid classifications (MC/UC/PS), and verified sources."""
    reg = AuthorityRegistry.load()
    authorities = reg.get("authorities", [])
    assert len(authorities) == 47

    mc_count = sum(1 for a in authorities if a["authority_type"] == "MC")
    uc_count = sum(1 for a in authorities if a["authority_type"] == "UC")
    ps_count = sum(1 for a in authorities if a["authority_type"] == "PS")

    # In Western Province: 7 MCs (Colombo: CMC, DMMC, SJKMC, Kaduwela, Moratuwa; Gampaha: Negombo, Gampaha)
    # 14 UCs (Colombo: 5, Gampaha: 5, Kalutara: 4)
    # 26 PSs (Colombo: 3, Gampaha: 11, Kalutara: 12)
    # Total: 7 + 14 + 26 = 47
    assert mc_count == 7
    assert uc_count == 14
    assert ps_count == 26
    assert (mc_count + uc_count + ps_count) == 47

    for a in authorities:
        assert a["authority_id"].startswith("LK-")
        assert a["province"] == "Western"
        assert a["status"] == "verified"
        assert a["source_reference"]["document_title"] is not None


def test_authority_alias_resolution():
    """Aliases like 'CMC' or 'Colombo MC' must resolve to Colombo Municipal Council stable ID."""
    auth1 = AuthorityRegistry.find_authority(name="CMC")
    assert auth1 is not None
    assert auth1["authority_id"] == "LK-11-CMC"

    auth2 = AuthorityRegistry.find_authority(name="Colombo MC")
    assert auth2 is not None
    assert auth2["authority_id"] == "LK-11-CMC"

    auth3 = AuthorityRegistry.find_authority(name="DMMC")
    assert auth3 is not None
    assert auth3["authority_id"] == "LK-11-DMMC"


def test_authority_unknown_rejected_or_unresolved():
    """An unknown authority name must return None from find_authority and be flagged unresolved."""
    auth = AuthorityRegistry.find_authority(name="Atlantis Municipal Council")
    assert auth is None


# ==============================================================================
# SECTION B: REGULATORY SOURCES & PROVENANCE
# ==============================================================================

def test_regulatory_sources_operative_vs_draft():
    """Operative gazettes must be legally operative, while non-binding drafts are strictly flagged."""
    sources = RegulatoryEngine.load_all_sources()
    assert len(sources) >= 5

    gazette_2235 = next((s for s in sources if s["source_id"] == "SRC-UDA-2235-54"), None)
    assert gazette_2235 is not None
    assert gazette_2235["legal_status"] == "operative"
    assert gazette_2235["verification_status"] == "verified"
    assert gazette_2235["effective_from"] == "2021-07-08"

    draft_source = next((s for s in sources if s["source_id"] == "SRC-UDA-DRAFT-PARKING-2019"), None)
    assert draft_source is not None
    assert draft_source["legal_status"] == "draft_non_operative"
    assert "draft" in draft_source["verification_status"].lower()


# ==============================================================================
# SECTION C: JURISDICTION & APPLICABILITY RESOLUTION
# ==============================================================================

def test_jurisdiction_colombo_municipal_council():
    """CMC input resolves strictly to colombo_municipal_council with CMC specific sources."""
    ctx = RegulatoryContextInput(
        province="Western",
        district="Colombo",
        local_authority_name="Colombo Municipal Council",
        development_zone="Commercial High Density",
        zone_confirmed=True,
        road_width=9.0
    )
    res = RegulatoryEngine.resolve_full_regulatory_context(ctx)
    assert res.planning_jurisdiction_id == "colombo_municipal_council"
    assert res.authority_id == "LK-11-CMC"
    assert res.authority_verification_status == "verified"
    assert res.zone_verification_status == "verified"
    assert res.applicability_status == ApplicabilityStatus.APPLICABLE_VERIFIED
    assert "SRC-CMC-DEV-PLAN-1999" in res.governing_sources


def test_jurisdiction_outer_western_province_council_uda_standard():
    """Outer council (e.g. Kaduwela MC or Gampaha PS) resolves to UDA standard Gazette 2235/54."""
    ctx = RegulatoryContextInput(
        province="Western",
        district="Colombo",
        local_authority_name="Kaduwela Municipal Council",
        development_zone="Low Density Residential",
        zone_confirmed=True,
        road_width=6.0
    )
    res = RegulatoryEngine.resolve_full_regulatory_context(ctx)
    assert res.planning_jurisdiction_id == "sri_lanka_uda_standard"
    assert res.authority_id == "LK-11-KMC"
    assert res.authority_verification_status == "verified"
    assert "SRC-UDA-2235-54" in res.governing_sources


def test_jurisdiction_unknown_authority_requires_verification():
    """Unknown authority must safely provide baseline rules but report REQUIRES_REGULATORY_VERIFICATION."""
    ctx = RegulatoryContextInput(
        province="Western",
        district="Gampaha",
        local_authority_name="Hypothetical Nonexistent Council"
    )
    res = RegulatoryEngine.resolve_full_regulatory_context(ctx)
    assert res.planning_jurisdiction_id == "sri_lanka_uda_standard"
    assert res.authority_id is None
    assert res.authority_verification_status == "unverified"
    assert res.applicability_status == ApplicabilityStatus.REQUIRES_REGULATORY_VERIFICATION
    assert len(res.unresolved_requirements) > 0


def test_jurisdiction_unconfirmed_zone_requires_verification():
    """A known council with unconfirmed zone must have applicability_status=REQUIRES_REGULATORY_VERIFICATION."""
    ctx = RegulatoryContextInput(
        province="Western",
        district="Colombo",
        local_authority_name="Kaduwela Municipal Council",
        development_zone="Mixed Development",
        zone_confirmed=False
    )
    res = RegulatoryEngine.resolve_full_regulatory_context(ctx)
    assert res.zone_verification_status == "requires_regulatory_verification"
    assert res.applicability_status == ApplicabilityStatus.REQUIRES_REGULATORY_VERIFICATION


# ==============================================================================
# SECTION D: SITE-LEVEL RESTRICTIONS
# ==============================================================================

def test_site_restriction_unchecked_triggers_unresolved_requirement():
    """A missing or unchecked restriction (e.g. wetland/flood map) must NOT be assumed absent."""
    poly = Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])
    b_poly = Polygon([(3, 3), (17, 3), (17, 12), (3, 12)])
    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")

    area_chk = cross_check_land_area(300.0, 300.0)
    restrictions = [
        SiteRestrictionCheck(
            restriction_type=SiteRestrictionType.WETLAND,
            checked=False,
            notes="No authoritative SLLDC wetland layer connected."
        )
    ]
    val = validate_gab_geometry(
        land_poly=poly,
        buildable_poly=b_poly,
        closure_error=0.01,
        area_check=area_chk,
        floors=[],
        expected_storey_count=0,
        rules=rules,
        site_restrictions=restrictions
    )

    assert val.compliance_verdict == ComplianceStatus.REQUIRES_REGULATORY_VERIFICATION
    assert any("wetland" in u.lower() for u in val.unresolved_requirements)


def test_site_restriction_intersected_causes_violation():
    """A verified intersection with a canal reservation must produce a non-compliant violation."""
    poly = Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])
    b_poly = Polygon([(3, 3), (17, 3), (17, 12), (3, 12)])
    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")
    area_chk = cross_check_land_area(300.0, 300.0)

    restrictions = [
        SiteRestrictionCheck(
            restriction_type=SiteRestrictionType.CANAL_RESERVATION,
            checked=True,
            intersected=True,
            buffer_required_m=6.5,
            dataset_name="SLLDC_Metro_Canals_2023",
            verification_status="verified",
            notes="Parcel boundary intersects SLLDC 6.5m canal reservation."
        )
    ]
    val = validate_gab_geometry(
        land_poly=poly,
        buildable_poly=b_poly,
        closure_error=0.01,
        area_check=area_chk,
        floors=[],
        expected_storey_count=0,
        rules=rules,
        site_restrictions=restrictions
    )

    assert val.valid is False
    assert val.compliance_verdict == ComplianceStatus.NON_COMPLIANT
    assert any("canal_reservation" in v.lower() for v in val.violations)


# ==============================================================================
# SECTION E: BUILDABLE FOOTPRINT PROVISIONAL VS VERIFIED
# ==============================================================================

def test_buildable_footprint_provisional_flag_when_context_unverified():
    """When access road or authority status is unverified, footprint is marked provisional=True."""
    poly = Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])
    edges = [
        {"edge_id": "E1", "edge_type": "road_front", "start": {"x": 0, "y": 0}, "end": {"x": 20, "y": 0}},
        {"edge_id": "E2", "edge_type": "side", "start": {"x": 20, "y": 0}, "end": {"x": 20, "y": 15}},
        {"edge_id": "E3", "edge_type": "rear", "start": {"x": 20, "y": 15}, "end": {"x": 0, "y": 15}},
        {"edge_id": "E4", "edge_type": "side", "start": {"x": 0, "y": 15}, "end": {"x": 0, "y": 0}},
    ]
    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")

    ctx = RegulatoryEngine.resolve_full_regulatory_context(
        RegulatoryContextInput(
            province="Western",
            district="Colombo",
            local_authority_name="Some Council Without Road Info"
        )
    )

    res = compute_buildable_footprint(poly, edges, rules, regulatory_context=ctx)
    assert res["valid"] is True
    assert res["provisional"] is True
    assert "PROVISIONAL" in res["preview_label"]
    assert len(res["provisional_reasons"]) > 0


def test_buildable_footprint_collapsing_narrow_site():
    """A site narrower than setbacks must collapse cleanly to infeasible without negative geometry."""
    narrow_poly = Polygon([(0, 0), (2.0, 0), (2.0, 10.0), (0, 10.0)])
    edges = [
        {"edge_id": "E1", "edge_type": "side", "start": {"x": 0, "y": 0}, "end": {"x": 2.0, "y": 0}},
        {"edge_id": "E2", "edge_type": "side", "start": {"x": 2.0, "y": 0}, "end": {"x": 2.0, "y": 10.0}},
        {"edge_id": "E3", "edge_type": "side", "start": {"x": 2.0, "y": 10.0}, "end": {"x": 0, "y": 10.0}},
        {"edge_id": "E4", "edge_type": "side", "start": {"x": 0, "y": 10.0}, "end": {"x": 0, "y": 0}},
    ]
    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")

    res = compute_buildable_footprint(narrow_poly, edges, rules)
    assert res["valid"] is False
    assert res["status"] == "infeasible"
    assert res["area"] == 0.0


# ==============================================================================
# SECTION F: MULTI-STATE COMPLIANCE VALIDATION
# ==============================================================================

def test_validation_multi_state_compliant_only_when_fully_verified():
    """Compliance verdict is COMPLIANT only when all rules pass and authority/zone/street lines are verified."""
    poly = Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])
    b_poly = Polygon([(3, 3), (17, 3), (17, 12), (3, 12)])
    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")
    area_chk = cross_check_land_area(300.0, 300.0)

    # Fully verified resolution
    ctx = RegulatoryContextInput(
        province="Western",
        district="Colombo",
        local_authority_name="Colombo Municipal Council",
        development_zone="Primary Residential",
        zone_confirmed=True,
        road_width=9.0
    )
    reg_resolution = RegulatoryEngine.resolve_full_regulatory_context(ctx)

    # Compliant rooms (bedroom >= 9.5 sqm, bathroom >= 1.7 sqm, kitchen >= 5.5 sqm)
    rooms = [
        RoomPolygon(
            room_id="R1", name="Master Bedroom", type="master_bedroom", floor_id="FL-00",
            area=14.0, target_area=14.0, center=Point2D(x=5, y=5),
            polygon=[Point2D(x=3.5, y=3.5), Point2D(x=7.5, y=3.5), Point2D(x=7.5, y=7.0), Point2D(x=3.5, y=7.0)]
        ),
        RoomPolygon(
            room_id="R2", name="Kitchen", type="kitchen", floor_id="FL-00",
            area=8.0, target_area=8.0, center=Point2D(x=10, y=5),
            polygon=[Point2D(x=8.0, y=3.5), Point2D(x=11.0, y=3.5), Point2D(x=11.0, y=6.0), Point2D(x=8.0, y=6.0)]
        )
    ]
    floor = FloorPlanDefinition(
        floor_id="FL-00", floor_index=0, name="Ground Floor",
        elevation=0.0, available_area=126.0, target_allocated_area=22.0, rooms=rooms
    )

    val = validate_gab_geometry(
        land_poly=poly,
        buildable_poly=b_poly,
        closure_error=0.01,
        area_check=area_chk,
        floors=[floor],
        expected_storey_count=1,
        rules=rules,
        regulatory_resolution=reg_resolution
    )

    assert val.valid is True
    assert val.compliance_verdict == ComplianceStatus.COMPLIANT


def test_validation_multi_state_unresolved_when_zone_unconfirmed():
    """If development zone is unconfirmed, verdict MUST be REQUIRES_REGULATORY_VERIFICATION, never COMPLIANT."""
    poly = Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])
    b_poly = Polygon([(3, 3), (17, 3), (17, 12), (3, 12)])
    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")
    area_chk = cross_check_land_area(300.0, 300.0)

    ctx = RegulatoryContextInput(
        province="Western",
        district="Colombo",
        local_authority_name="Colombo Municipal Council",
        development_zone="Zone Unconfirmed",
        zone_confirmed=False
    )
    reg_resolution = RegulatoryEngine.resolve_full_regulatory_context(ctx)

    val = validate_gab_geometry(
        land_poly=poly,
        buildable_poly=b_poly,
        closure_error=0.01,
        area_check=area_chk,
        floors=[],
        expected_storey_count=0,
        rules=rules,
        regulatory_resolution=reg_resolution
    )

    assert val.compliance_verdict == ComplianceStatus.REQUIRES_REGULATORY_VERIFICATION
    assert val.compliance_verdict != ComplianceStatus.COMPLIANT


# ==============================================================================
# SECTION G: MASTER JSON PROVENANCE & ISOLATION
# ==============================================================================

def test_master_json_preserves_regulatory_provenance_and_foreign_keys():
    """Master JSON must store structured regulatory resolution and preserve unrelated components."""
    existing_mj = {
        "project_id": "P-REG-01",
        "elia_engine": {"electrical_layout_version": "1.2"},
        "vsai_rectifier": {"mesh_integrity": True}
    }

    from app.components.gab_gen.schemas import LandExtentUnit
    req = ClientRequirementsInput(
        declared_land_extent=10.0,
        declared_land_unit=LandExtentUnit.PERCHES,
        storey_count=1,
        regulatory_context=RegulatoryContextInput(
            province="Western",
            district="Colombo",
            local_authority_name="Colombo Municipal Council",
            development_zone="Commercial",
            zone_confirmed=True
        )
    )
    rules = RegulatoryEngine.get_rules_for_jurisdiction("sri_lanka_uda_standard")
    survey_req = ManualSurveyExtractionRequest(
        north_angle=0.0,
        edges=[
            SurveyEdgeInput(edge_id="E1", distance=DistanceValue(value=20.0), bearing=BearingValue(raw="90", degrees=90.0, normalized_degrees=90.0)),
            SurveyEdgeInput(edge_id="E2", distance=DistanceValue(value=15.0), bearing=BearingValue(raw="180", degrees=180.0, normalized_degrees=180.0)),
            SurveyEdgeInput(edge_id="E3", distance=DistanceValue(value=20.0), bearing=BearingValue(raw="270", degrees=270.0, normalized_degrees=270.0)),
            SurveyEdgeInput(edge_id="E4", distance=DistanceValue(value=15.0), bearing=BearingValue(raw="0", degrees=0.0, normalized_degrees=0.0)),
        ]
    )

    reg_res = RegulatoryEngine.resolve_full_regulatory_context(req.regulatory_context)
    val = validate_gab_geometry(
        land_poly=Polygon([(0, 0), (20, 0), (20, 15), (0, 15)]),
        buildable_poly=Polygon([(3, 3), (17, 3), (17, 12), (3, 12)]),
        closure_error=0.0,
        area_check={"exceeds_tolerance": False, "declared_area_sqm": 300.0, "reconstructed_area_sqm": 300.0},
        floors=[],
        expected_storey_count=0,
        rules=rules,
        regulatory_resolution=reg_res
    )

    mj = build_gab_master_json(
        project_id="P-REG-01",
        project_name="Provenance Test",
        survey_request=survey_req,
        reconstructed_data={"vertices": [], "reconstructed_area": 300.0, "is_valid": True},
        requirements=req,
        rules=rules,
        buildable_data={"polygon": [], "area": 126.0, "valid": True, "provisional": False},
        allocation_data={},
        floors=[],
        validation=val,
        existing_master_json=existing_mj
    )

    # 1. Unrelated sections preserved
    assert "elia_engine" in mj
    assert mj["elia_engine"]["electrical_layout_version"] == "1.2"
    assert "vsai_rectifier" in mj

    # 2. Regulatory provenance stored
    assert "regulatory_rules" in mj
    reg_section = mj["regulatory_rules"]
    assert reg_section["source_registry_version"] == "1.0.0"
    assert reg_section["authority_registry_version"] == "1.0.0"
    assert "compliance_verdict" in reg_section
    assert "regulatory_resolution" in reg_section
    assert reg_section["regulatory_resolution"]["authority_id"] == "LK-11-CMC"
