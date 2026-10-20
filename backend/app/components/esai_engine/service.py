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
from .catalog import FurnitureCatalogRepository, CatalogAsset, FinishAsset
from .rules import ErgonomicStandardsRepository, ErgonomicRule
from .room_knowledge import RoomKnowledgeRepository
from .resolver import PreferenceToCatalogResolver
from .contracts import (
    StructuralInputDTO,
    RoomDTO,
    FloorDTO,
    RoomRequirementsDTO,
    ValidationResultDTO,
    ProjectPreferencesDTO,
    ValidationMessage,
    ResolvedRoomDesignInputDTO,
    GeneratedRoomDesignDTO,
    GeneratedBuildingDesignDTO,
    SaveDesignResponseDTO,
    SelectAlternativeResponseDTO,
    DesignStalenessReportDTO,
)
from .optimizer.genetic_optimizer import OptimizationConfig, PyGADLayoutOptimizer
from .optimizer.baselines import BaselineEvaluator, BaselineComparisonReport
from .generation.building_generator import BuildingGenerator
from .generation.room_generator import RoomGenerator
from .persistence import EsaiDesignPersistenceManager
from .parser import StructuralInputParser
from .normalizer import SpatialNormalizer
from .validators import EsaiInputValidator
from .repositories import EsaiDatabaseRepository
from .geometry import compute_geometry_fingerprint
from .exceptions import EsaiException, StructuralInputValidationError



class EsaiEngineService:
    """Core domain service for ESAI operations."""

    def __init__(self, db: Session):
        self.db = db
        self.catalog_repo = FurnitureCatalogRepository.get_instance()
        self.standards_repo = ErgonomicStandardsRepository.get_instance()
        self.room_knowledge_repo = RoomKnowledgeRepository.get_instance()
        self.resolver = PreferenceToCatalogResolver(
            self.catalog_repo, self.standards_repo, self.room_knowledge_repo
        )
        self.db_repo = EsaiDatabaseRepository(db)
        self.validator = EsaiInputValidator(self.catalog_repo, self.standards_repo)
        self.building_generator = BuildingGenerator()
        self.baseline_evaluator = BaselineEvaluator()
        self.persistence_mgr = EsaiDesignPersistenceManager(db, self)

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
    def get_catalog_categories(self) -> List[str]:
        return self.catalog_repo.get_all_categories()

    def get_catalog_items(
        self,
        category: Optional[str] = None,
        room_type: Optional[str] = None,
        subtype: Optional[str] = None,
        style: Optional[str] = None,
    ) -> List[CatalogAsset]:
        if subtype:
            return self.catalog_repo.get_by_subtype(subtype)
        if style:
            return self.catalog_repo.get_by_style(style)
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

    def get_finishes(
        self,
        category: Optional[str] = None,
        style: Optional[str] = None,
    ) -> List[FinishAsset]:
        return self.catalog_repo.get_all_finishes(category=category, style=style)

    def get_styles(self) -> Dict[str, Any]:
        return {k: v.dict() for k, v in self.room_knowledge_repo.list_styles().items()}

    def get_standards(
        self,
        enforceable_only: bool = False,
        mandatory_only: bool = False,
        category: Optional[str] = None,
    ) -> List[ErgonomicRule]:
        if category:
            rules = self.standards_repo.get_rules_for_category(category)
            if mandatory_only:
                return [r for r in rules if r.is_mandatory_compliance]
            if enforceable_only:
                return [r for r in rules if r.is_enforceable]
            return rules
        return self.standards_repo.get_all(enforceable_only=enforceable_only, mandatory_only=mandatory_only)

    def get_room_profiles(self) -> List[Dict[str, Any]]:
        return [p.dict() for p in self.room_knowledge_repo.list_profiles()]

    def get_functional_relationships(
        self,
        primary_category: Optional[str] = None,
        related_category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        rels = self.room_knowledge_repo.get_functional_relations(
            primary_category=primary_category, related_category=related_category
        )
        return [r.dict() for r in rels]

    def resolve_room_design_input(
        self,
        project: Project,
        room_id: str,
        floor_id: Optional[str] = None,
    ) -> ResolvedRoomDesignInputDTO:
        """
        Resolves effective room preferences against the catalog, ergonomic rules, and geometry.
        Generates the GA-ready design input contract without placing coordinates.
        """
        room = self.get_room_by_id(project, room_id)
        if not room:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Room '{room_id}' not found in project geometry."
            )
        target_floor_id = floor_id or room.floor_id
        effective_prefs = self.get_effective_preferences(project, room_id, target_floor_id)
        geo_fingerprint = self._get_geo_fingerprint(project)
        revision = getattr(project, "revision", 1) or 1

        return self.resolver.resolve(
            project_id=project.id,
            floor_id=target_floor_id,
            room_id=room.room_id,
            room_name=room.name,
            room_type_str=room.room_type.value if hasattr(room.room_type, "value") else str(room.room_type),
            polygon=room.polygon,
            area_sqm=room.area_sqm,
            ceiling_height_m=room.ceiling_height or 2.8,
            doors=room.doors,
            windows=room.windows,
            fixed_obstructions=room.fixed_obstructions,
            effective_preferences=effective_prefs,
            geometry_fingerprint=geo_fingerprint,
            geometry_revision=revision,
            elevation_m=room.elevation or 0.0,
        )

    def run_generation(
        self,
        project: Project,
        scope: str = "building",
        target_floor_id: Optional[str] = None,
        target_room_id: Optional[str] = None,
        config: Optional[OptimizationConfig] = None,
        expected_revision: Optional[int] = None,
    ) -> GeneratedBuildingDesignDTO:
        """
        Executes real evolutionary layout optimization across the requested scope.
        """
        self._check_revision(project, expected_revision)
        return self.building_generator.generate(
            service=self,
            project=project,
            scope=scope,
            target_floor_id=target_floor_id,
            target_room_id=target_room_id,
            config=config,
        )

    def run_baseline_comparison(
        self,
        project: Project,
        room_id: str,
        floor_id: Optional[str] = None,
        eval_budget: int = 250,
        seed: int = 42,
    ) -> BaselineComparisonReport:
        """
        Runs scientific benchmarking comparing GA against Random-Search and Greedy baselines.
        """
        design_input = self.resolve_room_design_input(project, room_id, floor_id)
        return self.baseline_evaluator.benchmark_room(
            design_input=design_input,
            eval_budget=eval_budget,
            seed=seed,
        )

    # ── Phase 5: Persistence, Selective Regeneration & Alternative Selection ───

    def save_design(
        self,
        project: Project,
        generation_result: Any,
        scope: str = "building",
        target_room_id: Optional[str] = None,
        target_floor_id: Optional[str] = None,
        expected_design_revision: Optional[int] = None,
    ) -> SaveDesignResponseDTO:
        """
        Stage B: Atomically and non-destructively persists validated layouts into Master JSON.
        """
        return self.persistence_mgr.save_generation_result(
            project=project,
            generation_result=generation_result,
            scope=scope,
            target_room_id=target_room_id,
            target_floor_id=target_floor_id,
            expected_design_revision=expected_design_revision,
        )

    def get_saved_designs(self, project: Project) -> Dict[str, Any]:
        """Retrieves all saved interior designs and revisions from Master JSON."""
        return self.persistence_mgr.get_saved_designs(project)

    def get_floor_designs(self, project: Project, floor_id: str) -> Dict[str, Any]:
        """Retrieves saved interior designs for a specific floor from Master JSON."""
        return self.persistence_mgr.get_floor_designs(project, floor_id)

    def get_room_design(self, project: Project, room_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves saved interior design for a single room from Master JSON."""
        return self.persistence_mgr.get_room_design(project, room_id)

    def get_room_alternatives(self, project: Project, room_id: str) -> List[Dict[str, Any]]:
        """Retrieves saved layout alternatives for a room from Master JSON."""
        return self.persistence_mgr.get_room_alternatives(project, room_id)

    def select_alternative(
        self,
        project: Project,
        room_id: str,
        alternative_id: str,
        expected_design_revision: Optional[int] = None,
    ) -> SelectAlternativeResponseDTO:
        """Activates a specific alternative layout for a room and persists atomically."""
        return self.persistence_mgr.select_alternative(
            project=project,
            room_id=room_id,
            alternative_id=alternative_id,
            expected_design_revision=expected_design_revision,
        )

    def check_design_staleness(self, project: Project) -> DesignStalenessReportDTO:
        """Audits saved designs against authoritative geometry and current client preferences."""
        return self.persistence_mgr.check_design_staleness(project)

    def regenerate(
        self,
        project: Project,
        scope: str = "room",
        target_room_id: Optional[str] = None,
        target_floor_id: Optional[str] = None,
        config: Optional[OptimizationConfig] = None,
        auto_save: bool = True,
        expected_design_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Executes selective regeneration across room, floor, or building scope."""
        return self.persistence_mgr.regenerate_scope(
            project=project,
            scope=scope,
            target_room_id=target_room_id,
            target_floor_id=target_floor_id,
            config=config,
            auto_save=auto_save,
            expected_design_revision=expected_design_revision,
        )

    # ── Phase 6: 3D Scene Visualization Data ──────────────────────────────────

    def get_scene_data(
        self,
        project: Project,
        floor_id: Optional[str] = None,
        room_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieves authoritative architectural geometry and saved interior layouts
        for 3D WebGL / React Three Fiber rendering.
        """
        structural_input = self.get_structural_context(project)
        floors = SpatialNormalizer.find_all_floors(structural_input)

        if floor_id:
            floors = [f for f in floors if f.floor_id == floor_id]
        if room_id:
            filtered_floors = []
            for f in floors:
                f_rooms = [r for r in f.rooms if r.room_id == room_id]
                if f_rooms:
                    f_copy = f.model_copy(update={"rooms": f_rooms})
                    filtered_floors.append(f_copy)
            floors = filtered_floors

        saved_designs_info = self.persistence_mgr.get_saved_designs(project)
        all_rooms_designs = saved_designs_info.get("rooms", {})

        if room_id:
            all_rooms_designs = {k: v for k, v in all_rooms_designs.items() if k == room_id}
        elif floor_id:
            all_rooms_designs = {
                k: v for k, v in all_rooms_designs.items()
                if v.get("floor_id") == floor_id
            }

        staleness = self.persistence_mgr.check_design_staleness(project)
        staleness_dict = staleness.model_dump(mode="json") if hasattr(staleness, "model_dump") else staleness.dict()

        return {
            "project_id": project.id,
            "project_name": project.project_name,
            "unit": structural_input.unit.value if hasattr(structural_input.unit, "value") else str(structural_input.unit),
            "geometry_revision": getattr(project, "revision", 1) or 1,
            "design_revision": saved_designs_info.get("design_revision", 0),
            "geometry_fingerprint": saved_designs_info.get("geometry_fingerprint"),
            "floors": floors,
            "saved_designs": all_rooms_designs,
            "staleness": staleness_dict,
        }

    # ── Phase 7: Interactive Editing, Validation, Locking & Selective Regeneration ──

    def validate_room_edit(
        self,
        project: Project,
        room_id: str,
        edit_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validates proposed room layout edits against authoritative geometry and rules."""
        return self.persistence_mgr.validate_room_edit(project, room_id, edit_data)

    def save_room_edit(
        self,
        project: Project,
        room_id: str,
        edit_data: Dict[str, Any],
        expected_design_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Atomically persists validated room layout edits into Master JSON."""
        return self.persistence_mgr.save_room_edit(project, room_id, edit_data, expected_design_revision)

    def toggle_asset_lock(
        self,
        project: Project,
        room_id: str,
        instance_id: str,
        is_locked: bool = True,
        lock_type: str = "all",
        expected_design_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Locks or unlocks an asset instance within a saved room layout."""
        return self.persistence_mgr.toggle_asset_lock(
            project, room_id, instance_id, is_locked, lock_type, expected_design_revision
        )

    def regenerate_unlocked(
        self,
        project: Project,
        room_id: str,
        config: Optional[OptimizationConfig] = None,
        expected_design_revision: Optional[int] = None,
        auto_save: bool = True,
    ) -> Dict[str, Any]:
        """Reoptimizes unlocked furniture in a room while preserving all locked items."""
        return self.persistence_mgr.regenerate_unlocked(
            project, room_id, config, expected_design_revision, auto_save
        )

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

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 2: Multi-level Preference Hierarchy
    # ──────────────────────────────────────────────────────────────────────────

    def _get_geo_fingerprint(self, project: Project) -> str:
        structural_input = self.get_structural_context(project)
        return compute_geometry_fingerprint(structural_input)

    def _assert_floor_exists(self, project: Project, floor_id: str) -> None:
        floors = self.get_floors(project)
        if not any(f.floor_id == floor_id for f in floors):
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Floor '{floor_id}' not found in project geometry."
            )

    def _assert_room_exists(self, project: Project, room_id: str) -> None:
        room = self.get_room_by_id(project, room_id)
        if not room:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Room '{room_id}' not found in project geometry."
            )

    def _check_revision(self, project: Project, expected_revision: Optional[int]) -> None:
        if expected_revision is not None:
            current_rev = int(getattr(project, "revision", 1) or 1)
            if current_rev != expected_revision:
                raise HTTPException(
                    status_code=http_status.HTTP_409_CONFLICT,
                    detail={
                        "code": "PROJECT_STALE_REVISION",
                        "message": "Project changed since the supplied revision; reload before retrying.",
                        "expected_revision": expected_revision,
                        "current_revision": current_rev,
                    }
                )

    # ── Building Preferences ──────────────────────────────────────────────────

    def get_building_preferences(self, project_id: str) -> Optional[Dict[str, Any]]:
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

    def save_building_preferences(
        self,
        project: Project,
        preferences_data: Dict[str, Any],
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._check_revision(project, expected_revision)
        geo_fingerprint = self._get_geo_fingerprint(project)

        try:
            record = self.db_repo.upsert_design_preference(
                project_id=project.id,
                preferences_data=preferences_data,
                geometry_fingerprint=geo_fingerprint,
                auto_commit=False,
            )
            master_copy = deepcopy(project.master_json or {})
            interior_layout = master_copy.setdefault("interior_layout", {})
            pref_section = interior_layout.setdefault("preferences", {})
            if isinstance(preferences_data, dict):
                pref_section.update(preferences_data)
            pref_section["building_defaults"] = preferences_data
            interior_layout["geometry_fingerprint"] = geo_fingerprint
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

    # Kept for backward compatibility with existing Phase 1 endpoints
    def get_design_preferences(self, project_id: str) -> Optional[Dict[str, Any]]:
        return self.get_building_preferences(project_id)

    def save_design_preferences(
        self,
        project: Project,
        preferences_data: Dict[str, Any],
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self.save_building_preferences(project, preferences_data, expected_revision)

    # ── Floor Preferences ─────────────────────────────────────────────────────

    def get_floor_preferences(self, project_id: str, floor_id: str) -> Optional[Dict[str, Any]]:
        record = self.db_repo.get_floor_preference(project_id, floor_id)
        if not record:
            return None
        return {
            "id": record.id,
            "project_id": record.project_id,
            "floor_id": record.floor_id,
            "preferences": record.preferences_json,
            "geometry_fingerprint": record.geometry_fingerprint,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }

    def save_floor_preferences(
        self,
        project: Project,
        floor_id: str,
        preferences_data: Dict[str, Any],
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._check_revision(project, expected_revision)
        self._assert_floor_exists(project, floor_id)
        geo_fingerprint = self._get_geo_fingerprint(project)

        try:
            record = self.db_repo.upsert_floor_preference(
                project_id=project.id,
                floor_id=floor_id,
                preferences_data=preferences_data,
                geometry_fingerprint=geo_fingerprint,
                auto_commit=False,
            )
            master_copy = deepcopy(project.master_json or {})
            interior_layout = master_copy.setdefault("interior_layout", {})
            pref_section = interior_layout.setdefault("preferences", {})
            floors_section = pref_section.setdefault("floors", {})
            floors_section[floor_id] = preferences_data
            interior_layout["geometry_fingerprint"] = geo_fingerprint

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
            "floor_id": record.floor_id,
            "preferences": record.preferences_json,
            "geometry_fingerprint": record.geometry_fingerprint,
        }

    def reset_floor_preferences(self, project: Project, floor_id: str) -> bool:
        """Delete the floor override; rooms fall back to building defaults."""
        deleted = self.db_repo.delete_floor_preference(project.id, floor_id)
        if deleted:
            master_copy = deepcopy(project.master_json or {})
            interior_layout = master_copy.get("interior_layout", {})
            floors_section = interior_layout.get("preferences", {}).get("floors", {})
            floors_section.pop(floor_id, None)
            project.master_json = master_copy
            project.revision = (getattr(project, "revision", 1) or 1) + 1
            self.db.commit()
            self.db.refresh(project)
        return deleted

    # ── Room Preferences ──────────────────────────────────────────────────────

    def get_room_preferences(self, project_id: str, room_id: str) -> Optional[Dict[str, Any]]:
        record = self.db_repo.get_room_preference(project_id, room_id)
        if not record:
            return None
        return {
            "id": record.id,
            "project_id": record.project_id,
            "floor_id": record.floor_id,
            "room_id": record.room_id,
            "room_type": record.room_type,
            "preferences": record.preferences_json,
            "preference_revision": record.preference_revision,
            "is_orphaned": record.is_orphaned,
            "geometry_fingerprint": record.geometry_fingerprint,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }

    def list_room_preferences(self, project_id: str, floor_id: Optional[str] = None) -> List[Dict[str, Any]]:
        records = self.db_repo.get_all_room_preferences(project_id, floor_id=floor_id)
        return [
            {
                "id": r.id,
                "project_id": r.project_id,
                "floor_id": r.floor_id,
                "room_id": r.room_id,
                "room_type": r.room_type,
                "preferences": r.preferences_json,
                "preference_revision": r.preference_revision,
                "is_orphaned": r.is_orphaned,
                "geometry_fingerprint": r.geometry_fingerprint,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in records
        ]

    def save_room_preferences(
        self,
        project: Project,
        room_id: str,
        preferences_data: Dict[str, Any],
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._check_revision(project, expected_revision)
        room = self.get_room_by_id(project, room_id)
        if not room:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Room '{room_id}' not found in project geometry."
            )
        geo_fingerprint = self._get_geo_fingerprint(project)

        try:
            record = self.db_repo.upsert_room_preference(
                project_id=project.id,
                floor_id=room.floor_id,
                room_id=room_id,
                room_type=room.room_type.value,
                preferences_data=preferences_data,
                geometry_fingerprint=geo_fingerprint,
                auto_commit=False,
            )

            master_copy = deepcopy(project.master_json or {})
            interior_layout = master_copy.setdefault("interior_layout", {})
            pref_section = interior_layout.setdefault("preferences", {})
            rooms_section = pref_section.setdefault("rooms", {})
            rooms_section[room_id] = {
                "floor_id": room.floor_id,
                **preferences_data,
            }
            interior_layout["geometry_fingerprint"] = geo_fingerprint

            pref_section.setdefault("metadata", {}).update({
                "geometry_revision": getattr(project, "revision", 1),
                "preference_revision": record.preference_revision,
            })

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
            "floor_id": record.floor_id,
            "room_id": record.room_id,
            "room_type": record.room_type,
            "preferences": record.preferences_json,
            "preference_revision": record.preference_revision,
            "geometry_fingerprint": record.geometry_fingerprint,
        }

    def patch_room_preferences(
        self,
        project: Project,
        room_id: str,
        patch_data: Dict[str, Any],
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._check_revision(project, expected_revision)
        self._assert_room_exists(project, room_id)

        record = self.db_repo.patch_room_preference(
            project_id=project.id,
            room_id=room_id,
            patch_data=patch_data,
            auto_commit=False,
        )
        if not record:
            # No existing record; create fresh from patch data
            room = self.get_room_by_id(project, room_id)
            geo_fingerprint = self._get_geo_fingerprint(project)
            record = self.db_repo.upsert_room_preference(
                project_id=project.id,
                floor_id=room.floor_id,
                room_id=room_id,
                room_type=room.room_type.value,
                preferences_data=patch_data,
                geometry_fingerprint=geo_fingerprint,
                auto_commit=False,
            )

        # Mirror patch to Master JSON
        master_copy = deepcopy(project.master_json or {})
        rooms_section = (
            master_copy
            .setdefault("interior_layout", {})
            .setdefault("preferences", {})
            .setdefault("rooms", {})
        )
        existing = rooms_section.get(room_id, {})
        existing.update(patch_data)
        rooms_section[room_id] = existing

        project.master_json = master_copy
        project.revision = (getattr(project, "revision", 1) or 1) + 1
        self.db.commit()
        self.db.refresh(record)
        self.db.refresh(project)

        return {
            "id": record.id,
            "project_id": record.project_id,
            "floor_id": record.floor_id,
            "room_id": record.room_id,
            "room_type": record.room_type,
            "preferences": record.preferences_json,
            "preference_revision": record.preference_revision,
        }

    def reset_room_preferences(self, project: Project, room_id: str) -> bool:
        """Delete the room override; the room falls back to floor/building defaults."""
        deleted = self.db_repo.delete_room_preference(project.id, room_id)
        if deleted:
            master_copy = deepcopy(project.master_json or {})
            rooms_section = (
                master_copy
                .get("interior_layout", {})
                .get("preferences", {})
                .get("rooms", {})
            )
            rooms_section.pop(room_id, None)
            project.master_json = master_copy
            project.revision = (getattr(project, "revision", 1) or 1) + 1
            self.db.commit()
            self.db.refresh(project)
        return deleted

    # ── Effective Preference Resolution ───────────────────────────────────────

    def get_effective_preferences(
        self,
        project: Project,
        room_id: str,
        floor_id: str,
    ) -> Dict[str, Any]:
        self._assert_room_exists(project, room_id)
        return self.db_repo.resolve_effective_preferences(
            project_id=project.id,
            room_id=room_id,
            floor_id=floor_id,
        )

    # ── Orphan Detection ──────────────────────────────────────────────────────

    def detect_orphaned_preferences(self, project: Project) -> Dict[str, Any]:
        all_rooms = self.get_rooms(project)
        valid_ids = {r.room_id for r in all_rooms}
        all_prefs = self.db_repo.get_all_room_preferences(project.id)
        orphaned = self.db_repo.mark_orphaned_preferences(project.id, valid_ids)
        return {
            "scanned_count": len(all_prefs),
            "orphaned_count": len(orphaned),
            "orphaned_room_ids": orphaned,
            "valid_room_count": len(valid_ids),
            "details": [{"room_id": rid, "status": "orphaned"} for rid in orphaned],
            "message": (
                f"Marked {len(orphaned)} preference record(s) as orphaned."
                if orphaned else
                "All saved room preferences are valid against current geometry."
            ),
        }


    # ── Room-Type Preference Schema ───────────────────────────────────────────

    def get_preference_schema_for_room_type(self, room_type_str: str) -> Dict[str, Any]:
        """
        Returns the preference schema and options available for a given room type.
        Used by the frontend to build dynamic forms.
        """
        from .contracts import RoomType
        room_type_map = {
            RoomType.MASTER_BEDROOM.value: "bedroom",
            RoomType.BEDROOM.value: "bedroom",
            RoomType.GUEST_ROOM.value: "bedroom",
            RoomType.LIVING_ROOM.value: "living_room",
            RoomType.FAMILY_LIVING_AREA.value: "living_room",
            RoomType.TV_LOBBY.value: "living_room",
            RoomType.TV_LOUNGE.value: "living_room",
            RoomType.LOUNGE.value: "living_room",
            RoomType.DINING_ROOM.value: "dining",
            RoomType.DINING_AREA.value: "dining",
            RoomType.KITCHEN.value: "kitchen",
            RoomType.PANTRY.value: "kitchen",
            RoomType.BATHROOM.value: "bathroom",
            RoomType.ATTACHED_BATHROOM.value: "bathroom",
            RoomType.COMMON_BATHROOM.value: "bathroom",
            RoomType.TOILET.value: "bathroom",
            RoomType.STUDY.value: "office",
            RoomType.STUDY_OFFICE.value: "office",
            RoomType.HOME_OFFICE.value: "office",
            RoomType.UTILITY_ROOM.value: "utility",
            RoomType.LAUNDRY_ROOM.value: "utility",
        }
        schema_key = room_type_map.get(room_type_str, "generic")

        schemas: Dict[str, Any] = {
            "bedroom": {
                "specific_section": "bedroom",
                "fields": {
                    "bed_type": ["single", "twin", "double", "queen", "king", "bunk", "triple_sleeper"],
                    "bed_count": {"type": "integer", "min": 1, "max": 4},
                    "headboard_required": {"type": "boolean"},
                    "headboard_material": {"type": "string", "optional": True},
                    "bedside_tables_count": {"type": "integer", "min": 0, "max": 2},
                    "wardrobe_type": {"type": "string", "optional": True},
                    "wardrobe_wall_count": {"type": "integer", "min": 0, "max": 4},
                    "dressing_table_required": {"type": "boolean"},
                    "study_desk_required": {"type": "boolean"},
                    "tv_in_bedroom": {"type": "boolean"},
                    "tv_wall_location": {"type": "string", "optional": True},
                    "bedside_charging_outlets": {"type": "integer", "min": 0},
                    "mirror_required": {"type": "boolean"},
                    "seating_required": {"type": "boolean"},
                    "seating_type": {"type": "string", "optional": True},
                },
            },
            "bathroom": {
                "specific_section": "bathroom",
                "fields": {
                    "has_bathtub": {"type": "boolean"},
                    "bathtub_type": {"type": "string", "optional": True},
                    "has_shower": {"type": "boolean"},
                    "shower_type": {"type": "string", "optional": True},
                    "shower_screen_type": {"type": "string", "optional": True},
                    "toilet_type": {"type": "string", "optional": True},
                    "bidet_required": {"type": "boolean"},
                    "washbasin_count": {"type": "integer", "min": 0, "max": 3},
                    "washbasin_type": {"type": "string", "optional": True},
                    "vanity_required": {"type": "boolean"},
                    "mirror_type": {"type": "string", "optional": True},
                    "hot_water_connection": ["hot_cold", "cold_only", "hot_only"],
                    "water_heater_type": {"type": "string", "optional": True},
                    "exhaust_fan_required": {"type": "boolean"},
                    "towel_rail_count": {"type": "integer", "min": 0},
                    "heated_towel_rail": {"type": "boolean"},
                },
            },
            "kitchen": {
                "specific_section": "kitchen",
                "fields": {
                    "layout_type": ["single_wall", "l_shaped", "u_shaped", "galley", "parallel", "island", "breakfast_counter", "custom"],
                    "has_island": {"type": "boolean"},
                    "island_with_seating": {"type": "boolean"},
                    "island_seating_count": {"type": "integer", "min": 0},
                    "countertop_material": {"type": "string", "optional": True},
                    "cabinet_material": {"type": "string", "optional": True},
                    "cabinet_finish": {"type": "string", "optional": True},
                    "sink_type": ["single", "double", "undermount", "farmhouse"],
                    "hob_type": ["gas", "induction", "electric", "mixed"],
                    "hob_burner_count": {"type": "integer", "min": 2, "max": 6},
                    "oven_type": ["built_in", "freestanding", "microwave_combo"],
                    "hood_type": ["chimney", "island", "under_cabinet", "recirculating"],
                    "refrigerator_type": {"type": "string", "optional": True},
                    "dishwasher_required": {"type": "boolean"},
                    "pantry_cabinet_required": {"type": "boolean"},
                    "breakfast_bar_required": {"type": "boolean"},
                    "under_cabinet_lighting": {"type": "boolean"},
                },
            },
            "living_room": {
                "specific_section": "living_room",
                "fields": {
                    "sofa_type": ["2_seater", "3_seater", "l_shaped", "sectional", "chesterfield", "modular"],
                    "sofa_count": {"type": "integer", "min": 1},
                    "armchair_count": {"type": "integer", "min": 0},
                    "coffee_table_required": {"type": "boolean"},
                    "coffee_table_shape": ["rectangular", "round", "oval", "square"],
                    "tv_unit_type": ["floor_stand", "wall_mounted", "media_console", "floating"],
                    "tv_size_inches": {"type": "integer", "min": 32, "max": 100, "optional": True},
                    "fireplace_required": {"type": "boolean"},
                    "bookshelf_required": {"type": "boolean"},
                    "rug_required": {"type": "boolean"},
                    "open_to_dining": {"type": "boolean"},
                },
            },
            "dining": {
                "specific_section": "dining",
                "fields": {
                    "table_shape": ["rectangular", "round", "oval", "square", "extendable"],
                    "seating_count": {"type": "integer", "min": 2, "max": 16},
                    "chair_style": {"type": "string", "optional": True},
                    "sideboard_required": {"type": "boolean"},
                    "buffet_cabinet_required": {"type": "boolean"},
                    "chandelier_over_table": {"type": "boolean"},
                    "open_to_kitchen": {"type": "boolean"},
                },
            },
            "office": {
                "specific_section": "office",
                "fields": {
                    "desk_type": ["single", "l_shaped", "standing", "corner"],
                    "desk_count": {"type": "integer", "min": 1},
                    "chair_type": {"type": "string", "optional": True},
                    "bookcase_required": {"type": "boolean"},
                    "filing_cabinet_required": {"type": "boolean"},
                    "monitor_count": {"type": "integer", "min": 1},
                    "ethernet_outlet_required": {"type": "boolean"},
                    "whiteboard_required": {"type": "boolean"},
                },
            },
            "utility": {
                "specific_section": "utility",
                "fields": {
                    "washing_machine_required": {"type": "boolean"},
                    "dryer_required": {"type": "boolean"},
                    "utility_sink_required": {"type": "boolean"},
                    "shelf_count": {"type": "integer", "min": 0},
                    "countertop_required": {"type": "boolean"},
                    "ventilation_required": {"type": "boolean"},
                },
            },
            "generic": {
                "specific_section": None,
                "fields": {},
            },
        }

        common_fields = {
            "common": {
                "furniture_density": ["minimal", "standard", "luxurious"],
                "circulation_priority": ["compact", "standard", "spacious", "accessible"],
                "accessibility_profile": ["standard", "wheelchair_accessible", "elderly_friendly", "child_safe"],
                "interior_style": ["modern", "minimalist", "scandinavian", "industrial", "traditional", "contemporary", "luxury", "rustic", "bohemian", "coastal"],
                "notes": {"type": "string", "optional": True},
            },
            "finishes": {
                "wall_finish": ["paint_matte", "paint_satin", "paint_gloss", "wallpaper", "textured_plaster", "ceramic_tile", "stone_cladding", "wood_panel", "other"],
                "wall_color": {"type": "string", "optional": True},
                "floor_finish": ["hardwood", "engineered_wood", "laminate", "ceramic_floor_tile", "porcelain_tile", "marble", "vinyl", "carpet", "polished_concrete", "other"],
                "ceiling_finish": ["plaster_smooth", "pop_design", "gypsum_board", "wooden_ceiling", "open_exposed", "other"],
            },
            "lighting": {
                "ambient_lighting_type": ["warm_white", "neutral_white", "cool_white", "rgb", "tunable"],
                "lighting_items": "list[LightingPreferenceItem]",
            },
            "electrical": {
                "outlets": "list[ElectricalOutletItem]",
            },
            "services": {
                "provisions": "list[ServiceProvision]",
            },
            "items": {
                "furniture_items": "list[FurnitureRequirementItem]",
            },
            "placement": {
                "mandatory_catalog_ids": "list[str]",
                "excluded_catalog_ids": "list[str]",
                "user_locked_instance_ids": "list[str]",
            },
        }

        result = schemas.get(schema_key, schemas["generic"])
        result["common_fields"] = common_fields
        result["room_type"] = room_type_str
        result["schema_key"] = schema_key
        return result
