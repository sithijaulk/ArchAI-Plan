from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import update
from sqlalchemy.orm import Session
from typing import Any, List

from ..database import get_db
from ..dependencies import require_admin
from ..models.project import Project
from ..models.component_run import ComponentRun
from ..schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from ..services.master_json import VALID_COMPONENTS, merge_master_json, new_master_json

router = APIRouter(prefix="/projects", tags=["Projects"])


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


@router.post("/{project_id}/vsai-rectifier/run")
def run_vsai(project_id: str, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    return _component_not_implemented(project_id, "vsai_rectifier", db)


@router.post("/{project_id}/esai-engine/run")
def run_esai(project_id: str, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    return _component_not_implemented(project_id, "esai_engine", db)
