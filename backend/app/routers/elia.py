from __future__ import annotations

import logging
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..components.elia_engine.exceptions import ELIAError
from ..components.elia_engine.adapter import normalize_master_json
from ..components.elia_engine.geometry import feet_to_meters
from ..components.elia_engine.parser import parse_exterior_context
from ..components.elia_engine.requirements import normalize_requirements
from ..components.elia_engine.rule_repository import elia_rules, lighting_rules, vehicle_profiles, vegetation_catalog
from ..components.elia_engine.schemas import ELIARequest, ELIAResponse
from ..components.elia_engine.solar import extract_master_location, fetch_live_solar_conditions, search_sri_lanka_locations
from ..components.elia_engine.generation import generate_exterior
from ..components.elia_engine.gate_garage import plan_gate
from ..components.elia_engine.output import build_processing_master, build_updated_master
from ..database import get_db
from ..dependencies import require_admin
from ..models.component_run import ComponentRun
from ..models.project import Project

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ELIA-Engine"])


def _safe_diagnostic(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "<truncated>"
    if value is None or isinstance(value, (str, bool, int)):
        return value if not isinstance(value, str) else value[:1000]
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else "<non_finite>"
    if isinstance(value, Mapping):
        return {str(key)[:200]: _safe_diagnostic(item, depth + 1) for key, item in list(value.items())[:500]}
    if isinstance(value, (list, tuple)):
        return [_safe_diagnostic(item, depth + 1) for item in value[:500]]
    return str(value)[:1000]


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
                    should_persist: bool, expected_revision: int | None = None,
                    candidate_output: dict[str, Any] | None = None,
                    source_revision: int | None = None) -> None:
    db.rollback()
    run = db.query(ComponentRun).filter(ComponentRun.id == run_id).first()
    project = db.query(Project).filter(Project.id == project_id).first()
    if run is not None:
        run.status = "failed"
        run.error_message = f"{code}: {message}"[:4000]
        run.completed_at = datetime.now(timezone.utc)
        if candidate_output is not None:
            diagnostic = _safe_diagnostic(candidate_output)
            json.dumps(diagnostic, allow_nan=False)
            run.output_json = diagnostic
    if should_persist and project is not None:
        revision = expected_revision if expected_revision is not None else project.revision
        if revision is not None:
            # Only update metadata if this run still owns the project's elia_engine slot
            current_elia = (project.master_json or {}).get("processing", {}).get("elia_engine", {})
            if isinstance(current_elia, dict) and current_elia.get("run_id", run_id) != run_id:
                # A newer run has already claimed ownership; skip metadata update.
                db.commit()
                return
            document = build_processing_master(project.master_json or {}, {
                "status": "failed", "run_id": run_id, "version": "1.0", "schema_version": "1.0",
                "completed_at": datetime.now(timezone.utc).isoformat(), "error_code": code,
                "source_revision": source_revision if source_revision is not None else revision,
            })
            db.execute(update(Project).where(Project.id == project_id, Project.revision == revision).values(
                master_json=document, revision=revision + 1))
    db.commit()


def _record_stale_conflict(db: Session, run_id: str, project_id: str, source_revision: int,
                           candidate_output: dict[str, Any]) -> int | None:
    db.rollback()
    run = db.query(ComponentRun).filter(ComponentRun.id == run_id).first()
    project = db.query(Project).filter(Project.id == project_id).first()
    if run is not None:
        run.status = "failed"
        run.output_json = candidate_output
        run.error_message = "ELIA_STALE_SOURCE_REVISION: Project changed while ELIA was running."
        run.completed_at = datetime.now(timezone.utc)
        processing = (project.master_json or {}).get("processing", {}) if project is not None else {}
        elia_metadata = processing.get("elia_engine") if isinstance(processing, dict) else None
        latest_revision = int(project.revision) if project is not None and project.revision is not None else None
        if (project is not None and latest_revision is not None and
            isinstance(elia_metadata, dict) and elia_metadata.get("run_id") == run_id):
            document = build_processing_master(project.master_json or {}, {
                "status": "failed", "run_id": run_id, "version": "1.0", "schema_version": "1.0",
                "error_code": "ELIA_STALE_SOURCE_REVISION", "source_revision": source_revision,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            changed = db.execute(update(Project).where(
                Project.id == project_id, Project.revision == latest_revision
            ).values(master_json=document, revision=latest_revision + 1))
            if changed.rowcount == 1:
                latest_revision += 1
            else:
                db.rollback()
                run = db.query(ComponentRun).filter(ComponentRun.id == run_id).first()
                if run is not None:
                    run.status = "failed"
                    run.output_json = candidate_output
                    run.error_message = "ELIA_STALE_SOURCE_REVISION: Project changed while ELIA was running."
                    run.completed_at = datetime.utcnow()
                current = db.query(Project).filter(Project.id == project_id).first()
                latest_revision = int(current.revision) if current is not None else None
    db.commit()
    return latest_revision


@router.post("/projects/{project_id}/elia-engine/run", response_model=ELIAResponse)
def run_project_elia(project_id: str, request: ELIARequest,
                     db: Session = Depends(get_db), _admin=Depends(require_admin)):
    project = _project_or_404(db, project_id)
    db.refresh(project)
    source_revision = int(project.revision or 1)
    source_is_supplied = request.master_json is not None
    should_persist = not source_is_supplied or request.apply_to_project
    source_master = deepcopy(request.master_json if source_is_supplied else project.master_json)
    if not isinstance(source_master, dict):
        raise HTTPException(status_code=422, detail={"code": "ELIA_INVALID_MASTER_JSON", "message": "Project has no valid Master JSON object."})
    if should_persist and source_is_supplied:
        if request.source_revision is None:
            raise HTTPException(status_code=422, detail={"code": "ELIA_SOURCE_REVISION_REQUIRED",
                                                        "message": "source_revision is required when applying a supplied Master JSON snapshot."})
        if request.source_revision != source_revision or source_master != (project.master_json or {}):
            raise HTTPException(status_code=409, detail={"code": "ELIA_STALE_SOURCE_REVISION",
                                                        "message": "The supplied Master JSON does not match the current project revision.",
                                                        "current_revision": source_revision})

    requirements = request.requirements.model_dump(mode="json", exclude_none=True, exclude_unset=True)
    run_input = {"requirements": requirements, "master_json_snapshot": source_master,
                 "source_revision": source_revision,
                 "master_json_source": "request" if source_is_supplied else "project_database",
                 "generation_mode": request.generation_mode, "model_version": None,
                 "effective_requirement_units": requirements.get("units", "m"),
                 "requirement_units_explicit": "units" in request.requirements.model_fields_set,
                 "schema_version": "1.0", "applied_to_project": should_persist}
    run = ComponentRun(
        project_id=project_id,
        component_name="elia_engine",
        status="processing",
        started_at=datetime.now(timezone.utc),
        input_json=run_input,
    )
    db.add(run)
    db.flush()
    expected_revision = source_revision
    if should_persist:
        processing_master = build_processing_master(project.master_json or {}, {
            "status": "processing", "run_id": run.id, "version": "1.0", "schema_version": "1.0",
            "generation_mode": request.generation_mode, "source_revision": source_revision,
            "started_at": datetime.now(timezone.utc).isoformat(),
        })
        changed = db.execute(update(Project).where(
            Project.id == project_id, Project.revision == source_revision
        ).values(master_json=processing_master, revision=source_revision + 1))
        if changed.rowcount != 1:
            db.rollback()
            run.status = "failed"
            run.error_message = "ELIA_STALE_SOURCE_REVISION: Project changed before ELIA started."
            run.completed_at = datetime.now(timezone.utc)
            db.add(run)
            db.commit()
            current_rev = int(db.query(Project).filter(Project.id == project_id).one().revision)
            raise HTTPException(status_code=409, detail={"code": "ELIA_STALE_SOURCE_REVISION",
                                                        "message": "Project changed before the ELIA run started.",
                                                        "expected_revision": source_revision,
                                                        "current_revision": current_rev})
        expected_revision = source_revision + 1
    db.commit()
    db.refresh(run)
    if should_persist:
        db.refresh(project)

    try:
        exterior, outcome = generate_exterior(source_master, requirements, run.id, request.generation_mode)
        exterior["started_at"] = run.started_at.replace(tzinfo=timezone.utc).isoformat() if run.started_at else None
        run.status = "completed"
        run.output_json = exterior
        run.completed_at = datetime.now(timezone.utc)
        run.input_json = {**(run.input_json or {}), "model_version": exterior.get("model_version")}
        try:
            json.dumps(exterior, allow_nan=False)
            response = ELIAResponse(project_id=project_id, run_id=run.id,
                                    status="completed" if outcome == "valid" else "infeasible",
                                    outcome=outcome, exterior_landscape=exterior,
                                    master_json_updated=should_persist, generation_mode=request.generation_mode)
            json.dumps(response.model_dump(mode="json"), allow_nan=False)
        except Exception as exc:
            # Output validation failure — this is a server-side bug, not malformed client input.
            _record_failure(db, run.id, project_id, "ELIA_INVALID_OUTPUT",
                            f"ELIA produced invalid output: {exc}", should_persist,
                            expected_revision, exterior, source_revision)
            raise HTTPException(
                status_code=500,
                detail={"code": "ELIA_INVALID_OUTPUT",
                        "message": f"ELIA produced invalid output: {exc}"}
            ) from exc
        if should_persist:
            current_master = project.master_json or {}
            updated_master = build_updated_master(
                current_master, exterior, run.id, outcome,
                generation_mode=request.generation_mode,
                source_revision=source_revision,
                model_version=exterior.get("model_version"),
            )
            values: dict[str, Any] = {"master_json": updated_master, "revision": expected_revision + 1}
            if outcome == "valid":
                values["current_component"] = "elia_engine"
            changed = db.execute(update(Project).where(
                Project.id == project_id, Project.revision == expected_revision
            ).values(**values))
            if changed.rowcount != 1:
                current_revision = _record_stale_conflict(db, run.id, project_id, source_revision, exterior)
                raise HTTPException(status_code=409, detail={"code": "ELIA_STALE_SOURCE_REVISION",
                                                            "message": "Project changed while ELIA was running; the candidate was saved to run history.",
                                                            "expected_revision": expected_revision,
                                                            "current_revision": current_revision})
        db.commit()
        return response
    except HTTPException:
        raise
    except ELIAError as exc:
        _record_failure(db, run.id, project_id, exc.code, exc.message, should_persist,
                        expected_revision, getattr(exc, "candidate_output", None), source_revision)
        detail = {"code": exc.code, "message": exc.message}
        if exc.code == "ELIA_MODEL_UNAVAILABLE":
            detail["generation_status"] = "model_unavailable"
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc
    except Exception as exc:
        logger.exception("ELIA processing failed for project %s", project_id)
        _record_failure(db, run.id, project_id, "ELIA_PROCESSING_FAILED", "ELIA processing failed; see server logs.",
                        should_persist, expected_revision, getattr(exc, "candidate_output", None), source_revision)
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
        normalized = normalize_requirements(request.requirements.model_dump(mode="json", exclude_none=True, exclude_unset=True), master, context.source_units)
        canonical_master = normalize_master_json(master)
        if plan_gate(context.land, context.house, canonical_master, normalized["access"], context.unit_scale) is None:
            raise ELIAError("ELIA_MISSING_ROAD_ACCESS",
                            "ELIA requires inherited road-side/edge access information or an existing gate.")
    except ELIAError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"valid": True, "project_id": project_id, "normalized_requirements": normalized,
            "geometry": {"land_area_m2": context.land.area, "house_footprint_area_m2": context.house.area,
                 "source_units": context.source_units},
            "orientation": {"north_angle_degrees": normalized["north_angle"],
                    "convention": normalized["north_orientation_convention"]}}


@router.post("/elia-engine/preview")
def preview_standalone_elia(request: ELIARequest, _admin=Depends(require_admin)):
    """Run a validated supplied Master JSON without writing project data or history."""
    if request.master_json is None:
        raise HTTPException(status_code=422, detail={"code": "ELIA_INVALID_MASTER_JSON", "message": "A Master JSON object is required for preview."})
    run_id = str(uuid4())
    try:
        exterior, outcome = generate_exterior(request.master_json,
                                              request.requirements.model_dump(mode="json", exclude_none=True, exclude_unset=True),
                                              run_id, request.generation_mode)
    except ELIAError as exc:
        detail = {"code": exc.code, "message": exc.message}
        if exc.code == "ELIA_MODEL_UNAVAILABLE":
            detail["generation_status"] = "model_unavailable"
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc
    try:
        json.dumps(exterior, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail={"code": "ELIA_SERIALIZATION_ERROR",
                                                    "message": f"Generated exterior result is not JSON-serializable: {exc}"}) from exc
    updated = build_updated_master(request.master_json, exterior, run_id, outcome,
                                   generation_mode=request.generation_mode,
                                   source_revision=request.source_revision,
                                   model_version=exterior.get("model_version"))
    return {"run_id": run_id, "status": "completed" if outcome == "valid" else "infeasible",
            "outcome": outcome, "exterior_landscape": exterior, "master_json": updated,
            "generation_mode": request.generation_mode, "persisted": False}


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
