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

# Fallback in-memory/file storage when remote database is temporarily unreachable
_OFFLINE_PROJECTS: Dict[str, Any] = {}


def _save_offline_project(project_data: dict) -> None:
    p_id = project_data["id"]
    _OFFLINE_PROJECTS[p_id] = project_data
    try:
        shared_root = Path(__file__).resolve().parents[3] / "shared" / "vsai-bd"
        shared_root.mkdir(parents=True, exist_ok=True)
        if "master_json" in project_data and isinstance(project_data["master_json"], dict):
            with open(shared_root / f"{p_id}.json", "w", encoding="utf-8") as f:
                json.dump(project_data["master_json"], f, indent=2)
    except Exception as ex:
        logger.warning(f"Could not persist offline project to disk: {ex}")


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    try:
        project = Project(project_name=data.project_name, description=data.description)
        db.add(project)
        db.flush()
        project.master_json = new_master_json(project.id, data.project_name)
        db.commit()
        db.refresh(project)
        _save_offline_project({
            "id": project.id,
            "project_name": project.project_name,
            "description": project.description,
            "current_component": project.current_component,
            "master_json": project.master_json,
            "revision": project.revision or 1,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
        })
        return project
    except Exception as db_err:
        logger.warning(f"Remote database unreachable during project creation ({db_err}). Falling back to local session.")
        new_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        m_json = new_master_json(new_id, data.project_name)
        offline_obj = {
            "id": new_id,
            "project_name": data.project_name,
            "description": data.description,
            "current_component": "gab-gen",
            "master_json": m_json,
            "revision": 1,
            "created_at": now,
            "updated_at": now,
        }
        _save_offline_project(offline_obj)
        return offline_obj


@router.get("", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    try:
        return db.query(Project).order_by(Project.created_at.desc()).all()
    except Exception:
        return list(_OFFLINE_PROJECTS.values())


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)):
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            return project
    except Exception:
        pass

    if project_id in _OFFLINE_PROJECTS:
        return _OFFLINE_PROJECTS[project_id]

    # Check shared disk as well
    try:
        shared_file = Path(__file__).resolve().parents[3] / "shared" / "vsai-bd" / f"{project_id}.json"
        if shared_file.exists():
            with open(shared_file, "r", encoding="utf-8") as f:
                loaded_m = json.load(f)
            now = datetime.now(timezone.utc)
            return {
                "id": project_id,
                "project_name": loaded_m.get("project_name", "Recovered Project"),
                "description": loaded_m.get("description", ""),
                "current_component": "gab-gen",
                "master_json": loaded_m,
                "revision": 1,
                "created_at": now,
                "updated_at": now,
            }
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Project not found")


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, data: ProjectUpdate, db: Session = Depends(get_db)):
    values = data.model_dump(exclude_unset=True)
    expected_revision = values.pop("expected_revision", None)
    master_json = values.pop("master_json", None)

    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            current_revision = int(project.revision or 1)
            expected_revision = current_revision if expected_revision is None else expected_revision
            if expected_revision != current_revision:
                _revision_conflict(db, project_id, expected_revision)
            if master_json is not None:
                values["master_json"] = merge_master_json(project.master_json, master_json)
            if not values:
                return project
            updated = _compare_and_swap_project(db, project, expected_revision, values)
            _save_offline_project({
                "id": updated.id,
                "project_name": updated.project_name,
                "description": updated.description,
                "current_component": updated.current_component,
                "master_json": updated.master_json,
                "revision": updated.revision,
                "created_at": updated.created_at,
                "updated_at": updated.updated_at,
            })
            return updated
    except Exception as db_err:
        logger.warning(f"Remote DB error during update ({db_err}). Updating local/offline state.")

    # Offline update
    current_offline = _OFFLINE_PROJECTS.get(project_id)
    if not current_offline:
        current_offline = {
            "id": project_id,
            "project_name": values.get("project_name", "Offline Project"),
            "description": values.get("description", ""),
            "current_component": "gab-gen",
            "master_json": {},
            "revision": 1,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    if master_json is not None:
        values["master_json"] = merge_master_json(current_offline.get("master_json", {}), master_json)
    current_offline.update(values)
    current_offline["revision"] = current_offline.get("revision", 1) + 1
    current_offline["updated_at"] = datetime.now(timezone.utc)
    _save_offline_project(current_offline)
    return current_offline


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()


@router.get("/{project_id}/master-json")
def get_master_json(project_id: str, response: Response, db: Session = Depends(get_db)):
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            response.headers["ETag"] = f'"{project.revision}"'
            response.headers["X-Project-Revision"] = str(project.revision)
            mj = dict(project.master_json or {})
            mj["project_revision"] = int(project.revision)
            return mj
    except Exception:
        pass

    if project_id in _OFFLINE_PROJECTS:
        offline = _OFFLINE_PROJECTS[project_id]
        rev = offline.get("revision", 1)
        response.headers["ETag"] = f'"{rev}"'
        response.headers["X-Project-Revision"] = str(rev)
        return offline.get("master_json")

    raise HTTPException(status_code=404, detail="Project not found")


def _has_floor_plan_geometry(master_json: Dict[str, Any]) -> bool:
    floor_plan = master_json.get("floor_plan") or {}
    rect = master_json.get("structural_rectification") or {}
    return bool(
        floor_plan.get("floors")
        or floor_plan.get("rooms")
        or rect.get("floor_plan")
        or rect.get("rectified_floor_plan")
    )


def _ensure_skip_allowed(component: str, master_json: Dict[str, Any]) -> None:
    """Block skipping Component 2 when neither Component 1 nor an uploaded image produced a floor plan."""
    if component == "vsai_rectifier" and not _has_floor_plan_geometry(master_json):
        raise HTTPException(
            status_code=409,
            detail=(
                "No floor plan found for this project. Component 1 (GAB-Gen) was skipped and no floor plan "
                "image was uploaded in Component 2. Please run Component 1 first, or upload a floor plan "
                "image in Component 2, before continuing."
            ),
        )


@router.post("/{project_id}/skip/{component}")
def skip_component(project_id: str, component: str, expected_revision: int | None = Query(default=None, ge=1),
                   db: Session = Depends(get_db)):
    if component not in VALID_COMPONENTS:
        raise HTTPException(status_code=400, detail=f"Invalid component. Valid: {VALID_COMPONENTS}")

    project = None
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
    except Exception:
        pass

    if not project:
        if project_id in _OFFLINE_PROJECTS:
            offline = _OFFLINE_PROJECTS[project_id]
            current_revision = int(offline.get("revision", 1))
            existing_mj = offline.get("master_json") or {}
            _ensure_skip_allowed(component, existing_mj)
            offline_patch: Dict[str, Any] = {"processing": {component: {"status": "skipped"}}}

            updated_master = merge_master_json(
                existing_mj,
                offline_patch,
            )
            offline["master_json"] = updated_master
            offline["revision"] = current_revision + 1
            offline["updated_at"] = datetime.now(timezone.utc)
            _save_offline_project(offline)
            return {
                "component": component,
                "status": "skipped",
                "master_json": updated_master,
                "revision": current_revision + 1,
            }
        raise HTTPException(status_code=404, detail="Project not found")

    current_revision = int(project.revision or 1)
    if expected_revision is not None and expected_revision != current_revision:
        _revision_conflict(db, project_id, expected_revision)
    expected_revision = current_revision

    # No synthetic/dummy layout is ever seeded here. Skipping Component 1 just marks it skipped
    # (the user can then upload a floor-plan image in Component 2). Skipping Component 2 with no
    # floor plan geometry at all is blocked, because Components 3 and 4 would have nothing to use.
    _ensure_skip_allowed(component, project.master_json or {})
    patch: Dict[str, Any] = {"processing": {component: {"status": "skipped"}}}

    updated_master = merge_master_json(
        project.master_json,
        patch,
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


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            db.delete(project)
            db.commit()
    except Exception as e:
        logger.warning(f"Error deleting project from db: {e}")
    if project_id in _OFFLINE_PROJECTS:
        _OFFLINE_PROJECTS.pop(project_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


