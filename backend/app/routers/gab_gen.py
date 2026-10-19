"""
FastAPI Router for GAB-Gen (Geo-Spatial AI Blueprint Generator).
Enforces real user workflow preconditions:
- Requires verified manual survey boundaries (edges >= 3)
- Requires uploaded deed/survey source file (unless explicit test mode)
- Requires complete client requirements
- Requires valid regulatory context
- Never silently generates from default fixtures or fake residential requirements
- Non-destructively merges Master JSON
- Secure file upload with magic byte / format validation (Pillow verify & PDF signature)
"""
import io
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from sqlalchemy.orm import Session
from PIL import Image

from ..database import get_db
from ..models.project import Project
from ..models.component_run import ComponentRun
from ..config import settings
from ..services.master_json import merge_master_json

from ..components.gab_gen.schemas import (
    ManualSurveyExtractionRequest,
    ClientRequirementsInput,
    GabGenRunOutput,
    SurveySource,
    BuildingType,
    LandExtentUnit,
    RegulatoryRule
)
from ..components.gab_gen.survey_provider import FixtureSurveyExtractionProvider
from ..components.gab_gen.service import GabGenService
from ..components.gab_gen.vector_reconstruction.reconstruct import reconstruct_polygon
from ..components.gab_gen.regulations.rules import RegulatoryEngine

router = APIRouter(prefix="/projects/{project_id}/gab-gen", tags=["GAB-Gen"])
gab_service = GabGenService()
fixture_provider = FixtureSurveyExtractionProvider()

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/jpg", "application/pdf"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}

# Configurable max upload size from validation config (default 15MB)
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "components", "gab_gen", "data", "gab_validation_config.json")
def get_max_upload_size() -> int:
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return int(cfg.get("max_upload_size_bytes", {}).get("value", 15 * 1024 * 1024))
        except Exception:
            pass
    return 15 * 1024 * 1024


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _validate_file_content(contents: bytes, ext: str):
    """
    Validates file integrity using Pillow verify() for images or signature check for PDF.
    Does not trust MIME type or extension alone.
    """
    if ext in (".jpg", ".jpeg", ".png"):
        try:
            img = Image.open(io.BytesIO(contents))
            img.verify()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid or corrupted image file: {str(e)}")
    elif ext == ".pdf":
        # Check PDF header signature '%PDF-'
        if not contents.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Invalid PDF file: Missing standard %PDF- header signature.")
        # Check for EOF marker in last 1024 bytes
        if b"%%EOF" not in contents[-1024:]:
            raise HTTPException(status_code=400, detail="Invalid or truncated PDF file: Missing EOF marker.")


@router.get("/context")
def get_gab_gen_context(project_id: str, db: Session = Depends(get_db)):
    """Fetches stored GAB-Gen inputs, requirements, and latest state."""
    project = _get_project_or_404(project_id, db)
    mj = project.master_json or {}

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
    Performs content-level validation (Pillow verify / PDF signature) and stores under UUID filename.
    Never exposes internal server paths.
    """
    project = _get_project_or_404(project_id, db)

    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{ext}'. Allowed: {list(ALLOWED_EXTENSIONS)}"
        )

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported MIME type '{file.content_type}'.")

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    max_size = get_max_upload_size()
    if len(contents) > max_size:
        raise HTTPException(status_code=400, detail=f"File exceeds maximum allowed size of {max_size // (1024*1024)}MB.")

    # Validate actual file payload content
    _validate_file_content(contents, ext)

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
        "uploaded_at": datetime.now(timezone.utc).isoformat()
    }

    # Non-destructively merge input_metadata
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


@router.delete("/survey-file")
def remove_survey_file(
    project_id: str,
    db: Session = Depends(get_db)
):
    """Removes currently uploaded survey plan file."""
    project = _get_project_or_404(project_id, db)
    mj = project.master_json or {}
    source_file = mj.get("input_metadata", {}).get("source_file")

    if source_file and source_file.get("stored_filename"):
        stored_path = os.path.join(settings.upload_dir, "surveys", project_id, source_file["stored_filename"])
        if os.path.exists(stored_path):
            try:
                os.remove(stored_path)
            except Exception:
                pass

    if "input_metadata" in mj and "source_file" in mj["input_metadata"]:
        del mj["input_metadata"]["source_file"]
    project.master_json = mj
    db.commit()
    return {"message": "Survey file removed successfully"}


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
                "source_notes": req.source_notes,
                "regulatory_context": req.regulatory_context.model_dump() if req.regulatory_context else {}
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
    Saves verified manual survey measurement extraction data.
    If source was marked 'fixture' but is edited by user, provenance is saved as 'manual'.
    """
    project = _get_project_or_404(project_id, db)

    # Convert to dictionary and verify edge count
    data_dict = survey_data.model_dump()
    if len(data_dict.get("edges", [])) < 3:
        raise HTTPException(status_code=400, detail="Survey boundary must contain at least 3 edges.")

    project.master_json = merge_master_json(
        project.master_json,
        {
            "survey_extraction": data_dict
        }
    )
    db.commit()

    return {
        "message": "Manual survey measurements stored successfully",
        "survey_extraction": data_dict
    }


@router.post("/validate-land")
def preview_land_reconstruction(
    project_id: str,
    survey_data: Optional[ManualSurveyExtractionRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Pre-validates and previews mathematical vector reconstruction in canonical P0 coordinates.
    Does NOT silently repair or replace with fixtures.
    """
    project = _get_project_or_404(project_id, db)
    mj = project.master_json or {}

    if not survey_data:
        stored_survey = mj.get("survey_extraction")
        if not stored_survey or not stored_survey.get("edges"):
            raise HTTPException(
                status_code=400,
                detail="No survey boundary data available. Please provide survey measurements with at least 3 edges."
            )
        survey_data = ManualSurveyExtractionRequest(**stored_survey)

    reconstructed = reconstruct_polygon(survey_data)
    reconstructed.pop("shapely_polygon", None)
    return reconstructed


@router.get("/regulatory-rules")
def get_available_regulatory_rules(
    allow_research_test: bool = Query(default=False)
):
    """Returns available regulatory rules in repository."""
    rules = RegulatoryEngine.load_all_rules()
    if not allow_research_test:
        rules = [r for r in rules if r.verification_status == "verified"]
    return [r.model_dump() for r in rules]


@router.post("/load-test-fixture")
def load_test_fixture(
    project_id: str,
    fixture_name: str = Query(default="standard_10_perch"),
    db: Session = Depends(get_db)
):
    """
    EXPLICIT DEV/TEST ONLY: Loads a known test fixture into survey_extraction.
    Clearly marked as test fixture with fixture source provenance.
    """
    project = _get_project_or_404(project_id, db)
    fixture_data = fixture_provider.extract_survey({"fixture_name": fixture_name})
    data_dict = fixture_data.model_dump()

    project.master_json = merge_master_json(
        project.master_json,
        {"survey_extraction": data_dict}
    )
    db.commit()
    return {
        "message": f"Dev fixture '{fixture_name}' loaded successfully",
        "survey_extraction": data_dict
    }


@router.post("/generate", response_model=GabGenRunOutput)
def generate_blueprint(
    project_id: str,
    dev_test_mode: bool = Query(default=False, description="Enable explicit test/research mode for mock/relaxed generation"),
    db: Session = Depends(get_db)
):
    """
    Executes the full GAB-Gen Stage 1 generation pipeline:
    Precondition enforcement:
    1. Uploaded survey source file (or explicit dev_test_mode)
    2. Client requirements exists with declared extent
    3. Manual survey extraction data exists with at least 3 edges
    4. Valid verified regulatory configuration exists

    Never silently falls back to fixtures or default houses.
    """
    project = _get_project_or_404(project_id, db)
    mj = project.master_json or {}

    # Precondition 1: Survey extraction data must exist
    survey_extraction_dict = mj.get("survey_extraction")
    if not survey_extraction_dict or not survey_extraction_dict.get("edges"):
        raise HTTPException(
            status_code=400,
            detail="Survey boundary data is missing. Please enter boundary measurements with at least 3 edges."
        )

    if len(survey_extraction_dict.get("edges", [])) < 3:
        raise HTTPException(
            status_code=400,
            detail="At least 3 boundary edges are required to generate blueprint geometry."
        )

    try:
        survey_req = ManualSurveyExtractionRequest(**survey_extraction_dict)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid survey extraction data: {str(e)}")

    # Precondition 2: Client requirements must exist
    req_dict = mj.get("client_requirements")
    if not req_dict:
        raise HTTPException(
            status_code=400,
            detail="Client building programme requirements are missing. Please configure project requirements before generating."
        )

    try:
        req_obj = ClientRequirementsInput(**req_dict)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid client requirements input: {str(e)}")

    # Precondition 3: Source file check (unless explicit dev_test_mode)
    file_meta = mj.get("input_metadata", {}).get("source_file")
    if not file_meta and not dev_test_mode:
        raise HTTPException(
            status_code=400,
            detail="Uploaded deed/survey plan file is required for verified blueprint generation. (Dev mode can override with ?dev_test_mode=true)."
        )

    # Precondition 4: Regulatory context check
    jurisdiction_id = (
        req_obj.regulatory_context.jurisdiction_id if req_obj.regulatory_context
        else "sri_lanka_uda_standard"
    )
    available_rules = RegulatoryEngine.get_rules_for_jurisdiction(
        jurisdiction_id=jurisdiction_id,
        allow_research_test=dev_test_mode
    )
    if not available_rules:
        raise HTTPException(
            status_code=400,
            detail=f"regulatory_configuration_required: No verified regulatory rules found for jurisdiction '{jurisdiction_id}'."
        )

    # Start run record
    run = ComponentRun(
        project_id=project_id,
        component_name="gab_gen",
        status="processing",
        input_json=mj,
        started_at=datetime.now(timezone.utc)
    )
    db.add(run)
    db.commit()

    try:
        # Execute Pipeline Non-Destructively
        output = gab_service.run_pipeline(
            project_id=project_id,
            project_name=project.project_name,
            survey_request=survey_req,
            requirements=req_obj,
            jurisdiction=jurisdiction_id,
            file_metadata=file_meta,
            existing_master_json=mj,
            allow_research_test=dev_test_mode
        )

        # Update Project Master JSON non-destructively
        project.master_json = output.master_json
        project.current_component = "gab_gen"

        # Complete run record
        run.status = output.status
        run.output_json = output.master_json
        run.completed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(project)

        return output

    except Exception as e:
        db.rollback()
        run.status = "failed"
        run.error_message = str(e)
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"GAB-Gen generation failed: {str(e)}"
        )


@router.post("/extract-survey")
def extract_survey_ocr(
    project_id: str,
    db: Session = Depends(get_db)
):
    """
    Triggers automated OpenCV + EasyOCR extraction from the uploaded survey/deed file.
    Populates candidate boundary measurements with confidence scores and verification flags.
    Never fabricates values; ambiguous results are marked for verification.
    """
    project = _get_project_or_404(project_id, db)
    mj = project.master_json or {}
    source_file = mj.get("input_metadata", {}).get("source_file")

    if not source_file or not source_file.get("stored_filename"):
        raise HTTPException(
            status_code=400,
            detail="No uploaded survey/deed plan found. Please upload a file first."
        )

    stored_path = os.path.join(settings.upload_dir, "surveys", project_id, source_file["stored_filename"])
    if not os.path.exists(stored_path):
        raise HTTPException(status_code=404, detail="Uploaded survey file not found on disk.")

    with open(stored_path, "rb") as f:
        file_bytes = f.read()

    from ..components.gab_gen.easyocr_provider import EasyOCRSurveyExtractionProvider
    provider = EasyOCRSurveyExtractionProvider()

    ext = os.path.splitext(source_file.get("original_filename", ""))[1].lower() or ".png"
    try:
        extracted = provider.extract_survey({
            "file_bytes": file_bytes,
            "filename": source_file.get("original_filename"),
            "ext": ext
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Survey OCR extraction failed: {str(e)}")

    extracted_dict = extracted.model_dump()
    project.master_json = merge_master_json(
        project.master_json,
        {"survey_extraction": extracted_dict}
    )
    db.commit()

    return {
        "message": "Survey extraction completed successfully",
        "survey_extraction": extracted_dict
    }


@router.post("/edit-room")
def edit_blueprint_room(
    project_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    Validates and applies a live room geometry modification.
    Enforces buildable footprint boundaries and room overlap constraints.
    """
    project = _get_project_or_404(project_id, db)
    mj = project.master_json or {}

    room_id = payload.get("room_id")
    target_floor_id = payload.get("target_floor_id")
    new_polygon_raw = payload.get("polygon", [])

    if not room_id or not target_floor_id or not new_polygon_raw:
        raise HTTPException(status_code=400, detail="room_id, target_floor_id, and polygon are required.")

    from ..components.gab_gen.schemas import Point2D, FloorPlanDefinition
    from ..components.gab_gen.blueprint.editor import apply_room_edit
    from shapely.geometry import Polygon

    floors_raw = mj.get("floor_plan", {}).get("floors", [])
    if not floors_raw:
        raise HTTPException(status_code=400, detail="No generated floor plan to edit.")

    floors = [FloorPlanDefinition(**f) for f in floors_raw]
    buildable_pts = mj.get("buildable_footprint", {}).get("polygon", [])
    buildable_poly = Polygon([(p["x"], p["y"]) for p in buildable_pts]) if len(buildable_pts) >= 3 else None

    new_polygon = [Point2D(x=p["x"], y=p["y"]) for p in new_polygon_raw]

    res = apply_room_edit(room_id, target_floor_id, new_polygon, floors, buildable_poly)
    if not res["success"]:
        return {
            "valid": False,
            "violations": res["violations"]
        }

    # Save edited floors into master_json
    updated_floors_dict = [f.model_dump() for f in res["floors"]]
    mj["floor_plan"]["floors"] = updated_floors_dict
    project.master_json = mj
    db.commit()

    return {
        "valid": True,
        "message": "Room edited successfully",
        "floor_plan": mj["floor_plan"]
    }


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


@router.post("/run")
def run_gab_gen_compat(project_id: str, db: Session = Depends(get_db)):
    """Compatibility endpoint for shared run trigger."""
    return generate_blueprint(project_id, dev_test_mode=True, db=db)

