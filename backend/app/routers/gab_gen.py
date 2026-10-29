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
import copy
import io
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Response, status
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


def _safe_survey_path(project_id: str, stored_filename: str) -> str:
    """
    Safely resolves the stored survey file path, rejecting path traversal attempts.
    """
    if not stored_filename or ".." in stored_filename or "/" in stored_filename or "\\" in stored_filename:
        raise HTTPException(status_code=400, detail="Invalid filename or path traversal detected.")
    
    base_dir = os.path.abspath(os.path.join(settings.upload_dir, "surveys", project_id))
    full_path = os.path.abspath(os.path.join(base_dir, stored_filename))
    if not full_path.startswith(base_dir):
        raise HTTPException(status_code=400, detail="Invalid file path outside survey directory.")
    return full_path


def _check_and_bump_revision(project: Project, db: Session, expected_revision: Optional[int] = None) -> int:
    """
    Enforces optimistic concurrency control.
    If expected_revision is provided, verifies that project.revision matches.
    If mismatched, raises HTTP 409 Conflict.
    Increments project.revision atomically and synchronizes project_revision in master_json.
    """
    current_rev = int(project.revision or 1)
    if expected_revision is not None and expected_revision != current_rev:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PROJECT_STALE_REVISION",
                "message": f"Stale revision conflict. Expected {expected_revision}, but project is currently at revision {current_rev}.",
                "expected_revision": expected_revision,
                "current_revision": current_rev
            }
        )
    next_rev = current_rev + 1
    project.revision = next_rev
    if isinstance(project.master_json, dict):
        project.master_json["project_revision"] = next_rev
    return next_rev


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

    # Multi-page PDF inspection
    total_pages = 1
    if ext == ".pdf":
        from ..components.gab_gen.survey_vision.preprocessing import get_pdf_page_count
        try:
            total_pages = get_pdf_page_count(contents)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

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
        "total_pages": total_pages,
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
        stored_path = _safe_survey_path(project_id, source_file["stored_filename"])
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

        # Bump project revision for newly generated blueprint
        next_rev = int(project.revision or 1) + 1
        project.revision = next_rev
        if isinstance(output.master_json, dict):
            output.master_json["project_revision"] = next_rev

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
    page_number: int = Query(default=1, ge=1),
    db: Session = Depends(get_db)
):
    """
    Triggers automated OpenCV + EasyOCR extraction from the uploaded survey/deed file.
    Supports specific page selection for multi-page PDF documents.
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

    stored_path = _safe_survey_path(project_id, source_file["stored_filename"])
    if not os.path.exists(stored_path):
        raise HTTPException(status_code=404, detail="Uploaded survey file not found on disk.")

    with open(stored_path, "rb") as f:
        file_bytes = f.read()

    from ..components.gab_gen.easyocr_provider import EasyOCRSurveyExtractionProvider
    provider = EasyOCRSurveyExtractionProvider()

    ext = os.path.splitext(source_file.get("original_filename", ""))[1].lower() or ".png"
    target_area_sqm = None
    reqs = mj.get("client_requirements", {})
    input_meta = mj.get("input_metadata", {})
    
    decl_val = reqs.get("declared_land_extent") or (reqs.get("declared_extent", {}).get("value") if isinstance(reqs.get("declared_extent"), dict) else None)
    decl_unit = reqs.get("declared_land_unit") or (reqs.get("declared_extent", {}).get("unit") if isinstance(reqs.get("declared_extent"), dict) else None)

    if not decl_val and "declared_land_extent" in input_meta:
        meta_decl = input_meta.get("declared_land_extent")
        if isinstance(meta_decl, dict):
            decl_val = meta_decl.get("value")
            decl_unit = meta_decl.get("unit")
        elif isinstance(meta_decl, (int, float)):
            decl_val = float(meta_decl)

    if decl_val:
        from ..components.gab_gen.input.units import convert_area_to_sqm
        from ..components.gab_gen.schemas import LandExtentUnit
        try:
            unit_enum = LandExtentUnit(str(decl_unit).lower()) if decl_unit else LandExtentUnit.PERCHES
            target_area_sqm = convert_area_to_sqm(float(decl_val), unit_enum)
        except Exception:
            target_area_sqm = float(decl_val) * 25.29285264

    try:
        extracted = provider.extract_survey({
            "file_bytes": file_bytes,
            "filename": source_file.get("original_filename"),
            "ext": ext,
            "page_number": page_number,
            "target_area_sqm": target_area_sqm
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
    expected_revision: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db)
):
    """
    Validates and applies a live room geometry modification.
    Enforces buildable footprint boundaries and room overlap constraints.
    Supports optimistic concurrency check using expected_revision.
    """
    project = _get_project_or_404(project_id, db)
    _check_and_bump_revision(project, db, expected_revision or payload.get("expected_revision"))
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
    
    # Track edit history
    history = mj.get("edit_history", [])
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "edit_room",
        "room_id": room_id,
        "target_floor_id": target_floor_id
    })
    mj["edit_history"] = history
    project.master_json = mj
    db.commit()

    return {
        "valid": True,
        "message": "Room edited successfully",
        "floor_plan": mj["floor_plan"],
        "revision": project.revision
    }


@router.post("/remove-room")
def remove_blueprint_room(
    project_id: str,
    payload: Dict[str, Any],
    expected_revision: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db)
):
    """Removes a non-structural room from the generated floor plan."""
    project = _get_project_or_404(project_id, db)
    _check_and_bump_revision(project, db, expected_revision or payload.get("expected_revision"))
    mj = project.master_json or {}
    room_id = payload.get("room_id")
    if not room_id:
        raise HTTPException(status_code=400, detail="room_id is required.")

    from ..components.gab_gen.schemas import FloorPlanDefinition
    from ..components.gab_gen.blueprint.editor import remove_room_from_blueprint
    from shapely.geometry import Polygon

    floors_raw = mj.get("floor_plan", {}).get("floors", [])
    floors = [FloorPlanDefinition(**f) for f in floors_raw]
    buildable_pts = mj.get("buildable_footprint", {}).get("polygon", [])
    buildable_poly = Polygon([(p["x"], p["y"]) for p in buildable_pts]) if len(buildable_pts) >= 3 else None

    res = remove_room_from_blueprint(room_id, floors, buildable_poly)
    if not res["success"]:
        return {"valid": False, "violations": res["violations"]}

    mj["floor_plan"]["floors"] = [f.model_dump() for f in res["floors"]]
    history = mj.get("edit_history", [])
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "remove_room",
        "room_id": room_id
    })
    mj["edit_history"] = history
    project.master_json = mj
    db.commit()

    return {"valid": True, "message": "Room removed successfully", "floor_plan": mj["floor_plan"]}


@router.post("/add-room")
def add_blueprint_room(
    project_id: str,
    payload: Dict[str, Any],
    expected_revision: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db)
):
    """Adds a room polygon to a designated floor."""
    project = _get_project_or_404(project_id, db)
    _check_and_bump_revision(project, db, expected_revision or payload.get("expected_revision"))
    mj = project.master_json or {}
    target_floor_id = payload.get("target_floor_id", "F0")
    room_data = payload.get("room_data", {})

    from ..components.gab_gen.schemas import FloorPlanDefinition
    from ..components.gab_gen.blueprint.editor import add_room_to_blueprint
    from shapely.geometry import Polygon

    floors_raw = mj.get("floor_plan", {}).get("floors", [])
    floors = [FloorPlanDefinition(**f) for f in floors_raw]
    buildable_pts = mj.get("buildable_footprint", {}).get("polygon", [])
    buildable_poly = Polygon([(p["x"], p["y"]) for p in buildable_pts]) if len(buildable_pts) >= 3 else None

    res = add_room_to_blueprint(target_floor_id, room_data, floors, buildable_poly)
    if not res["success"]:
        return {"valid": False, "violations": res["violations"]}

    mj["floor_plan"]["floors"] = [f.model_dump() for f in res["floors"]]
    history = mj.get("edit_history", [])
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "add_room",
        "room_id": res.get("created_room_id"),
        "target_floor_id": target_floor_id
    })
    mj["edit_history"] = history
    project.master_json = mj
    db.commit()

    return {"valid": True, "message": "Room added successfully", "floor_plan": mj["floor_plan"], "created_room_id": res.get("created_room_id"), "revision": project.revision}


@router.post("/edit-door")
def edit_blueprint_door(
    project_id: str,
    payload: Dict[str, Any],
    expected_revision: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db)
):
    """Edits an explicit door position and width with circulation revalidation."""
    project = _get_project_or_404(project_id, db)
    _check_and_bump_revision(project, db, expected_revision or payload.get("expected_revision"))
    mj = project.master_json or {}
    door_id = payload.get("door_id")
    target_floor_id = payload.get("target_floor_id")
    pos_data = payload.get("position", {})
    width_m = payload.get("width_m", 0.90)

    if not door_id or not target_floor_id or not pos_data:
        raise HTTPException(status_code=400, detail="door_id, target_floor_id, and position are required.")

    from ..components.gab_gen.schemas import FloorPlanDefinition, Point2D
    from ..components.gab_gen.blueprint.editor import edit_door_in_blueprint

    floors_raw = mj.get("floor_plan", {}).get("floors", [])
    floors = [FloorPlanDefinition(**f) for f in floors_raw]
    new_pos = Point2D(x=pos_data["x"], y=pos_data["y"])

    res = edit_door_in_blueprint(door_id, target_floor_id, new_pos, width_m, floors)
    if not res["success"]:
        return {"valid": False, "violations": res["violations"]}

    mj["floor_plan"]["floors"] = [f.model_dump() for f in res["floors"]]
    history = mj.get("edit_history", [])
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "edit_door",
        "door_id": door_id,
        "target_floor_id": target_floor_id
    })
    mj["edit_history"] = history
    project.master_json = mj
    db.commit()

    return {"valid": True, "message": "Door edited successfully", "floor_plan": mj["floor_plan"], "revision": project.revision}


@router.post("/edit-window")
def edit_blueprint_window(
    project_id: str,
    payload: Dict[str, Any],
    expected_revision: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db)
):
    """Edits an explicit exterior window position and dimensions."""
    project = _get_project_or_404(project_id, db)
    _check_and_bump_revision(project, db, expected_revision or payload.get("expected_revision"))
    mj = project.master_json or {}
    window_id = payload.get("window_id")
    target_floor_id = payload.get("target_floor_id")
    pos_data = payload.get("position", {})
    width_m = payload.get("width_m", 1.20)
    height_m = payload.get("height_m", 1.20)

    if not window_id or not target_floor_id or not pos_data:
        raise HTTPException(status_code=400, detail="window_id, target_floor_id, and position are required.")

    from ..components.gab_gen.schemas import FloorPlanDefinition, Point2D
    from ..components.gab_gen.blueprint.editor import edit_window_in_blueprint

    floors_raw = mj.get("floor_plan", {}).get("floors", [])
    floors = [FloorPlanDefinition(**f) for f in floors_raw]
    new_pos = Point2D(x=pos_data["x"], y=pos_data["y"])

    res = edit_window_in_blueprint(window_id, target_floor_id, new_pos, width_m, height_m, floors)
    if not res["success"]:
        return {"valid": False, "violations": res["violations"]}

    mj["floor_plan"]["floors"] = [f.model_dump() for f in res["floors"]]
    history = mj.get("edit_history", [])
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "edit_window",
        "window_id": window_id,
        "target_floor_id": target_floor_id
    })
    mj["edit_history"] = history
    project.master_json = mj
    db.commit()

    return {"valid": True, "message": "Window edited successfully", "floor_plan": mj["floor_plan"], "revision": project.revision}


@router.post("/change-roof")
def change_blueprint_roof_endpoint(
    project_id: str,
    payload: Dict[str, Any],
    expected_revision: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db)
):
    """Changes the roof type and regenerates validated 3D roof geometry."""
    project = _get_project_or_404(project_id, db)
    _check_and_bump_revision(project, db, expected_revision or payload.get("expected_revision"))
    mj = project.master_json or {}
    new_roof_type = payload.get("roof_type")
    pitch_deg = payload.get("pitch_angle_deg")

    if not new_roof_type:
        raise HTTPException(status_code=400, detail="roof_type is required.")

    from ..components.gab_gen.blueprint.editor import change_blueprint_roof
    from shapely.geometry import Polygon

    b_pts = mj.get("building_footprint", {}).get("polygon", []) or mj.get("buildable_footprint", {}).get("polygon", [])
    if len(b_pts) < 3:
        raise HTTPException(status_code=400, detail="Building footprint polygon is missing or invalid.")

    b_poly = Polygon([(p["x"], p["y"]) for p in b_pts])
    res = change_blueprint_roof(b_poly, new_roof_type, pitch_deg)
    if not res["success"]:
        return {"valid": False, "violations": res["violations"]}

    roof_dict = res["roof_geometry"].model_dump()
    mj["roof_geometry"] = roof_dict
    history = mj.get("edit_history", [])
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "change_roof",
        "roof_type": new_roof_type
    })
    mj["edit_history"] = history
    project.master_json = mj
    db.commit()

    return {
        "valid": True,
        "message": f"Roof changed to '{new_roof_type}' successfully",
        "roof_geometry": roof_dict,
        "revision": project.revision
    }


@router.post("/undo-edit")
def undo_last_blueprint_edit(
    project_id: str,
    payload: Optional[Dict[str, Any]] = None,
    expected_revision: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db)
):
    """Undoes the last accepted edit transaction using edit history tracking."""
    project = _get_project_or_404(project_id, db)
    _check_and_bump_revision(project, db, expected_revision or (payload.get("expected_revision") if payload else None))
    mj = project.master_json or {}
    history = mj.get("edit_history", [])
    if not history:
        return {"valid": False, "message": "No edits to undo."}

    last_action = history.pop()
    # If the candidate was original, we can reset from candidate pool if candidate_generation exists
    cand_section = mj.get("candidate_generation", {})
    selected_id = cand_section.get("selected_candidate_id") or mj.get("building_footprint", {}).get("candidate_id")
    candidates = cand_section.get("candidates", [])
    cand = next((c for c in candidates if c.get("candidate_id") == selected_id), None)
    if cand:
        mj["floor_plan"] = {"floors": cand.get("floors", [])}
        if cand.get("roof_geometry"):
            mj["roof_geometry"] = cand.get("roof_geometry")

    mj["edit_history"] = history
    project.master_json = mj
    db.commit()

    return {
        "valid": True,
        "message": f"Undid action '{last_action.get('action')}'",
        "floor_plan": mj["floor_plan"],
        "roof_geometry": mj.get("roof_geometry"),
        "revision": project.revision
    }



@router.get("/result")
def get_gab_gen_result(project_id: str, response: Response, db: Session = Depends(get_db)):
    """Returns the latest generated GAB-Gen results with revision headers."""
    project = _get_project_or_404(project_id, db)
    mj = project.master_json or {}
    floor_plan = mj.get("floor_plan", {})
    if not floor_plan.get("floors"):
        raise HTTPException(status_code=404, detail="No GAB-Gen blueprint has been generated yet for this project.")
    response.headers["ETag"] = f'"{project.revision}"'
    response.headers["X-Project-Revision"] = str(project.revision)
    return mj


@router.get("/master-json")
def get_gab_master_json(project_id: str, response: Response, db: Session = Depends(get_db)):
    """Returns the full Master JSON with schema migration and revision headers."""
    project = _get_project_or_404(project_id, db)
    mj = project.master_json or {}
    from ..components.gab_gen.output.master_json_builder import migrate_master_json_schema
    migrated = migrate_master_json_schema(mj)
    response.headers["ETag"] = f'"{project.revision}"'
    response.headers["X-Project-Revision"] = str(project.revision)
    return migrated


@router.get("/candidates")
def get_generated_candidates(project_id: str, db: Session = Depends(get_db)):
    """Returns the generated candidates list, ranking, and selection metadata."""
    project = _get_project_or_404(project_id, db)
    mj = project.master_json or {}
    cand_section = mj.get("candidate_generation", {})
    if not cand_section.get("candidates"):
        raise HTTPException(status_code=404, detail="No candidates generated yet for this project.")
    return cand_section


@router.post("/select-candidate")
def select_candidate(
    project_id: str,
    payload: Dict[str, Any],
    expected_revision: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db)
):
    """
    Selects a candidate by ID, activating its floors, footprint, roof, and validation in Master JSON.
    Preserves all unselected candidates in the candidate pool.
    Supports optimistic concurrency check using expected_revision.
    """
    project = _get_project_or_404(project_id, db)
    _check_and_bump_revision(project, db, expected_revision or payload.get("expected_revision"))
    mj = project.master_json or {}
    candidate_id = payload.get("candidate_id")
    if not candidate_id:
        raise HTTPException(status_code=400, detail="candidate_id is required.")

    cand_section = mj.get("candidate_generation", {})
    candidates = cand_section.get("candidates", [])
    matching_cand = next((c for c in candidates if c.get("candidate_id") == candidate_id), None)

    if not matching_cand:
        raise HTTPException(status_code=404, detail=f"Candidate with ID '{candidate_id}' not found in candidate pool.")

    # Activate matching candidate geometry
    mj["floor_plan"] = {"floors": matching_cand.get("floors", [])}
    if matching_cand.get("roof_geometry"):
        mj["roof_geometry"] = matching_cand.get("roof_geometry")
    if matching_cand.get("building_footprint_polygon"):
        mj["building_footprint"] = {
            "candidate_id": candidate_id,
            "shape_type": matching_cand.get("footprint_variant", "conformal_offset"),
            "polygon": matching_cand.get("building_footprint_polygon", []),
            "area": matching_cand.get("building_footprint_area_sqm", 0.0)
        }
    if matching_cand.get("validation"):
        mj["gab_gen_validation"] = matching_cand.get("validation")

    # Update active selection in candidate_generation and processing
    cand_section["selected_candidate_id"] = candidate_id
    mj["candidate_generation"] = cand_section
    if "processing" in mj and "gab_gen" in mj["processing"]:
        mj["processing"]["gab_gen"]["selected_candidate_id"] = candidate_id

    # Record edit history
    history = mj.get("edit_history", [])
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "select_candidate",
        "candidate_id": candidate_id
    })
    mj["edit_history"] = history

    from sqlalchemy.orm.attributes import flag_modified
    project.master_json = copy.deepcopy(mj)
    flag_modified(project, "master_json")
    db.commit()
    db.refresh(project)

    return {
        "message": f"Candidate '{candidate_id}' selected successfully.",
        "selected_candidate_id": candidate_id,
        "floor_plan": mj["floor_plan"],
        "master_json": mj,
        "revision": project.revision
    }


@router.post("/run")
def run_gab_gen_compat(project_id: str, db: Session = Depends(get_db)):
    """Compatibility endpoint for shared run trigger."""
    return generate_blueprint(project_id, dev_test_mode=True, db=db)


