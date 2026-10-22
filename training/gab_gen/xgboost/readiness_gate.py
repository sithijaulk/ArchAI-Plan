"""
Phase 10: Training Readiness Gate for GAB-Gen XGBoost Architectural Quality Regressor.
Inspects empirical dataset provenance, expert ratings, and geometric feasibility.
Enforces strict scientific criteria:
- Model training is BLOCKED unless genuine human architectural expert labels are present.
- Heuristic scores can NEVER be silently converted into expert training targets.
- Candidates violating hard constraints can NEVER enter the training set.
- Parcels/sites must have zero leakage across train, val, and test partitions.
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.components.gab_gen.dataset.schemas import (
    CandidateFeasibilityStatus,
    DatasetRecord,
    DatasetSanityReport,
    SiteGroupedDatasetSplit,
)
from app.components.gab_gen.dataset.dataset_builder import DatasetBuilder, FEATURE_KEYS


class TrainingReadinessStatus(str, Enum):
    READY_FOR_TRAINING = "READY_FOR_TRAINING"
    NOT_READY_FOR_TRAINING = "NOT_READY_FOR_TRAINING"


class TrainingReadinessReport(BaseModel):
    status: TrainingReadinessStatus
    can_train_research_model: bool
    reasons_blocked: List[str] = Field(default_factory=list)
    dataset_version: str = "1.0.0"
    feature_schema_version: str = "1.0.0"

    # Dataset provenance & statistics
    total_sites: int = 0
    total_candidates: int = 0
    total_feasible_candidates: int = 0
    total_labeled_candidates: int = 0
    unique_reviewers: List[str] = Field(default_factory=list)
    expert_rubric_version: Optional[str] = None
    target_score_definition: str = "expert_overall_quality_score (0.0 to 1.0, human architect assessed)"

    # Split integrity
    site_grouped_splits_valid: bool = False
    site_leakage_detected: bool = False
    leakage_details: List[str] = Field(default_factory=list)

    # Feature completeness
    feature_keys_verified: List[str] = Field(default_factory=list)
    nan_or_inf_detected: bool = False
    zero_variance_features: List[str] = Field(default_factory=list)

    # Warnings and actionable next steps
    actionable_next_steps: List[str] = Field(default_factory=list)


class TrainingReadinessGate:
    """
    Evaluates whether an empirical dataset meets scientific prerequisites for XGBoost training.
    """

    MINIMUM_INDEPENDENT_SITES: int = 20
    MINIMUM_LABELED_CANDIDATES: int = 60
    MINIMUM_INDEPENDENT_REVIEWERS: int = 2

    @classmethod
    def audit_dataset_readiness(
        cls,
        split: Optional[SiteGroupedDatasetSplit],
    ) -> TrainingReadinessReport:
        if split is None:
            return TrainingReadinessReport(
                status=TrainingReadinessStatus.NOT_READY_FOR_TRAINING,
                can_train_research_model=False,
                reasons_blocked=[
                    "No dataset split provided. Empirical dataset manifest is missing or empty."
                ],
                actionable_next_steps=[
                    "Assemble cadastral survey parcel samples and client design programs.",
                    "Generate feasible floor-plan candidate pools using GabGenService.",
                    "Obtain human architectural expert assessments with ExpertArchitecturalEvaluation.",
                ],
            )

        sanity: DatasetSanityReport = DatasetBuilder.audit_dataset_sanity(split)

        all_records = split.train_records + split.val_records + split.test_records
        reasons_blocked: List[str] = []

        # 1. Inspect Genuine Expert Labels
        labeled_records = [r for r in all_records if r.is_labeled and r.expert_evaluation is not None]
        reviewers = set(
            r.expert_evaluation.expert_id
            for r in labeled_records
            if r.expert_evaluation and r.expert_evaluation.expert_id
        )

        if len(labeled_records) == 0:
            reasons_blocked.append(
                "Zero expert-labeled candidates available. Synthetic or heuristic scores cannot substitute for human expert quality labels."
            )
        elif len(labeled_records) < cls.MINIMUM_LABELED_CANDIDATES:
            reasons_blocked.append(
                f"Insufficient labeled candidates ({len(labeled_records)} < {cls.MINIMUM_LABELED_CANDIDATES})."
            )

        if len(reviewers) < cls.MINIMUM_INDEPENDENT_REVIEWERS:
            reasons_blocked.append(
                f"Insufficient independent expert reviewers ({len(reviewers)} < {cls.MINIMUM_INDEPENDENT_REVIEWERS})."
            )

        # 2. Inspect Site Grouping and Independence
        if split.total_sites < cls.MINIMUM_INDEPENDENT_SITES:
            reasons_blocked.append(
                f"Insufficient independent site groups ({split.total_sites} < {cls.MINIMUM_INDEPENDENT_SITES}) for robust GroupKFold evaluation."
            )

        if sanity.site_leakage_detected:
            reasons_blocked.append(
                f"Site leakage detected between partitions: {sanity.leakage_details}"
            )

        # 3. Inspect Feasibility & Hard Constraints
        if sanity.infeasible_candidates_included > 0:
            reasons_blocked.append(
                f"{sanity.infeasible_candidates_included} infeasible/invalid candidates detected in dataset. Infeasible candidates must not enter the quality ranking pool."
            )

        # 4. Numerical Feature Health
        if sanity.nan_or_inf_detected:
            reasons_blocked.append("Non-finite values (NaN or Inf) found in feature matrix.")

        is_ready = len(reasons_blocked) == 0

        next_steps = []
        if not is_ready:
            next_steps.append("Maintain Phase 5 deterministic heuristic ranker in active runtime.")
            next_steps.append("Collect SLIA/chartered architectural expert evaluations for candidate pools.")
            next_steps.append("Rerun TrainingReadinessGate once authorized expert annotations are verified.")

        return TrainingReadinessReport(
            status=TrainingReadinessStatus.READY_FOR_TRAINING if is_ready else TrainingReadinessStatus.NOT_READY_FOR_TRAINING,
            can_train_research_model=is_ready,
            reasons_blocked=reasons_blocked,
            dataset_version=split.dataset_version,
            feature_schema_version=split.feature_schema_version,
            total_sites=split.total_sites,
            total_candidates=len(all_records),
            total_feasible_candidates=sum(
                1 for r in all_records
                if r.feasibility_status == CandidateFeasibilityStatus.FEASIBLE_VERIFIED_CONSTRAINTS
            ),
            total_labeled_candidates=len(labeled_records),
            unique_reviewers=sorted(list(reviewers)),
            expert_rubric_version="slia_5axis_rubric_v1.0" if labeled_records else None,
            site_grouped_splits_valid=not sanity.site_leakage_detected,
            site_leakage_detected=sanity.site_leakage_detected,
            leakage_details=sanity.leakage_details,
            feature_keys_verified=FEATURE_KEYS,
            nan_or_inf_detected=sanity.nan_or_inf_detected,
            zero_variance_features=sanity.zero_variance_features,
            actionable_next_steps=next_steps,
        )
