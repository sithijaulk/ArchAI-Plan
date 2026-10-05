from __future__ import annotations

from typing import Any, Mapping


def collect_metrics(started_at: float, land_area: float, available_area: float, driveway_length: float,
                    explored_nodes: int, utility_status: str, turning_valid: bool, solar_completed: bool,
                    vertical_triggered: bool, validation: Mapping[str, Any], used_ground_area: float = 0.0) -> dict[str, Any]:
    import time

    return {
        "generation_time_ms": round((time.perf_counter() - started_at) * 1000, 3),
        "driveway_length_m": round(driveway_length, 3),
        "astar_explored_nodes": explored_nodes,
        "available_ground_ratio": round(available_area / land_area, 6) if land_area else 0.0,
        "ground_space_utilization": round(min(1.0, used_ground_area / available_area), 6) if available_area else 0.0,
        "utility_safety_compliance": True if utility_status == "passed" else False if utility_status == "failed" else None,
        "utility_safety_status": utility_status,
        "driveway_path_feasible": driveway_length > 0,
        "vehicle_access_valid": turning_valid,
        "solar_analysis_completed": solar_completed,
        "vertical_greenery_triggered": vertical_triggered,
        "constraint_satisfaction_rate": (0.0 if validation.get("violations") and validation.get("constraint_satisfaction_rate", 0.0) >= 1.0
                                         else validation.get("constraint_satisfaction_rate", 0.0)),
        "constraint_violation_count": len(validation.get("violations", [])),
    }
