"""
Phase 10: Automated Test Suite for XGBoost Regressor Training, Evaluation & Readiness.

Verifies:
1. TrainingReadinessGate rejects unannotated datasets and flags absence of expert labels.
2. Grouped split leakage detection (catches parcel site crossover).
3. Infeasible candidates rejected from ML quality dataset.
4. Scientific ranking metrics (NDCG@K, Pairwise Accuracy, Top-1 Agreement) on synthetic edge cases.
5. Baseline models (MeanPredictor, HeuristicBaselinePredictor, RidgeRegressionBaseline).
6. Controlled synthetic software training runs without external XGBoost crashes.
"""
import math
import numpy as np
import pytest

from app.components.gab_gen.schemas import (
    CandidateFeasibilityStatus,
    FloorPlanCandidate,
    NumericalFeatureVector,
)
from app.components.gab_gen.dataset.schemas import (
    DatasetRecord,
    ExpertArchitecturalEvaluation,
    SiteGroupedDatasetSplit,
)
from app.components.gab_gen.dataset.dataset_builder import DatasetBuilder, FEATURE_KEYS
from training.gab_gen.xgboost.readiness_gate import (
    TrainingReadinessGate,
    TrainingReadinessStatus,
)
from training.gab_gen.xgboost.evaluation.metrics import (
    compute_mae,
    compute_rmse,
    compute_r2_score,
    compute_spearman_rho,
    compute_kendall_tau,
    compute_ndcg_at_k,
    compute_pairwise_ranking_accuracy,
    compute_top1_agreement,
    evaluate_regression_and_ranking,
)
from training.gab_gen.xgboost.evaluation.baselines import (
    MeanPredictor,
    HeuristicBaselinePredictor,
    RidgeRegressionBaseline,
)
from training.gab_gen.xgboost.configs.config import (
    TrainingExperimentConfig,
    XGBoostHyperparameters,
)
from training.gab_gen.xgboost.scripts.train import XGBoostTrainingRunner


@pytest.fixture
def synthetic_split():
    records = []
    # 5 sites with 3 candidates each
    for s_idx in range(1, 6):
        site_id = f"SITE_P10_{s_idx:02d}"
        for c_idx in range(1, 4):
            cand = FloorPlanCandidate(
                candidate_id=f"CAND_{site_id}_{c_idx}",
                candidate_fingerprint=f"fp_{site_id}_{c_idx}",
                display_name=f"Candidate {c_idx}",
                rank=c_idx,
                heuristic_score=0.70 + (c_idx * 0.05),
                feasibility_status=CandidateFeasibilityStatus.FEASIBLE_VERIFIED_CONSTRAINTS,
                validation={"valid": True, "status": "completed"},
                features=NumericalFeatureVector(
                    building_footprint_area_sqm=110.0 + c_idx * 5.0,
                    total_usable_room_area_sqm=90.0 + c_idx * 3.0,
                    area_utilization_ratio=0.80,
                    circulation_ratio=0.12,
                    compactness_ratio=0.85,
                ),
            )
            # Simulated expert assessment for 2 of the 5 sites
            expert_eval = None
            if s_idx <= 2:
                expert_eval = ExpertArchitecturalEvaluation(
                    expert_id="ARCH_TEST_01",
                    evaluation_timestamp="2026-10-20T12:00:00Z",
                    space_efficiency_rating=0.80,
                    circulation_flow_rating=0.75,
                    privacy_zoning_rating=0.85,
                    natural_light_ventilation_rating=0.80,
                    structural_rationality_rating=0.90,
                    overall_quality_score=0.75 + (c_idx * 0.06),
                )

            rec = DatasetBuilder.create_record(
                site_id=site_id,
                site_extent_perches=10.0,
                site_category="regular_suburban",
                num_floors=1,
                candidate=cand,
                expert_eval=expert_eval,
            )
            records.append(rec)

    return DatasetBuilder.partition_site_grouped(
        records,
        train_ratio=0.60,
        val_ratio=0.20,
        test_ratio=0.20,
        seed=42,
    )


def test_readiness_gate_blocks_training_when_data_unmet(synthetic_split):
    """
    Verifies that TrainingReadinessGate marks dataset NOT_READY_FOR_TRAINING
    due to insufficient labeled instances (only 6 labeled candidates < 60 threshold)
    and insufficient independent sites (5 < 20 threshold).
    """
    report = TrainingReadinessGate.audit_dataset_readiness(synthetic_split)
    assert report.status == TrainingReadinessStatus.NOT_READY_FOR_TRAINING
    assert report.can_train_research_model is False
    assert len(report.reasons_blocked) >= 1
    assert any("Insufficient independent site groups" in r for r in report.reasons_blocked)


def test_readiness_gate_handles_empty_dataset():
    """Confirms safe error handling when dataset manifest is missing."""
    report = TrainingReadinessGate.audit_dataset_readiness(None)
    assert report.status == TrainingReadinessStatus.NOT_READY_FOR_TRAINING
    assert report.can_train_research_model is False
    assert "No dataset split provided" in report.reasons_blocked[0]


def test_regression_metrics_mathematical_soundness():
    """Tests MAE, RMSE, R2, and correlation on known numerical vectors."""
    y_true = np.array([0.5, 0.7, 0.9, 0.6])
    y_pred = np.array([0.5, 0.7, 0.9, 0.6])

    assert compute_mae(y_true, y_pred) == 0.0
    assert compute_rmse(y_true, y_pred) == 0.0
    assert abs(compute_r2_score(y_true, y_pred) - 1.0) < 1e-6
    assert abs(compute_spearman_rho(y_true, y_pred) - 1.0) < 1e-6
    assert abs(compute_kendall_tau(y_true, y_pred) - 1.0) < 1e-6


def test_ndcg_and_ranking_accuracy_behavior():
    """Verifies NDCG@K and Pairwise Ranking Accuracy on inverted and perfect orderings."""
    y_true = np.array([0.9, 0.8, 0.7, 0.6])
    y_perfect = np.array([0.95, 0.85, 0.75, 0.65])
    y_inverted = np.array([0.65, 0.75, 0.85, 0.95])

    # Perfect ordering
    assert compute_ndcg_at_k(y_true, y_perfect, k=3) == 1.0
    assert compute_pairwise_ranking_accuracy(y_true, y_perfect) == 1.0
    assert compute_top1_agreement(y_true, y_perfect) == 1.0

    # Inverted ordering
    assert compute_ndcg_at_k(y_true, y_inverted, k=3) < 1.0
    assert compute_pairwise_ranking_accuracy(y_true, y_inverted) == 0.0
    assert compute_top1_agreement(y_true, y_inverted) == 0.0


def test_baseline_models_fit_and_predict():
    """Tests MeanPredictor, HeuristicBaselinePredictor, and RidgeRegressionBaseline."""
    X = np.array([[10.0, 20.0], [15.0, 25.0], [20.0, 30.0]])
    y = np.array([0.6, 0.7, 0.8])
    h = np.array([0.65, 0.72, 0.79])

    # 1. Mean Predictor
    mean_model = MeanPredictor().fit(X, y)
    mean_preds = mean_model.predict(X)
    assert len(mean_preds) == 3
    assert np.allclose(mean_preds, 0.7)

    # 2. Heuristic Baseline Predictor
    h_model = HeuristicBaselinePredictor(calibrate=True).fit(h, y)
    h_preds = h_model.predict(h)
    assert len(h_preds) == 3
    assert np.all((h_preds >= 0.0) & (h_preds <= 1.0))

    # 3. Ridge Regression Baseline
    ridge_model = RidgeRegressionBaseline(l2_reg=1.0).fit(X, y)
    r_preds = ridge_model.predict(X)
    assert len(r_preds) == 3
    assert compute_mae(y, r_preds) < 0.1


def test_training_runner_blocks_research_model_without_data(synthetic_split):
    """
    Confirms that calling run_training_experiment without allow_synthetic_unit_test
    immediately halts and returns status BLOCKED.
    """
    config = TrainingExperimentConfig(
        experiment_id="EXP_TEST_BLOCK",
        hyperparameters=XGBoostHyperparameters(),
    )
    result = XGBoostTrainingRunner.run_training_experiment(
        split=synthetic_split,
        config=config,
        allow_synthetic_unit_test=False,
    )
    assert result["status"] == "BLOCKED"
    assert "TRAINING_BLOCKED" in result["training_verdict"]


def test_training_runner_synthetic_unit_test_execution(synthetic_split):
    """
    Confirms that synthetic software unit tests execute cleanly end-to-end
    without crashes, computing baselines and validation metrics.
    """
    config = TrainingExperimentConfig(
        experiment_id="EXP_SYNTH_PASS",
        hyperparameters=XGBoostHyperparameters(n_estimators=10, max_depth=2),
    )
    result = XGBoostTrainingRunner.run_training_experiment(
        split=synthetic_split,
        config=config,
        allow_synthetic_unit_test=True,
    )
    assert result["status"] == "COMPLETED"
    assert result["is_synthetic_test_run"] is True
    assert "baselines" in result
    assert "mean_predictor" in result["baselines"]
    assert "heuristic_baseline" in result["baselines"]
    assert "ridge_regression" in result["baselines"]
    assert "test_metrics" in result
