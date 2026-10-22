"""
Phase 10: Training Configuration, Model Metadata & Serialized Artifact Specifications.
Manages hyperparameter search grids, artifact checksums, and version metadata.
"""
import hashlib
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class XGBoostHyperparameters(BaseModel):
    n_estimators: int = Field(default=200, ge=10, le=2000)
    max_depth: int = Field(default=4, ge=2, le=10)
    learning_rate: float = Field(default=0.05, gt=0.001, le=0.5)
    subsample: float = Field(default=0.8, gt=0.1, le=1.0)
    colsample_bytree: float = Field(default=0.8, gt=0.1, le=1.0)
    min_child_weight: float = Field(default=1.0, ge=0.0)
    reg_alpha: float = Field(default=0.1, ge=0.0)
    reg_lambda: float = Field(default=1.0, ge=0.0)
    random_state: int = Field(default=42)
    n_jobs: int = Field(default=2)


class TrainingExperimentConfig(BaseModel):
    experiment_id: str
    dataset_version: str = "1.0.0"
    feature_schema_version: str = "1.0.0"
    target_metric: str = "mean_within_site_ndcg"
    random_seed: int = 42
    hyperparameters: XGBoostHyperparameters = Field(default_factory=XGBoostHyperparameters)
    search_budget: int = Field(default=10, ge=1, le=100)


class ModelMetadata(BaseModel):
    model_version: str = "1.0.0"
    xgboost_version: Optional[str] = None
    python_version: str = "3.14.7"
    created_at: str
    feature_schema_version: str = "1.0.0"
    feature_names: List[str]
    training_site_count: int
    training_candidate_count: int
    validation_site_count: int
    validation_candidate_count: int
    test_site_count: int
    test_candidate_count: int
    hyperparameters: Dict[str, Any]
    validation_metrics: Dict[str, float]
    test_metrics: Dict[str, float]
    artifact_checksum: str
    status: str = "MODEL_TRAINED_BUT_NOT_APPROVED_FOR_RUNTIME"
