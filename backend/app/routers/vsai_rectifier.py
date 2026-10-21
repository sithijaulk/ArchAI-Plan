import json
import logging
import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.component_run import ComponentRun, ProjectOutput
from ..models.project import Project
from ..schemas.vsai_rectifier import VsaiRunRequest
from ..services.master_json import merge_master_json
from ..services.vastu_engine import evaluate_vastu_shastra, load_vastu_rules
from ..services.vsai_rectifier import VsaiInputError, prepare_master_json, run_vsai_rectifier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["VSAI-Rectifier"])
COMPONENT_NAME = "vsai_rectifier"
SUPPORTED_IMAGE_TYPES = {
    ".png": ("PNG", "image/png"),
    ".jpg": ("JPEG", "image/jpeg"),
    ".jpeg": ("JPEG", "image/jpeg"),
}


def resolve_stored_master_json(
    project_id: str,
    project: Project | None = None,
    db: Session | None = None,
) -> dict[str, Any] | None:
    """Resolves Master JSON from database or fallback shared/upload filesystem locations."""
    if project is not None and isinstance(project.master_json, dict):
        return project.master_json

    if db is not None:
        try:
            p = db.query(Project).filter(Project.id == project_id).first()
            if p is not None and isinstance(p.master_json, dict):
                return p.master_json
        except Exception as db_err:
            logger.debug("Database lookup in resolve_stored_master_json skipped: %s", db_err)

    shared_root = Path(__file__).resolve().parents[3] / "shared"
    candidates = [
        shared_root / "vsi-bd" / f"{project_id}.json",
        shared_root / "vsai-bd" / f"{project_id}.json",
        Path(settings.upload_dir).resolve() / "projects" / project_id / "master_input.json",
    ]
    for cp in candidates:
        if cp.is_file():
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as file_err:
                logger.debug("Could not read candidate file %s: %s", cp, file_err)

    return None


@router.post(
    "/{project_id}/vsai-rectifier/run",
    summary="Run deterministic VSAI Stage 1 checks",
    description=(
        "Validates room and structural polygon geometry and evaluates only explicitly configured rules. "
        "This endpoint does not perform image segmentation or claim complete Vastu compliance."
    ),
)
def run_vsai(
    project_id: str,
    data: VsaiRunRequest | None = None,
    db: Session = Depends(get_db),
):
    project = None
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
    except Exception as db_err:
        logger.warning("Database unavailable in run_vsai: %s", db_err)

    stored_master_json = resolve_stored_master_json(project_id, project=project, db=db)

    if stored_master_json is None and (data is None or data.master_json is None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if stored_master_json is None and data is not None:
        stored_master_json = deepcopy(data.master_json)

    supplied = data.master_json if data else None
    original_snapshot = deepcopy(supplied if supplied is not None else stored_master_json)
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    logger.info("Starting VSAI Stage 1 processing for project %s", project_id)
    try:
        master_json = prepare_master_json(project_id, stored_master_json, supplied)
        output = run_vsai_rectifier(master_json)
        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # Update disk files in shared/vsi-bd and shared/vsai-bd
        try:
            shared_root = Path(__file__).resolve().parents[3] / "shared"
            for folder in ["vsi-bd", "vsai-bd"]:
                target_file = shared_root / folder / f"{project_id}.json"
                if target_file.parent.exists():
                    with open(target_file, "w", encoding="utf-8") as f:
                        json.dump(output["master_json"], f, indent=2)
        except Exception as disk_err:
            logger.warning("Could not update disk file: %s", disk_err)

        run_id = str(uuid.uuid4())
        try:
            run = ComponentRun(
                project_id=project_id,
                component_name=COMPONENT_NAME,
                status="completed",
                input_json=original_snapshot,
                output_json=output,
                started_at=started_at,
                completed_at=completed_at,
            )
            if project is not None:
                project.master_json = output["master_json"]
            db.add(run)
            db.commit()
            run_id = run.id
        except Exception as db_err:
            logger.warning("Could not persist run to database: %s", db_err)
            try:
                db.rollback()
            except Exception:
                pass

        logger.info("Completed VSAI Stage 1 processing for project %s", project_id)
        return {
            "run_id": run_id,
            "status": "completed",
            **output["result"],
            "master_json": output["master_json"],
        }
    except VsaiInputError as error:
        _record_failed_run(db, project_id, original_snapshot, started_at, str(error))
        logger.warning("Rejected VSAI input for project %s: %s", project_id, error)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except Exception as error:
        try:
            db.rollback()
        except Exception:
            pass
        logger.exception("VSAI processing failed for project %s", project_id)
        _record_failed_run(db, project_id, original_snapshot, started_at, f"{type(error).__name__}: {error}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="VSAI processing failed; the previously saved Master JSON was not changed.",
        ) from error


def _record_failed_run(
    db: Session,
    project_id: str,
    input_snapshot: Any,
    started_at: datetime,
    error_message: str,
) -> None:
    try:
        db.rollback()
        project = db.query(Project).filter(Project.id == project_id).first()
        if (
            project is not None
            and isinstance(project.master_json, dict)
            and project.master_json.get("project_id") == project_id
            and isinstance(project.master_json.get("processing"), dict)
        ):
            project.master_json = merge_master_json(
                project.master_json,
                {"processing": {COMPONENT_NAME: {"status": "failed"}}},
            )
        run = ComponentRun(
            project_id=project_id,
            component_name=COMPONENT_NAME,
            status="failed",
            input_json=input_snapshot,
            error_message=error_message[:4000],
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(run)
        db.commit()
    except Exception as ex:
        logger.warning("Could not record failed run in DB: %s", ex)


@router.post(
    "/{project_id}/vsai-rectifier/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a floor-plan image for future AI processing",
)
async def upload_floor_plan_image(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    expected = SUPPORTED_IMAGE_TYPES.get(extension)
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported image extension. Supported formats are PNG and JPEG.",
        )
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if max_bytes <= 0:
        raise HTTPException(status_code=500, detail="Image upload size limit is misconfigured.")
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image exceeds the configured upload size limit.")
    try:
        with Image.open(BytesIO(content)) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded content is not a valid PNG or JPEG image.") from error
    actual_format, media_type = expected
    if image_format != actual_format:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image content does not match its file extension.")
    if file.content_type not in {media_type, "image/jpg" if media_type == "image/jpeg" else media_type}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image media type does not match its file content.")

    safe_name = f"{uuid.uuid4()}{extension}"
    relative_path = Path("projects") / project_id / "vsai_rectifier" / safe_name
    upload_root = Path(settings.upload_dir).resolve()
    target = (upload_root / relative_path).resolve()
    if os.path.commonpath((str(upload_root), str(target))) != str(upload_root):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid upload path.")
    target.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "original_filename": filename.replace("\\", "/").split("/")[-1][:255],
        "media_type": media_type,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "processing_status": "pending_ai_processing",
        "vector_extraction": "pending_ai_processing",
        "note": "Stage 1 stores the image only; image-to-vector conversion is not implemented.",
    }
    output = ProjectOutput(
        project_id=project_id,
        component_name=COMPONENT_NAME,
        output_type=extension.lstrip("."),
        file_path=relative_path.as_posix(),
        metadata_json=metadata,
    )
    try:
        with target.open("xb") as destination:
            destination.write(content)
        db.add(output)
        db.commit()
    except Exception:
        db.rollback()
        target.unlink(missing_ok=True)
        logger.exception("Failed to save VSAI image upload for project %s", project_id)
        raise HTTPException(status_code=500, detail="Image upload could not be saved.")
    return {
        "id": output.id,
        "project_id": project_id,
        "file_path": output.file_path,
        **metadata,
        "image_to_vector_status": "pending_ai_processing",
    }


@router.get(
    "/{project_id}/vsai-rectifier/history",
    summary="List VSAI processing history",
)
def get_vsai_history(project_id: str, db: Session = Depends(get_db)):
    if db.query(Project.id).filter(Project.id == project_id).first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    runs = (
        db.query(ComponentRun)
        .filter(ComponentRun.project_id == project_id, ComponentRun.component_name == COMPONENT_NAME)
        .order_by(ComponentRun.started_at.desc(), ComponentRun.id.desc())
        .all()
    )
    items = []
    for run in runs:
        result = (run.output_json or {}).get("result", {})
        items.append({
            "id": run.id,
            "status": run.status,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "error": run.error_message if run.status == "failed" else None,
            "score_status": result.get("score_status"),
            "vastu_compliance_score": result.get("vastu_compliance_score"),
            "rule_coverage": result.get("rule_coverage"),
            "result": result or None,
        })
    return {"project_id": project_id, "runs": items}


@router.get(
    "/vastu-rules",
    summary="Get extensible Vastu Shastra rules configuration",
)
def get_vastu_rules() -> dict[str, Any]:
    """Returns all active, extensible Vastu Shastra rule definitions."""
    return {"rules": load_vastu_rules()}


@router.post(
    "/vastu-analysis",
    summary="Directly evaluate Vastu Shastra score and defects on supplied JSON",
)
def evaluate_vastu_direct(data: dict[str, Any]) -> dict[str, Any]:
    """Calculates spatial harmony score, defects, and recommendations on given Master JSON."""
    return evaluate_vastu_shastra(data)


@router.get(
    "/{project_id}/vastu-analysis",
    summary="Get comprehensive Vastu compliance score, good aspects, and defects",
)
def get_project_vastu_analysis(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Retrieves project floor plan and evaluates Vastu Shastra spatial compliance."""
    master_json = resolve_stored_master_json(project_id, db=db)
    if not master_json:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project Master JSON not found")

    return evaluate_vastu_shastra(master_json)


@router.post(
    "/vsai-rectifier/confirm-missing-info",
    summary="Merge user-confirmed inputs into Master JSON and run Vastu analysis",
)
def confirm_missing_info_direct(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Applies user-confirmed inputs to a normalized copy of the Master JSON without destructive overwrite,
    re-validates, and runs the four finalized Vastu rules once all required inputs are present."""
    from ..services.missing_info_service import merge_confirmed_inputs
    from ..services.vsai_validator import validate_master_json

    master_json = payload.get("master_json")
    answers = payload.get("confirmed_answers") or {}
    project_id = payload.get("project_id")

    if not isinstance(master_json, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing or invalid 'master_json'.")

    normalized_master_json = merge_confirmed_inputs(master_json, answers)
    validation = validate_master_json(normalized_master_json)

    remaining_report = validation.get("missing_info_report") or {}
    is_complete = not remaining_report.get("has_blocking_missing_info", False)

    vastu_analysis = None
    if is_complete:
        try:
            vastu_analysis = evaluate_vastu_shastra(normalized_master_json)
        except Exception as v_err:
            logger.warning("Vastu analysis execution error after confirmation: %s", v_err)

    if project_id:
        try:
            shared_root = Path(__file__).resolve().parents[3] / "shared"
            for folder in ["vsi-bd", "vsai-bd"]:
                target_file = shared_root / folder / f"{project_id}.json"
                if target_file.parent.exists():
                    with open(target_file, "w", encoding="utf-8") as f:
                        json.dump(normalized_master_json, f, indent=2)

            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                project.master_json = normalized_master_json
                db.commit()
        except Exception as update_err:
            logger.warning("Could not persist updated master json for project %s: %s", project_id, update_err)

    return {
        "is_complete": is_complete,
        "master_json": normalized_master_json,
        "missing_info_report": remaining_report,
        "validation": validation,
        "vastu_analysis": vastu_analysis,
    }


@router.post(
    "/{project_id}/vsai-rectifier/confirm-missing-info",
    summary="Merge user-confirmed inputs for a specific project ID",
)
def confirm_missing_info_project(
    project_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    master_json = payload.get("master_json") or resolve_stored_master_json(project_id, db=db)
    if not master_json:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project Master JSON not found")
    
    payload_with_id = dict(payload)
    payload_with_id["master_json"] = master_json
    payload_with_id["project_id"] = project_id
    return confirm_missing_info_direct(payload_with_id, db=db)


@router.post(
    "/vsai-rectifier/rectify",
    summary="Directly run Stage 2 spatial geometry rectification on supplied Master JSON",
)
def rectify_floor_plan_direct(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from ..services.spatial_rectifier_service import run_spatial_rectification

    master_json = payload.get("master_json") if isinstance(payload.get("master_json"), dict) else payload
    project_id = payload.get("project_id") or (master_json.get("project_id") if isinstance(master_json, dict) else None)

    if (not isinstance(master_json, dict) or not (master_json.get("floor_plan") or master_json.get("rooms"))) and project_id:
        stored = resolve_stored_master_json(project_id, db=db)
        if stored:
            master_json = stored

    if isinstance(master_json, dict) and not master_json.get("floor_plan"):
        if "rooms" in master_json:
            master_json = {"floor_plan": master_json}
        elif "baseline_floor_plan" in payload and isinstance(payload.get("baseline_floor_plan"), dict):
            master_json = {"floor_plan": payload["baseline_floor_plan"]}
        elif "baseline_floor_plan" in master_json and isinstance(master_json.get("baseline_floor_plan"), dict):
            master_json = {"floor_plan": master_json["baseline_floor_plan"]}

    if not isinstance(master_json, dict) or not master_json.get("floor_plan"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing or invalid Master JSON with floor_plan.")

    rectification_output = run_spatial_rectification(master_json)

    # Persist if project_id exists
    if project_id and rectification_output.get("master_json"):
        try:
            shared_root = Path(__file__).resolve().parents[3] / "shared"
            for folder in ["vsi-bd", "vsai-bd"]:
                target_file = shared_root / folder / f"{project_id}.json"
                if target_file.parent.exists():
                    with open(target_file, "w", encoding="utf-8") as f:
                        json.dump(rectification_output["master_json"], f, indent=2)

            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                project.master_json = rectification_output["master_json"]
                db.commit()
        except Exception as persist_err:
            logger.warning("Could not persist rectified Master JSON for project %s: %s", project_id, persist_err)

    return rectification_output


@router.post(
    "/{project_id}/vsai-rectifier/rectify",
    summary="Run Stage 2 spatial geometry rectification for a specific project",
)
def rectify_project_floor_plan(
    project_id: str,
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    stored_master_json = resolve_stored_master_json(project_id, db=db)
    supplied = payload.get("master_json") if payload else None
    master_json = supplied or stored_master_json

    if not master_json:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project Master JSON not found.")

    return rectify_floor_plan_direct({"master_json": master_json, "project_id": project_id}, db=db)


