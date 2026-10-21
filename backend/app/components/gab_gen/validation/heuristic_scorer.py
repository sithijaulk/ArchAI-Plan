"""
Deterministic Heuristic Scorer and Candidate Ranking.
Calculates explainable, multi-dimensional score for feasible candidates based on:
1. Space Utilization (w=0.25)
2. Circulation Efficiency (w=0.15)
3. Room Dimension Suitability & Aspect Ratios (w=0.15)
4. Adjacency Satisfaction (w=0.20)
5. Preference Satisfaction (w=0.15)
6. Compactness & Envelope Efficiency (w=0.10)
Total Score is bounded strictly in [0.0, 1.0].
Tie-breaking is deterministic using candidate fingerprint.
"""
from typing import Dict, List, Tuple
from ..schemas import (
    FloorPlanCandidate,
    HeuristicScoreBreakdown,
    CandidateFeasibilityStatus,
)


# Configurable baseline weights summing to 1.0
DEFAULT_SCORING_WEIGHTS = {
    "space_utilization": 0.25,
    "circulation_efficiency": 0.15,
    "room_suitability": 0.15,
    "adjacency_satisfaction": 0.20,
    "preference_satisfaction": 0.15,
    "compactness": 0.10,
}


def score_candidate(
    candidate: FloorPlanCandidate,
    weights: Dict[str, float] = None
) -> Tuple[float, HeuristicScoreBreakdown]:
    """
    Computes an explainable heuristic score and dimension breakdown.
    Does NOT allow score to override hard constraint failures.
    """
    w = weights or DEFAULT_SCORING_WEIGHTS
    feats = candidate.features

    # 1. Space Utilization Score (favors 70%-90% utilization)
    util = feats.area_utilization_ratio
    if 0.70 <= util <= 0.90:
        s_util = 1.0
    elif util < 0.70:
        s_util = max(0.0, util / 0.70)
    else:
        # Penalize over-crowded / zero-margin allocations
        s_util = max(0.5, 1.0 - (util - 0.90) * 3.0)

    # 2. Circulation Efficiency Score (favors 10%-20% circulation buffer)
    circ = feats.circulation_ratio
    if 0.08 <= circ <= 0.22:
        s_circ = 1.0
    elif circ < 0.08:
        s_circ = max(0.4, circ / 0.08)
    else:
        s_circ = max(0.0, 1.0 - (circ - 0.22) * 2.5)

    # 3. Room Suitability Score (penalizes extreme aspect ratios)
    s_room = max(0.0, min(1.0, 1.0 - feats.room_dimension_penalty))

    # 4. Adjacency Satisfaction Score
    s_adj = feats.adjacency_satisfaction_ratio

    # 5. User Preference Satisfaction Score (combines mandatory, preferred dimensions & parking)
    s_pref = (
        feats.mandatory_room_satisfaction_ratio * 0.4 +
        feats.preferred_room_size_satisfaction_ratio * 0.3 +
        feats.parking_satisfaction * 0.3
    )

    # 6. Compactness Score
    s_comp = feats.compactness_ratio

    breakdown = HeuristicScoreBreakdown(
        space_utilization=round(s_util, 3),
        circulation_efficiency=round(s_circ, 3),
        room_suitability=round(s_room, 3),
        adjacency_satisfaction=round(s_adj, 3),
        preference_satisfaction=round(s_pref, 3),
        staircase_efficiency=round(1.0 - feats.staircase_area_ratio, 3),
        compactness=round(s_comp, 3),
    )

    total_score = (
        w.get("space_utilization", 0.25) * s_util +
        w.get("circulation_efficiency", 0.15) * s_circ +
        w.get("room_suitability", 0.15) * s_room +
        w.get("adjacency_satisfaction", 0.20) * s_adj +
        w.get("preference_satisfaction", 0.15) * s_pref +
        w.get("compactness", 0.10) * s_comp
    )

    bounded_score = round(max(0.0, min(1.0, total_score)), 3)
    return bounded_score, breakdown


def rank_candidates(
    candidates: List[FloorPlanCandidate],
    weights: Dict[str, float] = None
) -> List[FloorPlanCandidate]:
    """
    Ranks feasible candidates in descending order of heuristic score with deterministic tie-breaking.
    Infeasible candidates are never ranked as valid selectable options.
    """
    feasible_cands = [
        c for c in candidates
        if c.feasibility_status in (
            CandidateFeasibilityStatus.FEASIBLE_VERIFIED_CONSTRAINTS,
            CandidateFeasibilityStatus.FEASIBLE_WITH_REGULATORY_UNCERTAINTY
        )
    ]

    for cand in feasible_cands:
        score, breakdown = score_candidate(cand, weights)
        cand.heuristic_score = score
        cand.score_breakdown = breakdown

    # Sort descending by heuristic_score, then fingerprint for stable deterministic tie-breaking
    feasible_cands.sort(key=lambda c: (c.heuristic_score, c.candidate_fingerprint), reverse=True)

    for rank_idx, cand in enumerate(feasible_cands, start=1):
        cand.rank = rank_idx

    return feasible_cands
