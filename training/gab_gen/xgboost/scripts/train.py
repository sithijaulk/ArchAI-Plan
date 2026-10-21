"""
Phase 10: XGBoost Regressor Training, Cross-Validation & Experiment Runner.
Executes hyperparameter tuning and model training only when readiness conditions are satisfied.
When real expert training is blocked, provides deterministic dry-run verification
and mock regression modeling for unit testing without fabricating empirical claims.
"""
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from app.components.gab_gen.dataset.schemas import (
    DatasetRecord,
    SiteGroupedDatasetSplit,
)
from app.components.gab_gen.dataset.dataset_builder import DatasetBuilder, FEATURE_KEYS
from training.gab_gen.xgboost.readiness_gate import (
    TrainingReadinessGate,
    TrainingReadinessReport,
    TrainingReadinessStatus,
)
from training.gab_gen.xgboost.evaluation.metrics import evaluate_regression_and_ranking
from training.gab_gen.xgboost.evaluation.baselines import (
    MeanPredictor,
    HeuristicBaselinePredictor,
    RidgeRegressionBaseline,
)
from training.gab_gen.xgboost.configs.config import (
    TrainingExperimentConfig,
    XGBoostHyperparameters,
    ModelMetadata,
)


class XGBoostTrainingRunner:
    """
    Coordinates training readiness audit, baseline comparison, and XGBoost regression fitting.
    """

    @classmethod
    def run_training_experiment(
        cls,
        split: Optional[SiteGroupedDatasetSplit],
        config: TrainingExperimentConfig,
        output_dir: Optional[str] = None,
        allow_synthetic_unit_test: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes complete training and evaluation pipeline.
        Strict Boundary:
        If split fails readiness checks, blocks training unless allow_synthetic_unit_test is True.
        """
        start_time = time.perf_counter()
        readiness: TrainingReadinessReport = TrainingReadinessGate.audit_dataset_readiness(split)

        if not readiness.can_train_research_model and not allow_synthetic_unit_test:
            return {
                "status": "BLOCKED",
                "training_verdict": "TRAINING_BLOCKED_DUE_TO_UNMET_READINESS_CONDITIONS",
                "readiness_report": readiness.model_dump(),
                "duration_seconds": round(time.perf_counter() - start_time, 3),
            }

        # Check XGBoost library availability
        xgb_available = False
        xgb_version = None
        try:
            import xgboost as xgb
            # Verify C-API library is loaded and functional
            _ = xgb.DMatrix([[1.0]], label=[1.0])
            xgb_available = True
            xgb_version = xgb.__version__
        except Exception:
            xgb_available = False

        if not xgb_available and not allow_synthetic_unit_test:
            return {
                "status": "BLOCKED",
                "training_verdict": "TRAINING_BLOCKED_XGBOOST_NOT_INSTALLED",
                "readiness_report": readiness.model_dump(),
                "duration_seconds": round(time.perf_counter() - start_time, 3),
            }

        # Extract features and targets
        feature_names, X_train, y_train = DatasetBuilder.export_tabular_features(split.train_records)
        _, X_val, y_val = DatasetBuilder.export_tabular_features(split.val_records)
        _, X_test, y_test = DatasetBuilder.export_tabular_features(split.test_records)

        X_tr = np.asarray(X_train, dtype=float)
        y_tr = np.asarray([v if v is not None else 0.5 for v in y_train], dtype=float)

        X_va = np.asarray(X_val, dtype=float)
        y_va = np.asarray([v if v is not None else 0.5 for v in y_val], dtype=float)

        X_te = np.asarray(X_test, dtype=float)
        y_te = np.asarray([v if v is not None else 0.5 for v in y_test], dtype=float)

        val_sites = [r.site_id for r in split.val_records]
        test_sites = [r.site_id for r in split.test_records]

        # 1. Fit Baselines
        mean_model = MeanPredictor().fit(X_tr, y_tr)
        mean_preds = mean_model.predict(X_te)
        mean_metrics = evaluate_regression_and_ranking(y_te, mean_preds, test_sites)

        h_train = np.asarray([r.baseline_heuristic_score for r in split.train_records], dtype=float)
        h_test = np.asarray([r.baseline_heuristic_score for r in split.test_records], dtype=float)
        heuristic_model = HeuristicBaselinePredictor(calibrate=True).fit(h_train, y_tr)
        heuristic_preds = heuristic_model.predict(h_test)
        heuristic_metrics = evaluate_regression_and_ranking(y_te, heuristic_preds, test_sites)

        ridge_model = RidgeRegressionBaseline(l2_reg=1.0).fit(X_tr, y_tr)
        ridge_preds = ridge_model.predict(X_te)
        ridge_metrics = evaluate_regression_and_ranking(y_te, ridge_preds, test_sites)

        # 2. Fit XGBoost or Synthetic Test Model
        if xgb_available:
            import xgboost as xgb
            hp = config.hyperparameters
            model = xgb.XGBRegressor(
                n_estimators=hp.n_estimators,
                max_depth=hp.max_depth,
                learning_rate=hp.learning_rate,
                subsample=hp.subsample,
                colsample_bytree=hp.colsample_bytree,
                min_child_weight=hp.min_child_weight,
                reg_alpha=hp.reg_alpha,
                reg_lambda=hp.reg_lambda,
                random_state=hp.random_state,
                n_jobs=hp.n_jobs,
                objective="reg:squarederror",
            )
            model.fit(X_tr, y_tr)
            val_preds = model.predict(X_va)
            test_preds = model.predict(X_te)
        else:
            # Fallback for synthetic software test runs
            val_preds = ridge_model.predict(X_va)
            test_preds = ridge_model.predict(X_te)

        val_metrics = evaluate_regression_and_ranking(y_va, val_preds, val_sites)
        test_metrics = evaluate_regression_and_ranking(y_te, test_preds, test_sites)

        # Compare with heuristic baseline
        outperformed_heuristic = (
            test_metrics["mean_within_site_ndcg"] >= heuristic_metrics["mean_within_site_ndcg"]
            and test_metrics["mae"] <= heuristic_metrics["mae"]
        )

        approval_status = (
            "MODEL_APPROVED_FOR_RUNTIME"
            if (outperformed_heuristic and readiness.can_train_research_model)
            else "MODEL_TRAINED_BUT_NOT_APPROVED_FOR_RUNTIME"
        )

        duration = round(time.perf_counter() - start_time, 3)

        return {
            "status": "COMPLETED",
            "is_synthetic_test_run": allow_synthetic_unit_test and not readiness.can_train_research_model,
            "readiness_report": readiness.model_dump(),
            "baselines": {
                "mean_predictor": mean_metrics,
                "heuristic_baseline": heuristic_metrics,
                "ridge_regression": ridge_metrics,
            },
            "validation_metrics": val_metrics,
            "test_metrics": test_metrics,
            "outperformed_heuristic": outperformed_heuristic,
            "model_approval_status": approval_status,
            "training_duration_seconds": duration,
        }
