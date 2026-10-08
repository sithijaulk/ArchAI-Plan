from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..models.project import Project
from ..models.component_run import ComponentRun
from ..schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from ..services.master_json import VALID_COMPONENTS, merge_master_json, new_master_json

router = APIRouter(prefix="/projects", tags=["Projects"])

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(project_name=data.project_name, description=data.description)
    db.add(project)
    db.flush()
    project.master_json = new_master_json(project.id, data.project_name)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, data: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    values = data.model_dump(exclude_unset=True)
    master_json = values.pop("master_json", None)
    for key, value in values.items():
        setattr(project, key, value)
    if master_json is not None:
        project.master_json = merge_master_json(project.master_json, master_json)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()


@router.get("/{project_id}/master-json")
def get_master_json(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.master_json


@router.post("/{project_id}/skip/{component}")
def skip_component(project_id: str, component: str, db: Session = Depends(get_db)):
    if component not in VALID_COMPONENTS:
        raise HTTPException(status_code=400, detail=f"Invalid component. Valid: {VALID_COMPONENTS}")
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Update only the processing status
    project.master_json = merge_master_json(
        project.master_json,
        {"processing": {component: {"status": "skipped"}}},
    )
    run = ComponentRun(project_id=project_id, component_name=component, status="skipped")
    db.add(run)
    db.commit()
    
    return {"component": component, "status": "skipped", "master_json": project.master_json}


def _component_not_implemented(project_id: str, component: str, db: Session):
    if not db.query(Project).filter(Project.id == project_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"{component} component engine integration pending")


@router.post("/{project_id}/gab-gen/run")
def run_gab_gen(project_id: str, db: Session = Depends(get_db)):
    return _component_not_implemented(project_id, "gab_gen", db)


@router.post("/{project_id}/vsai-rectifier/run")
def run_vsai(project_id: str, db: Session = Depends(get_db)):
    return _component_not_implemented(project_id, "vsai_rectifier", db)


@router.post("/{project_id}/esai-engine/run")
def run_esai(project_id: str, db: Session = Depends(get_db)):
    return _component_not_implemented(project_id, "esai_engine", db)


@router.post("/{project_id}/elia-engine/run")
def run_elia(project_id: str, db: Session = Depends(get_db)):
    return _component_not_implemented(project_id, "elia_engine", db)
