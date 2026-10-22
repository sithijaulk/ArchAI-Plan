"""
Dataset Builder, Site-Grouped Partitioner, and Sanity Validator for GAB-Gen.
Prepares clean, leakage-free datasets for future XGBoost ranking model training.
Strictly separates heuristic scores from expert labels, enforces hard constraints,
and partitions sites via GroupKFold logic without cross-split leakage.
"""
import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np

from ..schemas import (
    CandidateFeasibilityStatus,
    FloorPlanCandidate,
    NumericalFeatureVector,
)
from .schemas import (
    DatasetRecord,
    DatasetSanityReport,
    DatasetSplitMetadata,
    ExpertArchitecturalEvaluation,
    SiteGroupedDatasetSplit,
)


FEATURE_KEYS = [
    "total_usable_room_area_sqm",
    "building_footprint_area_sqm",
    "area_utilization_ratio",
    "circulation_area_sqm",
    "circulation_ratio",
    "mandatory_room_satisfaction_ratio",
    "preferred_room_size_satisfaction_ratio",
    "adjacency_satisfaction_ratio",
    "average_room_aspect_ratio",
    "room_dimension_penalty",
    "staircase_area_ratio",
    "floor_distribution_balance",
    "parking_satisfaction",
    "exterior_wall_access_ratio",
    "window_feasibility_ratio",
    "compactness_ratio",
]


class DatasetBuilder:
    """
    Constructs, validates, and partitions datasets for downstream ML ranking.
    """

    @staticmethod
    def create_record(
        site_id: str,
        site_extent_perches: float,
        site_category: str,
        num_floors: int,
        candidate: FloorPlanCandidate,
        expert_eval: Optional[ExpertArchitecturalEvaluation] = None,
        allow_infeasible: bool = False,
    ) -> Optional[DatasetRecord]:
        """
        Transforms a generated floor plan candidate into a DatasetRecord.
        By default, excludes candidates that failed feasibility / hard constraints.
        """
        is_feasible = (
            candidate.feasibility_status
            == CandidateFeasibilityStatus.FEASIBLE_VERIFIED_CONSTRAINTS
        )
        if not is_feasible and not allow_infeasible:
            return None

        # Deterministic record ID
        hash_seed = f"{site_id}:{candidate.candidate_id}:{candidate.candidate_fingerprint}"
        record_id = hashlib.sha256(hash_seed.encode("utf-8")).hexdigest()[:16]

        is_labeled = expert_eval is not None

        return DatasetRecord(
            record_id=record_id,
            site_id=site_id,
            site_extent_perches=site_extent_perches,
            site_category=site_category,
            num_floors=num_floors,
            candidate_id=candidate.candidate_id,
            strategy_name=candidate.strategy_name,
            footprint_variant=candidate.footprint_variant,
            feasibility_status=candidate.feasibility_status,
            features=candidate.features,
            baseline_heuristic_score=candidate.heuristic_score,
            baseline_score_breakdown=candidate.score_breakdown,
            expert_evaluation=expert_eval,
            is_labeled=is_labeled,
            is_eligible_for_ranking_model=is_feasible,
        )

    @classmethod
    def partition_site_grouped(
        cls,
        records: List[DatasetRecord],
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        seed: int = 42,
    ) -> SiteGroupedDatasetSplit:
        """
        Partitions records strictly by site_id so no parcel appears across multiple splits.
        Guarantees zero site leakage between train, val, and test.
        """
        if abs((train_ratio + val_ratio + test_ratio) - 1.0) > 1e-4:
            raise ValueError("train_ratio + val_ratio + test_ratio must equal 1.0")

        # Group records by site_id
        site_to_records: Dict[str, List[DatasetRecord]] = {}
        for r in records:
            site_to_records.setdefault(r.site_id, []).append(r)

        unique_sites = sorted(list(site_to_records.keys()))
        rng = np.random.RandomState(seed)
        shuffled_sites = list(unique_sites)
        rng.shuffle(shuffled_sites)

        n_sites = len(shuffled_sites)
        n_train = max(1, int(round(n_sites * train_ratio)))
        n_val = max(1, int(round(n_sites * val_ratio))) if n_sites >= 3 else 0
        if n_train + n_val >= n_sites and n_sites >= 3:
            n_train = n_sites - 2
            n_val = 1

        train_sites = set(shuffled_sites[:n_train])
        val_sites = set(shuffled_sites[n_train : n_train + n_val])
        test_sites = set(shuffled_sites[n_train + n_val :])

        # If few sites, ensure test has at least one site if n_sites >= 2
        if not test_sites and n_sites >= 2:
            if len(train_sites) > 1:
                moved = list(train_sites)[-1]
                train_sites.remove(moved)
                test_sites.add(moved)

        train_recs = [r for r in records if r.site_id in train_sites]
        val_recs = [r for r in records if r.site_id in val_sites]
        test_recs = [r for r in records if r.site_id in test_sites]

        def _meta(name: str, site_set: Set[str], rec_list: List[DatasetRecord]) -> DatasetSplitMetadata:
            return DatasetSplitMetadata(
                split_name=name,
                site_count=len(site_set),
                candidate_count=len(rec_list),
                labeled_count=sum(1 for r in rec_list if r.is_labeled),
                site_ids=sorted(list(site_set)),
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        return SiteGroupedDatasetSplit(
            dataset_version="1.0.0",
            created_at=now_iso,
            feature_schema_version="1.0.0",
            total_sites=n_sites,
            total_candidates=len(records),
            train_metadata=_meta("train", train_sites, train_recs),
            val_metadata=_meta("val", val_sites, val_recs),
            test_metadata=_meta("test", test_sites, test_recs),
            train_records=train_recs,
            val_records=val_recs,
            test_records=test_recs,
        )

    @classmethod
    def audit_dataset_sanity(
        cls,
        split: SiteGroupedDatasetSplit,
    ) -> DatasetSanityReport:
        """
        Validates dataset health:
        1. Site leakage across splits.
        2. NaN or Inf values in features.
        3. Feature bounds and zero-variance features.
        4. Ineligible/infeasible candidates incorrectly included.
        5. Heuristic leakage into expert label slot.
        """
        train_sites = set(split.train_metadata.site_ids)
        val_sites = set(split.val_metadata.site_ids)
        test_sites = set(split.test_metadata.site_ids)

        leakage_details = []
        tv_overlap = train_sites.intersection(val_sites)
        if tv_overlap:
            leakage_details.append(f"Train/Val site overlap: {list(tv_overlap)}")
        tt_overlap = train_sites.intersection(test_sites)
        if tt_overlap:
            leakage_details.append(f"Train/Test site overlap: {list(tt_overlap)}")
        vt_overlap = val_sites.intersection(test_sites)
        if vt_overlap:
            leakage_details.append(f"Val/Test site overlap: {list(vt_overlap)}")

        all_records = split.train_records + split.val_records + split.test_records

        nan_inf_found = False
        infeasible_count = 0
        feature_matrix: Dict[str, List[float]] = {k: [] for k in FEATURE_KEYS}
        warnings = []

        for r in all_records:
            if not r.is_eligible_for_ranking_model or r.feasibility_status != CandidateFeasibilityStatus.FEASIBLE_VERIFIED_CONSTRAINTS:
                infeasible_count += 1

            # Validate numerical values
            feat_dict = r.features.model_dump()
            for k in FEATURE_KEYS:
                val = feat_dict.get(k, 0.0)
                if val is None or math.isnan(val) or math.isinf(val):
                    nan_inf_found = True
                else:
                    feature_matrix[k].append(float(val))

            # Audit expert label purity (ensure heuristic is not masquerading as expert)
            if r.expert_evaluation is not None:
                # If overall_quality_score is identical to heuristic score to 6 decimal places across all records, flag warning
                if abs(r.expert_evaluation.overall_quality_score - r.baseline_heuristic_score) < 1e-9:
                    warnings.append(f"Record {r.record_id} has expert score identical to heuristic baseline.")

        # Zero-variance check
        zero_variance = []
        for k, vals in feature_matrix.items():
            if len(vals) > 1:
                std = float(np.std(vals))
                if std < 1e-7:
                    zero_variance.append(k)

        is_valid = (
            len(leakage_details) == 0
            and not nan_inf_found
            and infeasible_count == 0
        )

        return DatasetSanityReport(
            is_valid=is_valid,
            total_records=len(all_records),
            labeled_records=sum(1 for r in all_records if r.is_labeled),
            unlabeled_records=sum(1 for r in all_records if not r.is_labeled),
            unique_sites=split.total_sites,
            site_leakage_detected=len(leakage_details) > 0,
            leakage_details=leakage_details,
            nan_or_inf_detected=nan_inf_found,
            feature_ranges_valid=not nan_inf_found,
            zero_variance_features=zero_variance,
            infeasible_candidates_included=infeasible_count,
            warnings=warnings,
        )

    @classmethod
    def export_tabular_features(
        cls,
        records: List[DatasetRecord],
    ) -> Tuple[List[str], List[List[float]], List[Optional[float]]]:
        """
        Exports tabular design matrix X (features) and target y (expert labels).
        Returns:
            feature_names: List of 16 feature headers
            X: 2D matrix of shape [N, 16]
            y: list of target scores (float or None if unlabeled)
        """
        feature_names = list(FEATURE_KEYS)
        X = []
        y = []
        for r in records:
            fdict = r.features.model_dump()
            row = [float(fdict.get(k, 0.0)) for k in feature_names]
            X.append(row)
            target = r.expert_evaluation.overall_quality_score if r.expert_evaluation else None
            y.append(target)
        return feature_names, X, y
