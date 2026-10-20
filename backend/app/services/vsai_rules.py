from collections.abc import Callable, Mapping
from dataclasses import dataclass
import math
from typing import Any


RuleEvaluator = Callable[[Mapping[str, Any]], bool | None]


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: str
    group: str
    description: str
    configured: bool = False
    weight: float | None = None
    evaluator: RuleEvaluator | None = None
    unavailable_reason: str = "An exact, validated rule definition is not present in the project specification."


def _eval_brahmasthan_exact_center(master_json: Mapping[str, Any]) -> bool | None:
    try:
        from .vastu_engine import evaluate_vastu_shastra
        res = evaluate_vastu_shastra(dict(master_json))
        return res["brahmasthan"]["status"] == "CLEAR"
    except Exception:
        return None


def _eval_dwara_sthana(master_json: Mapping[str, Any]) -> bool | None:
    try:
        from .vastu_engine import evaluate_vastu_shastra
        res = evaluate_vastu_shastra(dict(master_json))
        return res["dwara_sthana"]["classification"] in ("VERY_GOOD", "GOOD")
    except Exception:
        return None


def _eval_main_entrance(master_json: Mapping[str, Any]) -> bool | None:
    try:
        from .vastu_engine import evaluate_vastu_shastra
        res = evaluate_vastu_shastra(dict(master_json))
        return res["main_entrance"].get("classification") == "POSITIVE_SUITABLE"
    except Exception:
        return None


def _eval_room_direction(master_json: Mapping[str, Any]) -> bool | None:
    try:
        from .vastu_engine import evaluate_vastu_shastra
        res = evaluate_vastu_shastra(dict(master_json))
        # Pass if no critical or high defects detected in room placement
        critical_room_defects = [
            d for d in res["defects"]
            if d.get("rule_id") == "vsai.room.direction" and d.get("severity") in ("CRITICAL", "HIGH")
        ]
        return len(critical_room_defects) == 0
    except Exception:
        return None


# Legacy unconfigured rule definitions tested by regression tests
RULE_DEFINITIONS = (
    RuleDefinition(
        "vastu.padavinyasa_9x9",
        "vastu_grid",
        "9x9 Vastu Padavinyasa grid evaluation",
        unavailable_reason="Grid origin, orientation, cell semantics, and applicable constraints are unspecified.",
    ),
    RuleDefinition(
        "vastu.brahmasthan",
        "vastu_grid",
        "Brahmasthan evaluation",
        unavailable_reason="The applicable Brahmasthan definition and element constraints are unspecified.",
    ),
    RuleDefinition(
        "vastu.main_door_32_pada",
        "entrance",
        "32-Pada main entrance evaluation",
        unavailable_reason="The entrance reference frame, pada boundaries, and acceptable padas are unspecified.",
    ),
    RuleDefinition(
        "structure.grid_alignment",
        "structural_alignment",
        "Structural grid-alignment evaluation",
        unavailable_reason="The civil-engineering grid dimensions, tolerances, and structural references are unspecified.",
    ),
    RuleDefinition(
        "vastu.directional_constraints",
        "directional",
        "Directional room-use evaluation",
        unavailable_reason="The directional requirements, orientation source, and room-use mapping are unspecified.",
    ),
)

# 4 Finalized Vastu Rules from VSAI_Rectifier_Finalized_Vastu_Rules.json
FINALIZED_RULE_DEFINITIONS = (
    RuleDefinition(
        "vsai.brahmasthan.exact_center",
        "brahmasthan",
        "Brahmasthan Exact Center-Point Check: verifies exact center point is free of spatial objects",
        configured=True,
        weight=25.0,
        evaluator=_eval_brahmasthan_exact_center,
    ),
    RuleDefinition(
        "vsai.dwara_sthana.combination",
        "door_combination",
        "Dwara Sthana Door-Combination Analysis: classifies 16 cardinal door configurations",
        configured=True,
        weight=25.0,
        evaluator=_eval_dwara_sthana,
    ),
    RuleDefinition(
        "vsai.main_entrance.direction",
        "main_entrance",
        "Main Entrance Direction Analysis: verifies positive suitable entrance sectors",
        configured=True,
        weight=25.0,
        evaluator=_eval_main_entrance,
    ),
    RuleDefinition(
        "vsai.room.direction",
        "room_placement",
        "Room Direction Analysis: directional room orientation and avoidance constraints",
        configured=True,
        weight=25.0,
        evaluator=_eval_room_direction,
    ),
)


def evaluate_rules(
    master_json: Mapping[str, Any],
    definitions: tuple[RuleDefinition, ...] = RULE_DEFINITIONS,
) -> dict[str, Any]:
    ids = [rule.rule_id for rule in definitions]
    if len(ids) != len(set(ids)):
        raise ValueError("Rule identifiers must be unique")

    results: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    unevaluable: list[dict[str, str]] = []
    unconfigured: list[dict[str, str]] = []
    configured = applicable = evaluated = passed = failed = 0
    weighted_passed = weighted_total = 0.0

    for rule in definitions:
        if not isinstance(rule.rule_id, str) or not rule.rule_id.strip():
            raise ValueError("Rule identifiers must be non-empty strings")
        if rule.weight is not None and (
            isinstance(rule.weight, bool)
            or not isinstance(rule.weight, (int, float))
            or not math.isfinite(rule.weight)
            or rule.weight <= 0
        ):
            raise ValueError(f"Rule '{rule.rule_id}' must have a positive finite weight")
        configured += int(rule.configured)
        if not rule.configured:
            reason = rule.unavailable_reason
            state = "unconfigured"
            unconfigured.append({"rule_id": rule.rule_id, "reason": reason})
        elif rule.evaluator is None:
            reason = "No evaluator is registered for this configured rule."
            state = "unevaluable"
            unevaluable.append({"rule_id": rule.rule_id, "reason": reason})
        else:
            result = rule.evaluator(master_json)
            if result is not None and not isinstance(result, bool):
                raise TypeError(f"Rule '{rule.rule_id}' evaluator must return bool or None")
            if result is None:
                reason = "The rule's required input data is unavailable."
                state = "unevaluable"
                unevaluable.append({"rule_id": rule.rule_id, "reason": reason})
            else:
                applicable += 1
                evaluated += 1
                passed += int(result)
                failed += int(not result)
                state = "passed" if result else "failed"
                weight = rule.weight if rule.weight is not None else 1.0
                weighted_total += weight
                weighted_passed += weight if result else 0.0
                if not result:
                    violations.append({
                        "rule_id": rule.rule_id,
                        "group": rule.group,
                        "description": rule.description,
                    })
                reason = None
        results.append({
            "rule_id": rule.rule_id,
            "group": rule.group,
            "description": rule.description,
            "configured": rule.configured,
            "status": state,
            "weight": rule.weight,
            "reason": reason,
        })

    score_available = evaluated > 0
    return {
        "rule_results": results,
        "violations": violations,
        "unevaluable_rules": unevaluable,
        "unconfigured_rules": unconfigured,
        "rule_coverage": {
            "total": len(definitions),
            "configured": configured,
            "applicable": applicable,
            "evaluated": evaluated,
            "passed": passed,
            "failed": failed,
            "unconfigured": len(definitions) - configured,
            "unevaluable": len(unevaluable),
            "coverage_percent": (evaluated / configured * 100) if configured else None,
        },
        "vastu_compliance_score": round(weighted_passed / weighted_total * 100, 2) if score_available else None,
        "score_status": "evaluated" if score_available else "unavailable",
        "score_formula": "100 * sum(weight of passed evaluated rules) / sum(weight of all evaluated rules).",
    }
