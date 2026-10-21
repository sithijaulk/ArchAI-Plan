"""
Multi-Candidate Blueprint Generation Orchestrator.
Generates, validates, deduplicates, features, scores, and ranks candidate floor plans.
Preserves Phase 2 multi-state regulatory compliance and Phase 3 survey provenance.
"""
from typing import Any, Dict, List, Optional, Tuple
from shapely.geometry import Polygon

from ..schemas import (
    ManualSurveyExtractionRequest,
    ClientRequirementsInput,
    RegulatoryRule,
    FloorPlanDefinition,
    FloorPlanCandidate,
    CandidateFeasibilityStatus,
    CandidateRejectionReason,
    CandidateGenerationConfig,
    Point2D,
    PreferenceEvaluationStatus,
)
from .candidate_generator import (
    generate_footprint_variants,
    generate_candidate_floors,
)
from .roof_generator import generate_roof_geometry
from ..validation.validator import validate_gab_geometry
from ..validation.preference_evaluator import evaluate_architectural_preferences
from ..validation.feature_extractor import extract_candidate_features
from ..validation.similarity_detector import compute_candidate_fingerprint, deduplicate_candidate_pool
from ..validation.heuristic_scorer import rank_candidates


def generate_multi_candidates(
    shapely_land: Polygon,
    shapely_buildable: Polygon,
    survey_request: ManualSurveyExtractionRequest,
    requirements: ClientRequirementsInput,
    rules: List[RegulatoryRule],
    allocation_res: Dict[str, Any],
    closure_error: float,
    area_check: Dict[str, Any],
    reg_resolution: Optional[Any] = None,
    config: Optional[CandidateGenerationConfig] = None
) -> Tuple[List[FloorPlanCandidate], List[FloorPlanCandidate]]:
    """
    Executes bounded multi-candidate generation.
    Returns:
      (feasible_ranked_candidates, rejected_candidates)
    """
    cfg = config or CandidateGenerationConfig()
    requested_count = cfg.requested_candidate_count
    max_attempts = cfg.max_generation_attempts

    # Step 1: Generate Footprint Variants
    footprint_variants = generate_footprint_variants(shapely_buildable, max_variants=4)

    # Step 2: Define systematic architectural variation strategies
    # Bounded exploration matrix: footprint x room_order x slice_mode x stair_corner
    strategies = [
        {"name": "conformal_standard", "footprint_idx": 0, "slice_mode": "auto", "stair": "south_west", "reverse": False},
        {"name": "compact_zoning", "footprint_idx": 1 if len(footprint_variants) > 1 else 0, "slice_mode": "x_first", "stair": "south_east", "reverse": False},
        {"name": "rear_private_cluster", "footprint_idx": 0, "slice_mode": "y_first", "stair": "south_west", "reverse": True},
        {"name": "winged_courtyard", "footprint_idx": 2 if len(footprint_variants) > 2 else 0, "slice_mode": "auto", "stair": "north_west", "reverse": False},
        {"name": "frontage_oriented", "footprint_idx": 3 if len(footprint_variants) > 3 else (1 if len(footprint_variants) > 1 else 0), "slice_mode": "x_first", "stair": "south_west", "reverse": True},
        {"name": "alternative_linear_circulation", "footprint_idx": 0, "slice_mode": "y_first", "stair": "south_east", "reverse": False},
    ]

    all_generated: List[FloorPlanCandidate] = []
    rejected_pool: List[FloorPlanCandidate] = []
    attempts = 0

    site_restrictions = requirements.regulatory_context.site_restrictions if requirements.regulatory_context else []
    base_floor_allocs = allocation_res.get("floors", [])

    for strat in strategies:
        if attempts >= max_attempts:
            break
        attempts += 1

        f_idx = strat["footprint_idx"]
        footprint_name, footprint_poly = footprint_variants[f_idx]

        # Generate Floor Plans for this candidate
        cand_floors = generate_candidate_floors(
            footprint_poly=footprint_poly,
            floor_allocations=base_floor_allocs,
            strategy_name=strat["name"],
            stair_corner=strat["stair"],
            slice_mode=strat["slice_mode"],
            reverse_room_order=strat["reverse"]
        )

        if not cand_floors or all(len(f.rooms) == 0 for f in cand_floors):
            continue

        # Validate geometry, containment, regulations, room overlaps, and stairs
        val = validate_gab_geometry(
            land_poly=shapely_land,
            buildable_poly=footprint_poly,
            closure_error=closure_error,
            area_check=area_check,
            floors=cand_floors,
            expected_storey_count=requirements.storey_count,
            rules=rules,
            regulatory_resolution=reg_resolution,
            site_restrictions=site_restrictions
        )

        # Evaluate architectural preferences
        pref_results = evaluate_architectural_preferences(
            requirements=requirements,
            floors=cand_floors,
            survey_request=survey_request,
            buildable_poly=footprint_poly
        )
        val.preference_evaluations = pref_results

        # Evaluate hard constraint feasibility
        rejection_reasons: List[CandidateRejectionReason] = []

        if not val.valid:
            for v in val.violations:
                rejection_reasons.append(CandidateRejectionReason(code="GEOMETRY_OR_REGULATORY_VIOLATION", message=v))

        failed_hard_prefs = [
            p for p in pref_results
            if p.is_hard_constraint and p.status in (PreferenceEvaluationStatus.NOT_SATISFIED, PreferenceEvaluationStatus.NOT_EVALUABLE)
        ]
        if failed_hard_prefs:
            for hp in failed_hard_prefs:
                rejection_reasons.append(
                    CandidateRejectionReason(
                        code="HARD_ARCHITECTURAL_PREFERENCE_FAILED",
                        requirement_id=hp.preference_id,
                        message=f"{hp.preference_id}: {hp.explanation}"
                    )
                )

        # Candidate Feasibility Classification
        if rejection_reasons:
            status = CandidateFeasibilityStatus.INFEASIBLE
        else:
            # Check for regulatory uncertainty
            if val.regulatory_status in ("unverified", "incomplete", "research_test") or (
                reg_resolution and reg_resolution.authority_verification_status != "verified"
            ):
                status = CandidateFeasibilityStatus.FEASIBLE_WITH_REGULATORY_UNCERTAINTY
            else:
                status = CandidateFeasibilityStatus.FEASIBLE_VERIFIED_CONSTRAINTS

        # Fingerprint & Footprint Points
        fingerprint = compute_candidate_fingerprint(footprint_poly, cand_floors)
        fp_coords = [Point2D(x=round(c[0], 3), y=round(c[1], 3)) for c in list(footprint_poly.exterior.coords)[:-1]]

        # Roof geometry
        roof_geom = generate_roof_geometry(
            building_footprint_poly=footprint_poly,
            roof_pref=requirements.roof_preference
        )

        # Features
        features = extract_candidate_features(
            floors=cand_floors,
            requirements=requirements,
            footprint_poly=footprint_poly,
            preference_evaluations=pref_results
        )

        unmet = [
            p.explanation for p in pref_results
            if not p.is_hard_constraint and p.status in (PreferenceEvaluationStatus.NOT_SATISFIED, PreferenceEvaluationStatus.NOT_EVALUABLE)
        ]

        candidate = FloorPlanCandidate(
            candidate_id=f"FP_CANDIDATE_{attempts:03d}",
            candidate_fingerprint=fingerprint,
            display_name=f"Alternative {attempts}: {strat['name'].replace('_', ' ').title()}",
            rank=attempts,
            heuristic_score=0.0,
            feasibility_status=status,
            rejection_reasons=rejection_reasons,
            strategy_name=strat["name"],
            footprint_variant=footprint_name,
            building_footprint_polygon=fp_coords,
            building_footprint_area_sqm=round(float(footprint_poly.area), 2),
            floors=cand_floors,
            roof_geometry=roof_geom,
            validation=val,
            preference_evaluations=pref_results,
            features=features,
            unmet_preferences=unmet,
            regulatory_verification_status=val.regulatory_status or "unverified"
        )

        if status == CandidateFeasibilityStatus.INFEASIBLE:
            rejected_pool.append(candidate)
        else:
            all_generated.append(candidate)

    # Step 3: Deduplication
    unique_feasible = deduplicate_candidate_pool(all_generated, min_diversity=cfg.minimum_layout_diversity)

    # Step 4: Deterministic Heuristic Ranking
    ranked_feasible = rank_candidates(unique_feasible)

    # Re-assign stable, clean IDs and ranks
    for idx, c in enumerate(ranked_feasible, start=1):
        c.rank = idx
        c.candidate_id = f"FP_CANDIDATE_{idx:03d}"
        c.display_name = f"Layout Option {idx} ({c.strategy_name.replace('_', ' ').title()})"

    # Return at most requested_count feasible candidates
    return ranked_feasible[:requested_count], rejected_pool
