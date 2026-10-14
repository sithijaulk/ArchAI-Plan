"""
FastAPI Router for GAB-Gen (Geo-Spatial AI Blueprint Generator).
Provides endpoints:
- GET  /api/projects/{project_id}/gab-gen/context
- POST /api/projects/{project_id}/gab-gen/upload-survey
- PUT  /api/projects/{project_id}/gab-gen/requirements
- POST /api/projects/{project_id}/gab-gen/manual-survey-data
- POST /api/projects/{project_id}/gab-gen/validate-land
- POST /api/projects/{project_id}/gab-gen/generate
- GET  /api/projects/{project_id}/gab-gen/result
- GET  /api/projects/{project_id}/gab-gen/master-json
- POST /api/projects/{project_id}/gab-gen/run (Compatibility wrapper)
"""
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.project import Project
from ..models.component_run import ComponentRun, ProjectOutput
from ..config import settings
from ..services.master_json import merge_master_json

from ..components.gab_gen.schemas import (
    ManualSurveyExtractionRequest,
    ClientRequirementsInput,
    GabGenRunOutput,
    SurveySource,
    BuildingType,
    LandExtentUnit
)
from ..components.gab_gen.survey_provider import FixtureSurveyExtractionProvider
from ..components.gab_gen.service import GabGenService
from ..components.gab_gen.vector_reconstruction.reconstruct import reconstruct_polygon

router = APIRouter(prefix="/projects/{project_id}/gab-gen", tags=["GAB-Gen"])
gab_service = GabGenService()
fixture_provider = FixtureSurveyExtractionProvider()

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/jpg", "application/pdf"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/context")
def get_gab_gen_context(project_id: str, db: Session = Depends(get_db)):
    """Fetches all stored GAB-Gen metadata, inputs, requirements, and state for a project."""
    project = _get_project_or_404(project_id, db)
    mj = project.master_json or {}
    
    # Check latest component run
    latest_run = (
        db.query(ComponentRun)
        .filter(ComponentRun.project_id == project_id, ComponentRun.component_name == "gab_gen")
        .order_by(ComponentRun.started_at.desc())
        .first()
    )

    return {
        "project_id": project.id,
        "project_name": project.project_name,
        "input_metadata": mj.get("input_metadata", {}),
        "survey_extraction": mj.get("survey_extraction", {}),
        "client_requirements": mj.get("client_requirements", {}),
        "status": mj.get("processing", {}).get("gab_gen", {}).get("status", "pending"),
        "latest_run": {
            "id": latest_run.id if latest_run else None,
            "status": latest_run.status if latest_run else None,
            "error_message": latest_run.error_message if latest_run else None
        } if latest_run else None
    }


@router.post("/upload-survey")
async def upload_survey_file(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Securely uploads deed/survey plan file (JPG, JPEG, PNG, PDF).
    Stores under project upload directory with a UUID filename.
    """
    project = _get_project_or_404(project_id, db)

    # 1. Validate file extension
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file extension '{ext}'. Allowed: {ALLOWED_EXTENSIONS}")

    # 2. Validate MIME type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported MIME type '{file.content_type}'.")

    # 3. Read content & validate size
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File exceeds maximum allowed size of 15MB.")

    # 4. Save to secure storage
    upload_dir = os.path.join(settings.upload_dir, "surveys", project_id)
    os.makedirs(upload_dir, exist_ok=True)
    stored_name = f"{uuid.uuid4()}{ext}"
    stored_path = os.path.join(upload_dir, stored_name)

    with open(stored_path, "wb") as f:
        f.write(contents)

    rel_url = f"/uploads/surveys/{project_id}/{stored_name}"
    file_metadata = {
        "original_filename": filename,
        "stored_filename": stored_name,
        "file_path": rel_url,
        "content_type": file.content_type,
        "size_bytes": len(contents),
        "uploaded_at": datetime.utcnow().isoformat()
    }

    # Update Master JSON
    project.master_json = merge_master_json(
        project.master_json,
        {
            "input_metadata": {"source_file": file_metadata},
            "processing": {"gab_gen": {"status": "input_ready"}}
        }
    )
    db.commit()

    return {
        "message": "Survey file uploaded successfully",
        "file_metadata": file_metadata
    }


@router.put("/requirements")
def update_client_requirements(
    project_id: str,
    req: ClientRequirementsInput,
    db: Session = Depends(get_db)
):
    """Saves residential client requirements."""
    project = _get_project_or_404(project_id, db)

    if req.project_name and req.project_name != project.project_name:
        project.project_name = req.project_name

    project.master_json = merge_master_json(
        project.master_json,
        {
            "client_requirements": req.model_dump(),
            "input_metadata": {
                "declared_land_extent": {
                    "value": req.declared_land_extent,
                    "unit": req.declared_land_unit.value if hasattr(req.declared_land_unit, "value") else str(req.declared_land_unit)
                },
                "scale": {"ratio": req.drawing_scale or "1:100"},
                "source_notes": req.source_notes
            }
        }
    )
    db.commit()
    db.refresh(project)

    return {
        "message": "Requirements saved successfully",
        "client_requirements": req.model_dump()
    }


@router.post("/manual-survey-data")
def save_manual_survey_data(
    project_id: str,
    survey_data: ManualSurveyExtractionRequest,
    db: Session = Depends(get_db)
):
    """
    Saves verified manual/test survey measurement extraction data.
    Adheres to the normalized schema that future EasyOCR will generate.
    """
    project = _get_project_or_404(project_id, db)

    project.master_json = merge_master_json(
        project.master_json,
        {
            "survey_extraction": survey_data.model_dump()
        }
    )
    db.commit()

    return {
        "message": "Manual survey measurements stored successfully",
        "survey_extraction": survey_data.model_dump()
    }


@router.post("/validate-land")
def preview_land_reconstruction(
    project_id: str,
    survey_data: Optional[ManualSurveyExtractionRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Pre-validates and previews mathematical vector reconstruction.
    """
    project = _get_project_or_404(project_id, db)
    mj = project.master_json or {}

    if not survey_data:
        stored_survey = mj.get("survey_extraction")
        if not stored_survey or not stored_survey.get("edges"):
            # Provide standard test fixture
            survey_data = fixture_provider.extract_survey({"fixture_name": "standard_10_perch"})
        else:
            survey_data = ManualSurveyExtractionRequest(**stored_survey)

    reconstructed = reconstruct_polygon(survey_data)
    # Remove Shapely polygon object before returning JSON
    reconstructed.pop("shapely_polygon", None)
    return reconstructed


@router.post("/generate", response_model=GabGenRunOutput)
def generate_blueprint(
    project_id: str,
    db: Session = Depends(get_db)
):
    """
    Executes the full GAB-Gen Stage 1 generation pipeline:
    Reconstructs parcel, verifies area & closures, checks setbacks,
    allocates spaces across floors, generates rooms/walls, validates,
    and updates Master JSON & ComponentRun history.
    """
    project = _get_project_or_404(project_id, db)
    mj = project.master_json or {}

    # Start run record
    run = ComponentRun(
        project_id=project_id,
        component_name="gab_gen",
        status="processing",
        input_json=mj,
        started_at=datetime.utcnow()
    )
    db.add(run)
    db.commit()

    try:
        # Load survey measurements
        survey_extraction_dict = mj.get("survey_extraction")
        if not survey_extraction_dict or not survey_extraction_dict.get("edges"):
            # Use fixture provider if no manual data entered yet
            survey_req = fixture_provider.extract_survey({"fixture_name": "standard_10_perch"})
        else:
            survey_req = ManualSurveyExtractionRequest(**survey_extraction_dict)

        # Load client requirements
        req_dict = mj.get("client_requirements")
        if not req_dict:
            # Default residential baseline
            req_obj = ClientRequirementsInput(
                project_name=project.project_name,
                declared_land_extent=10.0,
                declared_land_unit=LandExtentUnit.PERCHES,
                building_type=BuildingType.RESIDENTIAL_HOUSE,
                storey_count=1,
                rooms=[]
            )
        else:
            req_obj = ClientRequirementsInput(**req_dict)

        file_meta = mj.get("input_metadata", {}).get("source_file")

        # Execute Pipeline
        output = gab_service.run_pipeline(
            project_id=project_id,
            project_name=project.project_name,
            survey_request=survey_req,
            requirements=req_obj,
            jurisdiction="sri_lanka_uda_standard",
            file_metadata=file_meta
        )

        # Persist updated Master JSON
        project.master_json = output.master_json
        project.current_component = "gab_gen"

        # Complete run record
        run.status = output.status
        run.output_json = output.master_json
        run.completed_at = datetime.utcnow()

        db.commit()
        db.refresh(project)

        return output

    except Exception as e:
        db.rollback()
        run.status = "failed"
        run.error_message = str(e)
        run.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"GAB-Gen generation failed: {str(e)}"
        )


@router.get("/result")
def get_gab_gen_result(project_id: str, db: Session = Depends(get_db)):
    """Returns the latest generated GAB-Gen results."""
    project = _get_project_or_404(project_id, db)
    mj = project.master_json or {}
    floor_plan = mj.get("floor_plan", {})
    if not floor_plan.get("floors"):
        raise HTTPException(status_code=404, detail="No GAB-Gen blueprint has been generated yet for this project.")
    return mj


@router.get("/master-json")
def get_gab_master_json(project_id: str, db: Session = Depends(get_db)):
    """Returns the full Master JSON."""
    project = _get_project_or_404(project_id, db)
    return project.master_json


# Compatibility wrapper for existing common projects route
@router.post("/run")
def run_gab_gen_compat(project_id: str, db: Session = Depends(get_db)):
    return generate_blueprint(project_id, db)
