from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.esai import EsaiRoomRequirement, EsaiDesignPreference, EsaiSavedConfig
from app.models.project import Project

router = APIRouter(
    prefix="/api/projects/{project_id}/esai-engine",
    tags=["esai-engine"]
)

# Placeholder route to run the ESAI Engine (returns 501 currently)
@router.post("/run")
def run_esai_engine(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 501 Not Implemented (as instructed for Stage 1)
    raise HTTPException(status_code=501, detail="ESAI-Engine optimizer not yet implemented in Stage 1")

@router.get("/context")
def get_context(project_id: str, db: Session = Depends(get_db)):
    return {"project_id": project_id, "status": "ESAI-Engine is available"}

@router.get("/floors")
def get_floors(project_id: str, db: Session = Depends(get_db)):
    # In a real implementation this would extract floors from the Master JSON
    return {"floors": []}

@router.get("/rooms")
def get_rooms(project_id: str, db: Session = Depends(get_db)):
    # In a real implementation this would extract rooms from the Master JSON
    return {"rooms": []}

@router.get("/requirements")
def get_requirements(project_id: str, db: Session = Depends(get_db)):
    reqs = db.query(EsaiRoomRequirement).filter(EsaiRoomRequirement.project_id == project_id).all()
    return {"requirements": reqs}

@router.put("/requirements")
def update_requirements(project_id: str, data: dict, db: Session = Depends(get_db)):
    # Mock update
    return {"status": "success", "message": "Requirements updated"}
