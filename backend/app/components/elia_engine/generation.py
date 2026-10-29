from __future__ import annotations

from typing import Any, Mapping

from .exceptions import ELIAError
from .service import run_elia


def generate_exterior(
    master: Mapping[str, Any],
    requirements: Mapping[str, Any],
    run_id: str,
    generation_mode: str = "baseline",
    model_adapter: Any | None = None,
) -> tuple[dict[str, Any], str]:
    """Execute ELIA exterior planning.
    
    Architecture:
    Rule-based feasibility and validation + geometric layout planning and optimization.
    Neural inference and trained model modes are unsupported and rejected.
    """
    if generation_mode == "trained_model":
        raise ELIAError(
            "ELIA_UNSUPPORTED_GENERATION_MODE_ELIA_MODEL_UNAVAILABLE",
            "Trained model mode is not supported. ELIA is a rule-based, preference-driven "
            "exterior planning system using geometric layout generation and optimization.",
            status_code=400,
        )
    if generation_mode not in {"baseline", "rule_based_geometric", "geometric_planner", "default"}:
        raise ELIAError(
            "ELIA_UNSUPPORTED_GENERATION_MODE",
            f"Unsupported ELIA generation mode: {generation_mode!r}. Supported mode: 'baseline' (rule-based geometric planner).",
            status_code=400,
        )

    exterior, outcome = run_elia(master, requirements, run_id)
    exterior["schema_version"] = "1.0"
    exterior["generation_mode"] = generation_mode
    exterior["engine_type"] = "rule_based_geometric_planner"
    exterior["planner_version"] = "1.0.0"
    exterior["ruleset_version"] = "1.0"
    exterior["catalogue_version"] = "2.1"
    exterior["search_seed"] = None
    exterior["model_inference_status"] = "not_requested"
    exterior["structural_load_assessed"] = False
    return exterior, outcome