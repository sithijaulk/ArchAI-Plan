"""
ESAI Phase 5: Safe Master JSON Persistence, Revision Control & Selective Interior Regeneration
Authoritative project data source: projects.master_json["interior_layout"]
Implements two-stage generation & atomic, non-destructive persistence with optimistic concurrency.
"""
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from sqlalchemy.orm import Session

from app.models.project import Project
from .contracts import (
    Coordinate2D,
    Dimensions3D,
    GeneratedBuildingDesignDTO,
    GeneratedRoomDesignDTO,
    PersistedRoomDesignDTO,
    PlacedAssetPersistedDTO,
    PlacedFixturePointDTO,
    DesignStalenessRoomReportDTO,
    DesignStalenessReportDTO,
    SaveDesignResponseDTO,
    SelectAlternativeResponseDTO,
)
from .exceptions import (
    AlternativeNotFoundError,
    DesignRevisionConflictError,
    GeometryStalenessError,
    InvalidDesignSaveError,
    PreferenceStalenessError,
)
from .geometry import compute_geometry_fingerprint


def classify_asset_bucket(category: Optional[str]) -> str:
    """Classifies catalog asset category into semantic Master JSON sub-lists."""
    cat = (category or "").lower().strip()
    if cat in {
        "countertop", "base_cabinet", "wall_cabinet", "tall_cabinet",
        "kitchen_island", "vanity_cabinet", "vanity", "cabinetry"
    }:
        return "cabinetry"
    elif cat in {
        "refrigerator", "cooktop", "hob", "oven", "hood", "extractor",
        "dishwasher", "microwave", "washing_machine", "dryer", "appliance"
    }:
        return "appliances"
    elif cat in {
        "wc", "toilet", "washbasin", "basin", "sink", "shower",
        "bathtub", "bidet", "sanitary_fixture"
    }:
        return "sanitary_fixtures"
    elif cat in {
        "rug", "mirror", "plant", "artwork", "curtains", "decoration"
    }:
        return "decorations"
    else:
        return "furniture"


class EsaiDesignPersistenceManager:
    """
    Manages safe, atomic, non-destructive Master JSON persistence,
    revision checking, selective regeneration, and alternative activation.
    """

    def __init__(self, db: Session, service: Any):
        self.db = db
        self.service = service

    def save_generation_result(
        self,
        project: Project,
        generation_result: Union[GeneratedBuildingDesignDTO, GeneratedRoomDesignDTO, Dict[str, Any]],
        scope: str = "building",
        target_room_id: Optional[str] = None,
        target_floor_id: Optional[str] = None,
        expected_design_revision: Optional[int] = None,
    ) -> SaveDesignResponseDTO:
        """
        Stage B: Atomically persists generated layout results into projects.master_json.
        Applies optimistic concurrency, geometry staleness checks, and preference freshness checks.
        """
        # 1. Reload latest project state inside short transaction
        self.db.refresh(project)

        # 2. Geometry Staleness Check
        structural_input = self.service.get_structural_context(project)
        current_geo_fp = compute_geometry_fingerprint(structural_input)

        gen_geo_fp = None
        if hasattr(generation_result, "geometry_fingerprint"):
            gen_geo_fp = generation_result.geometry_fingerprint
        elif isinstance(generation_result, dict):
            gen_geo_fp = generation_result.get("geometry_fingerprint")

        if gen_geo_fp and gen_geo_fp != current_geo_fp:
            raise GeometryStalenessError(
                message=f"Floor plan geometry has changed since generation (generated={gen_geo_fp[:8]}, current={current_geo_fp[:8]}). Please regenerate with authoritative geometry.",
                project_id=project.id,
                generated_fingerprint=gen_geo_fp,
                current_fingerprint=current_geo_fp,
            )

        # 3. Optimistic Concurrency Check on design_revision
        master_json = project.master_json or {}
        interior_layout = master_json.get("interior_layout", {})
        current_design_rev = interior_layout.get("design_revision", 0)

        if expected_design_revision is not None and expected_design_revision != current_design_rev:
            raise DesignRevisionConflictError(
                message=f"Concurrent design update conflict: expected revision {expected_design_revision}, but current design revision is {current_design_rev}.",
                project_id=project.id,
                expected_rev=expected_design_revision,
                current_rev=current_design_rev,
            )

        # 4. Extract room designs to process
        rooms_to_save: Dict[str, Any] = {}
        if isinstance(generation_result, GeneratedBuildingDesignDTO):
            rooms_to_save = generation_result.rooms
        elif isinstance(generation_result, GeneratedRoomDesignDTO):
            rooms_to_save = {generation_result.room_id: generation_result}
        elif isinstance(generation_result, dict):
            if "rooms" in generation_result and isinstance(generation_result["rooms"], dict):
                rooms_to_save = generation_result["rooms"]
            elif "room_id" in generation_result:
                rooms_to_save = {generation_result["room_id"]: generation_result}

        # Filter by scope if requested
        if scope == "room" and target_room_id:
            rooms_to_save = {k: v for k, v in rooms_to_save.items() if k == target_room_id}
        elif scope == "floor" and target_floor_id:
            filtered = {}
            for k, v in rooms_to_save.items():
                f_id = getattr(v, "floor_id", None) or (v.get("floor_id") if isinstance(v, dict) else None)
                if f_id == target_floor_id:
                    filtered[k] = v
            rooms_to_save = filtered

        # 5. Check Room Preference Staleness & Hard Constraint Validity
        saved_room_preferences = {
            r["room_id"]: r for r in self.service.list_room_preferences(project.id)
        }

        saved_room_ids: List[str] = []
        skipped_infeasible_ids: List[str] = []

        # Prepare deep copy of master_json
        master_copy = deepcopy(master_json)
        il_section = master_copy.setdefault("interior_layout", {})
        designs_section = il_section.setdefault("designs", {})
        saved_rooms_map = designs_section.setdefault("rooms", {})

        for room_id, r_data in rooms_to_save.items():
            status = getattr(r_data, "status", None) or (r_data.get("status") if isinstance(r_data, dict) else "unknown")
            hard_passed = getattr(r_data, "hard_constraints_passed", True) if hasattr(r_data, "hard_constraints_passed") else r_data.get("hard_constraints_passed", True)

            # Check preference revision freshness
            current_pref = saved_room_preferences.get(room_id)
            if current_pref:
                current_pref_rev = current_pref.get("preference_revision", 1)
                gen_pref_rev = getattr(r_data, "preference_revision", None) or (r_data.get("preference_revision") if isinstance(r_data, dict) else None)
                if gen_pref_rev is not None and gen_pref_rev != current_pref_rev:
                    raise PreferenceStalenessError(
                        message=f"Room preferences for '{room_id}' have changed (current={current_pref_rev}, generated={gen_pref_rev}). Please regenerate.",
                        project_id=project.id,
                        room_id=room_id,
                        generated_rev=gen_pref_rev,
                        current_rev=current_pref_rev,
                    )

            # Hard Constraint validation: reject invalid layouts
            if status != "success" or not hard_passed:
                if scope == "room":
                    violations = getattr(r_data, "diagnostics", []) if hasattr(r_data, "diagnostics") else r_data.get("diagnostics", [])
                    raise InvalidDesignSaveError(
                        message=f"Cannot save room '{room_id}': layout is '{status}' with hard-constraint violations.",
                        room_id=room_id,
                        violations=violations,
                    )
                else:
                    # In multi-room scopes, skip failed rooms to avoid corrupting valid layouts
                    skipped_infeasible_ids.append(room_id)
                    continue

            # Convert to PersistedRoomDesignDTO and serialize into Master JSON
            persisted_dict = self._build_persisted_room_dict(project.id, r_data, current_geo_fp, current_design_rev + 1)
            saved_rooms_map[room_id] = persisted_dict
            saved_room_ids.append(room_id)

        # 6. Apply Non-Destructive Master JSON Metadata & Revisions
        new_design_rev = current_design_rev + 1
        il_section["schema_version"] = "1.0.0"
        il_section["design_revision"] = new_design_rev
        il_section["geometry_fingerprint"] = current_geo_fp
        il_section["geometry_source"] = structural_input.geometry_source

        revisions_list = il_section.setdefault("revisions", [])
        now_iso = datetime.now(timezone.utc).isoformat()
        revisions_list.append({
            "design_revision": new_design_rev,
            "timestamp": now_iso,
            "scope": scope,
            "saved_rooms": saved_room_ids,
            "skipped_infeasible_rooms": skipped_infeasible_ids,
            "geometry_fingerprint": current_geo_fp,
        })

        processing = master_copy.setdefault("processing", {})
        esai_proc = processing.setdefault("esai_engine", {})
        esai_proc["status"] = "completed"
        esai_proc["design_revision"] = new_design_rev
        esai_proc["last_saved_at"] = now_iso

        # 7. Atomic DB Commit
        try:
            project.master_json = master_copy
            project.revision = (getattr(project, "revision", 1) or 1) + 1
            self.db.commit()
            self.db.refresh(project)
        except Exception:
            self.db.rollback()
            raise

        return SaveDesignResponseDTO(
            success=True,
            project_id=project.id,
            design_revision=new_design_rev,
            saved_rooms_count=len(saved_room_ids),
            saved_room_ids=saved_room_ids,
            timestamp=now_iso,
            details={
                "scope": scope,
                "skipped_infeasible_rooms": skipped_infeasible_ids,
                "geometry_fingerprint": current_geo_fp,
            }
        )

    def _build_persisted_room_dict(
        self,
        project_id: str,
        room_data: Any,
        geometry_fingerprint: str,
        design_revision: int,
    ) -> Dict[str, Any]:
        """Maps generated room design into the authoritative Master JSON room layout structure."""
        if isinstance(room_data, dict):
            rd = room_data
        else:
            rd = room_data.model_dump(mode="json") if hasattr(room_data, "model_dump") else room_data.dict()

        placed_assets = rd.get("placed_assets", [])
        service_points = rd.get("service_points", [])
        lighting_fixtures = rd.get("lighting_fixtures", [])
        finishes = rd.get("finishes", {})
        alternatives = rd.get("alternatives", [])
        validation_summary = {
            "fitness_score": rd.get("fitness_score", 0.0),
            "fitness_breakdown": rd.get("fitness_breakdown"),
            "hard_constraints_passed": rd.get("hard_constraints_passed", True),
            "ergonomic_evaluations": rd.get("ergonomic_evaluations", []),
            "diagnostics": rd.get("diagnostics", []),
        }

        # Classify placed assets into semantic Master JSON buckets
        furniture_list = []
        cabinetry_list = []
        appliances_list = []
        sanitary_list = []
        decorations_list = []

        for asset in placed_assets:
            cat = asset.get("category", "")
            bucket = classify_asset_bucket(cat)
            if bucket == "cabinetry":
                cabinetry_list.append(asset)
            elif bucket == "appliances":
                appliances_list.append(asset)
            elif bucket == "sanitary_fixtures":
                sanitary_list.append(asset)
            elif bucket == "decorations":
                decorations_list.append(asset)
            else:
                furniture_list.append(asset)

        # Separate service points into electrical vs plumbing vs generic
        electrical_pts = []
        plumbing_pts = []
        for sp in service_points:
            ptype = sp.get("point_type", "").lower()
            if any(k in ptype for k in ("socket", "power", "data", "tv", "switch", "fan", "ac")):
                electrical_pts.append(sp)
            elif any(k in ptype for k in ("water", "drain", "drainage", "plumb", "gas")):
                plumbing_pts.append(sp)

        now_iso = datetime.now(timezone.utc).isoformat()

        return {
            "project_id": project_id,
            "floor_id": rd.get("floor_id"),
            "room_id": rd.get("room_id"),
            "room_name": rd.get("room_name"),
            "room_type": rd.get("room_type"),
            "geometry_revision": rd.get("geometry_revision", 1),
            "geometry_fingerprint": geometry_fingerprint,
            "preference_revision": rd.get("preference_revision", 1),
            "design_revision": design_revision,
            "catalog_version": rd.get("catalog_version", "1.0.0"),
            "generation_status": rd.get("status", "success"),
            "generation_timestamp": rd.get("generation_timestamp", now_iso),
            "active_alternative_id": rd.get("active_alternative_id", "primary"),
            "polygon": rd.get("polygon", []),
            "area_sqm": rd.get("area_sqm", 0.0),
            "ceiling_height_m": rd.get("ceiling_height_m", 2.8),
            "furniture": furniture_list,
            "cabinetry": cabinetry_list,
            "appliances": appliances_list,
            "sanitary_fixtures": sanitary_list,
            "lighting": lighting_fixtures,
            "electrical_points": electrical_pts,
            "plumbing_requirements": plumbing_pts,
            "service_requirements": service_points,
            "wall_finishes": finishes.get("walls", {}),
            "floor_finishes": finishes.get("floor", {}),
            "ceiling_finishes": finishes.get("ceiling", {}),
            "decorations": decorations_list,
            "validation": validation_summary,
            "alternatives": alternatives,
            "generation_metadata": rd.get("optimization_metadata", {}),
        }

    # ── Read & Retrieval Operations ──────────────────────────────────────────

    def get_saved_designs(self, project: Project) -> Dict[str, Any]:
        """Retrieves all saved room designs and top-level interior layout metadata."""
        interior_layout = (project.master_json or {}).get("interior_layout", {})
        designs = interior_layout.get("designs", {})
        rooms = designs.get("rooms", {})
        return {
            "project_id": project.id,
            "design_revision": interior_layout.get("design_revision", 0),
            "schema_version": interior_layout.get("schema_version", "1.0.0"),
            "geometry_fingerprint": interior_layout.get("geometry_fingerprint"),
            "geometry_source": interior_layout.get("geometry_source"),
            "total_saved_rooms": len(rooms),
            "rooms": rooms,
            "revisions": interior_layout.get("revisions", []),
        }

    def get_floor_designs(self, project: Project, floor_id: str) -> Dict[str, Any]:
        """Retrieves saved room designs for a specific floor."""
        all_designs = self.get_saved_designs(project)
        floor_rooms = {
            r_id: r for r_id, r in all_designs["rooms"].items()
            if r.get("floor_id") == floor_id
        }
        return {
            "project_id": project.id,
            "floor_id": floor_id,
            "design_revision": all_designs["design_revision"],
            "total_saved_rooms": len(floor_rooms),
            "rooms": floor_rooms,
        }

    def get_room_design(self, project: Project, room_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves saved design for a single room."""
        interior_layout = (project.master_json or {}).get("interior_layout", {})
        rooms = interior_layout.get("designs", {}).get("rooms", {})
        return rooms.get(room_id)

    def get_room_alternatives(self, project: Project, room_id: str) -> List[Dict[str, Any]]:
        """Retrieves generated design alternatives for a room."""
        room_design = self.get_room_design(project, room_id)
        if not room_design:
            return []
        return room_design.get("alternatives", [])

    # ── Alternative Activation ───────────────────────────────────────────────

    def select_alternative(
        self,
        project: Project,
        room_id: str,
        alternative_id: str,
        expected_design_revision: Optional[int] = None,
    ) -> SelectAlternativeResponseDTO:
        """
        Activates a valid alternative layout for a room, updates its active assets
        and service requirements, increments design revision, and commits atomically.
        """
        self.db.refresh(project)
        master_copy = deepcopy(project.master_json or {})
        interior_layout = master_copy.setdefault("interior_layout", {})
        current_rev = interior_layout.get("design_revision", 0)

        if expected_design_revision is not None and expected_design_revision != current_rev:
            raise DesignRevisionConflictError(
                message=f"Concurrent conflict: expected design revision {expected_design_revision}, but current revision is {current_rev}.",
                project_id=project.id,
                expected_rev=expected_design_revision,
                current_rev=current_rev,
            )

        rooms = interior_layout.setdefault("designs", {}).setdefault("rooms", {})
        room_design = rooms.get(room_id)
        if not room_design:
            raise AlternativeNotFoundError(
                message=f"No saved design found for room '{room_id}'.",
                room_id=room_id,
                alternative_id=str(alternative_id),
            )

        alternatives = room_design.get("alternatives", [])
        matched_alt = None
        for alt in alternatives:
            alt_idx_str = str(alt.get("alternative_index", ""))
            alt_id_str = str(alt.get("alternative_id", ""))
            target_str = str(alternative_id).strip()
            if target_str in (alt_idx_str, alt_id_str):
                matched_alt = alt
                break

        if not matched_alt:
            raise AlternativeNotFoundError(
                message=f"Alternative '{alternative_id}' was not found in room '{room_id}' alternatives.",
                room_id=room_id,
                alternative_id=str(alternative_id),
            )

        # Check hard constraint validity of the chosen alternative
        alt_fb = matched_alt.get("fitness_breakdown", {})
        if not alt_fb.get("is_hard_constraint_valid", True):
            raise InvalidDesignSaveError(
                message=f"Alternative '{alternative_id}' violates hard constraints and cannot be activated.",
                room_id=room_id,
                violations=alt_fb.get("violations", []),
            )

        # Re-slot placed assets from the selected alternative
        alt_assets = matched_alt.get("placed_assets", [])
        furniture_list = []
        cabinetry_list = []
        appliances_list = []
        sanitary_list = []
        decorations_list = []

        for asset in alt_assets:
            cat = asset.get("category", "")
            bucket = classify_asset_bucket(cat)
            if bucket == "cabinetry":
                cabinetry_list.append(asset)
            elif bucket == "appliances":
                appliances_list.append(asset)
            elif bucket == "sanitary_fixtures":
                sanitary_list.append(asset)
            elif bucket == "decorations":
                decorations_list.append(asset)
            else:
                furniture_list.append(asset)

        room_design["furniture"] = furniture_list
        room_design["cabinetry"] = cabinetry_list
        room_design["appliances"] = appliances_list
        room_design["sanitary_fixtures"] = sanitary_list
        room_design["decorations"] = decorations_list
        room_design["active_alternative_id"] = str(alternative_id)
        room_design["validation"]["fitness_score"] = matched_alt.get("fitness_score", room_design["validation"].get("fitness_score", 0.0))
        room_design["validation"]["fitness_breakdown"] = alt_fb

        # Increment design revision
        new_rev = current_rev + 1
        interior_layout["design_revision"] = new_rev
        room_design["design_revision"] = new_rev

        now_iso = datetime.now(timezone.utc).isoformat()
        interior_layout.setdefault("revisions", []).append({
            "design_revision": new_rev,
            "timestamp": now_iso,
            "scope": "room_select_alternative",
            "room_id": room_id,
            "active_alternative_id": str(alternative_id),
        })

        try:
            project.master_json = master_copy
            project.revision = (getattr(project, "revision", 1) or 1) + 1
            self.db.commit()
            self.db.refresh(project)
        except Exception:
            self.db.rollback()
            raise

        return SelectAlternativeResponseDTO(
            success=True,
            project_id=project.id,
            room_id=room_id,
            active_alternative_id=str(alternative_id),
            design_revision=new_rev,
            updated_at=now_iso,
        )

    # ── Staleness Analysis ───────────────────────────────────────────────────

    def check_design_staleness(self, project: Project) -> DesignStalenessReportDTO:
        """
        Inspects each discovered room's saved design against the project's latest
        authoritative geometry fingerprint and current saved client preference revisions.
        """
        structural_input = self.service.get_structural_context(project)
        current_geo_fp = compute_geometry_fingerprint(structural_input)

        saved_prefs = {
            r["room_id"]: r for r in self.service.list_room_preferences(project.id)
        }
        all_rooms = self.service.get_rooms(project)
        interior_layout = (project.master_json or {}).get("interior_layout", {})
        saved_designs = interior_layout.get("designs", {}).get("rooms", {})

        room_reports: Dict[str, DesignStalenessRoomReportDTO] = {}
        any_stale = False

        for r in all_rooms:
            room_id = r.room_id
            design = saved_designs.get(room_id)
            pref = saved_prefs.get(room_id)

            has_saved = design is not None
            design_rev = design.get("design_revision") if design else None
            saved_fp = design.get("geometry_fingerprint") if design else None
            saved_pref_rev = design.get("preference_revision") if design else None
            current_pref_rev = pref.get("preference_revision") if pref else None

            geo_stale = False
            pref_stale = False
            reason_parts = []

            if has_saved:
                if saved_fp != current_geo_fp:
                    geo_stale = True
                    reason_parts.append("Floor plan geometry updated since layout generation")
                if current_pref_rev is not None and saved_pref_rev != current_pref_rev:
                    pref_stale = True
                    reason_parts.append(f"Client preferences updated to revision {current_pref_rev}")

            is_stale = geo_stale or pref_stale
            if is_stale:
                any_stale = True

            room_reports[room_id] = DesignStalenessRoomReportDTO(
                room_id=room_id,
                floor_id=r.floor_id,
                room_name=r.name,
                has_saved_design=has_saved,
                design_revision=design_rev,
                is_stale=is_stale,
                geometry_stale=geo_stale,
                preference_stale=pref_stale,
                saved_geometry_fingerprint=saved_fp,
                current_geometry_fingerprint=current_geo_fp,
                saved_preference_revision=saved_pref_rev,
                current_preference_revision=current_pref_rev,
                reason="; ".join(reason_parts) if reason_parts else None,
            )

        return DesignStalenessReportDTO(
            project_id=project.id,
            current_geometry_fingerprint=current_geo_fp,
            is_any_room_stale=any_stale,
            rooms=room_reports,
        )

    # ── Selective Regeneration Coordinator ───────────────────────────────────

    def regenerate_scope(
        self,
        project: Project,
        scope: str = "room",  # "room" | "floor" | "building"
        target_room_id: Optional[str] = None,
        target_floor_id: Optional[str] = None,
        config: Optional[Any] = None,
        auto_save: bool = True,
        expected_design_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Executes selective regeneration:
        Stage A: Real GA generation over the requested scope (NO DB locks held).
        Stage B: Safe transactional persistence into projects.master_json.
        Preserves all unrelated rooms, floors, and other component data.
        """
        # Stage A: Generate
        gen_res = self.service.run_generation(
            project=project,
            scope=scope,
            target_floor_id=target_floor_id,
            target_room_id=target_room_id,
            config=config,
            expected_revision=None,
        )

        persistence_result = None
        if auto_save:
            # Stage B: Persist
            persistence_result = self.save_generation_result(
                project=project,
                generation_result=gen_res,
                scope=scope,
                target_room_id=target_room_id,
                target_floor_id=target_floor_id,
                expected_design_revision=expected_design_revision,
            )

        return {
            "generation": gen_res,
            "persistence": persistence_result,
            "scope": scope,
            "auto_saved": auto_save,
        }
