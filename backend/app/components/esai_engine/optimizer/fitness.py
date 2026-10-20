"""
ESAI Spatial Fitness Evaluator
Normalized multi-objective fitness formulation:
  F = wE * E + wC * C + wP * P + wR * R + wA * A - penalties
Guarantees strict separation of hard-constraint validation from soft objective scoring.
"""
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from .chromosome import PlacedAssetDTO
from .geometry_constraints import GeometryConstraintEvaluator, GeometryEvaluationResult
from .ergonomic_constraints import ErgonomicConstraintEvaluator, ErgonomicEvaluationResult
from .functional_constraints import FunctionalConstraintEvaluator, FunctionalEvaluationResult


class FitnessBreakdownDTO(BaseModel):
    total_fitness: float
    raw_fitness_score: float
    ergonomic_score: float
    circulation_score: float
    preference_score: float
    relationship_score: float
    aesthetic_score: float
    overlap_penalty: float
    out_of_bounds_penalty: float
    door_block_penalty: float
    is_hard_constraint_valid: bool
    violations: List[str] = Field(default_factory=list)


class SpatialFitnessEvaluator:
    """
    Evaluates candidates using normalized multi-objective criteria and penalties.
    """

    def __init__(
        self,
        geo_eval: GeometryConstraintEvaluator,
        ergo_eval: ErgonomicConstraintEvaluator,
        func_eval: FunctionalConstraintEvaluator,
        aesthetic_compatibility_score: float = 1.0,
        weights: Optional[Dict[str, float]] = None,
    ):
        self.geo_eval = geo_eval
        self.ergo_eval = ergo_eval
        self.func_eval = func_eval
        self.aesthetic_compatibility_score = aesthetic_compatibility_score

        # Default weights summing to 1.0
        self.weights = weights or {
            "ergonomic": 0.25,
            "circulation": 0.25,
            "preference": 0.20,
            "relationship": 0.15,
            "aesthetic": 0.15,
        }

    def evaluate(self, placed_assets: List[PlacedAssetDTO]) -> FitnessBreakdownDTO:
        """
        Calculates fitness score and audits all hard constraints.
        """
        # 1. Evaluate individual components
        geo_res: GeometryEvaluationResult = self.geo_eval.evaluate(placed_assets)
        ergo_res: ErgonomicEvaluationResult = self.ergo_eval.evaluate(placed_assets)
        func_res: FunctionalEvaluationResult = self.func_eval.evaluate(placed_assets)

        # 2. Weighted positive fitness
        w_e = self.weights.get("ergonomic", 0.25)
        w_c = self.weights.get("circulation", 0.25)
        w_p = self.weights.get("preference", 0.20)
        w_r = self.weights.get("relationship", 0.15)
        w_a = self.weights.get("aesthetic", 0.15)

        raw_score = (
            w_e * ergo_res.ergonomic_score
            + w_c * geo_res.circulation_score
            + w_p * func_res.preference_score
            + w_r * func_res.relationship_score
            + w_a * self.aesthetic_compatibility_score
        )

        # 3. Penalties for constraint violations during GA evolution
        overlap_pen = geo_res.overlap_area_sqm * 10.0
        oob_pen = geo_res.out_of_bounds_area_sqm * 15.0
        door_pen = geo_res.door_violation_count * 5.0
        ergo_hard_pen = len(ergo_res.violations) * 5.0
        func_hard_pen = len(func_res.violations) * 5.0

        total_penalty = overlap_pen + oob_pen + door_pen + ergo_hard_pen + func_hard_pen
        total_fitness = max(-100.0, raw_score - total_penalty)

        # 4. Strict Hard Constraint Verification (Zero Tolerance)
        all_violations = geo_res.violations + ergo_res.violations + func_res.violations
        is_hard_valid = (
            geo_res.is_valid
            and ergo_res.is_valid
            and func_res.is_valid
            and len(all_violations) == 0
        )

        return FitnessBreakdownDTO(
            total_fitness=round(total_fitness, 4),
            raw_fitness_score=round(raw_score, 4),
            ergonomic_score=round(ergo_res.ergonomic_score, 3),
            circulation_score=round(geo_res.circulation_score, 3),
            preference_score=round(func_res.preference_score, 3),
            relationship_score=round(func_res.relationship_score, 3),
            aesthetic_score=round(self.aesthetic_compatibility_score, 3),
            overlap_penalty=round(overlap_pen, 4),
            out_of_bounds_penalty=round(oob_pen, 4),
            door_block_penalty=round(door_pen, 4),
            is_hard_constraint_valid=is_hard_valid,
            violations=all_violations,
        )
