"""
ESAI Engine Core Service
Orchestrates Master JSON parsing, room and floor discovery, client requirement management,
catalog queries, standards retrieval, and cross-validation without AI optimization.
Maintains controlled HTTP 501 on run() until Stage 2.
Enforces transactional persistence and non-destructive Master JSON transformations.
"""
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status as http_status
from sqlalchemy.orm import Session

from app.models.project import Project
from .catalog import FurnitureCatalogRepository, CatalogAsset
from .rules import ErgonomicStandardsRepository, ErgonomicRule
from .contracts import (
    StructuralInputDTO,
    RoomDTO,
    FloorDTO,
    RoomRequirementsDTO,
    ValidationResultDTO,
    ProjectPreferencesDTO,
    ValidationMessage,
)
from .parser import StructuralInputParser
from .normalizer import SpatialNormalizer
from .validators import EsaiInputValidator
from .repositories import EsaiDatabaseRepository
from .geometry import compute_geometry_fingerprint
from .exceptions import EsaiException, StructuralInputValidationError



class EsaiEngineService:
    """Core domain service for ESAI Stage 1 backend operations."""

    def __init__(self, db: Session):
        self.db = db
        self.catalog_repo = FurnitureCatalogRepository.get_instance()
        self.standards_repo = ErgonomicStandardsRepository.get_instance()
        self.db_repo = EsaiDatabaseRepository(db)
        self.validator = EsaiInputValidator(self.catalog_repo, self.standards_repo)

    # 1. Project Structural Context
    def get_structural_context(self, project: Project) -> StructuralInputDTO:
        master_json = project.master_json or {}
        return StructuralInputParser.parse(master_json)

    def get_floors(self, project: Project) -> List[FloorDTO]:
        structural_input = self.get_structural_context(project)
        return SpatialNormalizer.find_all_floors(structural_input)

    def get_rooms(self, project: Project, floor_id: Optional[str] = None) -> List[RoomDTO]:
        structural_input = self.get_structural_context(project)
        all_rooms = SpatialNormalizer.find_all_rooms(structural_input)
        if floor_id:
            return [r for r in all_rooms if r.floor_id == floor_id]
        return all_rooms

    def get_room_by_id(self, project: Project, room_id: str) -> Optional[RoomDTO]:
        structural_input = self.get_structural_context(project)
        return SpatialNormalizer.find_room_by_id(structural_input, room_id)

    # 2. Catalogs & Standards
    def get_catalog_items(self, category: Optional[str] = None, room_type: Optional[str] = None) -> List[CatalogAsset]:
        if room_type:
            return self.catalog_repo.get_by_room_type(room_type)
        if category:
            from .contracts import AssetCategory
            try:
                cat = AssetCategory(category)
                return self.catalog_repo.get_by_category(cat)
            except ValueError:
                return []
        return self.catalog_repo.get_all()

    def get_catalog_item(self, catalog_id: str) -> CatalogAsset:
        return self.catalog_repo.get_by_id(catalog_id)

    def get_standards(self, enforceable_only: bool = False) -> List[ErgonomicRule]:
        return self.standards_repo.get_all(enforceable_only=enforceable_only)

    def get_room_profiles(self) -> List[Dict[str, Any]]:
        import json
        import os
        path = os.path.join(os.path.dirname(__file__), "data", "room_profiles.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("profiles", [])

    # 3. Validation Operations
    def validate_project_input(self, project: Project) -> ValidationResultDTO:
        try:
            structural_input = self.get_structural_context(project)
            return self.validator.validate_structural_input(structural_input)
        except StructuralInputValidationError as e:
            return ValidationResultDTO(
                valid=False,
                errors=[
                    ValidationMessage(
                        code="STRUCTURAL_VALIDATION_FAILED",
                        path=e.details.get("path", "floor_plan"),
                        room_id=e.details.get("room_id"),
                        message=str(e),
                        severity="error"
                    )
                ]
            )

    def validate_room_requirements(self, project: Project, requirements: RoomRequirementsDTO) -> ValidationResultDTO:
        try:
            structural_input = self.get_structural_context(project)
            room = SpatialNormalizer.find_room_by_id(structural_input, requirements.room_id)
            return self.validator.validate_room_requirements(requirements, room, structural_input=structural_input)
        except StructuralInputValidationError as e:
            return ValidationResultDTO(
                valid=False,
                errors=[
                    ValidationMessage(
                        code="STRUCTURAL_VALIDATION_FAILED",
                        path=e.details.get("path", "floor_plan"),
                        room_id=requirements.room_id,
                        message=str(e),
                        severity="error"
                    )
                ]
            )

    # 4. Requirements & Persistence (Transactional & Non-Destructive)
    def get_all_requirements(self, project_id: str) -> List[Dict[str, Any]]:
        records = self.db_repo.get_room_requirements(project_id)
        return [
            {
                "id": r.id,
                "project_id": r.project_id,
                "floor_id": r.floor_id,
                "room_id": r.room_id,
                "requirements": r.requirements_json,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in records
        ]

    def check_geometry_staleness(self, project: Project) -> Dict[str, Any]:
        structural_input = self.get_structural_context(project)
        current_fingerprint = compute_geometry_fingerprint(structural_input)
        master_json = project.master_json or {}
        interior_layout = master_json.get("interior_layout", {})
        stored_fingerprint = interior_layout.get("geometry_fingerprint")

        if stored_fingerprint is None:
            return {
                "is_stale": False,
                "status": "initial",
                "geometry_fingerprint": current_fingerprint,
                "stored_fingerprint": None,
                "geometry_source": structural_input.geometry_source,
                "message": "No previous interior geometry fingerprint stored."
            }

        is_stale = (current_fingerprint != stored_fingerprint)
        return {
            "is_stale": is_stale,
            "status": "stale" if is_stale else "up_to_date",
            "geometry_fingerprint": current_fingerprint,
            "stored_fingerprint": stored_fingerprint,
            "geometry_source": structural_input.geometry_source,
            "message": "Authoritative structural geometry has changed since interior layout was processed. Revalidation required." if is_stale else "Interior layout geometry matches authoritative structural geometry."
        }

    def save_room_requirements(
        self,
        project: Project,
        requirements: RoomRequirementsDTO,
        status: str = "draft",
        target_status: Optional[str] = None,
        expected_revision: Optional[int] = None
    ) -> Dict[str, Any]:
        desired_status = target_status if target_status is not None else status

        # 0. Concurrency check if expected_revision supplied
        if expected_revision is not None:
            current_rev = int(getattr(project, "revision", 1) or 1)
            if current_rev != expected_revision:
                raise HTTPException(
                    status_code=http_status.HTTP_409_CONFLICT,
                    detail={
                        "code": "PROJECT_STALE_REVISION",
                        "message": "Project changed since the supplied revision; reload before retrying.",
                        "expected_revision": expected_revision,
                        "current_revision": current_rev
                    }
                )

        # 1. Validate requirements against project geometry
        val_result = self.validate_room_requirements(project, requirements)

        # Room/Floor identity errors: reject immediately
        room_not_found = any(err.code == "ROOM_NOT_FOUND" for err in val_result.errors)
        floor_not_found = any(err.code == "FLOOR_NOT_FOUND" for err in val_result.errors)
        if room_not_found or floor_not_found:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND if (room_not_found or floor_not_found) else http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "ROOM_OR_FLOOR_NOT_FOUND",
                    "message": "Requirements reference a room or floor that does not exist in the loaded project geometry.",
                    "errors": [err.model_dump() for err in val_result.errors]
                }
            )

        # If invalid and not draft: reject submission.
        # If draft and invalid: mark explicitly as invalid_draft, never usable for optimization.
        if not val_result.valid:
            if desired_status != "draft":
                raise HTTPException(
                    status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "code": "REQUIREMENTS_VALIDATION_FAILED",
                        "message": "Client requirements contain errors and cannot be submitted as usable.",
                        "errors": [err.model_dump() for err in val_result.errors]
                    }
                )
            effective_status = "invalid_draft"
        else:
            effective_status = desired_status

        # 2. Compute geometry fingerprint
        structural_input = self.get_structural_context(project)
        geo_fingerprint = compute_geometry_fingerprint(structural_input)

        # 3. Transactional persistence: relational upsert + Master JSON update roll back together
        try:
            rec = self.db_repo.upsert_room_requirement(
                project_id=project.id,
                floor_id=requirements.floor_id,
                room_id=requirements.room_id,
                requirements_data=requirements.model_dump(mode="json"),
                status=effective_status,
                auto_commit=False
            )

            # Non-destructive immutable transformation on Master JSON
            # Only update ESAI-owned fields: interior_layout.room_requirements and processing.esai_engine
            master_copy = deepcopy(project.master_json or {})
            interior_layout = master_copy.setdefault("interior_layout", {})
            interior_layout["geometry_fingerprint"] = geo_fingerprint
            interior_layout["geometry_source"] = structural_input.geometry_source
            room_reqs = interior_layout.setdefault("room_requirements", {})
            room_reqs[requirements.room_id] = requirements.model_dump(mode="json")

            processing = master_copy.setdefault("processing", {})
            esai_proc = processing.setdefault("esai_engine", {})
            esai_proc["status"] = "pending"
            esai_proc["last_requirements_update"] = datetime.now(timezone.utc).isoformat()

            project.master_json = master_copy
            project.revision = (getattr(project, "revision", 1) or 1) + 1

            self.db.commit()
            self.db.refresh(rec)
            self.db.refresh(project)
        except Exception:
            self.db.rollback()
            raise

        return {
            "id": rec.id,
            "project_id": rec.project_id,
            "room_id": rec.room_id,
            "status": rec.status,
            "validation": val_result.model_dump()
        }

    def get_design_preferences(self, project_id: str) -> Optional[Dict[str, Any]]:
        record = self.db_repo.get_design_preference(project_id)
        if not record:
            return None
        return {
            "id": record.id,
            "project_id": record.project_id,
            "preferences": record.preferences_json,
            "geometry_fingerprint": record.geometry_fingerprint,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }

    def save_design_preferences(
        self,
        project: Project,
        preferences_data: Dict[str, Any],
        expected_revision: Optional[int] = None
    ) -> Dict[str, Any]:
        if expected_revision is not None:
            current_rev = int(getattr(project, "revision", 1) or 1)
            if current_rev != expected_revision:
                raise HTTPException(
                    status_code=http_status.HTTP_409_CONFLICT,
                    detail={
                        "code": "PROJECT_STALE_REVISION",
                        "message": "Project changed since the supplied revision; reload before retrying.",
                        "expected_revision": expected_revision,
                        "current_revision": current_rev
                    }
                )

        structural_input = self.get_structural_context(project)
        geo_fingerprint = compute_geometry_fingerprint(structural_input)

        try:
            record = self.db_repo.upsert_design_preference(
                project_id=project.id,
                preferences_data=preferences_data,
                geometry_fingerprint=geo_fingerprint,
                auto_commit=False
            )

            master_copy = deepcopy(project.master_json or {})
            interior_layout = master_copy.setdefault("interior_layout", {})
            interior_layout["preferences"] = preferences_data
            interior_layout["geometry_fingerprint"] = geo_fingerprint
            interior_layout["geometry_source"] = structural_input.geometry_source

            processing = master_copy.setdefault("processing", {})
            esai_proc = processing.setdefault("esai_engine", {})
            esai_proc["last_preferences_update"] = datetime.now(timezone.utc).isoformat()

            project.master_json = master_copy
            project.revision = (getattr(project, "revision", 1) or 1) + 1

            self.db.commit()
            self.db.refresh(record)
            self.db.refresh(project)
        except Exception:
            self.db.rollback()
            raise

        return {
            "id": record.id,
            "project_id": record.project_id,
            "preferences": record.preferences_json,
            "geometry_fingerprint": record.geometry_fingerprint,
        }


    # 5. Saved Configurations (Validated against actual project geometry)
    def list_saved_configurations(self, project_id: str) -> List[Dict[str, Any]]:
        configs = self.db_repo.list_saved_configs(project_id)
        return [
            {
                "id": c.id,
                "project_id": c.project_id,
                "configuration_name": c.configuration_name,
                "room_ids": c.room_ids_json,
                "settings": c.settings_json,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in configs
        ]

    def create_saved_configuration(
        self,
        project: Project,
        name: str,
        room_ids: List[str],
        settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        all_rooms = self.get_rooms(project)
        valid_room_ids = {r.room_id for r in all_rooms}

        if not room_ids:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Saved configuration must include at least one room ID."
            )

        invalid_rooms = [rid for rid in room_ids if rid not in valid_room_ids]
        if invalid_rooms:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Configuration references invalid room ID(s): {invalid_rooms}. All room IDs must exist in project geometry."
            )

        config = self.db_repo.create_saved_config(project.id, name, room_ids, settings)
        return {
            "id": config.id,
            "project_id": config.project_id,
            "configuration_name": config.configuration_name,
            "room_ids": config.room_ids_json,
            "settings": config.settings_json,
        }

    def update_saved_configuration(
        self,
        project: Project,
        config_id: str,
        name: Optional[str] = None,
        room_ids: Optional[List[str]] = None,
        settings: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        if room_ids is not None:
            all_rooms = self.get_rooms(project)
            valid_room_ids = {r.room_id for r in all_rooms}
            invalid_rooms = [rid for rid in room_ids if rid not in valid_room_ids]
            if invalid_rooms:
                raise HTTPException(
                    status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Configuration references invalid room ID(s): {invalid_rooms}. All room IDs must exist in project geometry."
                )

        config = self.db_repo.update_saved_config(
            project_id=project.id,
            config_id=config_id,
            configuration_name=name,
            room_ids=room_ids,
            settings_data=settings
        )
        if not config:
            return None
        return {
            "id": config.id,
            "project_id": config.project_id,
            "configuration_name": config.configuration_name,
            "room_ids": config.room_ids_json,
            "settings": config.settings_json,
        }

    def delete_saved_configuration(self, project_id: str, config_id: str) -> bool:
        return self.db_repo.delete_saved_config(project_id, config_id)
