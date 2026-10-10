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
        "score_status": "incomplete" if score_available else "unavailable",
        "score_formula": "100 * sum(weight of passed evaluated rules) / sum(weight of all evaluated rules); unspecified weights equal 1.",
    }
