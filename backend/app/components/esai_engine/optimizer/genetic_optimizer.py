"""
ESAI PyGAD Genetic Optimizer
Executes real evolutionary spatial optimization for interior layout placement.
Connects PyGAD evolutionary operators directly to Shapely geometric constraints.
"""
import time
import random
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np
import pygad
from pydantic import BaseModel, Field

from ..contracts import (
    DoorDTO,
    FixedObstructionDTO,
    ResolvedAssetInstanceDTO,
    ResolvedErgonomicConstraintDTO,
    ResolvedFunctionalRelationshipDTO,
    ResolvedRoomDesignInputDTO,
    WindowDTO,
)
from .chromosome import ChromosomeCodec, PlacedAssetDTO
from .candidate_generator import CandidateGenerator
from .geometry_constraints import GeometryConstraintEvaluator
from .ergonomic_constraints import ErgonomicConstraintEvaluator
from .functional_constraints import FunctionalConstraintEvaluator
from .fitness import FitnessBreakdownDTO, SpatialFitnessEvaluator
from .alternatives import LayoutAlternativeDTO, LayoutAlternativeSelector


class OptimizationConfig(BaseModel):
    population_size: int = 30
    num_generations: int = 25
    num_parents_mating: int = 10
    mutation_percent_genes: float = 15.0
    keep_elitism: int = 2
    crossover_type: str = "uniform"
    mutation_type: str = "random"
    parent_selection_type: str = "rank"
    seed: Optional[int] = 42
    alternatives_count: int = 2
    max_runtime_sec: float = 20.0


class OptimizationResult(BaseModel):
    status: str  # "success" | "no_valid_candidate_found" | "infeasible" | "blocked"
    room_id: str
    room_type: str
    best_layout: Optional[List[PlacedAssetDTO]] = None
    fitness_breakdown: Optional[FitnessBreakdownDTO] = None
    alternatives: List[LayoutAlternativeDTO] = Field(default_factory=list)
    generations_completed: int = 0
    total_evaluations: int = 0
    execution_time_sec: float = 0.0
    fitness_history: List[float] = Field(default_factory=list)
    initial_best_fitness: float = 0.0
    final_best_fitness: float = 0.0
    diagnostics: List[str] = Field(default_factory=list)


class PyGADLayoutOptimizer:
    """
    Real Genetic Algorithm layout engine executing PyGAD evolutionary search.
    """

    def __init__(self, config: Optional[OptimizationConfig] = None):
        self.config = config or OptimizationConfig()

    def optimize_room(
        self,
        design_input: ResolvedRoomDesignInputDTO,
        config: Optional[OptimizationConfig] = None,
    ) -> OptimizationResult:
        """
        Runs evolutionary optimization for a single room's design input.
        """
        cfg = config or self.config
        start_time = time.time()
        diagnostics: List[str] = []

        # 1. Deterministic Seeding
        if cfg.seed is not None:
            random.seed(cfg.seed)
            np.random.seed(cfg.seed)

        # 2. Extract geometry and construct Shapely Polygon
        poly_pts = [(p.x, p.y) for p in design_input.polygon]
        if len(poly_pts) < 3:
            return OptimizationResult(
                status="blocked_missing_geometry",
                room_id=design_input.room_id,
                room_type=design_input.room_type,
                diagnostics=["Room polygon contains fewer than 3 vertices."],
            )

        from shapely.geometry import Polygon as ShapelyPoly
        room_poly = ShapelyPoly(poly_pts)
        if not room_poly.is_valid or room_poly.area <= 0.5:
            return OptimizationResult(
                status="blocked_missing_geometry",
                room_id=design_input.room_id,
                room_type=design_input.room_type,
                diagnostics=["Room polygon is invalid or has near-zero area."],
            )

        # 3. Guard against unresolvable congestion
        if design_input.feasibility_status == "infeasible":
            return OptimizationResult(
                status="infeasible",
                room_id=design_input.room_id,
                room_type=design_input.room_type,
                diagnostics=design_input.diagnostics + ["Room declared infeasible due to extreme footprint congestion."],
            )

        # 4. Instantiate Codec & Evaluators
        codec = ChromosomeCodec(
            room_polygon=room_poly,
            asset_instances=design_input.asset_instances,
        )

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

        fitness_evaluator = SpatialFitnessEvaluator(
            geo_eval=geo_eval,
            ergo_eval=ergo_eval,
            func_eval=func_eval,
            aesthetic_compatibility_score=aesthetic_score,
        )

        # Handle zero movable instances (all locked or empty)
        if codec.num_movable == 0:
            placed = list(codec.locked_assets)
            fb = fitness_evaluator.evaluate(placed)
            status = "success" if fb.is_hard_constraint_valid else "infeasible"
            return OptimizationResult(
                status=status,
                room_id=design_input.room_id,
                room_type=design_input.room_type,
                best_layout=placed,
                fitness_breakdown=fb,
                execution_time_sec=round(time.time() - start_time, 3),
            )

        # 5. Candidate Generator & Initial Population
        cand_gen = CandidateGenerator(
            codec=codec,
            doors=design_input.doors,
            windows=design_input.windows,
            fixed_obstructions=design_input.fixed_obstructions,
            seed=cfg.seed,
        )
        initial_pop = cand_gen.generate_initial_population(population_size=cfg.population_size)

        # Initial baseline evaluation
        initial_best_fitness = max(
            fitness_evaluator.evaluate(codec.decode(sol)).total_fitness
            for sol in initial_pop
        )

        # 6. PyGAD Fitness Callback
        eval_counter = 0
        population_archive: List[Tuple[List[float], float, List[PlacedAssetDTO], FitnessBreakdownDTO]] = []

        def pygad_fitness_func(ga_instance: Any, solution: Any, solution_idx: Any) -> float:
            nonlocal eval_counter
            eval_counter += 1
            placed_cand = codec.decode(solution)
            fb = fitness_evaluator.evaluate(placed_cand)

            # Archive candidates that satisfy hard constraints or have high fitness
            if fb.is_hard_constraint_valid or fb.total_fitness > 0.0:
                population_archive.append((list(solution), fb.total_fitness, placed_cand, fb))

            return fb.total_fitness

        # 7. Configure and Run PyGAD Genetic Algorithm
        ga_instance = pygad.GA(
            num_generations=cfg.num_generations,
            num_parents_mating=min(cfg.num_parents_mating, cfg.population_size // 2),
            fitness_func=pygad_fitness_func,
            initial_population=initial_pop,
            gene_space=codec.get_gene_space(),
            parent_selection_type=cfg.parent_selection_type,
            crossover_type=cfg.crossover_type,
            mutation_type=cfg.mutation_type,
            mutation_percent_genes=cfg.mutation_percent_genes,
            keep_elitism=cfg.keep_elitism,
            random_seed=cfg.seed,
            suppress_warnings=True,
        )

        ga_instance.run()

        # 8. Extract Best Solution
        best_sol, best_fit, _ = ga_instance.best_solution()
        best_placed = codec.decode(best_sol)
        best_fb = fitness_evaluator.evaluate(best_placed)

        fitness_history = [float(f) for f in getattr(ga_instance, "best_solutions_fitness", [])]
        final_best_fitness = float(best_fit)

        # 9. Alternative Layout Selector & Strict Hard-Constraint Validation
        alt_selector = LayoutAlternativeSelector()
        alternatives = alt_selector.select_alternatives(
            archive=population_archive,
            target_count=cfg.alternatives_count,
        )

        # Strict Hard Constraint Policy:
        # A solution is ONLY successful if all mandatory constraints are completely satisfied!
        if best_fb.is_hard_constraint_valid:
            status = "success"
        elif alternatives:
            # If the primary best had minor soft constraint issues, promote best valid alternative
            status = "success"
            best_placed = alternatives[0].placed_assets
            best_fb = alternatives[0].fitness_breakdown
        else:
            status = "no_valid_candidate_found"
            diagnostics.append(
                f"No candidate met all hard constraints. Top violations: {'; '.join(best_fb.violations[:3])}"
            )

        duration = round(time.time() - start_time, 3)

        return OptimizationResult(
            status=status,
            room_id=design_input.room_id,
            room_type=design_input.room_type,
            best_layout=best_placed if status == "success" else None,
            fitness_breakdown=best_fb,
            alternatives=alternatives,
            generations_completed=cfg.num_generations,
            total_evaluations=eval_counter,
            execution_time_sec=duration,
            fitness_history=fitness_history,
            initial_best_fitness=round(initial_best_fitness, 4),
            final_best_fitness=round(final_best_fitness, 4),
            diagnostics=diagnostics + design_input.diagnostics,
        )
