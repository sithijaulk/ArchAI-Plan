"""
GAB-Gen Centralized Master JSON builder.
Strictly adheres to non-destructive data principle:
Preserves legal source land geometry completely separate from derived buildable footprint and generated floors.
"""
from typing import Any, Dict, List
from ..schemas import (
    ManualSurveyExtractionRequest,
    ClientRequirementsInput,
    FloorPlanDefinition,
    ValidationResult,
    RegulatoryRule
)


def build_gab_master_json(
    project_id: str,
    project_name: str,
    survey_request: ManualSurveyExtractionRequest,
    reconstructed_data: Dict[str, Any],
    requirements: ClientRequirementsInput,
    rules: List[RegulatoryRule],
    buildable_data: Dict[str, Any],
    allocation_data: Dict[str, Any],
    floors: List[FloorPlanDefinition],
    validation: ValidationResult,
    file_metadata: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """
    Constructs the standard Master JSON structure for GAB-Gen.
    """
    return {
        "project_id": project_id,
        "project_name": project_name,
        "units": "meters",
        "input_metadata": {
            "source_file": file_metadata or {},
            "declared_land_extent": {
                "value": requirements.declared_land_extent,
                "unit": requirements.declared_land_unit.value if hasattr(requirements.declared_land_unit, "value") else requirements.declared_land_unit
            },
            "scale": {
                "ratio": requirements.drawing_scale or "1:100"
            },
            "source_notes": requirements.source_notes
        },
        "survey_extraction": {
            "provider": survey_request.source.value if hasattr(survey_request.source, "value") else survey_request.source,
            "north_angle": survey_request.north_angle,
            "reference_edge": survey_request.reference_edge,
            "edges": [e.model_dump() for e in survey_request.edges]
        },
        "land_info": {
            "source_land_polygon": reconstructed_data.get("vertices", []),
            "reconstructed_area": reconstructed_data.get("reconstructed_area", 0.0),
            "declared_area": validation.declared_area_sqm or 0.0,
            "area_difference_percent": validation.area_difference_percent or 0.0,
            "perimeter": reconstructed_data.get("perimeter", 0.0)
        },
        "geometry_validation": {
            "valid": reconstructed_data.get("is_valid", False),
            "closure_error": reconstructed_data.get("closure_error", 0.0),
            "relative_error": reconstructed_data.get("relative_error", 0.0),
            "warnings": reconstructed_data.get("warnings", [])
        },
        "regulatory_rules": {
            "jurisdiction": rules[0].jurisdiction if rules else "sri_lanka_uda_standard",
            "applied_rules": [r.model_dump() for r in rules]
        },
        "buildable_footprint": {
            "polygon": buildable_data.get("polygon", []),
            "area": buildable_data.get("area", 0.0),
            "valid": buildable_data.get("valid", False)
        },
        "client_requirements": requirements.model_dump(),
        "space_allocation": {
            "provider": allocation_data.get("provider", "rule_based_baseline"),
            "model_version": allocation_data.get("model_version"),
            "total_demanded_area": allocation_data.get("total_demanded_area", 0.0),
            "total_capacity": allocation_data.get("total_capacity", 0.0),
            "floors": allocation_data.get("floors", [])
        },
        "floor_plan": {
            "floors": [fl.model_dump() for fl in floors]
        },
        "gab_gen_validation": validation.model_dump(),
        "processing": {
            "gab_gen": {
                "status": validation.status,
                "stage": "stage_1",
                "survey_provider": survey_request.source.value if hasattr(survey_request.source, "value") else str(survey_request.source),
                "allocation_provider": allocation_data.get("provider", "rule_based_baseline")
            }
        }
    }
