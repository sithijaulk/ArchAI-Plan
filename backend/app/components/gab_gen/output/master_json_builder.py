"""
GAB-Gen Centralized Master JSON builder.
Strictly adheres to non-destructive data principle:
- Accepts existing_master_json and deepcopies it.
- Updates ONLY GAB-owned sections:
    input_metadata
    survey_extraction
    land_info
    geometry_validation
    regulatory_rules
    buildable_footprint
    client_requirements
    space_allocation
    floor_plan
    gab_gen_validation
    processing.gab_gen
- Preserves all unrelated sections (e.g., structural_rectification, interior_layout, exterior_landscape, etc.).
"""
import copy
from typing import Any, Dict, List, Optional
from ..schemas import (
    ManualSurveyExtractionRequest,
    ClientRequirementsInput,
    FloorPlanDefinition,
    ValidationResult,
    RegulatoryRule
)

SCHEMA_VERSION = "2.0.0"
GAB_GEN_VERSION = "1.0.0"


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
    file_metadata: Optional[Dict[str, Any]] = None,
    existing_master_json: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Constructs or non-destructively merges GAB-Gen results into Centralized Master JSON.
    """
    # 1. Non-destructively start from copy of existing Master JSON
    mj = copy.deepcopy(existing_master_json or {})

    # Top-level identifiers
    mj["project_id"] = project_id
    mj["project_name"] = project_name
    mj["schema_version"] = mj.get("schema_version") or SCHEMA_VERSION
    mj["units"] = "meters"

    # Merge input_metadata
    input_meta = mj.get("input_metadata", {})
    if file_metadata:
        input_meta["source_file"] = file_metadata
    input_meta["declared_land_extent"] = {
        "value": requirements.declared_land_extent,
        "unit": requirements.declared_land_unit.value if hasattr(requirements.declared_land_unit, "value") else str(requirements.declared_land_unit)
    }
    input_meta["scale"] = {"ratio": requirements.drawing_scale or "1:100"}
    if requirements.source_notes:
        input_meta["source_notes"] = requirements.source_notes
    if requirements.regulatory_context:
        input_meta["regulatory_context"] = requirements.regulatory_context.model_dump()
    mj["input_metadata"] = input_meta

    # GAB-owned domain sections
    mj["survey_extraction"] = {
        "provider": survey_request.source.value if hasattr(survey_request.source, "value") else str(survey_request.source),
        "north_angle": survey_request.north_angle,
        "reference_edge": survey_request.reference_edge,
        "edges": [e.model_dump() for e in survey_request.edges]
    }

    mj["land_info"] = {
        "source_land_polygon": reconstructed_data.get("vertices", []),
        "reconstructed_area": reconstructed_data.get("reconstructed_area", 0.0),
        "declared_area": validation.declared_area_sqm or 0.0,
        "area_difference_percent": validation.area_difference_percent or 0.0,
        "perimeter": reconstructed_data.get("perimeter", 0.0)
    }

    mj["geometry_validation"] = {
        "valid": reconstructed_data.get("is_valid", False),
        "closure_error": reconstructed_data.get("closure_error", 0.0),
        "relative_error": reconstructed_data.get("relative_error", 0.0),
        "warnings": reconstructed_data.get("warnings", [])
    }

    mj["regulatory_rules"] = {
        "jurisdiction": rules[0].jurisdiction_id if rules else "none",
        "applied_rules": [r.model_dump() for r in rules]
    }

    mj["buildable_footprint"] = {
        "polygon": buildable_data.get("polygon", []),
        "area": buildable_data.get("area", 0.0),
        "valid": buildable_data.get("valid", False)
    }

    mj["client_requirements"] = requirements.model_dump()

    mj["space_allocation"] = {
        "provider": allocation_data.get("provider", "rule_based_baseline"),
        "model_version": allocation_data.get("model_version"),
        "total_demanded_area": allocation_data.get("total_demanded_area", 0.0),
        "total_capacity": allocation_data.get("total_capacity", 0.0),
        "floors": allocation_data.get("floors", [])
    }

    mj["floor_plan"] = {
        "floors": [fl.model_dump() for fl in floors]
    }

    # Roof Geometry (Vectorized Canonical P0 coordinates)
    from ..blueprint.roof_generator import generate_roof_geometry
    shapely_buildable = buildable_data.get("shapely_polygon")
    if shapely_buildable is None and buildable_data.get("polygon"):
        from shapely.geometry import Polygon
        pts = [(p["x"], p["y"]) for p in buildable_data.get("polygon", [])]
        if len(pts) >= 3:
            shapely_buildable = Polygon(pts)

    roof_geom = generate_roof_geometry(
        building_footprint_poly=shapely_buildable,
        roof_pref=requirements.roof_preference
    )
    mj["roof_geometry"] = roof_geom.model_dump()

    # Building Footprint Candidate (Candidate 1: Optimal Setback Envelope)
    mj["building_footprint"] = {
        "candidate_id": "FP_PRIMARY",
        "shape_type": "conformal_offset",
        "polygon": buildable_data.get("polygon", []),
        "area": buildable_data.get("area", 0.0)
    }

    mj["gab_gen_validation"] = validation.model_dump()

    # Preserve or initialize edit history
    mj["edit_history"] = mj.get("edit_history", [])

    # Update processing state under GAB key without modifying other components
    processing = mj.get("processing", {})
    processing["gab_gen"] = {
        "status": validation.status,
        "stage": "stage_1",
        "gab_gen_version": GAB_GEN_VERSION,
        "survey_provider": survey_request.source.value if hasattr(survey_request.source, "value") else str(survey_request.source),
        "allocation_provider": allocation_data.get("provider", "rule_based_baseline")
    }
    mj["processing"] = processing

    return mj
