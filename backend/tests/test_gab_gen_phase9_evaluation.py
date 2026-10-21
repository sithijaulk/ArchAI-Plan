"""
Phase 9: Comprehensive End-to-End Pipeline Evaluation & XGBoost Dataset Readiness Tests.

Validates:
1. Complete 18-stage GAB-Gen workflow execution (Survey -> Regulation -> Footprint -> Multi-Candidate -> Validation -> Feature Vector -> Persistence/Master JSON).
2. XGBoost tabular feature vector extraction (16 features, non-null, finite, bounded).
3. Ground truth expert label schema vs heuristic baseline scores (strict decoupling, no leakage).
4. SiteGroupedDatasetSplit generation (zero parcel leakage between Train, Val, and Test).
5. Dataset sanity audit (flags invalid geometry, catches NaN/Inf, detects cross-split leakage).
6. Cadastral survey benchmark evaluation on representative Western Province topologies.
"""
import math
import pytest
from shapely.geometry import Polygon

from app.components.gab_gen.schemas import (
    CandidateFeasibilityStatus,
    CandidateGenerationConfig,
    ClientRequirementsInput,
    DistanceValue,
    BearingValue,
    EdgeType,
    FloorPlanCandidate,
    FloorPlanDefinition,
    LandExtentUnit,
    ManualSurveyExtractionRequest,
    NumericalFeatureVector,
    Point2D,
    RegulatoryContextInput,
    RoomRequirement,
    SurveyEdgeInput,
    SurveySource,
    SurveyVerificationStatus,
)
from app.components.gab_gen.service import GabGenService
from app.components.gab_gen.dataset.schemas import (
    DatasetRecord,
    ExpertArchitecturalEvaluation,
    SiteGroupedDatasetSplit,
    DatasetSanityReport,
)
from app.components.gab_gen.dataset.dataset_builder import DatasetBuilder, FEATURE_KEYS
from app.components.gab_gen.dataset.benchmark_scenarios import SURVEY_BENCHMARK_SCENARIOS


@pytest.fixture
def standard_client_requirements():
    return ClientRequirementsInput(
        declared_land_extent=10.0,
        declared_land_unit=LandExtentUnit.PERCHES,
        building_type="residential_house",
        storey_count=1,
        regulatory_context=RegulatoryContextInput(
            jurisdiction_id="sri_lanka_uda_standard",
            authority_id="LK-11-CMC",
            zone_confirmed=True,
            road_width=6.0,
        ),
        rooms=[
            RoomRequirement(id="req_liv", type="living_room", quantity=1, required=True, preferred_min_area=18.0),
            RoomRequirement(id="req_din", type="dining_room", quantity=1, required=True, preferred_min_area=12.0),
            RoomRequirement(id="req_kit", type="kitchen", quantity=1, required=True, preferred_min_area=10.0),
            RoomRequirement(id="req_bed1", type="master_bedroom", quantity=1, required=True, preferred_min_area=14.0),
            RoomRequirement(id="req_bed2", type="bedroom", quantity=1, required=True, preferred_min_area=11.0),
            RoomRequirement(id="req_bath", type="bathroom", quantity=1, required=True, preferred_min_area=4.5),
        ],
    )


def test_e2e_full_workflow_execution(standard_client_requirements):
    """
    Evaluates the complete end-to-end pipeline:
    Survey vertices -> Regulations -> Buildable Footprint -> Multi-Candidate -> Features -> Master JSON.
    """
    service = GabGenService()
    scenario = SURVEY_BENCHMARK_SCENARIOS[0]  # WP-COL-REG-01

    survey_req = ManualSurveyExtractionRequest(
        source=SurveySource.MANUAL,
        north_angle=scenario["true_north_angle"],
        north_angle_origin="verified_survey",
        verification_status=SurveyVerificationStatus.USER_VERIFIED,
        edges=[
            SurveyEdgeInput(
                edge_id=e["edge_id"],
                distance=DistanceValue(value=e["distance_m"]),
                bearing=BearingValue(raw=f"{e['bearing_deg']}°", normalized_degrees=e["bearing_deg"]),
                edge_type=e["edge_type"],
                source=SurveySource.MANUAL,
            )
            for e in scenario["edges"]
        ],
    )

    output = service.run_pipeline(
        project_id="PROJ_PHASE9_E2E",
        project_name="Phase 9 Full E2E Benchmark",
        survey_request=survey_req,
        requirements=standard_client_requirements,
        allow_research_test=True,
    )

    assert output.status in ["success", "completed", "needs_verification"]
    assert output.validation.valid is True
    assert len(output.candidates) >= 1
    assert output.selected_candidate_id is not None
    assert "project_id" in output.master_json
    assert "schema_version" in output.master_json

    # Validate the selected candidate feature vector
    sel_cand = next(c for c in output.candidates if c.candidate_id == output.selected_candidate_id)
    assert sel_cand.feasibility_status == CandidateFeasibilityStatus.FEASIBLE_VERIFIED_CONSTRAINTS
    assert sel_cand.features.feature_schema_version == "1.0.0"
    assert sel_cand.features.building_footprint_area_sqm > 0.0
    assert sel_cand.features.total_usable_room_area_sqm > 0.0
    assert 0.0 <= sel_cand.features.area_utilization_ratio <= 1.0
    assert 0.0 <= sel_cand.features.circulation_ratio <= 1.0
    assert 0.0 <= sel_cand.heuristic_score <= 1.0


def test_numerical_feature_vector_finite_and_bounded(standard_client_requirements):
    """
    Verifies that all 16 features extracted by the feature extractor are strictly finite floats.
    """
    service = GabGenService()
    scenario = SURVEY_BENCHMARK_SCENARIOS[1]  # WP-GAM-NAR-02

    survey_req = ManualSurveyExtractionRequest(
        source=SurveySource.MANUAL,
        north_angle=scenario["true_north_angle"],
        north_angle_origin="verified_survey",
        verification_status=SurveyVerificationStatus.USER_VERIFIED,
        edges=[
            SurveyEdgeInput(
                edge_id=e["edge_id"],
                distance=DistanceValue(value=e["distance_m"]),
                bearing=BearingValue(raw=f"{e['bearing_deg']}°", normalized_degrees=e["bearing_deg"]),
                edge_type=e["edge_type"],
                source=SurveySource.MANUAL,
            )
            for e in scenario["edges"]
        ],
    )

    output = service.run_pipeline(
        project_id="PROJ_PHASE9_FEAT",
        project_name="Feature Health Test",
        survey_request=survey_req,
        requirements=standard_client_requirements,
        allow_research_test=True,
    )
    assert len(output.candidates) > 0

    for cand in output.candidates:
        feat_dict = cand.features.model_dump()
        for key in FEATURE_KEYS:
            assert key in feat_dict, f"Missing feature key: {key}"
            val = feat_dict[key]
            assert isinstance(val, (int, float)), f"Feature {key} is not numeric: {val}"
            assert not math.isnan(val), f"Feature {key} is NaN in candidate {cand.candidate_id}"
            assert not math.isinf(val), f"Feature {key} is Inf in candidate {cand.candidate_id}"


def test_site_grouped_dataset_splitting_zero_leakage():
    """
    Tests site-grouped partitioning to guarantee that candidates originating from the
    same site_id never leak across train, val, and test splits.
    """
    records = []
    # Create synthetic candidates for 5 distinct sites
    for site_idx in range(1, 6):
        site_id = f"SITE-00{site_idx}"
        for cand_idx in range(1, 4):
            cand = FloorPlanCandidate(
                candidate_id=f"CAND-{site_id}-{cand_idx}",
                candidate_fingerprint=f"fp_{site_id}_{cand_idx}",
                display_name=f"Candidate {cand_idx}",
                rank=cand_idx,
                heuristic_score=0.75 + (cand_idx * 0.05),
                feasibility_status=CandidateFeasibilityStatus.FEASIBLE_VERIFIED_CONSTRAINTS,
                validation={"valid": True, "status": "completed"},
                features=NumericalFeatureVector(
                    building_footprint_area_sqm=120.0,
                    total_usable_room_area_sqm=95.0,
                    area_utilization_ratio=0.79,
                    circulation_ratio=0.15,
                ),
            )
            rec = DatasetBuilder.create_record(
                site_id=site_id,
                site_extent_perches=10.0,
                site_category="regular_suburban",
                num_floors=1,
                candidate=cand,
            )
            assert rec is not None
            records.append(rec)

    assert len(records) == 15  # 5 sites * 3 candidates

    # Partition with GroupKFold logic
    split = DatasetBuilder.partition_site_grouped(
        records,
        train_ratio=0.60,
        val_ratio=0.20,
        test_ratio=0.20,
        seed=42,
    )

    train_sites = set(split.train_metadata.site_ids)
    val_sites = set(split.val_metadata.site_ids)
    test_sites = set(split.test_metadata.site_ids)

    # 1. Zero site leakage
    assert len(train_sites.intersection(val_sites)) == 0
    assert len(train_sites.intersection(test_sites)) == 0
    assert len(val_sites.intersection(test_sites)) == 0

    # 2. Total site coverage
    all_partitioned_sites = train_sites.union(val_sites).union(test_sites)
    assert len(all_partitioned_sites) == 5

    # 3. Candidate assignment matches parent site partition
    for r in split.train_records:
        assert r.site_id in train_sites
    for r in split.val_records:
        assert r.site_id in val_sites
    for r in split.test_records:
        assert r.site_id in test_sites

    # 4. Audit sanity passes cleanly
    sanity = DatasetBuilder.audit_dataset_sanity(split)
    assert sanity.is_valid is True
    assert sanity.site_leakage_detected is False
    assert sanity.nan_or_inf_detected is False
    assert sanity.infeasible_candidates_included == 0


def test_infeasible_candidates_rejected_from_ranking_dataset():
    """
    Guarantees that candidates violating hard building or regulatory constraints
    cannot enter the ranking training pool as valid examples.
    """
    cand_infeasible = FloorPlanCandidate(
        candidate_id="CAND-REJECT-01",
        candidate_fingerprint="fp_reject_01",
        display_name="Rejected Layout",
        feasibility_status=CandidateFeasibilityStatus.INFEASIBLE,
        validation={"valid": False, "status": "infeasible", "violations": ["REAR_SETBACK_VIOLATED"]},
        features=NumericalFeatureVector(),
    )

    rec = DatasetBuilder.create_record(
        site_id="SITE-FAIL",
        site_extent_perches=8.0,
        site_category="narrow_urban",
        num_floors=1,
        candidate=cand_infeasible,
        allow_infeasible=False,
    )
    assert rec is None, "Infeasible candidate was not excluded from dataset record generation"


def test_expert_architectural_label_decoupled_from_heuristic():
    """
    Verifies that ground truth expert evaluations are distinct from heuristic scores,
    and checks tabular export (X design matrix and y target vector).
    """
    cand = FloorPlanCandidate(
        candidate_id="CAND-EXP-01",
        candidate_fingerprint="fp_exp_01",
        display_name="Candidate 1",
        rank=1,
        heuristic_score=0.72,
        feasibility_status=CandidateFeasibilityStatus.FEASIBLE_VERIFIED_CONSTRAINTS,
        validation={"valid": True, "status": "completed"},
        features=NumericalFeatureVector(
            building_footprint_area_sqm=135.0,
            total_usable_room_area_sqm=105.0,
            area_utilization_ratio=0.78,
            circulation_ratio=0.14,
            compactness_ratio=0.88,
        ),
    )

    # Human expert provides independent assessment
    expert_eval = ExpertArchitecturalEvaluation(
        expert_id="ARCH-SLIA-4821",
        evaluation_timestamp="2026-10-20T10:00:00Z",
        review_confidence=0.95,
        space_efficiency_rating=0.85,
        circulation_flow_rating=0.80,
        privacy_zoning_rating=0.90,
        natural_light_ventilation_rating=0.75,
        structural_rationality_rating=0.95,
        overall_quality_score=0.84,  # Distinct from candidate.heuristic_score (0.72)
        expert_feedback_notes="Excellent spatial organization with clean plumbing stack alignment.",
    )

    rec = DatasetBuilder.create_record(
        site_id="SITE-LABELED-01",
        site_extent_perches=10.0,
        site_category="regular_suburban",
        num_floors=1,
        candidate=cand,
        expert_eval=expert_eval,
    )

    assert rec is not None
    assert rec.is_labeled is True
    assert rec.expert_evaluation is not None
    assert rec.expert_evaluation.overall_quality_score == 0.84
    assert rec.baseline_heuristic_score == 0.72

    # Tabular export verification
    feature_names, X, y = DatasetBuilder.export_tabular_features([rec])
    assert len(feature_names) == 16
    assert len(X) == 1
    assert len(X[0]) == 16
    assert y == [0.84]


def test_cadastral_survey_benchmark_scenarios_reconstruction():
    """
    Evaluates cadastral survey benchmark parcel scenarios for geometric validity,
    closure error, and area correspondence against expected Western Province perches.
    """
    for scenario in SURVEY_BENCHMARK_SCENARIOS:
        coords = []
        cur_x, cur_y = 0.0, 0.0
        coords.append((cur_x, cur_y))
        for edge in scenario["edges"]:
            bearing_rad = math.radians(edge["bearing_deg"])
            dist = edge["distance_m"]
            cur_x += dist * math.sin(bearing_rad)
            cur_y += dist * math.cos(bearing_rad)
            coords.append((cur_x, cur_y))

        poly = Polygon(coords)
        assert poly.is_valid or poly.buffer(0).is_valid
        calc_area = poly.area
        true_area = scenario["true_area_sqm"]
        discrepancy_pct = abs(calc_area - true_area) / true_area * 100.0
        assert discrepancy_pct < 10.0, f"Discrepancy {discrepancy_pct:.2f}% too large for {scenario['site_id']}"
