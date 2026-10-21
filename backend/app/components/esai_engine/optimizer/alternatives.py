"""
ESAI Layout Alternatives Selector
Deduplicates and ranks distinct valid layouts generated during evolutionary optimization.
"""
import math
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from .chromosome import PlacedAssetDTO
from .fitness import FitnessBreakdownDTO


class LayoutAlternativeDTO(BaseModel):
    alternative_index: int
    fitness_score: float
    placed_assets: List[PlacedAssetDTO]
    fitness_breakdown: FitnessBreakdownDTO
    distinctness_score: float = 1.0


class LayoutAlternativeSelector:
    """
    Selects top unique, hard-constraint-valid design alternatives.
    """

    DUPLICATE_DISTANCE_THRESHOLD = 0.25  # meters
    DUPLICATE_ROTATION_THRESHOLD = 15.0  # degrees

    def select_alternatives(
        self,
        archive: List[Tuple[List[float], float, List[PlacedAssetDTO], FitnessBreakdownDTO]],
        target_count: int = 2,
    ) -> List[LayoutAlternativeDTO]:
        """
        Filters candidates for strict hard-constraint validity, removes duplicates, and ranks by fitness.
        """
        # 1. Filter only valid candidates that passed all hard constraints
        valid_candidates = [entry for entry in archive if entry[3].is_hard_constraint_valid]
        if not valid_candidates:
            return []

        # 2. Sort descending by fitness score
        valid_candidates.sort(key=lambda x: x[1], reverse=True)

        selected: List[LayoutAlternativeDTO] = []
        alt_idx = 1

        for sol_vector, fit_score, placed, fb in valid_candidates:
            # Check if duplicate of already selected alternatives
            is_dup = False
            min_dist_diff = 999.0
            for existing in selected:
                diff = self._compute_layout_difference(placed, existing.placed_assets)
                min_dist_diff = min(min_dist_diff, diff)
                if diff < self.DUPLICATE_DISTANCE_THRESHOLD:
                    is_dup = True
                    break

            if not is_dup:
                selected.append(
                    LayoutAlternativeDTO(
                        alternative_index=alt_idx,
                        fitness_score=round(fit_score, 4),
                        placed_assets=placed,
                        fitness_breakdown=fb,
                        distinctness_score=round(min(1.0, min_dist_diff), 3),
                    )
                )
                alt_idx += 1
                if len(selected) >= target_count:
                    break

        return selected

    def _compute_layout_difference(
        self,
        layout_a: List[PlacedAssetDTO],
        layout_b: List[PlacedAssetDTO],
    ) -> float:
        """
        Computes the average Euclidean distance between corresponding asset positions.
        """
        map_b = {item.instance_id: item for item in layout_b}
        dist_sum = 0.0
        count = 0

        for a in layout_a:
            b = map_b.get(a.instance_id)
            if b:
                d = math.hypot(a.position.x - b.position.x, a.position.y - b.position.y)
                # Rotation penalty if orientation changed
                rot_diff = abs((a.rotation_deg - b.rotation_deg + 180) % 360 - 180)
                if rot_diff > self.DUPLICATE_ROTATION_THRESHOLD:
                    d += 0.5  # Count rotation difference as substantial distinctness
                dist_sum += d
                count += 1

        return (dist_sum / count) if count > 0 else 0.0
