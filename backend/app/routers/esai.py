"""
ESAI API Router
Exposes context, floor/room exploration, furniture catalog, Neufert standards,
client requirement persistence, saved configs CRUD, and deterministic validation.
Preserves controlled 501 Not Implemented on the /run optimization endpoint.
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models.project import Project
from app.components.esai_engine.service import EsaiEngineService
from app.components.esai_engine.contracts import (
    RoomRequirementsDTO,
    ValidationResultDTO,
    FloorDTO,
    RoomDTO,
)
from app.schemas.esai import (
    ContextResponse,
    FloorsResponse,
    RoomsResponse,
    CatalogListResponse,
    StandardsListResponse,
    SavedConfigCreateRequest,
    SavedConfigUpdateRequest,
    SavedConfigResponse,
    RequirementsSaveResponse,
)

# Project-scoped router requiring authentication & authorization
project_router = APIRouter(
    prefix="/api/projects/{project_id}/esai-engine",
    tags=["ESAI-Engine"],
    dependencies=[Depends(require_admin)]
)

# Global ESAI knowledge endpoints (catalog, standards, room-profiles)
global_router = APIRouter(
    prefix="/api/esai",
    tags=["ESAI-Knowledge"]
)


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found."
        )
    return project


# 1. Controlled 501 Run Endpoint (Preserved for Stage 2)
@project_router.post("/run")
def run_esai_engine(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(project_id, db)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="ESAI-Engine Genetic Algorithm optimizer is scheduled for Stage 2. Stage 1 provides complete backend data contracts, geometry validation, requirements persistence, and catalog services."
    )


# 2. Context & Discovery Endpoints
@project_router.get("/context", response_model=ContextResponse)
def get_project_context(project_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    ctx = service.get_structural_context(project)
    total_rooms = sum(len(f.rooms) for f in ctx.floors)
    return ContextResponse(
        project_id=project.id,
        project_name=project.project_name,
        unit=ctx.unit,
        total_floors=len(ctx.floors),
        total_rooms=total_rooms
    )


@project_router.get("/floors", response_model=FloorsResponse)
def get_project_floors(project_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    floors = service.get_floors(project)
    return FloorsResponse(floors=floors)


@project_router.get("/rooms", response_model=RoomsResponse)
def get_project_rooms(project_id: str, floor_id: Optional[str] = None, db: Session = Depends(get_db)):
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    rooms = service.get_rooms(project, floor_id=floor_id)
    return RoomsResponse(rooms=rooms)


@project_router.get("/rooms/{room_id}", response_model=RoomDTO)
def get_single_room(project_id: str, room_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    room = service.get_room_by_id(project, room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room '{room_id}' not found in project '{project_id}'."
        )
    return room


# 3. Requirements Persistence
@project_router.get("/requirements")
def get_requirements(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    reqs = service.get_all_requirements(project_id)
    return {"requirements": reqs}


@project_router.put("/requirements", response_model=RequirementsSaveResponse)
def save_room_requirements(
    project_id: str,
    payload: RoomRequirementsDTO,
    status_param: str = Query(default="draft", alias="status"),
    expected_revision: Optional[int] = Query(default=None),
    db: Session = Depends(get_db)
):
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    result = service.save_room_requirements(
        project,
        payload,
        status=status_param,
        expected_revision=expected_revision
    )
    return RequirementsSaveResponse(
        id=result["id"],
        project_id=result["project_id"],
        room_id=result["room_id"],
        status=result["status"],
        validation=result["validation"]
    )


# 4. Geometry Staleness & Revision Tracking
@project_router.get("/staleness")
def check_geometry_staleness(project_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    return service.check_geometry_staleness(project)


# 5. Design Preferences (Preparation for Stage 2)
@project_router.get("/preferences")
def get_preferences(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    prefs = service.get_design_preferences(project_id)
    return {"preferences": prefs}


@project_router.put("/preferences")
def save_preferences(
    project_id: str,
    payload: Dict[str, Any],
    expected_revision: Optional[int] = Query(default=None),
    db: Session = Depends(get_db)
):
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    return service.save_design_preferences(project, payload, expected_revision=expected_revision)


# 6. Input Validation
@project_router.post("/validate-input", response_model=ValidationResultDTO)
def validate_project_input(project_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    return service.validate_project_input(project)



# 5. Saved Configurations CRUD
@project_router.get("/configurations", response_model=List[SavedConfigResponse])
def list_configurations(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    return service.list_saved_configurations(project_id)


@project_router.post("/configurations", response_model=SavedConfigResponse, status_code=status.HTTP_201_CREATED)
def create_configuration(project_id: str, payload: SavedConfigCreateRequest, db: Session = Depends(get_db)):
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    created = service.create_saved_configuration(
        project=project,
        name=payload.configuration_name,
        room_ids=payload.room_ids,
        settings=payload.settings
    )
    return created


@project_router.put("/configurations/{config_id}", response_model=SavedConfigResponse)
def update_configuration(
    project_id: str,
    config_id: str,
    payload: SavedConfigUpdateRequest,
    db: Session = Depends(get_db)
):
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    updated = service.update_saved_configuration(
        project=project,
        config_id=config_id,
        name=payload.configuration_name,
        room_ids=payload.room_ids,
        settings=payload.settings
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Saved configuration not found.")
    return updated


@project_router.delete("/configurations/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_configuration(project_id: str, config_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    success = service.delete_saved_configuration(project_id, config_id)
    if not success:
        raise HTTPException(status_code=404, detail="Saved configuration not found.")


# 6. Global Knowledge Endpoints
@global_router.get("/catalog", response_model=CatalogListResponse)
def list_catalog(
    category: Optional[str] = None,
    room_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    service = EsaiEngineService(db)
    items = service.get_catalog_items(category=category, room_type=room_type)
    return CatalogListResponse(total=len(items), items=items)


@global_router.get("/catalog/{catalog_id}")
def get_catalog_item(catalog_id: str, db: Session = Depends(get_db)):
    service = EsaiEngineService(db)
    try:
        return service.get_catalog_item(catalog_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Catalog item '{catalog_id}' not found.")


@global_router.get("/standards", response_model=StandardsListResponse)
def list_standards(enforceable_only: bool = False, db: Session = Depends(get_db)):
    service = EsaiEngineService(db)
    rules = service.get_standards(enforceable_only=enforceable_only)
    return StandardsListResponse(total=len(rules), rules=rules)

@global_router.get("/room-profiles")
def get_room_profiles(db: Session = Depends(get_db)):
    service = EsaiEngineService(db)
    return {"profiles": service.get_room_profiles()}


# Backward compatibility alias
router = project_router


