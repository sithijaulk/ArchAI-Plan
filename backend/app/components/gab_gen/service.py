"""
Core Orchestration Pipeline for GAB-Gen Stage 1.
Executes the deterministic end-to-end pipeline:
  Deed/Survey Data + Requirements + Regulatory Context
  -> Mathematical Vector Reconstruction in Canonical P0 Coordinates
  -> Auditable Polygon Validation (no silent repairs)
  -> Declared Land Area Cross Check with configurable tolerance
  -> Verified Regulatory Rule Resolution (no silent fallback fabrication)
  -> Deterministic Edge-Aware Buildable Footprint Generation
  -> Rule-Based Space Allocation with Hard Min Area Constraints & Stair Alignment
  -> Room/Floor Blueprint & Wall Generation with Proportional Targets
  -> Full GAB Validation
  -> Non-Destructive Master JSON Synthesis
"""
from typing import Any, Dict, List, Optional
from shapely.geometry import Polygon

from .schemas import (
    ManualSurveyExtractionRequest,
    ClientRequirementsInput,
    LandExtentUnit,
    GabGenRunOutput,
    ValidationResult
)
from .vector_reconstruction.reconstruct import reconstruct_polygon, PERCH_TO_SQM, SQFT_TO_SQM
from .regulations.rules import RegulatoryEngine
from .buildable_footprint.compute import compute_buildable_footprint
from .space_allocation.allocator import RuleBasedSpaceAllocationProvider
from .blueprint.generator import generate_blueprint_floors
from .validation.validator import cross_check_land_area, validate_gab_geometry
from .output.master_json_builder import build_gab_master_json


class GabGenService:
    """
    Service responsible for coordinating the GAB-Gen processing workflow.
    """

    def __init__(self):
        self.allocation_provider = RuleBasedSpaceAllocationProvider()

    def run_pipeline(
        self,
        project_id: str,
        project_name: str,
        survey_request: ManualSurveyExtractionRequest,
        requirements: ClientRequirementsInput,
        jurisdiction: Optional[str] = None,
        file_metadata: Optional[Dict[str, Any]] = None,
        existing_master_json: Optional[Dict[str, Any]] = None,
        allow_research_test: bool = False
    ) -> GabGenRunOutput:
        # Determine jurisdiction from requirements or parameter
        jurisdiction_id = (
            jurisdiction
            or (requirements.regulatory_context.jurisdiction_id if requirements.regulatory_context else None)
            or "sri_lanka_uda_standard"
        )

        # Step 1: Mathematical Vector Reconstruction in Canonical P0 Coordinates
        reconstructed = reconstruct_polygon(survey_request)
        shapely_land = reconstructed.get("shapely_polygon")
        closure_error = reconstructed.get("closure_error", 0.0)

        # Step 2: Convert declared area to square meters
        from .input.units import convert_area_to_sqm
        try:
            declared_sqm = convert_area_to_sqm(requirements.declared_land_extent, requirements.declared_land_unit)
        except Exception:
            declared_sqm = requirements.declared_land_extent

        # Step 3: Area Cross-Check using configurable tolerance
        area_check = cross_check_land_area(
            declared_area_sqm=declared_sqm,
            reconstructed_area_sqm=reconstructed.get("reconstructed_area", 0.0)
        )

        # Step 4: Regulatory Rule Loading without silent fabrication
        rules = RegulatoryEngine.get_rules_for_jurisdiction(
            jurisdiction_id=jurisdiction_id,
            allow_research_test=allow_research_test
        )

        if not rules:
            val_res = ValidationResult(
                valid=False,
                status="regulatory_configuration_required",
                closure_error=closure_error,
                declared_area_sqm=area_check.get("declared_area_sqm"),
                reconstructed_area_sqm=area_check.get("reconstructed_area_sqm"),
                area_difference_percent=area_check.get("area_difference_percent"),
                violations=[f"No verified regulatory configuration found for jurisdiction '{jurisdiction_id}'."],
                warnings=reconstructed.get("warnings", [])
            )
            master_json = build_gab_master_json(
                project_id=project_id,
                project_name=project_name,
                survey_request=survey_request,
                reconstructed_data=reconstructed,
                requirements=requirements,
                rules=[],
                buildable_data={"polygon": [], "area": 0.0, "valid": False},
                allocation_data={},
                floors=[],
                validation=val_res,
                file_metadata=file_metadata,
                existing_master_json=existing_master_json
            )
            return GabGenRunOutput(
                project_id=project_id,
                project_name=project_name,
                status="regulatory_configuration_required",
                master_json=master_json,
                validation=val_res,
                warnings=val_res.warnings
            )

        # Step 5: Buildable Footprint Engine
        buildable_res = compute_buildable_footprint(
            shapely_poly=shapely_land,
            edges=reconstructed.get("edges", []),
            rules=rules
        )
        shapely_buildable = buildable_res.get("shapely_polygon")
        buildable_area = buildable_res.get("area", 0.0)

        if not buildable_res.get("valid"):
            val_res = ValidationResult(
                valid=False,
                status=buildable_res.get("status", "infeasible"),
                closure_error=closure_error,
                declared_area_sqm=area_check.get("declared_area_sqm"),
                reconstructed_area_sqm=area_check.get("reconstructed_area_sqm"),
                area_difference_percent=area_check.get("area_difference_percent"),
                violations=[buildable_res.get("error", "Buildable footprint computation failed or collapsed site.")],
                warnings=reconstructed.get("warnings", [])
            )
            master_json = build_gab_master_json(
                project_id=project_id,
                project_name=project_name,
                survey_request=survey_request,
                reconstructed_data=reconstructed,
                requirements=requirements,
                rules=rules,
                buildable_data=buildable_res,
                allocation_data={},
                floors=[],
                validation=val_res,
                file_metadata=file_metadata,
                existing_master_json=existing_master_json
            )
            return GabGenRunOutput(
                project_id=project_id,
                project_name=project_name,
                status=val_res.status,
                master_json=master_json,
                validation=val_res,
                warnings=val_res.warnings
            )

        # Step 6: Rule-based Stage-1 Space Allocation
        allocation_res = self.allocation_provider.allocate_space(
            buildable_area=buildable_area,
            requirements=requirements
        )

        if not allocation_res.get("feasible"):
            val_res = ValidationResult(
                valid=False,
                status="infeasible",
                closure_error=closure_error,
                declared_area_sqm=area_check.get("declared_area_sqm"),
                reconstructed_area_sqm=area_check.get("reconstructed_area_sqm"),
                area_difference_percent=area_check.get("area_difference_percent"),
                violations=[allocation_res.get("details", "Client programme exceeds buildable footprint capacity.")],
                warnings=reconstructed.get("warnings", [])
            )
            master_json = build_gab_master_json(
                project_id=project_id,
                project_name=project_name,
                survey_request=survey_request,
                reconstructed_data=reconstructed,
                requirements=requirements,
                rules=rules,
                buildable_data=buildable_res,
                allocation_data=allocation_res,
                floors=[],
                validation=val_res,
                file_metadata=file_metadata,
                existing_master_json=existing_master_json
            )
            return GabGenRunOutput(
                project_id=project_id,
                project_name=project_name,
                status="infeasible",
                master_json=master_json,
                validation=val_res,
                warnings=val_res.warnings
            )

        # Step 7: Blueprint Generation (Floors, Rooms, Walls)
        floors = generate_blueprint_floors(
            buildable_poly=shapely_buildable,
            floor_allocations=allocation_res.get("floors", [])
        )

        # Step 8: Complete Validation
        validation = validate_gab_geometry(
            land_poly=shapely_land,
            buildable_poly=shapely_buildable,
            closure_error=closure_error,
            area_check=area_check,
            floors=floors,
            expected_storey_count=requirements.storey_count,
            rules=rules
        )

        # If reconstruction flagged needs_verification, ensure overall status reflects it
        if reconstructed.get("needs_verification") and validation.status == "completed":
            validation.status = "needs_verification"

        # Step 9: Synthesize Centralized Master JSON Non-Destructively
        master_json = build_gab_master_json(
            project_id=project_id,
            project_name=project_name,
            survey_request=survey_request,
            reconstructed_data=reconstructed,
            requirements=requirements,
            rules=rules,
            buildable_data=buildable_res,
            allocation_data=allocation_res,
            floors=floors,
            validation=validation,
            file_metadata=file_metadata,
            existing_master_json=existing_master_json
        )

        return GabGenRunOutput(
            project_id=project_id,
            project_name=project_name,
            status=validation.status,
            master_json=master_json,
            validation=validation,
            warnings=validation.warnings
        )
