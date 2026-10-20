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
    RegulatoryRule,
    FloorPlanCandidate
)

SCHEMA_VERSION = "2.1.0"
GAB_GEN_VERSION = "1.5.0"


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
    existing_master_json: Optional[Dict[str, Any]] = None,
    candidates: Optional[List[FloorPlanCandidate]] = None,
    selected_candidate_id: Optional[str] = None,
    generation_metadata: Optional[Dict[str, Any]] = None
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
    survey_dict = survey_request.model_dump()
    mj["survey_extraction"] = {
        "provider": survey_request.source.value if hasattr(survey_request.source, "value") else str(survey_request.source),
        "north_angle": survey_request.north_angle,
        "north_angle_origin": survey_request.north_angle_origin,
        "reference_edge": survey_request.reference_edge,
        "verification_status": survey_request.verification_status.value if hasattr(survey_request.verification_status, "value") else str(survey_request.verification_status),
        "verified_by_user": survey_request.verified_by_user,
        "verified_at": survey_request.verified_at,
        "drawing_scale": survey_request.drawing_scale,
        "drawing_scale_origin": survey_request.drawing_scale_origin,
        "selected_page_number": survey_request.selected_page_number,
        "total_pages": survey_request.total_pages,
        "georeference_status": survey_request.georeference_status.value if hasattr(survey_request.georeference_status, "value") else str(survey_request.georeference_status),
        "crs_identifier": survey_request.crs_identifier,
        "edges": [e.model_dump() for e in survey_request.edges]
    }

    mj["land_info"] = {
        "source_land_polygon": reconstructed_data.get("vertices", []),
        "bowditch_adjusted_polygon": reconstructed_data.get("bowditch_adjusted_vertices", []),
        "traverse_adjustment_method": reconstructed_data.get("traverse_adjustment_method", "none"),
        "reconstructed_area": reconstructed_data.get("reconstructed_area", 0.0),
        "declared_area": validation.declared_area_sqm or 0.0,
        "area_difference_percent": validation.area_difference_percent or 0.0,
        "perimeter": reconstructed_data.get("perimeter", 0.0),
        "coordinate_origin": reconstructed_data.get("coordinate_origin", "P0 local")
    }

    mj["geometry_validation"] = {
        "valid": reconstructed_data.get("is_valid", False),
        "closure_error": reconstructed_data.get("closure_error", 0.0),
        "relative_error": reconstructed_data.get("relative_error", 0.0),
        "warnings": reconstructed_data.get("warnings", [])
    }

    # Enhanced Regulatory Provenance in Master JSON
    reg_res_dict = validation.regulatory_resolution.model_dump() if validation.regulatory_resolution else None
    mj["regulatory_rules"] = {
        "jurisdiction": rules[0].jurisdiction_id if rules else "none",
        "regulatory_resolution": reg_res_dict,
        "source_registry_version": "1.0.0",
        "authority_registry_version": "1.0.0",
        "compliance_verdict": validation.compliance_verdict.value if hasattr(validation.compliance_verdict, "value") else str(validation.compliance_verdict),
        "unresolved_requirements": validation.unresolved_requirements,
        "conflicting_requirements": validation.conflicting_requirements,
        "site_restriction_summary": validation.site_restriction_summary,
        "applied_rules": [r.model_dump() for r in rules]
    }

    mj["buildable_footprint"] = {
        "polygon": buildable_data.get("polygon", []),
        "area": buildable_data.get("area", 0.0),
        "valid": buildable_data.get("valid", False),
        "provisional": buildable_data.get("provisional", False),
        "provisional_reasons": buildable_data.get("provisional_reasons", []),
        "preview_label": buildable_data.get("preview_label", "BUILDABLE ENVELOPE")
    }

    mj["client_requirements"] = requirements.model_dump()

    mj["space_allocation"] = {
        "provider": allocation_data.get("provider", "rule_based_baseline"),
        "model_version": allocation_data.get("model_version"),
        "total_demanded_area": allocation_data.get("total_demanded_area", 0.0),
        "total_capacity": allocation_data.get("total_capacity", 0.0),
        "floors": allocation_data.get("floors", [])
    }

    # Active / Selected Floor Plan Definition (Directly consumed by 2D/3D Viewer and Editor)
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

    # Active Building Footprint
    mj["building_footprint"] = {
        "candidate_id": selected_candidate_id or "FP_CANDIDATE_001",
        "shape_type": "conformal_offset",
        "polygon": buildable_data.get("polygon", []),
        "area": buildable_data.get("area", 0.0)
    }

    # Phase 5: Multi-Candidate Floor Plan Options & Selection Pool
    cands_list = [c.model_dump() for c in (candidates or [])]
    mj["candidate_generation"] = {
        "generation_run_id": (generation_metadata or {}).get("generation_run_id", f"RUN_{project_id[:8]}"),
        "generator_version": GAB_GEN_VERSION,
        "feature_schema_version": "1.0.0",
        "ranking_method": (generation_metadata or {}).get("ranking_method", "heuristic_v1"),
        "requested_candidate_count": (generation_metadata or {}).get("requested_candidate_count", len(cands_list)),
        "feasible_candidate_count": len(cands_list),
        "rejected_candidate_count": (generation_metadata or {}).get("rejected_candidate_count", 0),
        "selected_candidate_id": selected_candidate_id or (cands_list[0]["candidate_id"] if cands_list else None),
        "candidates": cands_list
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
        "allocation_provider": allocation_data.get("provider", "rule_based_baseline"),
        "candidate_count": len(cands_list),
        "selected_candidate_id": selected_candidate_id or (cands_list[0]["candidate_id"] if cands_list else None)
    }
    mj["processing"] = processing

    return mj

