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
from ..services.vsai_rectifier import VsaiInputError, prepare_master_json, run_vsai_rectifier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["VSAI-Rectifier"])
COMPONENT_NAME = "vsai_rectifier"
SUPPORTED_IMAGE_TYPES = {
    ".png": ("PNG", "image/png"),
    ".jpg": ("JPEG", "image/jpeg"),
    ".jpeg": ("JPEG", "image/jpeg"),
}


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
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    supplied = data.master_json if data else None
    original_snapshot = deepcopy(supplied if supplied is not None else project.master_json)
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    logger.info("Starting VSAI Stage 1 processing for project %s", project_id)
    try:
        master_json = prepare_master_json(project_id, project.master_json, supplied)
        output = run_vsai_rectifier(master_json)
        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        run = ComponentRun(
            project_id=project_id,
            component_name=COMPONENT_NAME,
            status="completed",
            input_json=original_snapshot,
            output_json=output,
            started_at=started_at,
            completed_at=completed_at,
        )
        project.master_json = output["master_json"]
        db.add(run)
        db.commit()
        logger.info("Completed VSAI Stage 1 processing for project %s", project_id)
        return {
            "run_id": run.id,
            "status": run.status,
            **output["result"],
            "master_json": output["master_json"],
        }
    except VsaiInputError as error:
        _record_failed_run(db, project_id, original_snapshot, started_at, str(error))
        logger.warning("Rejected VSAI input for project %s: %s", project_id, error)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except Exception as error:
        db.rollback()
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
