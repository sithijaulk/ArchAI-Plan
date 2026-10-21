"""
Phase 9: GAB-Gen XGBoost Dataset Readiness & Evaluation Schemas.
Formal schemas for candidate feature records, ground truth expert annotations,
site-grouped dataset partitions, and data sanity verification.

Strict Boundaries:
- Ground truth expert labels are strictly decoupled from baseline heuristic scores.
- Heuristic scores must never silently backfill expert labels.
- Hard constraint validation status determines eligibility for the candidate pool.
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ..schemas import (
    CandidateFeasibilityStatus,
    NumericalFeatureVector,
    HeuristicScoreBreakdown,
)


class ExpertRatingScale(str, Enum):
    """5-point Likert scale for architectural expert assessment."""
    UNACCEPTABLE = "1_unacceptable"
    POOR = "2_poor"
    ADEQUATE = "3_adequate"
    GOOD = "4_good"
    EXCELLENT = "5_excellent"


class ExpertArchitecturalEvaluation(BaseModel):
    """
    Independent ground truth architectural quality assessment provided by human architects.
    CRITICAL: This is never auto-filled by heuristic scores.
    """
    expert_id: str = Field(..., description="Anonymized licensed architect/reviewer identifier")
    evaluation_timestamp: str = Field(..., description="ISO 8601 timestamp of evaluation")
    review_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Self-reported expert confidence")

    # Granular architectural quality criteria (scored 0.0 to 1.0 or Likert)
    space_efficiency_rating: float = Field(..., ge=0.0, le=1.0, description="Spatial planning efficiency")
    circulation_flow_rating: float = Field(..., ge=0.0, le=1.0, description="Corridor & navigation quality")
    privacy_zoning_rating: float = Field(..., ge=0.0, le=1.0, description="Public vs private space separation")
    natural_light_ventilation_rating: float = Field(..., ge=0.0, le=1.0, description="Daylight & passive ventilation potential")
    structural_rationality_rating: float = Field(..., ge=0.0, le=1.0, description="Load-bearing and plumbing stack viability")

    # Overall target label for XGBoost Regression (0.0 to 1.0)
    overall_quality_score: float = Field(..., ge=0.0, le=1.0, description="Ground truth quality score")

    expert_feedback_notes: Optional[str] = Field(default=None, description="Qualitative feedback or design critiques")


class DatasetRecord(BaseModel):
    """
    Complete row for the XGBoost training / evaluation tabular dataset.
    Links site geometry context, layout strategy, 16D feature vector,
    baseline heuristic scores, and optional expert ground-truth label.
    """
    record_id: str = Field(..., description="Unique dataset record hash/uuid")
    site_id: str = Field(..., description="Parent parcel identifier for GroupKFold splitting")
    site_extent_perches: float = Field(..., gt=0.0)
    site_category: str = Field(..., description="e.g. regular_suburban, narrow_urban, corner_lot, irregular")
    num_floors: int = Field(default=1, ge=1, le=5)

    candidate_id: str
    strategy_name: str
    footprint_variant: str
    feasibility_status: CandidateFeasibilityStatus

    # 16-Dimensional Deterministic Numerical Feature Vector
    features: NumericalFeatureVector

    # Baseline Heuristic Score (for benchmark comparison, NOT as target label)
    baseline_heuristic_score: float = Field(..., ge=0.0, le=1.0)
    baseline_score_breakdown: HeuristicScoreBreakdown

    # Ground Truth Expert Evaluation (Optional: Present for labeled subset, None for unannotated candidates)
    expert_evaluation: Optional[ExpertArchitecturalEvaluation] = None

    # Flag indicating whether this record is labeled for supervised training
    is_labeled: bool = False

    # Eligibility for ML quality modeling (must be FEASIBLE with all hard constraints passed)
    is_eligible_for_ranking_model: bool = True


class DatasetSplitMetadata(BaseModel):
    split_name: str
    site_count: int
    candidate_count: int
    labeled_count: int
    site_ids: List[str]


class SiteGroupedDatasetSplit(BaseModel):
    """
    Partitioned dataset ensuring strict zero site leakage between train, validation, and test.
    All candidates generated on the same site_id belong exclusively to one split.
    """
    dataset_version: str = "1.0.0"
    created_at: str
    feature_schema_version: str = "1.0.0"
    total_sites: int
    total_candidates: int
    train_metadata: DatasetSplitMetadata
    val_metadata: DatasetSplitMetadata
    test_metadata: DatasetSplitMetadata

    train_records: List[DatasetRecord]
    val_records: List[DatasetRecord]
    test_records: List[DatasetRecord]


class DatasetSanityReport(BaseModel):
    """Summary report of dataset integrity, feature health, and leakage checks."""
    is_valid: bool
    total_records: int
    labeled_records: int
    unlabeled_records: int
    unique_sites: int
    site_leakage_detected: bool
    leakage_details: List[str] = Field(default_factory=list)
    nan_or_inf_detected: bool
    feature_ranges_valid: bool
    zero_variance_features: List[str] = Field(default_factory=list)
    infeasible_candidates_included: int = 0
    warnings: List[str] = Field(default_factory=list)
