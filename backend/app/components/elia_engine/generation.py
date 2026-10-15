from __future__ import annotations

from typing import Any, Mapping

from .model_adapter import ModelAdapter, run_model_generation
from .service import run_elia


def generate_exterior(master: Mapping[str, Any], requirements: Mapping[str, Any], run_id: str,
                      generation_mode: str, model_adapter: ModelAdapter | None = None) -> tuple[dict[str, Any], str]:
    if generation_mode == "trained_model":
        return run_model_generation(master, requirements, run_id, model_adapter)
    if generation_mode != "baseline":
        raise ValueError(f"Unsupported ELIA generation mode: {generation_mode}")
    exterior, outcome = run_elia(master, requirements, run_id)
    exterior["schema_version"] = "1.0"
    exterior["generation_mode"] = "baseline_demo"
    exterior["model_inference_status"] = "not_requested"
    exterior["structural_load_assessed"] = False
    return exterior, outcome