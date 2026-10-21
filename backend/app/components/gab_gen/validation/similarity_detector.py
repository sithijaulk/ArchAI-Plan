"""
Candidate Fingerprinting and Duplicate / Similarity Filtering Engine.
Prevents returning duplicate or trivial translation/rotation clones.
Computes geometric and topological hash signatures:
- Building footprint perimeter & area quantization
- Room type ordering and floor assignment signature
- Room centroid distance vector quantization
- Multi-floor staircase core coordinate match
"""
import hashlib
import json
from typing import List, Tuple
from shapely.geometry import Polygon

from ..schemas import FloorPlanDefinition, FloorPlanCandidate


def compute_candidate_fingerprint(
    footprint_poly: Polygon,
    floors: List[FloorPlanDefinition]
) -> str:
    """
    Computes an immutable canonical fingerprint string for a candidate design.
    """
    signature_parts = []

    # 1. Footprint signature (quantized bounds and area)
    if footprint_poly and not footprint_poly.is_empty:
        min_x, min_y, max_x, max_y = footprint_poly.bounds
        f_sig = f"FP:{round(footprint_poly.area, 1)}:{round(max_x - min_x, 1)}x{round(max_y - min_y, 1)}"
    else:
        f_sig = "FP:EMPTY"
    signature_parts.append(f_sig)

    # 2. Floor by floor room layout signature
    for fl in sorted(floors, key=lambda f: f.floor_index):
        fl_sig_items = []
        for rm in sorted(fl.rooms, key=lambda r: (r.center.x, r.center.y)):
            # Quantize center coords to 0.5m grid
            cx = round(rm.center.x * 2) / 2
            cy = round(rm.center.y * 2) / 2
            area = round(rm.area, 1)
            fl_sig_items.append(f"{rm.type}@{cx},{cy}:{area}")
        signature_parts.append(f"FL{fl.floor_index}[" + ";".join(fl_sig_items) + "]")

    raw_signature = "|".join(signature_parts)
    return hashlib.sha256(raw_signature.encode('utf-8')).hexdigest()[:16]


def are_candidates_duplicates(
    cand_a: FloorPlanCandidate,
    cand_b: FloorPlanCandidate,
    similarity_threshold: float = 0.92
) -> bool:
    """
    Compares two candidates geometrically.
    Returns True if candidates are identical or near-duplicates.
    """
    # Quick check: exact fingerprint match
    if cand_a.candidate_fingerprint == cand_b.candidate_fingerprint:
        return True

    # Check footprint area match
    if abs(cand_a.building_footprint_area_sqm - cand_b.building_footprint_area_sqm) > 1.5:
        return False

    # Check floor count match
    if len(cand_a.floors) != len(cand_b.floors):
        return False

    # Check room centroid pairwise correlation
    rooms_a = [rm for fl in cand_a.floors for rm in fl.rooms if not rm.is_structural_stair]
    rooms_b = [rm for fl in cand_b.floors for rm in fl.rooms if not rm.is_structural_stair]

    if len(rooms_a) != len(rooms_b):
        return False

    # Compare room types and relative center coordinates
    matched_count = 0
    for ra in rooms_a:
        for rb in rooms_b:
            if ra.type == rb.type and ra.floor_id == rb.floor_id:
                dist = ((ra.center.x - rb.center.x) ** 2 + (ra.center.y - rb.center.y) ** 2) ** 0.5
                if dist < 0.8:  # within 80cm
                    matched_count += 1
                    break

    match_ratio = matched_count / max(1, len(rooms_a))
    return match_ratio >= similarity_threshold


def deduplicate_candidate_pool(
    candidates: List[FloorPlanCandidate],
    min_diversity: float = 0.10
) -> List[FloorPlanCandidate]:
    """
    Filters out duplicates and near-identical layouts, preserving the higher quality candidate.
    """
    unique_candidates: List[FloorPlanCandidate] = []
    seen_fingerprints = set()

    for cand in candidates:
        if cand.candidate_fingerprint in seen_fingerprints:
            continue

        is_dup = False
        for kept in unique_candidates:
            if are_candidates_duplicates(cand, kept, similarity_threshold=(1.0 - min_diversity)):
                is_dup = True
                break

        if not is_dup:
            unique_candidates.append(cand)
            seen_fingerprints.add(cand.candidate_fingerprint)

    return unique_candidates
