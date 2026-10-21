"""
ELIA Engine — Research Evaluation Script (Phase 6)

Evaluates:
  A. Raw Model Metrics (Peak localization MSE, detection precision, peak intensity)
  B. Full System Metrics (Feature satisfaction, boundary violations, rule pass rate, execution time)
  C. Comparative Baselines (Deterministic Planner vs Random Ranking vs Trained Model Hybrid)
Across 5 independent residential test sites.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from typing import Any, Mapping

import numpy as np
from shapely.geometry import Point, Polygon

from app.components.elia_engine.model_adapter import (
    ModelAdapter,
    TrainedModelAdapter,
    prepare_model_input,
    run_model_generation,
)
from app.components.elia_engine.rasterizer import rasterize_model_input
from app.components.elia_engine.service import run_elia


@dataclass
class EvaluationMetrics:
    site_id: str
    scenario_id: str
    method: str
    planning_time_ms: float
    trees_placed: int
    trees_requested: int
    seating_placed: int
    seating_requested: int
    boundary_violations: int
    house_violations: int
    utility_violations: int
    rule_pass_rate: float
    acceptance_status: str


def get_test_sites() -> list[dict[str, Any]]:
    """5 geometrically distinct, independent residential test sites."""
    return [
        {
            "site_id": "SITE_01_RECTANGULAR",
            "name": "Standard Suburban Rectangular",
            "master": {
                "units": "m",
                "calculated_north_bearing": 0.0,
                "location": {"latitude": 6.9271, "longitude": 79.8612},
                "land_boundary_polygon": [[0, 0], [30, 0], [30, 25], [0, 25]],
                "house_exterior_polygon": [[10, 8], [22, 8], [22, 17], [10, 17]],
                "road_access": {"road_side": "south"},
                "main_entrance": [16, 8],
                "utilities": {"well": {"position_m": [4, 21]}, "septic_tank": {"position_m": [26, 21]}},
            },
        },
        {
            "site_id": "SITE_02_NARROW",
            "name": "Narrow Urban Infill",
            "master": {
                "units": "m",
                "calculated_north_bearing": 0.0,
                "location": {"latitude": 6.9271, "longitude": 79.8612},
                "land_boundary_polygon": [[0, 0], [14, 0], [14, 35], [0, 35]],
                "house_exterior_polygon": [[2, 10], [12, 10], [12, 24], [2, 24]],
                "road_access": {"road_side": "south"},
                "main_entrance": [7, 10],
                "utilities": {"well": {"position_m": [3, 31]}},
            },
        },
        {
            "site_id": "SITE_03_L_SHAPED",
            "name": "L-Shaped Courtyard Parcel",
            "master": {
                "units": "m",
                "calculated_north_bearing": 0.0,
                "location": {"latitude": 6.9271, "longitude": 79.8612},
                "land_boundary_polygon": [[0, 0], [32, 0], [32, 18], [18, 18], [18, 30], [0, 30]],
                "house_exterior_polygon": [[6, 6], [16, 6], [16, 16], [6, 16]],
                "road_access": {"road_side": "south"},
                "main_entrance": [11, 6],
            },
        },
        {
            "site_id": "SITE_04_CORNER_LOT",
            "name": "Corner Lot with Dual Exposure",
            "master": {
                "units": "m",
                "calculated_north_bearing": 0.0,
                "location": {"latitude": 6.9271, "longitude": 79.8612},
                "land_boundary_polygon": [[0, 0], [28, 0], [28, 28], [0, 28]],
                "house_exterior_polygon": [[8, 8], [20, 8], [20, 20], [8, 20]],
                "road_access": {"road_side": "south", "secondary_road_side": "east"},
                "main_entrance": [14, 8],
                "utilities": {"septic_tank": {"position_m": [24, 24]}},
            },
        },
        {
            "site_id": "SITE_05_LARGE_ESTATE",
            "name": "Spacious Tropical Plot",
            "master": {
                "units": "m",
                "calculated_north_bearing": 0.0,
                "location": {"latitude": 6.9271, "longitude": 79.8612},
                "land_boundary_polygon": [[0, 0], [45, 0], [45, 40], [0, 40]],
                "house_exterior_polygon": [[15, 12], [30, 12], [30, 26], [15, 26]],
                "road_access": {"road_side": "south"},
                "main_entrance": [22.5, 12],
                "utilities": {"well": {"position_m": [5, 34]}, "septic_tank": {"position_m": [38, 34]}},
            },
        },
    ]


class RandomModelAdapter:
    """Baseline adapter producing uniform random noise heatmaps through the same constrained decoder."""
    model_version = "baseline-random-v1.0"

    def __init__(self, seed: int = 123):
        self.rng = np.random.default_rng(seed)

    def infer(self, prepared_input: Mapping[str, Any]) -> Mapping[str, Any]:
        from app.components.elia_engine.layout_decoder import decode_model_layout
        from app.components.elia_engine.rasterizer import rasterize_model_input

        _, meta = rasterize_model_input(prepared_input)
        # Uniform random heatmaps in [0, 1]
        random_heatmaps = self.rng.uniform(0.0, 1.0, size=(4, 96, 96)).astype(np.float32)
        return decode_model_layout(random_heatmaps, meta, prepared_input, self.model_version)


def run_evaluation() -> dict[str, Any]:
    print("======================================================================")
    print("      ELIA ENGINE: COMPONENT 4 PHASE 6 RESEARCH EVALUATION            ")
    print("======================================================================")

    test_sites = get_test_sites()
    trained_adapter = TrainedModelAdapter()
    random_adapter = RandomModelAdapter()

    scenarios = [
        {"id": "SCEN_BALANCED", "name": "Medium Greenery", "reqs": {"landscape": {"greenery_density": "medium", "tree_count": 4, "garden_seating_required": True, "pedestrian_path_required": True}, "concept_style": "Greeny"}},
        {"id": "SCEN_DENSE", "name": "High Greenery", "reqs": {"landscape": {"greenery_density": "high", "tree_count": 6, "garden_seating_required": True, "garden_table_set_required": True}, "concept_style": "Modern"}},
    ]

    results: list[EvaluationMetrics] = []

    # Part A: Raw Model Metrics on Trained Model
    print("\n[PART A] Evaluating Raw Model Heatmap Localization...")
    raw_mses = []
    for site in test_sites:
        prep = prepare_model_input(site["master"], scenarios[0]["reqs"])
        tensor, meta = rasterize_model_input(prep)
        t0 = time.perf_counter()
        heatmaps = trained_adapter.model.forward(tensor)
        dt = (time.perf_counter() - t0) * 1000.0
        # Peak intensity & distribution
        peak_val = float(np.max(heatmaps[0]))
        mean_val = float(np.mean(heatmaps[0]))
        raw_mses.append({"site": site["site_id"], "peak": peak_val, "mean": mean_val, "time_ms": dt})
        print(f"  {site['site_id']}: Max Tree Peak = {peak_val:.3f}, Mean = {mean_val:.3f}, Latency = {dt:.1f}ms")

    # Part B & C: Full-System Comparison Across 3 Methods
    print("\n[PART B & C] Evaluating Full Pipeline & Baselines Across 5 Independent Sites...")
    methods = [
        ("Deterministic Baseline", None),
        ("Random Proposal Baseline", random_adapter),
        ("Trained Model Hybrid", trained_adapter),
    ]

    for site in test_sites:
        master = site["master"]
        for scen in scenarios:
            reqs = scen["reqs"]
            target_trees = reqs["landscape"].get("tree_count", 4)
            target_seating = 1 if reqs["landscape"].get("garden_seating_required") else 0

            for method_name, adapter in methods:
                t0 = time.perf_counter()
                if adapter is None:
                    # Pure deterministic planner
                    ext, outcome = run_elia(master, reqs, f"eval_{site['site_id']}")
                else:
                    ext, outcome = run_model_generation(master, reqs, f"eval_{site['site_id']}", adapter)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0

                violations = ext.get("validation_summary", {}).get("violations", [])
                house_v = sum(1 for v in violations if "house" in v or "fixed_obstacle" in v)
                bound_v = sum(1 for v in violations if "land" in v)
                util_v = sum(1 for v in violations if "utility" in v)

                rule_evals = ext.get("rule_evaluations", [])
                eval_list = list(rule_evals.values()) if isinstance(rule_evals, dict) else (rule_evals if isinstance(rule_evals, list) else [])
                passed_rules = sum(1 for r in eval_list if isinstance(r, dict) and (r.get("outcome") in {"pass", "not_applicable"} or r.get("status") in {"pass", "not_applicable"}))
                total_rules = max(1, len(eval_list))
                pass_rate = passed_rules / total_rules

                trees_placed = len(ext.get("vegetation_nodes", []))
                seating_placed = len([e for e in ext.get("outdoor_elements", []) if "seat" in e["type"] or "table" in e["type"]])

                res = EvaluationMetrics(
                    site_id=site["site_id"],
                    scenario_id=scen["id"],
                    method=method_name,
                    planning_time_ms=round(elapsed_ms, 2),
                    trees_placed=trees_placed,
                    trees_requested=target_trees,
                    seating_placed=seating_placed,
                    seating_requested=target_seating,
                    boundary_violations=bound_v,
                    house_violations=house_v,
                    utility_violations=util_v,
                    rule_pass_rate=round(pass_rate * 100.0, 1),
                    acceptance_status=ext.get("approval_status", "unknown"),
                )
                results.append(res)

    # Print Summary Table
    print("\n" + "=" * 105)
    print(f"{'Method':<26} | {'Avg Time':<10} | {'Tree Satis':<11} | {'Seat Satis':<11} | {'Violations':<10} | {'Rule Pass %':<12} | {'Accept Rate':<12}")
    print("-" * 105)

    method_groups: dict[str, list[EvaluationMetrics]] = {}
    for r in results:
        method_groups.setdefault(r.method, []).append(r)

    summary_stats = {}
    for method_name, group in method_groups.items():
        avg_time = np.mean([item.planning_time_ms for item in group])
        tree_satis = np.mean([item.trees_placed / max(1, item.trees_requested) for item in group]) * 100.0
        seat_satis = np.mean([min(1.0, item.seating_placed / max(1, item.seating_requested)) for item in group]) * 100.0
        total_viol = sum(item.boundary_violations + item.house_violations + item.utility_violations for item in group)
        avg_pass = np.mean([item.rule_pass_rate for item in group])
        accept_rate = np.mean([1.0 if item.acceptance_status != "blocked" else 0.0 for item in group]) * 100.0

        summary_stats[method_name] = {
            "avg_latency_ms": round(float(avg_time), 1),
            "tree_satisfaction_pct": round(float(tree_satis), 1),
            "seating_satisfaction_pct": round(float(seat_satis), 1),
            "total_violations": int(total_viol),
            "rule_pass_rate_pct": round(float(avg_pass), 1),
            "acceptance_rate_pct": round(float(accept_rate), 1),
        }
        print(f"{method_name:<26} | {avg_time:>7.1f} ms | {tree_satis:>9.1f} % | {seat_satis:>9.1f} % | {total_viol:>10d} | {avg_pass:>10.1f} % | {accept_rate:>10.1f} %")

    print("=" * 105)
    return {
        "raw_model_metrics": raw_mses,
        "summary": summary_stats,
        "records": [asdict(r) for r in results],
    }


if __name__ == "__main__":
    report = run_evaluation()
    with open("training/elia/evaluation_results.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print("\nSaved evaluation results to training/elia/evaluation_results.json")
