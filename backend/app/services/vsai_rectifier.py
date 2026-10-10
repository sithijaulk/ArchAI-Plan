from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..services.master_json import merge_master_json
from ..utils.vsai_geometry import (
    GeometryValidationError,
    find_room_overlaps,
    validate_floor_plan,
    validate_polygon,
)
from .vsai_rules import RULE_DEFINITIONS, RuleDefinition, evaluate_rules


class VsaiInputError(ValueError):
    """Raised when a Master JSON cannot be processed as Stage 1 input."""


PROCESSING_STATUSES = {"pending", "processing", "completed", "failed", "skipped"}
MASTER_OBJECT_SECTIONS = {
    "land_info",
    "buildable_footprint",
    "floor_plan",
    "structural_rectification",
    "interior_layout",
    "exterior_landscape",
}


@dataclass(frozen=True)
class RectificationDefinition:
    rule_id: str
    element_type: str
    proposer: Callable[[list[list[float]]], list[list[float]]]
    reason: str


def prepare_master_json(
    project_id: str,
    stored_master_json: Mapping[str, Any] | None,
    supplied_master_json: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if supplied_master_json is not None:
        _validate_master_contract(supplied_master_json)
        if supplied_master_json.get("project_id") != project_id:
            raise VsaiInputError("Supplied Master JSON project_id must match the requested project.")
    if supplied_master_json is None:
        candidate = deepcopy(stored_master_json) if stored_master_json is not None else None
    else:
        if stored_master_json is None:
            candidate = deepcopy(dict(supplied_master_json))
        else:
            # Only baseline sections are accepted from the optional payload. Keep VSAI,
            # downstream component outputs, and statuses already held by the project.
            baseline = {
                key: deepcopy(supplied_master_json[key])
                for key in ("project_name", "land_info", "buildable_footprint", "floor_plan")
                if key in supplied_master_json
            }
            candidate = deepcopy(dict(stored_master_json))
            candidate.update(baseline)

    if not isinstance(candidate, dict):
        raise VsaiInputError("The project has no Master JSON document.")
    _validate_master_contract(candidate)
    if candidate.get("project_id") != project_id:
        raise VsaiInputError("Stored Master JSON project_id does not match the requested project.")
    if not isinstance(candidate.get("floor_plan"), dict):
        raise VsaiInputError("Master JSON floor_plan must be an object.")
    try:
        validate_floor_plan(candidate["floor_plan"])
    except ValueError as error:
        raise VsaiInputError(str(error)) from error
    return candidate


def _validate_master_contract(document: Mapping[str, Any]) -> None:
    if not isinstance(document, Mapping):
        raise VsaiInputError("Master JSON must be an object.")
    if not isinstance(document.get("project_id"), str) or not document["project_id"].strip():
        raise VsaiInputError("Master JSON project_id must be a non-empty string.")
    if not isinstance(document.get("project_name"), str) or not document["project_name"].strip():
        raise VsaiInputError("Master JSON project_name must be a non-empty string.")
    for section in MASTER_OBJECT_SECTIONS:
        if section in document and not isinstance(document[section], dict):
            raise VsaiInputError(f"Master JSON {section} must be an object.")
    processing = document.get("processing")
    if not isinstance(processing, dict):
        raise VsaiInputError("Master JSON processing must be an object.")
    for component, state in processing.items():
        if not isinstance(state, dict):
            raise VsaiInputError(f"Master JSON processing.{component} must be an object.")
        component_status = state.get("status")
        if component_status is not None and component_status not in PROCESSING_STATUSES:
            raise VsaiInputError(
                f"Master JSON processing.{component}.status is not a supported processing status."
            )


def run_vsai_rectifier(
    master_json: Mapping[str, Any],
    rules: tuple[RuleDefinition, ...] = RULE_DEFINITIONS,
    rectifications: tuple[RectificationDefinition, ...] = (),
) -> dict[str, Any]:
    source = deepcopy(dict(master_json))
    geometry = validate_floor_plan(source.get("floor_plan"))
    rule_evaluation = evaluate_rules(source, rules)
    corrected_geometry, corrections, correction_warnings = _apply_rectifications(
        source["floor_plan"], geometry, rectifications
    )
    corrected_polygons = validate_floor_plan(corrected_geometry)
    overlaps = find_room_overlaps(corrected_polygons["rooms"])
    geometry_violations = [
        {
            "type": "room_overlap",
            "first_room_id": overlap["first_room_id"],
            "second_room_id": overlap["second_room_id"],
            "message": "Room polygons overlap; no automatic correction was applied.",
        }
        for overlap in overlaps
    ]
    timestamp = datetime.now(timezone.utc).isoformat()
    rectification = {
        "status": "completed",
        "original_geometry": deepcopy(source["floor_plan"]),
        "corrected_geometry": corrected_geometry,
        "vastu_compliance_score": rule_evaluation["vastu_compliance_score"],
        "score_status": rule_evaluation["score_status"],
        "rule_results": rule_evaluation["rule_results"],
        "violations": rule_evaluation["violations"] + geometry_violations,
        "corrections": corrections,
        "rule_coverage": rule_evaluation["rule_coverage"],
        "unevaluable_rules": rule_evaluation["unevaluable_rules"],
        "unconfigured_rules": rule_evaluation["unconfigured_rules"],
        "geometry_checks": {
            "room_polygons_valid": True,
            "structural_element_polygons_valid": True,
            "room_overlaps": overlaps,
        },
        "warnings": [
            "No Vastu or structural rules are configured from validated project definitions.",
            "Image segmentation and image-to-vector extraction require Stage 2 AI processing.",
        ] + correction_warnings,
        "processed_at": timestamp,
    }
    updated_master_json = merge_master_json(
        source,
        {
            "structural_rectification": rectification,
            "processing": {"vsai_rectifier": {"status": "completed"}},
        },
    )
    return {"result": rectification, "master_json": updated_master_json}


def _apply_rectifications(
    floor_plan: Mapping[str, Any],
    original_geometry: dict[str, list[dict[str, Any]]],
    definitions: tuple[RectificationDefinition, ...],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    corrected = deepcopy(dict(floor_plan))
    current_polygons = deepcopy(original_geometry)
    corrections: list[dict[str, Any]] = []
    warnings: list[str] = []
    for definition in definitions:
        if definition.element_type not in corrected:
            raise ValueError(f"Unsupported rectification element type '{definition.element_type}'")
        elements = corrected.get(definition.element_type, [])
        if not isinstance(elements, list):
            raise ValueError(f"floor_plan.{definition.element_type} must be an array")
        for element in elements:
            current_element = next(
                item for item in current_polygons[definition.element_type]
                if item["id"] == element["id"]
            )
            original = deepcopy(current_element["polygon"])
            proposed = definition.proposer(deepcopy(original))
            try:
                validated = validate_polygon(
                    proposed,
                    f"rectification.{definition.rule_id}.{element['id']}",
                )
            except (GeometryValidationError, TypeError, ValueError) as error:
                corrections.append({
                    "affected_element": element["id"],
                    "rule_id": definition.rule_id,
                    "original_coordinates": original,
                    "corrected_coordinates": None,
                    "reason": definition.reason,
                    "status": "rejected",
                    "issue": str(error),
                })
                warnings.append(f"Correction '{definition.rule_id}' for '{element['id']}' was rejected.")
                continue
            original_overlaps = {
                (entry["first_room_id"], entry["second_room_id"])
                for entry in find_room_overlaps(current_polygons["rooms"])
            }
            candidate_geometry = deepcopy(current_polygons)
            candidate_element = next(
                item for item in candidate_geometry[definition.element_type]
                if item["id"] == element["id"]
            )
            candidate_element["polygon"] = validated
            candidate_overlaps = {
                (entry["first_room_id"], entry["second_room_id"])
                for entry in find_room_overlaps(candidate_geometry["rooms"])
            }
            if candidate_overlaps - original_overlaps:
                corrections.append({
                    "affected_element": element["id"],
                    "rule_id": definition.rule_id,
                    "original_coordinates": original,
                    "corrected_coordinates": None,
                    "reason": definition.reason,
                    "status": "rejected",
                    "issue": "Proposed geometry introduces a new room overlap.",
                })
                warnings.append(f"Correction '{definition.rule_id}' for '{element['id']}' was rejected.")
                continue
            element["polygon"] = validated
            current_element["polygon"] = deepcopy(validated)
            corrections.append({
                "affected_element": element["id"],
                "rule_id": definition.rule_id,
                "original_coordinates": original,
                "corrected_coordinates": deepcopy(validated),
                "reason": definition.reason,
                "status": "applied",
            })

    try:
        validate_floor_plan({
            **floor_plan,
            "rooms": corrected["rooms"],
            "structural_elements": corrected["structural_elements"],
        })
    except GeometryValidationError as error:
        raise VsaiInputError(f"Corrected geometry failed validation: {error}") from error
    return corrected, corrections, warnings
