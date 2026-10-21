"""
Phase 9 Empirical Research Benchmark Runner
Direct scientific benchmarking comparing Genetic Algorithm (PyGAD)
against Random-Search and Greedy Heuristic baselines under identical constraints.

Uses the real, authoritative EsaiEngineService to resolve room inputs directly from
representative architectural fixtures (Single Bedroom, Multi-Floor Master Suite,
Living Room, and Kitchen), ensuring full fidelity with real catalog assets and constraints.
"""
import os
import sys
import json
import time
from copy import deepcopy
from typing import Any, Dict, List
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from shapely.geometry import Polygon as ShapelyPoly

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath("."))

from app.database import Base
from app.models.project import Project
from app.components.esai_engine.service import EsaiEngineService
from app.components.esai_engine.contracts import ResolvedRoomDesignInputDTO
from app.components.esai_engine.optimizer.chromosome import ChromosomeCodec
from app.components.esai_engine.optimizer.candidate_generator import CandidateGenerator
from app.components.esai_engine.optimizer.geometry_constraints import GeometryConstraintEvaluator
from app.components.esai_engine.optimizer.ergonomic_constraints import ErgonomicConstraintEvaluator
from app.components.esai_engine.optimizer.functional_constraints import FunctionalConstraintEvaluator
from app.components.esai_engine.optimizer.fitness import SpatialFitnessEvaluator
from app.components.esai_engine.optimizer.genetic_optimizer import PyGADLayoutOptimizer, OptimizationConfig
from tests.esai.fixtures import BEDROOM_PROJECT_FIXTURE, MULTI_FLOOR_PROJECT_FIXTURE

ARTIFACT_DIR = r"C:\Users\user\.gemini\antigravity-ide\brain\4858d3dc-0ac6-4ef5-a9aa-504db8fbd533"

def build_benchmark_inputs():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    db = Session()

    # 1. Standard Queen Bedroom
    p1 = Project(id="bm_p1", project_name="Benchmark Bedroom", master_json=deepcopy(BEDROOM_PROJECT_FIXTURE), revision=1)
    db.add(p1)
    db.commit()
    service = EsaiEngineService(db)
    service.save_room_preferences(
        p1,
        room_id="RM_BED_01",
        preferences_data={
            "room_specific": {"bed_type": "queen", "bed_quantity": 1, "wardrobe_type": "sliding"},
            "design_style": "modern",
        },
    )
    in_bed = service.resolve_room_design_input(p1, room_id="RM_BED_01", floor_id="floor_gf")

    # 2. Multi-Floor Project Rooms
    p2 = Project(id="bm_p2", project_name="Benchmark Multi", master_json=deepcopy(MULTI_FLOOR_PROJECT_FIXTURE), revision=1)
    db.add(p2)
    db.commit()

    # Living Room
    service.save_room_preferences(
        p2,
        room_id="RM_LIVING_01",
        preferences_data={
            "room_specific": {"seating_capacity": 5, "coffee_table": True, "tv_unit": True},
            "design_style": "contemporary",
        },
    )
    in_living = service.resolve_room_design_input(p2, room_id="RM_LIVING_01", floor_id="fl_0")

    # Modular Kitchen
    service.save_room_preferences(
        p2,
        room_id="RM_KITCHEN_01",
        preferences_data={
            "room_specific": {"layout_type": "straight", "dishwasher": True, "refrigerator": True},
            "design_style": "minimalist",
        },
    )
    in_kit = service.resolve_room_design_input(p2, room_id="RM_KITCHEN_01", floor_id="fl_0")

    # Attached Bathroom
    service.save_room_preferences(
        p2,
        room_id="RM_BATH_01",
        preferences_data={
            "room_specific": {"bathtub": False, "shower_enclosure": True, "vanity": True},
            "design_style": "modern",
        },
    )
    in_bath = service.resolve_room_design_input(p2, room_id="RM_BATH_01", floor_id="fl_1")

    return [
        ("Queen Bedroom (20 sqm)", in_bed),
        ("Formal Living Room (30 sqm)", in_living),
        ("Modular Kitchen (16 sqm)", in_kit),
        ("Attached Bathroom (6.25 sqm)", in_bath),
    ]

def run_single_evaluation(design_input: ResolvedRoomDesignInputDTO, seed: int, eval_budget: int = 400) -> Dict[str, Any]:
    poly_pts = [(p.x, p.y) for p in design_input.polygon]
    room_poly = ShapelyPoly(poly_pts)

    codec = ChromosomeCodec(room_polygon=room_poly, asset_instances=design_input.asset_instances)
    geo_eval = GeometryConstraintEvaluator(room_polygon=room_poly, doors=design_input.doors, windows=design_input.windows, fixed_obstructions=design_input.fixed_obstructions)
    ergo_eval = ErgonomicConstraintEvaluator(rules=design_input.ergonomic_constraints, room_polygon=room_poly)
    func_eval = FunctionalConstraintEvaluator(relationships=design_input.functional_relationships, room_polygon=room_poly)
    fitness_eval = SpatialFitnessEvaluator(geo_eval=geo_eval, ergo_eval=ergo_eval, func_eval=func_eval)

    # 1. Real PyGAD Genetic Algorithm
    ga_optimizer = PyGADLayoutOptimizer()
    pop_size = 20
    num_gen = eval_budget // pop_size
    ga_cfg = OptimizationConfig(
        population_size=pop_size,
        num_generations=num_gen,
        seed=seed,
    )
    t0_ga = time.time()
    ga_res = ga_optimizer.optimize_room(design_input, config=ga_cfg)
    t_ga = time.time() - t0_ga

    ga_valid = ga_res.status == "success"
    ga_fitness = float(ga_res.final_best_fitness)
    ga_violations = len(ga_res.fitness_breakdown.violations) if ga_res.fitness_breakdown else 99

    # 2. Random Search Baseline (Strictly identical evaluation budget)
    np.random.seed(seed)
    gene_space = codec.get_gene_space()

    t0_rnd = time.time()
    rnd_best_fit = -1.0
    rnd_best_valid = False
    rnd_best_violations = 99

    for _ in range(eval_budget):
        cand_solution = []
        for g_range in gene_space:
            low, high = g_range["low"], g_range["high"]
            cand_solution.append(float(np.random.uniform(low, high)))
        placed = codec.decode(cand_solution)
        fb = fitness_eval.evaluate(placed)
        if fb.total_fitness > rnd_best_fit:
            rnd_best_fit = fb.total_fitness
            rnd_best_valid = fb.is_hard_constraint_valid
            rnd_best_violations = len(fb.violations)
    t_rnd = time.time() - t0_rnd

    # 3. Greedy Heuristic Baseline (Wall attachment & primary axis alignment)
    cand_gen = CandidateGenerator(codec=codec, doors=design_input.doors, windows=design_input.windows, fixed_obstructions=design_input.fixed_obstructions, seed=seed)
    t0_grd = time.time()
    greedy_chrom = cand_gen.generate_greedy_chromosome()
    greedy_placed = codec.decode(greedy_chrom)
    grd_fb = fitness_eval.evaluate(greedy_placed)
    t_grd = time.time() - t0_grd

    grd_valid = grd_fb.is_hard_constraint_valid
    grd_fitness = float(grd_fb.total_fitness)
    grd_violations = len(grd_fb.violations)

    return {
        "seed": seed,
        "ga": {
            "valid": ga_valid,
            "fitness": round(ga_fitness, 4),
            "violations": ga_violations,
            "runtime_sec": round(t_ga, 3),
            "evaluations": ga_res.total_evaluations or eval_budget,
            "fitness_history": [round(f, 3) for f in ga_res.fitness_history],
        },
        "random": {
            "valid": rnd_best_valid,
            "fitness": round(rnd_best_fit, 4),
            "violations": rnd_best_violations,
            "runtime_sec": round(t_rnd, 3),
            "evaluations": eval_budget,
        },
        "greedy": {
            "valid": grd_valid,
            "fitness": round(grd_fitness, 4),
            "violations": grd_violations,
            "runtime_sec": round(t_grd, 3),
            "evaluations": 1,
        },
    }

def main():
    print("=" * 80)
    print("ESAI-Engine Phase 9: Multi-Seed Genetic Algorithm Research Benchmark")
    print("Direct Empirical Comparison: GA vs Random Search vs Greedy Placement")
    print("=" * 80)

    scenarios = build_benchmark_inputs()
    seeds = [42, 101, 2024, 777, 999]
    eval_budget = 300

    all_results = {}

    for name, input_dto in scenarios:
        print(f"\nEvaluating Class: {name} ({len(input_dto.asset_instances)} assets) across {len(seeds)} seeds...")
        scenario_runs = []
        for s in seeds:
            print(f"  -> Seed {s}...", end="", flush=True)
            res = run_single_evaluation(input_dto, seed=s, eval_budget=eval_budget)
            scenario_runs.append(res)
            print(f" Done. (GA Valid: {res['ga']['valid']}, Fit: {res['ga']['fitness']:.2f})")

        # Compute aggregate statistics
        ga_fits = [r["ga"]["fitness"] for r in scenario_runs]
        ga_valid_cnt = sum(1 for r in scenario_runs if r["ga"]["valid"])
        rnd_fits = [r["random"]["fitness"] for r in scenario_runs]
        rnd_valid_cnt = sum(1 for r in scenario_runs if r["random"]["valid"])
        grd_fits = [r["greedy"]["fitness"] for r in scenario_runs]
        grd_valid_cnt = sum(1 for r in scenario_runs if r["greedy"]["valid"])

        all_results[name] = {
            "room_id": input_dto.room_id,
            "room_type": input_dto.room_type,
            "assets_count": len(input_dto.asset_instances),
            "seeds": seeds,
            "runs": scenario_runs,
            "aggregates": {
                "ga": {
                    "feasible_rate": round(ga_valid_cnt / len(seeds), 2),
                    "mean_fitness": round(float(np.mean(ga_fits)), 4),
                    "std_fitness": round(float(np.std(ga_fits)), 4),
                    "mean_runtime": round(float(np.mean([r["ga"]["runtime_sec"] for r in scenario_runs])), 3),
                },
                "random": {
                    "feasible_rate": round(rnd_valid_cnt / len(seeds), 2),
                    "mean_fitness": round(float(np.mean(rnd_fits)), 4),
                    "std_fitness": round(float(np.std(rnd_fits)), 4),
                    "mean_runtime": round(float(np.mean([r["random"]["runtime_sec"] for r in scenario_runs])), 3),
                },
                "greedy": {
                    "feasible_rate": round(grd_valid_cnt / len(seeds), 2),
                    "mean_fitness": round(float(np.mean(grd_fits)), 4),
                    "std_fitness": round(float(np.std(grd_fits)), 4),
                    "mean_runtime": round(float(np.mean([r["greedy"]["runtime_sec"] for r in scenario_runs])), 3),
                },
            },
        }

    # Save artifact
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    out_file = os.path.join(ARTIFACT_DIR, "ga_research_benchmark_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n[Artifact Saved] Benchmark results written to:\n  {out_file}")

    # Print summary table
    print("\n" + "=" * 90)
    print(f"{'Scenario':<30} | {'Method':<8} | {'Feasible':<8} | {'Mean Fit':<9} | {'Std Dev':<8} | {'Mean Sec':<8}")
    print("-" * 90)
    for name, data in all_results.items():
        ag = data["aggregates"]
        print(f"{name:<30} | {'GA':<8} | {ag['ga']['feasible_rate']*100:>6.1f}% | {ag['ga']['mean_fitness']:>9.3f} | {ag['ga']['std_fitness']:>8.3f} | {ag['ga']['mean_runtime']:>7.2f}s")
        print(f"{'':<30} | {'Random':<8} | {ag['random']['feasible_rate']*100:>6.1f}% | {ag['random']['mean_fitness']:>9.3f} | {ag['random']['std_fitness']:>8.3f} | {ag['random']['mean_runtime']:>7.2f}s")
        print(f"{'':<30} | {'Greedy':<8} | {ag['greedy']['feasible_rate']*100:>6.1f}% | {ag['greedy']['mean_fitness']:>9.3f} | {ag['greedy']['std_fitness']:>8.3f} | {ag['greedy']['mean_runtime']:>7.2f}s")
        print("-" * 90)

if __name__ == "__main__":
    main()
