"""
Phase 10.1: Floor-Plan Dataset Pipeline, Candidate Generation, and Feature Extraction.
Generates research candidate pools from configurable site and requirements scenarios,
validates hard architectural constraints, deduplicates geometry fingerprints,
extracts the standardized 16D numerical feature vector, and prepares site-grouped splits.
"""
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from app.components.gab_gen.service import GabGenService
from app.components.gab_gen.schemas import (
    ManualSurveyExtractionRequest,
    ClientRequirementsInput,
    CandidateFeasibilityStatus,
    FloorPlanCandidate,
    SurveyEdgeInput,
    DistanceValue,
    BearingValue,
    DistanceUnit,
    SurveyVerificationStatus,
    SurveySource,
    RegulatoryContextInput,
)
from app.components.gab_gen.dataset.schemas import (
    DatasetRecord,
    SiteGroupedDatasetSplit,
)
from app.components.gab_gen.dataset.dataset_builder import (
    DatasetBuilder,
    FEATURE_KEYS,
)
from app.components.gab_gen.dataset.benchmark_scenarios import EXPANDED_SURVEY_BENCHMARK_SCENARIOS


class ResearchCandidatePipeline:
    def __init__(self):
        self.service = GabGenService()

    def generate_candidates_for_scenarios(
        self,
        scenarios: Optional[List[Dict[str, Any]]] = None,
        max_scenarios: Optional[int] = None,
    ) -> Tuple[List[DatasetRecord], Dict[str, Any]]:
        target_scenarios = scenarios or EXPANDED_SURVEY_BENCHMARK_SCENARIOS
        if max_scenarios:
            target_scenarios = target_scenarios[:max_scenarios]

        all_records: List[DatasetRecord] = []
        seen_fingerprints = set()

        stats = {
            "total_scenarios_evaluated": len(target_scenarios),
            "total_raw_candidates_generated": 0,
            "feasible_candidates": 0,
            "infeasible_candidates_excluded": 0,
            "duplicate_fingerprints_excluded": 0,
            "records_created": 0,
        }

        for sc in target_scenarios:
            site_id = sc["site_id"]
            site_cat = sc.get("category", "regular_suburban")
            extent = sc.get("extent_perches", 10.0)

            edges = []
            for e in sc["edges"]:
                edges.append(SurveyEdgeInput(
                    edge_id=e["edge_id"],
                    distance=DistanceValue(value=e["distance_m"], unit=DistanceUnit.METERS),
                    bearing=BearingValue(raw=f"{e['bearing_deg']} deg", normalized_degrees=e["bearing_deg"]),
                    edge_type=e.get("edge_type"),
                    source=SurveySource.MANUAL,
                    distance_origin="fixture",
                    bearing_origin="fixture",
                    verification_status="user_verified",
                ))

            survey_req = ManualSurveyExtractionRequest(
                north_angle=sc.get("true_north_angle", 0.0),
                reference_edge=edges[0].edge_id,
                source=SurveySource.MANUAL,
                edges=edges,
                verified_by_user=True,
                verification_status=SurveyVerificationStatus.USER_VERIFIED,
            )

            req_input = ClientRequirementsInput(
                declared_land_extent=extent,
                declared_land_unit="perches",
                building_type="residential_house",
                storey_count=sc.get("storey_count", 1),
                occupant_count=sc.get("occupant_count", 4),
                separate_kitchen=True,
                parking_capacity=sc.get("parking_capacity", 1),
                attached_bathroom_count=1,
                roof_preference={
                    "roof_type": sc.get("roof_type", "flat_slab"),
                    "material": "concrete_tile",
                    "pitch_angle_deg": 25.0 if sc.get("roof_type") in ("gable", "hip") else 0.0,
                    "overhang_m": 0.6,
                    "parapet_height_m": 1.0,
                    "rooftop_access": sc.get("roof_type") == "flat_slab",
                    "drainage_preference": "concealed_gutters",
                },
                regulatory_context=RegulatoryContextInput(
                    jurisdiction_id="sri_lanka_uda_standard",
                    authority_id="LK-11-CMC",
                    zone_confirmed=True,
                ),
            )

            try:
                run_out = self.service.run_pipeline(
                    project_id=f"proj_{site_id}",
                    project_name=f"Research Benchmark {site_id}",
                    survey_request=survey_req,
                    requirements=req_input,
                    allow_research_test=True,
                )
            except Exception as e:
                continue

            candidates = run_out.candidates or []
            stats["total_raw_candidates_generated"] += len(candidates)

            for cand in candidates:
                if cand.feasibility_status not in (CandidateFeasibilityStatus.FEASIBLE_VERIFIED_CONSTRAINTS, CandidateFeasibilityStatus.FEASIBLE_WITH_REGULATORY_UNCERTAINTY):
                    stats["infeasible_candidates_excluded"] += 1
                    continue

                stats["feasible_candidates"] += 1

                fp = cand.candidate_fingerprint
                if fp in seen_fingerprints:
                    stats["duplicate_fingerprints_excluded"] += 1
                    continue
                seen_fingerprints.add(fp)

                record = DatasetBuilder.create_record(
                    site_id=site_id,
                    site_extent_perches=extent,
                    site_category=site_cat,
                    num_floors=len(cand.floors),
                    candidate=cand,
                    expert_eval=None,
                    allow_infeasible=True,
                )

                if record:
                    all_records.append(record)
                    stats["records_created"] += 1

        return all_records, stats
