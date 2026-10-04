from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..components.elia_engine.exceptions import ELIAError
from ..components.elia_engine.geometry import feet_to_meters
from ..components.elia_engine.parser import parse_exterior_context
from ..components.elia_engine.requirements import normalize_requirements
from ..components.elia_engine.rule_repository import elia_rules, lighting_rules, vehicle_profiles, vegetation_catalog
from ..components.elia_engine.schemas import ELIARequest, ELIAResponse
from ..components.elia_engine.solar import extract_master_location, fetch_live_solar_conditions, search_sri_lanka_locations
from ..components.elia_engine.service import run_elia
from ..components.elia_engine.output import build_updated_master
from ..database import get_db
from ..dependencies import require_admin
from ..models.component_run import ComponentRun
from ..models.project import Project

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ELIA-Engine"])


def _project_or_404(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _set_processing(project: Project, metadata: dict[str, Any]) -> None:
    document = deepcopy(project.master_json or {})
    processing = document.setdefault("processing", {})
    processing["elia_engine"] = metadata
    project.master_json = document


def _record_failure(db: Session, run_id: str, project_id: str, code: str, message: str,
                    should_persist: bool) -> None:
    db.rollback()
    run = db.query(ComponentRun).filter(ComponentRun.id == run_id).first()
    project = db.query(Project).filter(Project.id == project_id).first()
    if run is not None:
        run.status = "failed"
        run.error_message = f"{code}: {message}"[:4000]
        run.completed_at = datetime.utcnow()
    if should_persist and project is not None:
        _set_processing(project, {"status": "failed", "run_id": run_id, "version": "1.0",
                                  "completed_at": datetime.now(timezone.utc).isoformat(), "error_code": code})
    db.commit()


@router.post("/projects/{project_id}/elia-engine/run", response_model=ELIAResponse)
def run_project_elia(project_id: str, request: ELIARequest,
                     db: Session = Depends(get_db), _admin=Depends(require_admin)):
    project = _project_or_404(db, project_id)
    source_is_supplied = request.master_json is not None
    should_persist = not source_is_supplied or request.apply_to_project
    source_master = request.master_json if source_is_supplied else project.master_json
    if not isinstance(source_master, dict):
        raise HTTPException(status_code=422, detail={"code": "ELIA_INVALID_MASTER_JSON", "message": "Project has no valid Master JSON object."})

    run = ComponentRun(
        project_id=project_id,
        component_name="elia_engine",
        status="processing",
        started_at=datetime.utcnow(),
        input_json={"requirements": request.requirements.model_dump(mode="json", exclude_none=True),
                    "master_json_source": "request" if source_is_supplied else "project_database",
                    "applied_to_project": should_persist},
    )
    db.add(run)
    db.flush()
    if should_persist:
        _set_processing(project, {"status": "processing", "run_id": run.id, "version": "1.0",
                                  "started_at": datetime.now(timezone.utc).isoformat()})
    db.commit()
    db.refresh(run)

    try:
        requirements = request.requirements.model_dump(mode="json", exclude_none=True)
        exterior, outcome = run_elia(source_master, requirements, run.id)
        exterior["started_at"] = run.started_at.replace(tzinfo=timezone.utc).isoformat() if run.started_at else None
        run.status = "completed"
        run.output_json = exterior
        run.completed_at = datetime.utcnow()
        if should_persist:
            project.master_json = build_updated_master(source_master, exterior, run.id, outcome)
            project.current_component = "elia_engine"
        db.commit()
        return ELIAResponse(project_id=project_id, run_id=run.id,
                            status="completed" if outcome == "valid" else "infeasible",
                            outcome=outcome, exterior_landscape=exterior, master_json_updated=should_persist)
    except ELIAError as exc:
        _record_failure(db, run.id, project_id, exc.code, exc.message, should_persist)
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    except Exception as exc:
        logger.exception("ELIA processing failed for project %s", project_id)
        _record_failure(db, run.id, project_id, "ELIA_PROCESSING_FAILED", "ELIA processing failed; see server logs.", should_persist)
        raise HTTPException(status_code=500, detail={"code": "ELIA_PROCESSING_FAILED", "message": "ELIA processing failed."}) from exc


@router.get("/projects/{project_id}/elia-engine/context")
def get_elia_context(project_id: str, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    project = _project_or_404(db, project_id)
    return {"project_id": project.id, "master_json": project.master_json}


@router.post("/projects/{project_id}/elia-engine/validate-input")
def validate_elia_input(project_id: str, request: ELIARequest,
                        db: Session = Depends(get_db), _admin=Depends(require_admin)):
    project = _project_or_404(db, project_id)
    master = request.master_json if request.master_json is not None else project.master_json
    try:
        context = parse_exterior_context(master, default_units=elia_rules()["units"]["default_input"])
        normalized = normalize_requirements(request.requirements.model_dump(mode="json", exclude_none=True), master, context.source_units)
    except ELIAError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"valid": True, "project_id": project_id, "normalized_requirements": normalized,
            "geometry": {"land_area_m2": context.land.area, "house_footprint_area_m2": context.house.area,
                         "source_units": context.source_units}}


@router.post("/elia-engine/preview")
def preview_standalone_elia(request: ELIARequest, _admin=Depends(require_admin)):
    """Run a validated supplied Master JSON without writing project data or history."""
    if request.master_json is None:
        raise HTTPException(status_code=422, detail={"code": "ELIA_INVALID_MASTER_JSON", "message": "A Master JSON object is required for preview."})
    run_id = str(uuid4())
    try:
        exterior, outcome = run_elia(request.master_json,
                                     request.requirements.model_dump(mode="json", exclude_none=True), run_id)
    except ELIAError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    updated = build_updated_master(request.master_json, exterior, run_id, outcome)
    return {"run_id": run_id, "status": "completed" if outcome == "valid" else "infeasible",
            "outcome": outcome, "exterior_landscape": exterior, "master_json": updated,
            "persisted": False}


@router.get("/projects/{project_id}/elia-engine/result")
def get_elia_result(project_id: str, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    _project_or_404(db, project_id)
    run = (db.query(ComponentRun).filter(ComponentRun.project_id == project_id,
                                         ComponentRun.component_name == "elia_engine")
           .order_by(ComponentRun.started_at.desc()).first())
    if run is None:
        raise HTTPException(status_code=404, detail="No ELIA run exists for this project")
    return {"run_id": run.id, "status": run.status, "output": run.output_json,
            "error_message": run.error_message, "started_at": run.started_at, "completed_at": run.completed_at}


@router.get("/projects/{project_id}/elia-engine/solar/current")
def get_project_live_solar(project_id: str, latitude: float | None = Query(default=None, ge=-90, le=90),
                           longitude: float | None = Query(default=None, ge=-180, le=180),
                           timezone: str | None = None, db: Session = Depends(get_db),
                           _admin=Depends(require_admin)):
    project = _project_or_404(db, project_id)
    master = project.master_json if isinstance(project.master_json, dict) else {}
    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=422, detail={"code": "ELIA_INVALID_LOCATION",
                                                     "message": "latitude and longitude must be provided together."})
    try:
        if latitude is None:
            location = extract_master_location(master)
            latitude, longitude = location["latitude"], location["longitude"]
            timezone = timezone or location.get("timezone")
        return fetch_live_solar_conditions(latitude, longitude, timezone)
    except ELIAError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc


@router.get("/elia-engine/rules")
def get_elia_rules():
    return elia_rules()


@router.get("/elia-engine/vehicle-profiles")
def get_vehicle_profiles():
    return vehicle_profiles()


@router.get("/elia-engine/vegetation-catalog")
def get_vegetation_catalog():
    return vegetation_catalog()


@router.get("/elia-engine/lighting-rules")
def get_lighting_rules():
    return lighting_rules()


@router.get("/elia-engine/locations/search")
def search_elia_locations(name: str = Query(min_length=2, max_length=100), _admin=Depends(require_admin)):
    try:
        return {"query": name, "country_code": "LK", "provider": "OpenStreetMap Nominatim",
                "attribution": "© OpenStreetMap contributors", "results": search_sri_lanka_locations(name)}
    except ELIAError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
