"""
Core Orchestration Pipeline for GAB-Gen Stage 1.
Executes the deterministic end-to-end pipeline:
  Deed/Survey Data + Requirements
  -> Mathematical Vector Reconstruction
  -> Polygon Validation
  -> Declared Land Area Cross Check
  -> Regulatory Rule Resolution
  -> Buildable Footprint Generation
  -> Stage-1 Rule-Based Space Allocation
  -> Room/Floor Blueprint & Wall Generation
  -> GAB Validation
  -> Master JSON Synthesis
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
        jurisdiction: str = "sri_lanka_uda_standard",
        file_metadata: Optional[Dict[str, Any]] = None
    ) -> GabGenRunOutput:
        # Step 1: Mathematical Vector Reconstruction
        reconstructed = reconstruct_polygon(survey_request)
        shapely_land = reconstructed.get("shapely_polygon")
        closure_error = reconstructed.get("closure_error", 0.0)

        # Step 2: Convert declared area to square meters
        unit = requirements.declared_land_unit
        if unit == LandExtentUnit.PERCHES:
            declared_sqm = requirements.declared_land_extent * PERCH_TO_SQM
        elif unit == LandExtentUnit.SQUARE_FEET:
            declared_sqm = requirements.declared_land_extent * SQFT_TO_SQM
        else:
            declared_sqm = requirements.declared_land_extent

        # Step 3: Area Cross-Check
        area_check = cross_check_land_area(
            declared_area_sqm=declared_sqm,
            reconstructed_area_sqm=reconstructed.get("reconstructed_area", 0.0),
            tolerance_percent=15.0
        )

        # Step 4: Regulatory Rule Loading
        rules = RegulatoryEngine.get_rules_for_jurisdiction(jurisdiction)
        if not rules:
            # Fallback to test rules if unknown jurisdiction
            rules = RegulatoryEngine.get_rules_for_jurisdiction("research_test_relaxed")

        # Step 5: Buildable Footprint
        buildable_res = compute_buildable_footprint(
            shapely_poly=shapely_land,
            edges=reconstructed.get("edges", []),
            rules=rules
        )
        shapely_buildable = buildable_res.get("shapely_polygon")
        buildable_area = buildable_res.get("area", 0.0)

        # Step 6: Rule-based Stage-1 Space Allocation
        allocation_res = self.allocation_provider.allocate_space(
            buildable_area=buildable_area,
            requirements=requirements
        )

        # Check for architectural infeasibility
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
                file_metadata=file_metadata
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
            floors=floors
        )

        # Step 9: Synthesize Centralized Master JSON
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
            file_metadata=file_metadata
        )

        return GabGenRunOutput(
            project_id=project_id,
            project_name=project_name,
            status=validation.status,
            master_json=master_json,
            validation=validation,
            warnings=validation.warnings
        )
