"""
ESAI Research Evaluation & Baselines
Direct scientific benchmarking comparing Genetic Algorithm (PyGAD)
against Random-Search and Greedy Heuristic baselines under identical constraints.
"""
import time
import random
from typing import Any, Dict, List, Optional
import numpy as np
from pydantic import BaseModel, Field

from ..contracts import ResolvedRoomDesignInputDTO
from .chromosome import ChromosomeCodec, PlacedAssetDTO
from .candidate_generator import CandidateGenerator
from .geometry_constraints import GeometryConstraintEvaluator
from .ergonomic_constraints import ErgonomicConstraintEvaluator
from .functional_constraints import FunctionalConstraintEvaluator
from .fitness import SpatialFitnessEvaluator
from .genetic_optimizer import PyGADLayoutOptimizer, OptimizationConfig, OptimizationResult


class BaselineMetricsDTO(BaseModel):
    method_name: str
    valid_layout_found: bool
    best_fitness: float
    ergonomic_score: float
    circulation_score: float
    preference_score: float
    relationship_score: float
    hard_violations_count: int
    evaluations_count: int
    runtime_seconds: float


class BaselineComparisonReport(BaseModel):
    room_id: str
    room_type: str
    ga_metrics: BaselineMetricsDTO
    random_metrics: BaselineMetricsDTO
    greedy_metrics: BaselineMetricsDTO
    ga_outperforms_random: bool
    ga_outperforms_greedy: bool
    summary: str


class BaselineEvaluator:
    """
    Executes fair, controlled benchmark comparisons between GA and baselines.
    """

    def benchmark_room(
        self,
        design_input: ResolvedRoomDesignInputDTO,
        eval_budget: int = 500,
        seed: int = 42,
    ) -> BaselineComparisonReport:
        """
        Runs GA, Random-Search, and Greedy Placement on identical room geometry & constraints.
        """
        from shapely.geometry import Polygon as ShapelyPoly
        room_poly = ShapelyPoly([(p.x, p.y) for p in design_input.polygon])

        codec = ChromosomeCodec(room_polygon=room_poly, asset_instances=design_input.asset_instances)
        geo_eval = GeometryConstraintEvaluator(
            room_polygon=room_poly,
            doors=design_input.doors,
            windows=design_input.windows,
            fixed_obstructions=design_input.fixed_obstructions,
        )
        ergo_eval = ErgonomicConstraintEvaluator(
            rules=design_input.ergonomic_constraints,
            room_polygon=room_poly,
        )
        func_eval = FunctionalConstraintEvaluator(
            relationships=design_input.functional_relationships,
            room_polygon=room_poly,
        )
        aesthetic_score = (
            design_input.aesthetic_profile.overall_compatibility_score
            if design_input.aesthetic_profile else 1.0
        )
        fitness_eval = SpatialFitnessEvaluator(
            geo_eval=geo_eval,
            ergo_eval=ergo_eval,
            func_eval=func_eval,
            aesthetic_compatibility_score=aesthetic_score,
        )

        cand_gen = CandidateGenerator(
            codec=codec,
            doors=design_input.doors,
            windows=design_input.windows,
            fixed_obstructions=design_input.fixed_obstructions,
            seed=seed,
        )

        # ── 1. Genetic Algorithm Run ──
        pop_size = 25
        num_gens = max(5, eval_budget // pop_size)
        ga_cfg = OptimizationConfig(
            population_size=pop_size,
            num_generations=num_gens,
            seed=seed,
        )
        ga_opt = PyGADLayoutOptimizer(ga_cfg)
        ga_res: OptimizationResult = ga_opt.optimize_room(design_input, ga_cfg)

        ga_fb = ga_res.fitness_breakdown
        ga_metrics = BaselineMetricsDTO(
            method_name="PyGAD Genetic Algorithm",
            valid_layout_found=(ga_res.status == "success"),
            best_fitness=ga_fb.total_fitness if ga_fb else -100.0,
            ergonomic_score=ga_fb.ergonomic_score if ga_fb else 0.0,
            circulation_score=ga_fb.circulation_score if ga_fb else 0.0,
            preference_score=ga_fb.preference_score if ga_fb else 0.0,
            relationship_score=ga_fb.relationship_score if ga_fb else 0.0,
            hard_violations_count=len(ga_fb.violations) if ga_fb else 99,
            evaluations_count=ga_res.total_evaluations,
            runtime_seconds=ga_res.execution_time_sec,
        )

        # ── 2. Random-Search Baseline ──
        # Sample eval_budget random candidates, measure best
        rnd_start = time.time()
        random.seed(seed)
        best_rnd_fit = -999.0
        best_rnd_fb = None

        for _ in range(eval_budget):
            chrom = cand_gen.generate_random_chromosome()
            placed = codec.decode(chrom)
            fb = fitness_eval.evaluate(placed)
            if fb.total_fitness > best_rnd_fit:
                best_rnd_fit = fb.total_fitness
                best_rnd_fb = fb

        rnd_runtime = round(time.time() - rnd_start, 3)
        rnd_metrics = BaselineMetricsDTO(
            method_name="Random Search Baseline",
            valid_layout_found=best_rnd_fb.is_hard_constraint_valid if best_rnd_fb else False,
            best_fitness=round(best_rnd_fit, 4),
            ergonomic_score=best_rnd_fb.ergonomic_score if best_rnd_fb else 0.0,
            circulation_score=best_rnd_fb.circulation_score if best_rnd_fb else 0.0,
            preference_score=best_rnd_fb.preference_score if best_rnd_fb else 0.0,
            relationship_score=best_rnd_fb.relationship_score if best_rnd_fb else 0.0,
            hard_violations_count=len(best_rnd_fb.violations) if best_rnd_fb else 99,
            evaluations_count=eval_budget,
            runtime_seconds=rnd_runtime,
        )

        # ── 3. Greedy Placement Baseline ──
        grd_start = time.time()
        greedy_chrom = cand_gen.generate_greedy_chromosome()
        greedy_placed = codec.decode(greedy_chrom)
        greedy_fb = fitness_eval.evaluate(greedy_placed)
        grd_runtime = round(time.time() - grd_start, 3)

        grd_metrics = BaselineMetricsDTO(
            method_name="Greedy Wall-Placement Baseline",
            valid_layout_found=greedy_fb.is_hard_constraint_valid,
            best_fitness=round(greedy_fb.total_fitness, 4),
            ergonomic_score=greedy_fb.ergonomic_score,
            circulation_score=greedy_fb.circulation_score,
            preference_score=greedy_fb.preference_score,
            relationship_score=greedy_fb.relationship_score,
            hard_violations_count=len(greedy_fb.violations),
            evaluations_count=1,
            runtime_seconds=grd_runtime,
        )

        # Comparative indicators
        ga_beats_rnd = (
            (ga_metrics.valid_layout_found and not rnd_metrics.valid_layout_found)
            or (ga_metrics.best_fitness > rnd_metrics.best_fitness)
        )
        ga_beats_grd = (
            (ga_metrics.valid_layout_found and not grd_metrics.valid_layout_found)
            or (ga_metrics.best_fitness >= grd_metrics.best_fitness)
        )

        summary = (
            f"Evaluated {design_input.room_name} ({design_input.room_type}): "
            f"GA fitness {ga_metrics.best_fitness:.2f} (valid: {ga_metrics.valid_layout_found}) vs "
            f"Random fitness {rnd_metrics.best_fitness:.2f} (valid: {rnd_metrics.valid_layout_found}) vs "
            f"Greedy fitness {grd_metrics.best_fitness:.2f} (valid: {grd_metrics.valid_layout_found})."
        )

        return BaselineComparisonReport(
            room_id=design_input.room_id,
            room_type=design_input.room_type,
            ga_metrics=ga_metrics,
            random_metrics=rnd_metrics,
            greedy_metrics=grd_metrics,
            ga_outperforms_random=ga_beats_rnd,
            ga_outperforms_greedy=ga_beats_grd,
            summary=summary,
        )
