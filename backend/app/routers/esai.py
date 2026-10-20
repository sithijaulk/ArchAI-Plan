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
    CatalogCategoriesResponse,
    FinishesListResponse,
    StylesCatalogResponse,
    FunctionalRelationsResponse,
    CatalogValidationRequest,
    CatalogValidationResponse,
    ResolvedDesignInputResponse,
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
@global_router.get("/catalog/categories", response_model=CatalogCategoriesResponse)
def get_catalog_categories(db: Session = Depends(get_db)):
    service = EsaiEngineService(db)
    return CatalogCategoriesResponse(categories=service.get_catalog_categories())


@global_router.get("/catalog", response_model=CatalogListResponse)
@global_router.get("/catalog/items", response_model=CatalogListResponse)
def list_catalog(
    category: Optional[str] = None,
    room_type: Optional[str] = None,
    subtype: Optional[str] = None,
    style: Optional[str] = None,
    db: Session = Depends(get_db),
):
    service = EsaiEngineService(db)
    items = service.get_catalog_items(
        category=category,
        room_type=room_type,
        subtype=subtype,
        style=style,
    )
    return CatalogListResponse(total=len(items), items=items)


@global_router.get("/catalog/finishes", response_model=FinishesListResponse)
def list_finishes(
    category: Optional[str] = None,
    style: Optional[str] = None,
    db: Session = Depends(get_db),
):
    service = EsaiEngineService(db)
    finishes = service.get_finishes(category=category, style=style)
    return FinishesListResponse(total=len(finishes), finishes=finishes)


@global_router.post("/catalog/validate-selections", response_model=CatalogValidationResponse)
def validate_catalog_selections(
    payload: CatalogValidationRequest,
    db: Session = Depends(get_db),
):
    service = EsaiEngineService(db)
    errors: List[str] = []
    warnings: List[str] = []
    validated: List[Dict[str, Any]] = []

    for item in payload.items:
        item_id = item.get("id") or item.get("asset_id")
        if not item_id:
            errors.append("Catalog item payload must specify an 'id' or 'asset_id'.")
            continue
        try:
            asset = service.get_catalog_item(item_id)
            if payload.room_type and payload.room_type not in asset.supported_room_types:
                warnings.append(
                    f"Item '{asset.name}' ({asset.id}) is not marked for room type '{payload.room_type}'."
                )
            validated.append({
                "id": asset.id,
                "name": asset.name,
                "category": asset.category.value,
                "dimensions": asset.dimensions.dict(),
                "status": "valid",
            })
        except Exception:
            errors.append(f"Catalog asset '{item_id}' not found.")

    return CatalogValidationResponse(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        validated_items=validated,
    )


@global_router.get("/catalog/{catalog_id}")
def get_catalog_item(catalog_id: str, db: Session = Depends(get_db)):
    service = EsaiEngineService(db)
    try:
        return service.get_catalog_item(catalog_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Catalog item '{catalog_id}' not found.")


@global_router.get("/standards", response_model=StandardsListResponse)
@global_router.get("/knowledge/rules", response_model=StandardsListResponse)
def list_standards(
    enforceable_only: bool = False,
    mandatory_only: bool = False,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    service = EsaiEngineService(db)
    rules = service.get_standards(
        enforceable_only=enforceable_only,
        mandatory_only=mandatory_only,
        category=category,
    )
    return StandardsListResponse(total=len(rules), rules=rules)


@global_router.get("/room-profiles")
@global_router.get("/knowledge/room-profiles")
def get_room_profiles(db: Session = Depends(get_db)):
    service = EsaiEngineService(db)
    return {"profiles": service.get_room_profiles()}


@global_router.get("/knowledge/styles", response_model=StylesCatalogResponse)
def get_styles_catalog(db: Session = Depends(get_db)):
    service = EsaiEngineService(db)
    return StylesCatalogResponse(styles=service.get_styles())


@global_router.get("/knowledge/functional-relations", response_model=FunctionalRelationsResponse)
def get_functional_relations(
    primary_category: Optional[str] = None,
    related_category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    service = EsaiEngineService(db)
    rels = service.get_functional_relationships(
        primary_category=primary_category,
        related_category=related_category,
    )
    return FunctionalRelationsResponse(total=len(rels), relations=rels)


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 2: Multi-Level Client Preference Hierarchy
# ──────────────────────────────────────────────────────────────────────────────

# Building-level preferences
@project_router.get("/preferences/building")
def get_building_preferences(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    prefs = service.get_building_preferences(project_id)
    return {"preferences": prefs}


@project_router.put("/preferences/building")
def save_building_preferences(
    project_id: str,
    payload: Dict[str, Any],
    expected_revision: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    return service.save_building_preferences(project, payload, expected_revision=expected_revision)


@project_router.patch("/preferences/building")
def patch_building_preferences(
    project_id: str,
    payload: Dict[str, Any],
    expected_revision: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Merge payload into existing building preferences (PATCH semantics)."""
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    existing = service.get_building_preferences(project_id)
    merged = (existing["preferences"] if existing and existing.get("preferences") else {})
    merged.update(payload)
    return service.save_building_preferences(project, merged, expected_revision=expected_revision)


# Floor-level preferences
@project_router.get("/preferences/floors/{floor_id}")
def get_floor_preferences(project_id: str, floor_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    prefs = service.get_floor_preferences(project_id, floor_id)
    return {"floor_id": floor_id, "preferences": prefs}


@project_router.put("/preferences/floors/{floor_id}")
def save_floor_preferences(
    project_id: str,
    floor_id: str,
    payload: Dict[str, Any],
    expected_revision: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    return service.save_floor_preferences(project, floor_id, payload, expected_revision=expected_revision)


@project_router.patch("/preferences/floors/{floor_id}")
def patch_floor_preferences(
    project_id: str,
    floor_id: str,
    payload: Dict[str, Any],
    expected_revision: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    existing = service.get_floor_preferences(project_id, floor_id)
    merged = (existing["preferences"] if existing and existing.get("preferences") else {})
    merged.update(payload)
    return service.save_floor_preferences(project, floor_id, merged, expected_revision=expected_revision)


@project_router.delete("/preferences/floors/{floor_id}", status_code=status.HTTP_204_NO_CONTENT)
def reset_floor_preferences(project_id: str, floor_id: str, db: Session = Depends(get_db)):
    """Delete floor overrides; rooms fall back to building defaults."""
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    service.reset_floor_preferences(project, floor_id)


# Room-level preferences
@project_router.get("/preferences/rooms")
def list_room_preferences(
    project_id: str,
    floor_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    return {"room_preferences": service.list_room_preferences(project_id, floor_id=floor_id)}


@project_router.get("/preferences/rooms/{room_id}")
def get_room_preferences(project_id: str, room_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    prefs = service.get_room_preferences(project_id, room_id)
    if prefs is None:
        return {"room_id": room_id, "preferences": None, "note": "No saved preferences. Room will inherit from floor/building defaults."}
    return prefs


@project_router.put("/preferences/rooms/{room_id}")
def save_room_preferences(
    project_id: str,
    room_id: str,
    payload: Dict[str, Any],
    expected_revision: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    return service.save_room_preferences(project, room_id, payload, expected_revision=expected_revision)


@project_router.patch("/preferences/rooms/{room_id}")
def patch_room_preferences(
    project_id: str,
    room_id: str,
    payload: Dict[str, Any],
    expected_revision: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    return service.patch_room_preferences(project, room_id, payload, expected_revision=expected_revision)


@project_router.delete("/preferences/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
def reset_room_preferences(project_id: str, room_id: str, db: Session = Depends(get_db)):
    """Reset a room's preferences to inherited; does not delete the room itself."""
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    service.reset_room_preferences(project, room_id)


# Effective preference resolution
@project_router.get("/preferences/rooms/{room_id}/effective")
def get_effective_room_preferences(
    project_id: str,
    room_id: str,
    floor_id: str = Query(..., description="Floor ID the room belongs to"),
    db: Session = Depends(get_db),
):
    """
    Resolve and return the effective preferences for a room.
    Merges building → floor → room in order; more specific wins.
    Returns both the effective result and per-level source attribution.
    """
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    return service.get_effective_preferences(project, room_id, floor_id)


# Room-type preference schema (for dynamic form building on the frontend)
@project_router.get("/preferences/schema/{room_type}")
def get_preference_schema(project_id: str, room_type: str, db: Session = Depends(get_db)):
    _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    return service.get_preference_schema_for_room_type(room_type)


@global_router.get("/preference-schema/{room_type}")
def get_preference_schema_global(room_type: str, db: Session = Depends(get_db)):
    service = EsaiEngineService(db)
    return service.get_preference_schema_for_room_type(room_type)


# Orphan detection
@project_router.post("/preferences/detect-orphans")
def detect_orphaned_preferences(project_id: str, db: Session = Depends(get_db)):
    """
    Scan saved preferences and mark any whose room_id no longer exists
    in the current project geometry as orphaned.
    """
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    return service.detect_orphaned_preferences(project)


# Interior context summary (floors + rooms + saved preference status)
@project_router.get("/interior-context")
def get_interior_context(project_id: str, db: Session = Depends(get_db)):
    """
    Returns full floors/rooms list from geometry plus preference completion status per room.
    Used by the frontend navigator to show which rooms have been configured.
    """
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    floors = service.get_floors(project)
    saved_prefs = {r["room_id"]: r for r in service.list_room_preferences(project_id)}

    floors_out = []
    for floor in floors:
        rooms_out = []
        for room in floor.rooms:
            saved = saved_prefs.get(room.room_id)
            rooms_out.append({
                "room_id": room.room_id,
                "name": room.name,
                "room_type": room.room_type.value,
                "area_sqm": room.area_sqm,
                "preference_saved": saved is not None,
                "preference_revision": saved["preference_revision"] if saved else None,
                "is_orphaned": saved["is_orphaned"] if saved else False,
            })
        floors_out.append({
            "floor_id": floor.floor_id,
            "floor_name": floor.floor_name,
            "level_index": floor.level_index,
            "rooms": rooms_out,
        })

    staleness = service.check_geometry_staleness(project)
    return {
        "project_id": project_id,
        "project_name": project.project_name,
        "floors": floors_out,
        "total_floors": len(floors_out),
        "total_rooms": sum(len(f["rooms"]) for f in floors_out),
        "configured_rooms": sum(1 for p in saved_prefs.values() if not p["is_orphaned"]),
        "geometry_staleness": staleness,
    }


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 3: Deterministic Preference-to-Catalog GA Design Package Resolution
# ──────────────────────────────────────────────────────────────────────────────

@project_router.post(
    "/preferences/rooms/{room_id}/resolve-design-input",
    response_model=ResolvedDesignInputResponse,
)
@project_router.post(
    "/rooms/{room_id}/resolve-design-input",
    response_model=ResolvedDesignInputResponse,
)
def resolve_room_design_input(
    project_id: str,
    room_id: str,
    floor_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Deterministically resolves effective preferences, geometry, and catalog into
    the GA-ready design input contract without placing coordinates or mutating Master JSON.
    """
    project = _get_project_or_404(project_id, db)
    service = EsaiEngineService(db)
    resolved = service.resolve_room_design_input(project, room_id=room_id, floor_id=floor_id)
    return ResolvedDesignInputResponse(resolved=resolved)

