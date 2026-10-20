"""
ESAI Functional Relationship & Preference Evaluator
Measures inter-furniture operational distances (e.g., Bed <-> Nightstand, Sofa <-> TV)
and evaluates client preference satisfaction (preferred walls, zones, orientations).
"""
import math
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from shapely.geometry import Point, Polygon

from ..contracts import (
    Coordinate2D,
    ResolvedFunctionalRelationshipDTO,
)
from .chromosome import PlacedAssetDTO


class FunctionalEvaluationResult(BaseModel):
    is_valid: bool = True
    violations: List[str] = Field(default_factory=list)
    relationship_score: float = 1.0
    preference_score: float = 1.0
    details: List[Dict[str, Any]] = Field(default_factory=list)


class FunctionalConstraintEvaluator:
    """
    Evaluates operational relationships and client preference adherence.
    """

    def __init__(
        self,
        relationships: List[ResolvedFunctionalRelationshipDTO],
        room_polygon: Polygon,
    ):
        self.relationships = relationships
        self.room_polygon = room_polygon

    def evaluate(self, placed_assets: List[PlacedAssetDTO]) -> FunctionalEvaluationResult:
        """
        Calculates functional distance scores and verifies preference satisfaction.
        """
        violations: List[str] = []
        details: List[Dict[str, Any]] = []

        # Index assets by category and subtype
        category_map: Dict[str, List[PlacedAssetDTO]] = {}
        for a in placed_assets:
            category_map.setdefault(a.category.lower().strip(), []).append(a)
            category_map.setdefault(a.subtype.lower().strip(), []).append(a)

        # 1. Functional Relationship Evaluation
        rel_scores: List[float] = []
        for rel in self.relationships:
            from_assets = category_map.get(rel.from_category.lower().strip(), [])
            to_assets = category_map.get(rel.to_category.lower().strip(), [])

            if not from_assets or not to_assets:
                continue

            # Evaluate distance between closest pair
            for fa in from_assets:
                # Find closest to_asset
                best_dist = 999.0
                best_ta = None
                for ta in to_assets:
                    if fa.instance_id == ta.instance_id:
                        continue
                    if fa.footprint_polygon is not None and ta.footprint_polygon is not None:
                        dist = float(fa.footprint_polygon.distance(ta.footprint_polygon))
                    else:
                        dist = math.hypot(fa.position.x - ta.position.x, fa.position.y - ta.position.y)
                    if dist < best_dist:
                        best_dist = dist
                        best_ta = ta

                if best_ta is None:
                    continue

                min_d = rel.min_distance_m or 0.2
                max_d = rel.max_distance_m or 4.0
                opt_d = rel.optimal_distance_m or ((min_d + max_d) / 2.0)

                # Score curve: 1.0 at optimal, drops toward min and max
                if min_d <= best_dist <= max_d:
                    # Normalized proximity score
                    delta = abs(best_dist - opt_d)
                    span = max(0.1, (max_d - min_d) / 2.0)
                    pair_score = max(0.0, 1.0 - (delta / span) * 0.5)
                    rel_scores.append(pair_score)
                    details.append({
                        "relation": rel.relation_id,
                        "from": fa.asset_name,
                        "to": best_ta.asset_name,
                        "distance_m": round(best_dist, 2),
                        "optimal_m": opt_d,
                        "status": "satisfactory",
                    })
                else:
                    pair_score = max(0.0, 1.0 - min(2.0, abs(best_dist - opt_d)) * 0.4)
                    rel_scores.append(pair_score)
                    details.append({
                        "relation": rel.relation_id,
                        "from": fa.asset_name,
                        "to": best_ta.asset_name,
                        "distance_m": round(best_dist, 2),
                        "optimal_m": opt_d,
                        "status": "suboptimal",
                    })

                    if rel.is_hard_constraint:
                        violations.append(
                            f"Hard Functional Constraint Violation: Distance between {fa.asset_name} and {best_ta.asset_name} is {best_dist:.2f}m (allowed: {min_d}m - {max_d}m)."
                        )

        relationship_score = (sum(rel_scores) / len(rel_scores)) if rel_scores else 1.0

        # 2. Preference Satisfaction Evaluation
        pref_scores: List[float] = []
        for a in placed_assets:
            # Preferred Wall Check
            if a.preferred_wall:
                pw = a.preferred_wall.lower().strip()
                min_x, min_y, max_x, max_y = self.room_polygon.bounds
                # Test which compass wall asset is closest to
                dist_to_wall = 999.0
                if "north" in pw or "top" in pw:
                    dist_to_wall = abs(max_y - a.position.y)
                elif "south" in pw or "bottom" in pw:
                    dist_to_wall = abs(a.position.y - min_y)
                elif "east" in pw or "right" in pw:
                    dist_to_wall = abs(max_x - a.position.x)
                elif "west" in pw or "left" in pw:
                    dist_to_wall = abs(a.position.x - min_x)

                # If within 1.0m of preferred wall, award full or proportional credit
                wall_score = max(0.0, min(1.0, 1.0 - (dist_to_wall / 2.0)))
                pref_scores.append(wall_score)

            # Locked positions: strictly awarded 1.0
            if a.is_locked:
                pref_scores.append(1.0)

        preference_score = (sum(pref_scores) / len(pref_scores)) if pref_scores else 1.0
        is_valid = len(violations) == 0

        return FunctionalEvaluationResult(
            is_valid=is_valid,
            violations=violations,
            relationship_score=round(relationship_score, 3),
            preference_score=round(preference_score, 3),
            details=details,
        )
