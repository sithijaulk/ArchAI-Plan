"""
ESAI Engine Core Service
Orchestrates Master JSON parsing, room and floor discovery, client requirement management,
catalog queries, standards retrieval, and cross-validation without AI optimization.
Maintains controlled HTTP 501 on run() until Stage 2.
"""
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.project import Project
from app.services.master_json import merge_master_json
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
        room = self.get_room_by_id(project, requirements.room_id)
        return self.validator.validate_room_requirements(requirements, room)

    # 4. Requirements & Persistence
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

    def save_room_requirements(
        self,
        project: Project,
        requirements: RoomRequirementsDTO,
        status: str = "draft"
    ) -> Dict[str, Any]:
        # Validate first
        val_result = self.validate_room_requirements(project, requirements)
        if not val_result.valid:
            # Raise or persist as draft with errors
            pass

        # Persist to relational table
        rec = self.db_repo.upsert_room_requirement(
            project_id=project.id,
            floor_id=requirements.floor_id,
            room_id=requirements.room_id,
            requirements_data=requirements.model_dump(),
            status=status
        )

        # Safely sync to Master JSON without mutating structural geometry
        current_master = project.master_json or {}
        interior_layout = current_master.get("interior_layout") or {}
        room_reqs = interior_layout.get("room_requirements") or {}
        room_reqs[requirements.room_id] = requirements.model_dump()

        interior_layout["room_requirements"] = room_reqs
        project.master_json = merge_master_json(
            project.master_json,
            {"interior_layout": interior_layout}
        )
        self.db.commit()
        self.db.refresh(project)

        return {
            "id": rec.id,
            "project_id": rec.project_id,
            "room_id": rec.room_id,
            "status": rec.status,
            "validation": val_result.model_dump()
        }

    # 5. Saved Configurations
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
        project_id: str,
        name: str,
        room_ids: List[str],
        settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        config = self.db_repo.create_saved_config(project_id, name, room_ids, settings)
        return {
            "id": config.id,
            "project_id": config.project_id,
            "configuration_name": config.configuration_name,
            "room_ids": config.room_ids_json,
            "settings": config.settings_json,
        }

    def update_saved_configuration(
        self,
        project_id: str,
        config_id: str,
        name: Optional[str] = None,
        room_ids: Optional[List[str]] = None,
        settings: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        config = self.db_repo.update_saved_config(
            project_id=project_id,
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
