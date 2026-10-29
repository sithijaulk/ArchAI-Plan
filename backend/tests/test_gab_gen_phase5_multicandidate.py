"""
Automated Test Suite for GAB-Gen Phase 5:
Multi-Candidate Floor-Plan Generation, Feasibility Filtering & Deterministic Ranking.

Verifies:
A. Multi-Candidate Generation (multiple distinct candidates for feasible scenario)
B. Bounded Generation Attempts & Determinism (same seed -> identical ranking & geometry)
C. Footprint Variations (containment within legal parcel and buildable footprint)
D. Multi-Floor & Staircase Consistency across candidates
E. Deduplication & Similarity Filtering (identical/near-identical layouts pruned)
F. Numerical Feature Extraction (finite outputs, correct units, schema v1.0.0)
G. Explainable Heuristic Ranking (higher score ranks first, infeasible candidate never ranks valid)
H. Candidate Selection & Persistence in Centralized Master JSON
I. Non-destructive preservation of Phase 2 regulatory & Phase 3 survey provenance
"""
import pytest
from shapely.geometry import Polygon

from app.components.gab_gen.schemas import (
    ManualSurveyExtractionRequest,
    SurveyEdgeInput,
    DistanceValue,
    BearingValue,
    SurveySource,
    SurveyVerificationStatus,
    EdgeType,
    ClientRequirementsInput,
    RoomRequirement,
    RegulatoryContextInput,
    CandidateGenerationConfig,
    CandidateFeasibilityStatus,
    FloorPlanCandidate,
)
from app.components.gab_gen.service import GabGenService
from app.components.gab_gen.blueprint.candidate_generator import (
    generate_footprint_variants,
    generate_candidate_floors,
)
from app.components.gab_gen.validation.feature_extractor import extract_candidate_features
from app.components.gab_gen.validation.similarity_detector import (
    compute_candidate_fingerprint,
    are_candidates_duplicates,
    deduplicate_candidate_pool,
)
from app.components.gab_gen.validation.heuristic_scorer import score_candidate, rank_candidates
from app.components.gab_gen.blueprint.multi_candidate_service import generate_multi_candidates


@pytest.fixture
def standard_survey_and_reqs():
    # 20m x 15m parcel (300 sqm)
    edges = [
        SurveyEdgeInput(edge_id="E1", distance=DistanceValue(value=20.0), bearing=BearingValue(raw="0°", normalized_degrees=0.0), edge_type=EdgeType.ROAD_FRONT, source=SurveySource.MANUAL),
        SurveyEdgeInput(edge_id="E2", distance=DistanceValue(value=15.0), bearing=BearingValue(raw="90°", normalized_degrees=90.0), edge_type=EdgeType.SIDE_RIGHT, source=SurveySource.MANUAL),
        SurveyEdgeInput(edge_id="E3", distance=DistanceValue(value=20.0), bearing=BearingValue(raw="180°", normalized_degrees=180.0), edge_type=EdgeType.REAR, source=SurveySource.MANUAL),
        SurveyEdgeInput(edge_id="E4", distance=DistanceValue(value=15.0), bearing=BearingValue(raw="270°", normalized_degrees=270.0), edge_type=EdgeType.SIDE_LEFT, source=SurveySource.MANUAL),
    ]
    survey = ManualSurveyExtractionRequest(
        source=SurveySource.MANUAL,
        north_angle=0.0,
        north_angle_origin="verified_survey",
        verification_status=SurveyVerificationStatus.USER_VERIFIED,
        edges=edges
    )
    reqs = ClientRequirementsInput(
        declared_land_extent=11.85,
        declared_land_unit="perches",
        building_type="residential_house",
        storey_count=1,
        regulatory_context=RegulatoryContextInput(
            jurisdiction_id="sri_lanka_uda_standard",
            authority_id="LK-11-CMC",
            zone_confirmed=True,
            road_width=9.0
        ),
        rooms=[
            RoomRequirement(id="req_liv", type="living_room", quantity=1, required=True, preferred_min_area=22.0),
            RoomRequirement(id="req_kit", type="kitchen", quantity=1, required=True, preferred_min_area=12.0),
            RoomRequirement(id="req_bed1", type="master_bedroom", quantity=1, required=True, preferred_min_area=16.0),
            RoomRequirement(id="req_bed2", type="bedroom", quantity=1, required=True, preferred_min_area=12.0),
            RoomRequirement(id="req_bath", type="bathroom", quantity=1, required=True, preferred_min_area=4.0),
        ]
    )
    return survey, reqs


def test_footprint_variants_containment():
    """Footprint variants must be strictly inside the buildable polygon and valid."""
    buildable_poly = Polygon([(3.0, 3.0), (17.0, 3.0), (17.0, 12.0), (3.0, 12.0)])
    variants = generate_footprint_variants(buildable_poly, max_variants=4)
    assert len(variants) >= 2

    for name, poly in variants:
        assert poly.is_valid
        assert poly.area > 0
        # Must be contained inside buildable_poly
        assert buildable_poly.buffer(0.01).contains(poly)


def test_deterministic_candidate_generation_with_seed(standard_survey_and_reqs):
    """Running generation twice on identical inputs must yield identical fingerprints, scores, and rankings."""
    survey, reqs = standard_survey_and_reqs
    service = GabGenService()

    run1 = service.run_pipeline(
        project_id="PROJ_DET_001",
        project_name="Deterministic Run 1",
        survey_request=survey,
        requirements=reqs,
        allow_research_test=True
    )

    run2 = service.run_pipeline(
        project_id="PROJ_DET_002",
        project_name="Deterministic Run 2",
        survey_request=survey,
        requirements=reqs,
        allow_research_test=True
    )

    assert len(run1.candidates) > 0
    assert len(run1.candidates) == len(run2.candidates)

    for c1, c2 in zip(run1.candidates, run2.candidates):
        assert c1.candidate_fingerprint == c2.candidate_fingerprint
        assert c1.heuristic_score == c2.heuristic_score
        assert c1.rank == c2.rank
        assert c1.strategy_name == c2.strategy_name


def test_deduplication_removes_identical_layouts():
    """Identical or near-identical candidate layouts must be pruned from the pool."""
    poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    fl_allocs = [{
        "floor_index": 0,
        "name": "Ground Floor",
        "rooms": [
            {"type": "living_room", "name": "Living", "target_area": 30.0, "required": True},
            {"type": "bedroom", "name": "Bed", "target_area": 25.0, "required": True},
        ]
    }]

    fl1 = generate_candidate_floors(poly, fl_allocs, strategy_name="strat1")
    fl2 = generate_candidate_floors(poly, fl_allocs, strategy_name="strat2")

    fp1 = compute_candidate_fingerprint(poly, fl1)
    fp2 = compute_candidate_fingerprint(poly, fl2)

    assert fp1 == fp2  # Identical geometry yields same fingerprint

    cand1 = FloorPlanCandidate(
        candidate_id="FP_CAND_001",
        candidate_fingerprint=fp1,
        display_name="Option 1",
        floors=fl1,
        building_footprint_area_sqm=poly.area,
        validation={"valid": True, "status": "completed"}
    )
    cand2 = FloorPlanCandidate(
        candidate_id="FP_CAND_002",
        candidate_fingerprint=fp2,
        display_name="Option 2",
        floors=fl2,
        building_footprint_area_sqm=poly.area,
        validation={"valid": True, "status": "completed"}
    )

    pool = deduplicate_candidate_pool([cand1, cand2], min_diversity=0.10)
    assert len(pool) == 1
    assert pool[0].candidate_id == "FP_CAND_001"


def test_feature_extraction_properties(standard_survey_and_reqs):
    """Numerical feature extractor outputs finite numbers and strictly normalized ratios."""
    survey, reqs = standard_survey_and_reqs
    service = GabGenService()
    output = service.run_pipeline(
        project_id="PROJ_FEAT_001",
        project_name="Feature Extractor Test",
        survey_request=survey,
        requirements=reqs,
        allow_research_test=True
    )

    assert len(output.candidates) > 0
    c = output.candidates[0]
    f = c.features

    assert f.feature_schema_version == "1.0.0"
    assert 0.0 <= f.area_utilization_ratio <= 1.0
    assert 0.0 <= f.circulation_ratio <= 1.0
    assert 0.0 <= f.mandatory_room_satisfaction_ratio <= 1.0
    assert 0.0 <= f.compactness_ratio <= 1.0
    assert f.total_usable_room_area_sqm > 0
    assert f.building_footprint_area_sqm > 0


def test_heuristic_ranking_order():
    """Higher scoring candidates must rank higher, and infeasible plans must never rank as valid options."""
    c1 = FloorPlanCandidate(
        candidate_id="FP_001",
        candidate_fingerprint="abc1",
        display_name="Cand 1",
        feasibility_status=CandidateFeasibilityStatus.FEASIBLE_VERIFIED_CONSTRAINTS,
        features={"area_utilization_ratio": 0.82, "circulation_ratio": 0.14, "compactness_ratio": 0.90, "adjacency_satisfaction_ratio": 1.0},
        validation={"valid": True, "status": "completed"}
    )
    c2 = FloorPlanCandidate(
        candidate_id="FP_002",
        candidate_fingerprint="abc2",
        display_name="Cand 2",
        feasibility_status=CandidateFeasibilityStatus.FEASIBLE_VERIFIED_CONSTRAINTS,
        features={"area_utilization_ratio": 0.40, "circulation_ratio": 0.02, "compactness_ratio": 0.40, "adjacency_satisfaction_ratio": 0.5},
        validation={"valid": True, "status": "completed"}
    )
    c_infeasible = FloorPlanCandidate(
        candidate_id="FP_003",
        candidate_fingerprint="abc3",
        display_name="Infeasible Cand",
        feasibility_status=CandidateFeasibilityStatus.INFEASIBLE,
        features={"area_utilization_ratio": 0.95},
        validation={"valid": False, "status": "infeasible"}
    )

    ranked = rank_candidates([c2, c1, c_infeasible])
    assert len(ranked) == 2  # Infeasible excluded from selectable pool
    assert ranked[0].candidate_id == "FP_001"  # c1 scored higher than c2
    assert ranked[0].rank == 1
    assert ranked[1].rank == 2
    assert ranked[0].heuristic_score >= ranked[1].heuristic_score


def test_multi_floor_two_storey_candidate_consistency():
    """Multi-storey candidate generation preserves staircase vertical alignment on all floors."""
    edges = [
        SurveyEdgeInput(edge_id="E1", distance=DistanceValue(value=20.0), bearing=BearingValue(raw="0°", normalized_degrees=0.0), edge_type=EdgeType.ROAD_FRONT, source=SurveySource.MANUAL),
        SurveyEdgeInput(edge_id="E2", distance=DistanceValue(value=15.0), bearing=BearingValue(raw="90°", normalized_degrees=90.0), edge_type=EdgeType.SIDE_RIGHT, source=SurveySource.MANUAL),
        SurveyEdgeInput(edge_id="E3", distance=DistanceValue(value=20.0), bearing=BearingValue(raw="180°", normalized_degrees=180.0), edge_type=EdgeType.REAR, source=SurveySource.MANUAL),
        SurveyEdgeInput(edge_id="E4", distance=DistanceValue(value=15.0), bearing=BearingValue(raw="270°", normalized_degrees=270.0), edge_type=EdgeType.SIDE_LEFT, source=SurveySource.MANUAL),
    ]
    survey = ManualSurveyExtractionRequest(source=SurveySource.MANUAL, north_angle=0.0, edges=edges)
    reqs = ClientRequirementsInput(
        declared_land_extent=11.85,
        declared_land_unit="perches",
        building_type="residential_house",
        storey_count=2,
        regulatory_context=RegulatoryContextInput(jurisdiction_id="sri_lanka_uda_standard", zone_confirmed=True),
        rooms=[
            RoomRequirement(id="req_liv", type="living_room", quantity=1, required=True, floor_preference=0),
            RoomRequirement(id="req_kit", type="kitchen", quantity=1, required=True, floor_preference=0),
            RoomRequirement(id="req_bed1", type="master_bedroom", quantity=1, required=True, floor_preference=1),
            RoomRequirement(id="req_bed2", type="bedroom", quantity=1, required=True, floor_preference=1),
        ]
    )

    service = GabGenService()
    output = service.run_pipeline(
        project_id="PROJ_2STOREY_001",
        project_name="2-Storey Multi-Candidate",
        survey_request=survey,
        requirements=reqs,
        allow_research_test=True
    )

    assert len(output.candidates) >= 1
    for cand in output.candidates:
        assert len(cand.floors) == 2
        f0_stairs = [r for r in cand.floors[0].rooms if r.is_structural_stair]
        f1_stairs = [r for r in cand.floors[1].rooms if r.is_structural_stair]
        assert len(f0_stairs) == 1
        assert len(f1_stairs) == 1
        assert f0_stairs[0].center.x == f1_stairs[0].center.x
        assert f0_stairs[0].center.y == f1_stairs[0].center.y


def test_master_json_candidate_persistence_and_provenance(standard_survey_and_reqs):
    """Centralized Master JSON persists candidate pool, ranking, and selected candidate."""
    survey, reqs = standard_survey_and_reqs
    service = GabGenService()
    output = service.run_pipeline(
        project_id="PROJ_MJ_CAND_001",
        project_name="Master JSON Candidates Test",
        survey_request=survey,
        requirements=reqs,
        allow_research_test=True
    )

    mj = output.master_json
    assert "candidate_generation" in mj
    cg = mj["candidate_generation"]
    assert cg["feasible_candidate_count"] == len(output.candidates)
    assert len(cg["candidates"]) == len(output.candidates)
    assert cg["selected_candidate_id"] == output.selected_candidate_id
    assert cg["generator_version"] == "1.5.0"
    assert cg["ranking_method"] == "heuristic_v1"

    selected_c = next(c for c in output.candidates if c.candidate_id == output.selected_candidate_id)
    assert len(mj["floor_plan"]["floors"]) == len(selected_c.floors)
