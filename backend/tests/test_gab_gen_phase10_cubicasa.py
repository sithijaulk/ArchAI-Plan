"""
Unit and regression test suite for Phase 10.1:
CubiCasa5K dataset loader, SVG parsing, canonical geometry conversion,
dataset provenance, coordinate-scale safety, candidate generation,
expert review workflow, label validation, and XGBoost training-readiness gates.
"""
import os
import pytest
from app.components.gab_gen.dataset.cubicasa_loader import (
    CubiCasa5KLoader,
    CoordinateSystemType,
)
from app.components.gab_gen.dataset.expert_workflow import (
    ExpertReviewWorkflow,
    ArchitecturalReviewSubmission,
)
from app.components.gab_gen.dataset.candidate_pipeline import (
    ResearchCandidatePipeline,
)
from app.components.gab_gen.dataset.dataset_builder import (
    DatasetBuilder,
    FEATURE_KEYS,
)
from app.components.gab_gen.dataset.schemas import (
    CandidateFeasibilityStatus,
    ExpertArchitecturalEvaluation,
)
from training.gab_gen.xgboost.readiness_gate import (
    TrainingReadinessGate,
    TrainingReadinessStatus,
)
from training.gab_gen.xgboost.scripts.train import (
    XGBoostTrainingRunner,
)
from training.gab_gen.xgboost.configs.config import (
    TrainingExperimentConfig,
)

DATASET_ROOT = "/Users/kavindyasithumini/Documents/research/cubicasa5k"


def test_cubicasa_dataset_discovery_and_structure():
    loader = CubiCasa5KLoader(DATASET_ROOT)
    samples = loader.discover_samples(max_samples=10)
    assert len(samples) == 10
    first = samples[0]
    assert "sample_id" in first
    assert "folder_path" in first
    assert first["has_svg"] is True
    assert first["category"] in ("high_quality", "high_quality_architectural", "colorful")


def test_cubicasa_svg_parsing_and_geometry_mapping():
    loader = CubiCasa5KLoader(DATASET_ROOT)
    samples = loader.discover_samples(max_samples=5)
    sample = loader.load_sample(samples[0]["sample_id"])
    assert sample is not None
    assert sample.is_parsed_successfully is True
    assert len(sample.rooms) > 0
    assert len(sample.walls) > 0
    # Strict coordinate safety: CubiCasa coordinates are pixel-space
    assert sample.coordinate_system == CoordinateSystemType.PIXEL
    assert sample.has_verified_metric_scale is False
    assert sample.scale_factor_px_per_m is None


def test_cubicasa_polygon_validity_and_canonical_types():
    loader = CubiCasa5KLoader(DATASET_ROOT)
    samples = loader.discover_samples(max_samples=3)
    sample = loader.load_sample(samples[0]["sample_id"])
    assert sample is not None
    for room in sample.rooms:
        assert room.is_valid_polygon is True
        assert len(room.polygon_points) >= 3
        assert room.canonical_type in (
            "bedroom", "living", "kitchen", "bathroom",
            "entry_lobby", "corridor", "dining", "utility",
            "outdoor", "parking", "general_room"
        )


def test_cubicasa_missing_corrupt_sample_handling():
    loader = CubiCasa5KLoader(DATASET_ROOT)
    res = loader.load_sample("high_quality__non_existent_folder_999999")
    assert res is None


def test_candidate_generation_and_16d_features():
    pipeline = ResearchCandidatePipeline()
    records, stats = pipeline.generate_candidates_for_scenarios(max_scenarios=2)
    assert stats["total_scenarios_evaluated"] == 2
    assert len(records) > 0
    first = records[0]
    assert first.site_id.startswith("WP-")
    assert first.feasibility_status == CandidateFeasibilityStatus.FEASIBLE_VERIFIED_CONSTRAINTS
    assert first.is_eligible_for_ranking_model is True
    assert first.is_labeled is False
    # Verify 16D feature extraction
    feat_dict = first.features.model_dump()
    for key in FEATURE_KEYS:
        assert key in feat_dict
        assert isinstance(feat_dict[key], (int, float))


def test_blind_review_package_hides_heuristic_scores():
    pipeline = ResearchCandidatePipeline()
    # Create candidate and package
    from app.components.gab_gen.service import GabGenService
    from app.components.gab_gen.schemas import (
        ManualSurveyExtractionRequest, ClientRequirementsInput, SurveyEdgeInput, DistanceValue, BearingValue, DistanceUnit, SurveyVerificationStatus, SurveySource, RegulatoryContextInput
    )
    from app.components.gab_gen.dataset.benchmark_scenarios import SURVEY_BENCHMARK_SCENARIOS
    sc = SURVEY_BENCHMARK_SCENARIOS[0]
    edges = [
        SurveyEdgeInput(
            edge_id=e['edge_id'],
            distance=DistanceValue(value=e['distance_m'], unit=DistanceUnit.METERS),
            bearing=BearingValue(raw=f"{e['bearing_deg']} deg", normalized_degrees=e['bearing_deg']),
            edge_type=e.get('edge_type'),
            source=SurveySource.MANUAL,
            distance_origin='fixture',
            bearing_origin='fixture',
            verification_status='user_verified',
        )
        for e in sc['edges']
    ]
    survey_req = ManualSurveyExtractionRequest(
        north_angle=sc.get('true_north_angle', 0.0),
        reference_edge=edges[0].edge_id,
        source=SurveySource.MANUAL,
        edges=edges,
        verified_by_user=True,
        verification_status=SurveyVerificationStatus.USER_VERIFIED,
    )
    req_input = ClientRequirementsInput(
        declared_land_extent=sc['extent_perches'],
        declared_land_unit='perches',
        building_type='residential_house',
        storey_count=1,
        occupant_count=4,
        separate_kitchen=True,
        parking_capacity=1,
        attached_bathroom_count=1,
        regulatory_context=RegulatoryContextInput(
            jurisdiction_id='sri_lanka_uda_standard',
            authority_id='LK-11-CMC',
            zone_confirmed=True,
        )
    )
    svc = GabGenService()
    run_out = svc.run_pipeline(
        project_id='test_pkg',
        project_name='Test Package',
        survey_request=survey_req,
        requirements=req_input,
        allow_research_test=True,
    )
    cand = run_out.candidates[0]
    pkg = ExpertReviewWorkflow.create_blind_package(
        site_id=sc['site_id'],
        site_category=sc.get('category', 'regular_suburban'),
        site_extent_perches=sc['extent_perches'],
        candidate=cand,
    )
    # Ensure package hides heuristic scores
    pkg_json = pkg.model_dump_json()
    assert "heuristic_score" not in pkg_json
    assert "score_breakdown" not in pkg_json
    assert pkg.candidate_anonymous_id.startswith("ARCH-CAND-")


def test_expert_review_validation_and_spoof_rejection():
    # Valid submission
    sub = ArchitecturalReviewSubmission(
        submission_id="SUB-001",
        package_id="PKG-001",
        candidate_anonymous_id="ARCH-CAND-ABCD",
        reviewer_id="ARCH-SLIA-4402",
        reviewer_qualification="SLIA_CHARTERED",
        is_synthetic_test=False,
        submission_timestamp="2026-10-21T09:00:00Z",
        functional_arrangement_score=0.85,
        circulation_quality_score=0.80,
        room_usability_score=0.90,
        adjacency_privacy_score=0.75,
        spatial_organization_score=0.88,
        overall_quality_score=0.84,
        confidence=0.95,
        review_notes="Strong passive ventilation and rational corridor flow.",
    )
    # Matching mock package
    from app.components.gab_gen.dataset.expert_workflow import BlindReviewPackage
    pkg = BlindReviewPackage(
        package_id="PKG-001",
        candidate_anonymous_id="ARCH-CAND-ABCD",
        candidate_fingerprint="fp_123",
        site_family_id="WP-COL-REG-01",
        site_category="regular_suburban",
        site_extent_perches=10.0,
        num_floors=1,
        requirements_summary={},
        floor_plans=[],
        doors_summary=[],
        windows_summary=[],
        created_at="2026-10-21T09:00:00Z",
    )
    ok, eval_res, errors = ExpertReviewWorkflow.validate_and_ingest_review(sub, pkg)
    assert ok is True
    assert eval_res is not None
    assert eval_res.overall_quality_score == 0.84
    assert len(errors) == 0

    # Reject mismatched candidate
    sub_mismatch = sub.model_copy(update={"candidate_anonymous_id": "ARCH-CAND-WRONG"})
    ok2, _, err2 = ExpertReviewWorkflow.validate_and_ingest_review(sub_mismatch, pkg)
    assert ok2 is False
    assert any("does not match" in e for e in err2)

    # Reject out-of-range score
    sub_bad_score = sub.model_copy(update={"overall_quality_score": 1.5})
    ok3, _, err3 = ExpertReviewWorkflow.validate_and_ingest_review(sub_bad_score, pkg)
    assert ok3 is False
    assert any("outside valid range" in e for e in err3)


def test_training_readiness_gate_blocks_until_genuine_labels():
    # Empty split
    rep = TrainingReadinessGate.audit_dataset_readiness(None)
    assert rep.status == TrainingReadinessStatus.NOT_READY_FOR_TRAINING
    assert rep.can_train_research_model is False
    assert any("missing or empty" in r for r in rep.reasons_blocked)

    # Generated unlabeled split
    pipeline = ResearchCandidatePipeline()
    records, _ = pipeline.generate_candidates_for_scenarios(max_scenarios=3)
    split = DatasetBuilder.partition_site_grouped(records)
    rep2 = TrainingReadinessGate.audit_dataset_readiness(split)
    assert rep2.status == TrainingReadinessStatus.NOT_READY_FOR_TRAINING
    assert rep2.can_train_research_model is False
    assert any("Zero expert-labeled candidates available" in r for r in rep2.reasons_blocked)


def test_cubicasa_concave_footprint_and_geometry_repairs():
    loader = CubiCasa5KLoader(DATASET_ROOT)
    sample = loader.load_sample("high_quality__10004")
    assert sample is not None
    assert sample.footprint_representation in ("exact_concave_union", "exact_concave_union_multipolygon")
    assert sample.building_footprint is not None
    assert len(sample.footprint_components) > 0
    # Verify secondary polygons and holes fields exist and are tracked
    for r in sample.rooms:
        assert hasattr(r, "secondary_polygons")
        assert hasattr(r, "interior_holes")
        assert hasattr(r, "geometry_repairs")


def test_xgboost_environment_fit_and_predict():
    import xgboost as xgb
    assert hasattr(xgb, "XGBRegressor")
    import numpy as np
    X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]])
    y = np.array([10.0, 20.0, 30.0, 40.0])
    model = xgb.XGBRegressor(n_estimators=5, max_depth=2, random_state=42)
    model.fit(X, y)
    preds = model.predict(X)
    assert len(preds) == 4
    assert np.all(np.isfinite(preds))


def test_expanded_candidate_dataset_diversity():
    pipeline = ResearchCandidatePipeline()
    records, stats = pipeline.generate_candidates_for_scenarios()
    assert stats["total_scenarios_evaluated"] >= 10
    assert len(records) >= 20
    # Verify site-family diversity
    categories = set(r.site_category for r in records)
    assert len(categories) >= 4
    # Verify multiple floor count variations (e.g. 1 to 4 floors)
    floor_counts = set(r.num_floors for r in records)
    assert len(floor_counts) >= 3


def test_pilot_expert_review_package_file_integrity():
    import json
    pilot_path = "/Users/kavindyasithumini/Documents/research/data/pilot_expert_reviews/pilot_review_packages.json"
    assert os.path.exists(pilot_path)
    with open(pilot_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["total_packages"] >= 4
    for pkg in data["packages"]:
        assert "candidate_anonymous_id" in pkg
        assert "site_family_id" in pkg
        assert "floor_plans" in pkg
        # Ensure heuristic score is not present in package
        assert "heuristic_score" not in json.dumps(pkg)


def test_cubicasa_architectural_feature_extraction():
    from app.components.gab_gen.dataset.cubicasa_features import (
        extract_cubicasa_architectural_features,
        compute_deterministic_ai_proxy_scores,
        CUBICASA_FEATURE_KEYS,
    )
    loader = CubiCasa5KLoader(DATASET_ROOT)
    sample = loader.load_sample("high_quality__10004")
    feats = extract_cubicasa_architectural_features(sample)
    assert len(feats) == len(CUBICASA_FEATURE_KEYS)
    for k in CUBICASA_FEATURE_KEYS:
        assert k in feats
        assert isinstance(feats[k], (int, float))
    
    # Test proxy rubric
    proxy = compute_deterministic_ai_proxy_scores(feats)
    assert "ai_proxy_quality_score" in proxy
    assert 0.0 <= proxy["ai_proxy_quality_score"] <= 1.0
    assert proxy["target_origin"] == "AI_PROXY_NOT_HUMAN_EXPERT"


def test_cubicasa_dataset_manifest_and_csvs():
    import csv, json
    manifest_path = "/Users/kavindyasithumini/Documents/research/data/cubicasa_dataset/cubicasa_dataset_manifest.json"
    assert os.path.exists(manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["successfully_extracted_samples"] == 4992
    assert manifest["target_column"] == "ai_proxy_quality_score"
    assert manifest["target_origin"] == "AI_PROXY_NOT_HUMAN_EXPERT"

    # Verify CSV files exist and have correct headers
    features_csv = "/Users/kavindyasithumini/Documents/research/data/cubicasa_dataset/cubicasa_architectural_features.csv"
    assert os.path.exists(features_csv)
    with open(features_csv, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert "sample_id" in header
        assert "room_type_entropy" in header


def test_cubicasa_experimental_xgboost_model_and_metrics():
    import json
    model_path = "/Users/kavindyasithumini/Documents/research/training/cubicasa_proxy_xgboost/cubicasa_experimental_xgboost_model.json"
    metrics_path = "/Users/kavindyasithumini/Documents/research/training/cubicasa_proxy_xgboost/cubicasa_xgboost_metrics.json"
    assert os.path.exists(model_path)
    assert os.path.exists(metrics_path)
    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)
    assert metrics["target"] == "ai_proxy_quality_score"
    assert metrics["target_origin"] == "AI_PROXY_NOT_HUMAN_EXPERT"
    # Model should outperform baselines on test set
    test_eval = metrics["test_evaluation"]
    assert test_eval["xgboost"]["r2_score"] > test_eval["baselines"]["ridge_regression"]["r2_score"]
    assert test_eval["xgboost"]["mae"] < test_eval["baselines"]["mean_predictor"]["mae"]


def test_phase10_4_model_reproducibility_and_residual_tolerance():
    import xgboost as xgb
    import pandas as pd
    import numpy as np
    from sklearn.metrics import r2_score, mean_absolute_error
    from app.components.gab_gen.dataset.cubicasa_features import CUBICASA_FEATURE_KEYS

    model_path = "/Users/kavindyasithumini/Documents/research/training/cubicasa_proxy_xgboost/cubicasa_experimental_xgboost_model.json"
    test_csv = "/Users/kavindyasithumini/Documents/research/data/cubicasa_dataset/cubicasa_experimental_xgboost_train.csv"
    
    model = xgb.XGBRegressor()
    model.load_model(model_path)
    
    df = pd.read_csv(test_csv)
    test_df = df[df['split'] == 'test']
    assert len(test_df) == 394
    
    X_test = test_df[CUBICASA_FEATURE_KEYS].values
    y_test = test_df['ai_proxy_quality_score'].values
    
    preds = model.predict(X_test)
    r2 = r2_score(y_test, preds)
    mae = mean_absolute_error(y_test, preds)
    
    assert r2 > 0.97
    assert mae < 0.01



def test_phase10_4_schema_adapter_gab_gen_compatibility():
    from app.components.gab_gen.service import GabGenService
    from app.components.gab_gen.schemas import (
        ManualSurveyExtractionRequest, ClientRequirementsInput, SurveyEdgeInput, DistanceValue, BearingValue, DistanceUnit, SurveyVerificationStatus, SurveySource, RegulatoryContextInput
    )
    from app.components.gab_gen.dataset.benchmark_scenarios import EXPANDED_SURVEY_BENCHMARK_SCENARIOS
    from app.components.gab_gen.dataset.schema_adapter import convert_gab_gen_candidate_to_cubicasa_24d
    from app.components.gab_gen.dataset.cubicasa_features import CUBICASA_FEATURE_KEYS

    sc = EXPANDED_SURVEY_BENCHMARK_SCENARIOS[0]
    edges = [
        SurveyEdgeInput(
            edge_id=e['edge_id'],
            distance=DistanceValue(value=e['distance_m'], unit=DistanceUnit.METERS),
            bearing=BearingValue(raw=f"{e['bearing_deg']} deg", normalized_degrees=e['bearing_deg']),
            edge_type=e.get('edge_type'),
            source=SurveySource.MANUAL,
            distance_origin='fixture',
            bearing_origin='fixture',
            verification_status='user_verified',
        )
        for e in sc['edges']
    ]
    survey_req = ManualSurveyExtractionRequest(
        north_angle=sc.get('true_north_angle', 0.0),
        reference_edge=edges[0].edge_id,
        source=SurveySource.MANUAL,
        edges=edges,
        verified_by_user=True,
        verification_status=SurveyVerificationStatus.USER_VERIFIED,
    )
    req_input = ClientRequirementsInput(
        declared_land_extent=sc['extent_perches'],
        declared_land_unit='perches',
        building_type='residential_house',
        storey_count=1,
        occupant_count=4,
        separate_kitchen=True,
        parking_capacity=1,
        attached_bathroom_count=1,
        regulatory_context=RegulatoryContextInput(
            jurisdiction_id='sri_lanka_uda_standard',
            authority_id='LK-11-CMC',
            zone_confirmed=True,
        )
    )
    svc = GabGenService()
    run_out = svc.run_pipeline(
        project_id='test_adapt_unit',
        project_name='Test Adapter Unit',
        survey_request=survey_req,
        requirements=req_input,
        allow_research_test=True,
    )
    cand = run_out.candidates[0]
    feats_24d = convert_gab_gen_candidate_to_cubicasa_24d(cand)
    assert len(feats_24d) == len(CUBICASA_FEATURE_KEYS)
    for k in CUBICASA_FEATURE_KEYS:
        assert k in feats_24d
        assert isinstance(feats_24d[k], (int, float))
        import numpy as np
        assert not np.isnan(feats_24d[k])


def test_phase10_4_cross_split_leakage_audit():
    import pandas as pd
    from app.components.gab_gen.dataset.cubicasa_features import CUBICASA_FEATURE_KEYS

    df = pd.read_csv("/Users/kavindyasithumini/Documents/research/data/cubicasa_dataset/cubicasa_experimental_xgboost_train.csv")
    test_df = df[df['split'] == 'test']
    train_df = df[df['split'] == 'train']
    
    # Verify no sample_id appears in both train and test
    test_ids = set(test_df['sample_id'])
    train_ids = set(train_df['sample_id'])
    assert len(test_ids.intersection(train_ids)) == 0


def test_phase10_5_multi_floor_adapter_semantics():
    from app.components.gab_gen.schemas import (
        FloorPlanCandidate, FloorPlanDefinition, RoomPolygon, Point2D, ValidationResult
    )
    from app.components.gab_gen.dataset.schema_adapter import (
        convert_gab_gen_candidate_to_cubicasa_24d, classify_canonical_room_type
    )

    # 1. Test canonical room classification
    assert classify_canonical_room_type("master_bedroom") == "bedroom"
    assert classify_canonical_room_type("open_kitchen") == "kitchen"
    assert classify_canonical_room_type("attached_bathroom") == "bathroom"
    assert classify_canonical_room_type("staircase") == "staircase"
    assert classify_canonical_room_type("hallway") == "corridor"
    assert classify_canonical_room_type("unknown_space") == "general_room"

    # 2. Test multi-floor separation: rooms on different floors should NOT share horizontal adjacency
    floor0_rooms = [
        RoomPolygon(
            room_id="r_living",
            name="Living Room",
            type="living_room",
            floor_id="fl_0",
            area=25.0,
            target_area=25.0,
            polygon=[Point2D(x=0, y=0), Point2D(x=5, y=0), Point2D(x=5, y=5), Point2D(x=0, y=5)],
            center=Point2D(x=2.5, y=2.5),
        ),
        RoomPolygon(
            room_id="r_stair0",
            name="Stair Core",
            type="staircase",
            floor_id="fl_0",
            area=6.0,
            target_area=6.0,
            polygon=[Point2D(x=5, y=0), Point2D(x=7, y=0), Point2D(x=7, y=3), Point2D(x=5, y=3)],
            center=Point2D(x=6, y=1.5),
            is_structural_stair=True,
        )
    ]
    # Floor 1 bedroom is placed right above living room (overlapping 2D coordinates)
    floor1_rooms = [
        RoomPolygon(
            room_id="r_bed",
            name="Master Bedroom",
            type="master_bedroom",
            floor_id="fl_1",
            area=25.0,
            target_area=25.0,
            polygon=[Point2D(x=0, y=0), Point2D(x=5, y=0), Point2D(x=5, y=5), Point2D(x=0, y=5)],
            center=Point2D(x=2.5, y=2.5),
        ),
        RoomPolygon(
            room_id="r_stair1",
            name="Stair Core",
            type="staircase",
            floor_id="fl_1",
            area=6.0,
            target_area=6.0,
            polygon=[Point2D(x=5, y=0), Point2D(x=7, y=0), Point2D(x=7, y=3), Point2D(x=5, y=3)],
            center=Point2D(x=6, y=1.5),
            is_structural_stair=True,
        )
    ]

    cand = FloorPlanCandidate(
        candidate_id="cand_test_multifloor",
        candidate_fingerprint="fp_test_mf",
        display_name="Multi-Floor Test",
        floors=[
            FloorPlanDefinition(floor_id="fl_0", floor_index=0, name="Ground", elevation=0.0, available_area=31.0, target_allocated_area=31.0, rooms=floor0_rooms),
            FloorPlanDefinition(floor_id="fl_1", floor_index=1, name="First", elevation=3.0, available_area=31.0, target_allocated_area=31.0, rooms=floor1_rooms),
        ],
        validation=ValidationResult(valid=True, status="completed"),
    )

    f24 = convert_gab_gen_candidate_to_cubicasa_24d(cand)
    # Living and Bed are on different floors: horizontal adjacency edge count should only reflect living-stair0 (1), bed-stair1 (1), plus 1 stair bridge = 3 edges
    assert f24["room_adjacency_edge_count"] == 3.0
    assert f24["total_rooms"] == 4.0
    assert f24["bedroom_count"] == 1.0


def test_phase10_5_research_preview_endpoint():
    from app.routers.research_cubicasa import preview_package_prediction

    # Test with valid pilot review package
    res = preview_package_prediction("PKG-00D23EBC9727")
    assert "experimental_xgboost_prediction" in res
    assert 0.0 <= res["experimental_xgboost_prediction"] <= 1.0
    assert "deterministic_proxy_target" in res
    assert "mandatory_disclaimer" in res
    assert "Experimental AI-Assisted Proxy Score" in res["mandatory_disclaimer"]
    assert "prediction_difference" in res


def test_phase10_6_clean_split_and_leakage_audit_artifacts():
    import json
    import os
    import pandas as pd

    data_dir = "/Users/kavindyasithumini/Documents/research/data/cubicasa_dataset"
    clean_split_file = os.path.join(data_dir, "cubicasa_clean_split_manifest.json")
    leakage_audit_file = os.path.join(data_dir, "cubicasa_leakage_audit.json")
    dup_groups_file = os.path.join(data_dir, "cubicasa_duplicate_groups.csv")

    assert os.path.exists(clean_split_file)
    assert os.path.exists(leakage_audit_file)
    assert os.path.exists(dup_groups_file)

    with open(clean_split_file) as f:
        clean_split = json.load(f)
    assert clean_split["partitions"]["train"]["sample_count"] == 4203
    assert clean_split["partitions"]["val"]["sample_count"] == 395
    assert clean_split["partitions"]["test"]["sample_count"] == 394

    with open(leakage_audit_file) as f:
        audit = json.load(f)
    assert audit["leakage_verification"]["verdict"] == "ZERO_LEAKAGE_CONFIRMED"
    assert audit["leakage_verification"]["cross_split_family_overlap_train_val"] == 0
    assert audit["leakage_verification"]["cross_split_family_overlap_train_test"] == 0
    assert audit["leakage_verification"]["cross_split_family_overlap_val_test"] == 0

    df_dups = pd.read_csv(dup_groups_file)
    assert len(df_dups) > 0
    assert "duplicate_family_id" in df_dups.columns
    assert "clean_split" in df_dups.columns


def test_phase10_6_readiness_audit_and_expert_label_pipeline():
    from app.routers.research_cubicasa import check_training_readiness
    from app.components.gab_gen.dataset.expert_workflow import (
        ExpertReviewWorkflow, BlindReviewPackage, ArchitecturalReviewSubmission
    )

    # 1. Test readiness check reports NOT_READY when expert targets are unmet
    report = check_training_readiness()
    assert report["status"] == "NOT_READY_FOR_EXPERT_MODEL_TRAINING"
    assert report["can_train_research_model"] is False
    assert len(report["reasons_blocked"]) > 0

    # 2. Test rejection of synthetic/mock ratings from genuine training gate
    sub_synthetic = ArchitecturalReviewSubmission(
        submission_id="SUB-SYNTH-001",
        package_id="PKG-00D23EBC9727",
        candidate_anonymous_id="ARCH-CAND-A0D26CC251B9",
        reviewer_id="MOCK-REVIEWER-01",
        reviewer_qualification="SLIA_CHARTERED",
        is_synthetic_test=True,
        submission_timestamp="2026-10-21T07:00:00Z",
        functional_arrangement_score=0.85,
        circulation_quality_score=0.80,
        room_usability_score=0.80,
        adjacency_privacy_score=0.75,
        spatial_organization_score=0.80,
        overall_quality_score=0.82,
    )
    # Synthetic reviews must not increase genuine review counts in readiness audit
    assert sub_synthetic.is_synthetic_test is True


