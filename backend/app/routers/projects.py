import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status, UploadFile, File, Body
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dependencies import require_admin
from ..models.project import Project
from ..models.component_run import ComponentRun, ProjectOutput
from ..schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from ..services.master_json import VALID_COMPONENTS, merge_master_json, new_master_json
from ..services.vsai_validator import validate_master_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("/validate-master-json")
async def validate_master_json_endpoint(
    data: Optional[Dict[str, Any]] = Body(None),
    file: Optional[UploadFile] = File(None),
):
    """
    Standalone validation endpoint to validate Master JSON data or files.
    Returns comprehensive validation results without persisting files or projects.
    """
    if file is not None:
        content = await file.read()
        return validate_master_json(content, filename=file.filename or "uploaded.json")
    if data is not None:
        return validate_master_json(data, filename="master.json")
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Must provide either JSON body or uploaded file."
    )


@router.post("/upload-master-json", status_code=status.HTTP_201_CREATED)
async def upload_master_json(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = file.filename or "master.json"
    if not filename.lower().endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a valid JSON file (.json)."
        )

    content = await file.read()

    # Run multi-stage JSON validation module
    validation = validate_master_json(content, filename=filename)

    # If critical syntax or schema errors exist, return 422 with validation report
    if validation["status"] == "INVALID":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": validation["summary"],
                "validation": validation,
            }
        )

    try:
        master_json = json.loads(content.decode("utf-8"))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON format: {str(e)}"
        )

    if not isinstance(master_json, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Master JSON must be a JSON object.")

    project_name = master_json.get("project_name") or Path(filename).stem.replace("_", " ").title()
    description = master_json.get("description") or f"Uploaded from {filename}"
    project_id = master_json.get("project_id") or str(uuid.uuid4())

    master_json["project_id"] = project_id
    master_json["project_name"] = project_name

    if "processing" not in master_json or not isinstance(master_json["processing"], dict):
        master_json["processing"] = {comp: {"status": "pending"} for comp in VALID_COMPONENTS}
    else:
        for comp in VALID_COMPONENTS:
            if comp not in master_json["processing"]:
                master_json["processing"][comp] = {"status": "pending"}

    # 1. Save physical JSON file to shared/vsi-bd and shared/vsai-bd (per user requirement)
    relative_path = f"shared/vsi-bd/{filename}"
    try:
        shared_root = Path(__file__).resolve().parents[3] / "shared"
        vsi_bd_dir = shared_root / "vsi-bd"
        vsi_bd_dir.mkdir(parents=True, exist_ok=True)
        with open(vsi_bd_dir / f"{project_id}.json", "wb") as f:
            f.write(content)
        with open(vsi_bd_dir / filename, "wb") as f:
            f.write(content)

        vsai_bd_dir = shared_root / "vsai-bd"
        vsai_bd_dir.mkdir(parents=True, exist_ok=True)
        with open(vsai_bd_dir / f"{project_id}.json", "wb") as f:
            f.write(content)
        with open(vsai_bd_dir / filename, "wb") as f:
            f.write(content)
    except Exception as ex:
        logger.warning(f"Could not save to shared/vsi-bd: {ex}")

    # 2. Save physical JSON file to backend uploads directory
    try:
        upload_root = Path(settings.upload_dir).resolve()
        project_upload_dir = upload_root / "projects" / project_id
        project_upload_dir.mkdir(parents=True, exist_ok=True)
        file_path_on_disk = project_upload_dir / "master_input.json"
        with open(file_path_on_disk, "wb") as f:
            f.write(content)
    except Exception as ex:
        logger.warning(f"Could not save file to upload disk: {ex}")

    # 3. Save to database if DB is reachable
    created_at_str = datetime.now(timezone.utc).isoformat()
    try:
        project = db.query(Project).filter_by(id=project_id).first()
        if not project:
            project = Project(id=project_id, project_name=project_name, description=description)
            db.add(project)
        else:
            project.project_name = project_name
            project.description = description

        project.master_json = master_json
        output_record = ProjectOutput(
            project_id=project_id,
            component_name="input_upload",
            output_type="json",
            file_path=f"projects/{project_id}/master_input.json",
            metadata_json={
                "original_filename": filename,
                "size_bytes": len(content),
                "source": "frontend_upload",
            }
        )
        db.add(output_record)
        db.commit()
        db.refresh(project)
        if project.created_at:
            created_at_str = project.created_at.isoformat()
    except Exception as db_err:
        logger.warning(f"Database unavailable or failed, stored in shared/vsi-bd: {db_err}")
        try:
            db.rollback()
        except Exception:
            pass

    return {
        "project": {
            "id": project_id,
            "project_name": project_name,
            "description": description,
            "created_at": created_at_str,
            "master_json": master_json,
        },
        "file_saved_path": relative_path,
        "filename": filename,
        "spatial_summary": validation["spatial_summary"],
        "validation": validation,
    }


def _revision_conflict(db: Session, project_id: str, expected_revision: int) -> None:
    db.rollback()
    current = db.query(Project).filter(Project.id == project_id).first()
    current_revision = int(current.revision or 1) if current is not None else None
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
        "code": "PROJECT_STALE_REVISION",
        "message": "Project changed since the supplied revision; reload before retrying.",
        "expected_revision": expected_revision,
        "current_revision": current_revision,
    })


def _compare_and_swap_project(db: Session, project: Project, expected_revision: int,
                              values: dict[str, Any]) -> Project:
    values["revision"] = expected_revision + 1
    result = db.execute(update(Project).where(
        Project.id == project.id, Project.revision == expected_revision
    ).values(**values).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        _revision_conflict(db, project.id, expected_revision)
    db.commit()
    db.refresh(project)
    return project

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    project = Project(project_name=data.project_name, description=data.description)
    db.add(project)
    db.flush()
    project.master_json = new_master_json(project.id, data.project_name)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, data: ProjectUpdate, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    values = data.model_dump(exclude_unset=True)
    expected_revision = values.pop("expected_revision", None)
    master_json = values.pop("master_json", None)
    current_revision = int(project.revision or 1)
    expected_revision = current_revision if expected_revision is None else expected_revision
    if expected_revision != current_revision:
        _revision_conflict(db, project_id, expected_revision)
    if master_json is not None:
        values["master_json"] = merge_master_json(project.master_json, master_json)
    if not values:
        return project
    return _compare_and_swap_project(db, project, expected_revision, values)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()


@router.get("/{project_id}/master-json")
def get_master_json(project_id: str, response: Response, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    response.headers["ETag"] = f'"{project.revision}"'
    response.headers["X-Project-Revision"] = str(project.revision)
    return project.master_json


@router.post("/{project_id}/skip/{component}")
def skip_component(project_id: str, component: str, expected_revision: int | None = Query(default=None, ge=1),
                   db: Session = Depends(get_db), _admin=Depends(require_admin)):
    if component not in VALID_COMPONENTS:
        raise HTTPException(status_code=400, detail=f"Invalid component. Valid: {VALID_COMPONENTS}")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    current_revision = int(project.revision or 1)
    if expected_revision is not None and expected_revision != current_revision:
        _revision_conflict(db, project_id, expected_revision)
    expected_revision = current_revision
    updated_master = merge_master_json(
        project.master_json,
        {"processing": {component: {"status": "skipped"}}},
    )
    changed = db.execute(update(Project).where(
        Project.id == project_id, Project.revision == expected_revision
    ).values(master_json=updated_master, revision=expected_revision + 1)
        .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        _revision_conflict(db, project_id, expected_revision)
    run = ComponentRun(project_id=project_id, component_name=component, status="skipped")
    db.add(run)
    db.commit()
    db.refresh(project)

    return {"component": component, "status": "skipped", "master_json": updated_master,
            "revision": expected_revision + 1}


def _component_not_implemented(project_id: str, component: str, db: Session):
    if not db.query(Project).filter(Project.id == project_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"{component} component engine integration pending")


@router.post("/{project_id}/gab-gen/run")
def run_gab_gen(project_id: str, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    return _component_not_implemented(project_id, "gab_gen", db)


@router.post("/{project_id}/esai-engine/run")
def run_esai(project_id: str, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    return _component_not_implemented(project_id, "esai_engine", db)
