"""
ESAI Phase 5: Safe Master JSON Persistence, Revision Control & Selective Interior Regeneration
Authoritative project data source: projects.master_json["interior_layout"]
Implements two-stage generation & atomic, non-destructive persistence with optimistic concurrency.
"""
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from sqlalchemy.orm import Session

import uuid
from fastapi import HTTPException, status as http_status
from shapely.geometry import Polygon

from app.models.project import Project
from .contracts import (
    Coordinate2D,
    Dimensions3D,
    GeneratedBuildingDesignDTO,
    GeneratedRoomDesignDTO,
    PersistedRoomDesignDTO,
    PlacedAssetPersistedDTO,
    PlacedFixturePointDTO,
    PlacementMode,
    ResolvedErgonomicConstraintDTO,
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
from .optimizer.chromosome import ChromosomeCodec, PlacedAssetDTO
from .optimizer.geometry_constraints import GeometryConstraintEvaluator
from .optimizer.ergonomic_constraints import ErgonomicConstraintEvaluator


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

    # ── Phase 7: Interactive Editing, Validation, Locking & Selective Regeneration ──

    def validate_room_edit(
        self,
        project: Project,
        room_id: str,
        edit_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Validates proposed manual edits to a room layout against authoritative geometry,
        collision rules, door/window access, ergonomic rules, and mandatory item policies.
        """
        room = self.service.get_room_by_id(project, room_id)
        if not room:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Room '{room_id}' not found.")

        # Convert room polygon to Shapely Polygon
        poly_coords = [(pt.x, pt.y) if hasattr(pt, "x") else (pt["x"], pt["y"]) for pt in room.polygon]
        room_poly = Polygon(poly_coords)

        # Collect all placed assets from edit_data
        raw_assets = (
            edit_data.get("furniture", []) +
            edit_data.get("cabinetry", []) +
            edit_data.get("appliances", []) +
            edit_data.get("sanitary_fixtures", []) +
            edit_data.get("decorations", [])
        )

        placed_dto_list: List[PlacedAssetDTO] = []
        diagnostics = []

        for asset in raw_assets:
            if isinstance(asset, dict):
                a_dict = asset
            else:
                a_dict = asset.model_dump(mode="json") if hasattr(asset, "model_dump") else asset.dict()

            inst_id = a_dict.get("instance_id") or str(uuid.uuid4())
            asset_id = a_dict.get("asset_id", "")
            asset_name = a_dict.get("asset_name", asset_id)
            cat = a_dict.get("category") or "furniture"
            subcat = a_dict.get("subcategory") or cat or "furniture"
            dims_raw = a_dict.get("dimensions", {})
            w = float(dims_raw.get("width", 1.0) if isinstance(dims_raw, dict) else getattr(dims_raw, "width", 1.0))
            d = float(dims_raw.get("depth", 1.0) if isinstance(dims_raw, dict) else getattr(dims_raw, "depth", 1.0))
            h = float(dims_raw.get("height", 1.0) if isinstance(dims_raw, dict) else getattr(dims_raw, "height", 1.0))
            pos_raw = a_dict.get("position", {})
            px = float(pos_raw.get("x", 0.0) if isinstance(pos_raw, dict) else getattr(pos_raw, "x", 0.0))
            py = float(pos_raw.get("y", 0.0) if isinstance(pos_raw, dict) else getattr(pos_raw, "y", 0.0))
            rot = float(a_dict.get("rotation_deg", 0.0))
            is_locked = bool(a_dict.get("is_locked", False) or a_dict.get("is_user_locked", False))

            footprint = ChromosomeCodec.calculate_footprint(px, py, w, d, rot)

            dto = PlacedAssetDTO(
                instance_id=inst_id,
                asset_id=asset_id,
                asset_name=asset_name,
                category=cat,
                subtype=subcat,
                dimensions=Dimensions3D(width=w, depth=d, height=h),
                position=Coordinate2D(x=px, y=py),
                rotation_deg=rot,
                placement_mode=PlacementMode.FLOOR_STANDING,
                priority="user_locked" if is_locked else ("mandatory" if a_dict.get("is_mandatory", True) else "optional"),
                wall_affinity=a_dict.get("associated_wall_id"),
                material_variant=a_dict.get("material"),
                is_locked=is_locked,
                footprint_polygon=footprint,
            )
            placed_dto_list.append(dto)

        # 1. Geometry Validation using Shapely
        geom_eval = GeometryConstraintEvaluator(
            room_polygon=room_poly,
            doors=room.doors,
            windows=room.windows,
            fixed_obstructions=room.fixed_obstructions,
        )
        geom_result = geom_eval.evaluate(placed_dto_list)

        for v in geom_result.violations:
            code = "GEOMETRIC_VIOLATION"
            if "outside usable room" in v:
                code = "FURNITURE_OUTSIDE_ROOM"
            elif "door swing" in v:
                code = "DOOR_ACCESS_BLOCKED"
            elif "blocks window" in v:
                code = "WINDOW_ACCESS_BLOCKED"
            elif "structural obstruction" in v:
                code = "OBSTRUCTION_COLLISION"
            elif "Collision between" in v:
                code = "ASSET_COLLISION"

            diagnostics.append({
                "code": code,
                "severity": "error",
                "message": v,
                "suggested_correction": "Reposition or rotate the asset away from boundaries, openings, or other furniture.",
            })

        # 2. Ergonomic Validation
        ergo_rules = self.service.standards_repo.get_all(enforceable_only=True)
        resolved_rules = [
            ResolvedErgonomicConstraintDTO(
                rule_id=r.id,
                applicable_categories=r.applicable_categories,
                clearance_direction=r.clearance_direction,
                threshold_m=r.threshold_m,
                priority=r.priority,
                verification_status=r.verification_status,
                source_title=r.source_title,
                source_edition=r.source_edition,
                source_section=r.source_section,
                is_mandatory=r.is_mandatory_compliance,
                description=r.description or "",
            )
            for r in ergo_rules
        ]
        ergo_eval = ErgonomicConstraintEvaluator(rules=resolved_rules, room_polygon=room_poly)
        ergo_result = ergo_eval.evaluate(placed_dto_list)

        for ev in ergo_result.violations:
            diagnostics.append({
                "code": "ERGONOMIC_CLEARANCE_VIOLATION",
                "severity": "warning",
                "message": ev,
                "suggested_correction": "Increase clearance around asset to satisfy Neufert ergonomic standards.",
            })

        # 3. Domain Room Specific Checks
        room_type_lower = room.room_type.value.lower() if hasattr(room.room_type, "value") else str(room.room_type).lower()
        if "bed" in room_type_lower:
            has_bed = any("bed" in a.category.lower() or "bed" in a.asset_id.lower() for a in placed_dto_list)
            if not has_bed:
                diagnostics.append({
                    "code": "MANDATORY_ASSET_REMOVAL",
                    "severity": "error",
                    "message": "A bedroom requires at least one bed. Removing mandatory bed is not permitted without preference update.",
                    "suggested_correction": "Add a bed from the catalog or update room preferences.",
                })

        # Bathroom bathtub check
        effective_prefs = self.service.get_effective_preferences(project, room_id, room.floor_id)
        pref_dict = effective_prefs.get("effective_preferences", {}) or effective_prefs.get("effective", {}) or {}
        plumbing_prefs = pref_dict.get("plumbing", {})
        if plumbing_prefs.get("bathtub_preferred") is False or plumbing_prefs.get("bathtub") is False:
            has_bathtub = any("bathtub" in a.category.lower() or "bathtub" in a.asset_id.lower() for a in placed_dto_list)
            if has_bathtub:
                diagnostics.append({
                    "code": "EXCLUDED_ASSET_VIOLATION",
                    "severity": "error",
                    "message": "Bathtub is explicitly excluded by client preferences for this bathroom.",
                    "suggested_correction": "Remove bathtub or update client bathroom preferences to bathtub_preferred=True.",
                })

        hard_passed = (
            geom_result.is_valid
            and not any(d["severity"] == "error" for d in diagnostics)
        )

        return {
            "is_valid": hard_passed and len(diagnostics) == 0,
            "hard_constraints_passed": hard_passed,
            "diagnostics": diagnostics,
            "overlap_area_sqm": geom_result.overlap_area_sqm,
            "out_of_bounds_area_sqm": geom_result.out_of_bounds_area_sqm,
            "door_violation_count": geom_result.door_violation_count,
            "window_violation_count": geom_result.window_violation_count,
            "ergonomic_score": ergo_result.ergonomic_score,
        }

    def save_room_edit(
        self,
        project: Project,
        room_id: str,
        edit_data: Dict[str, Any],
        expected_design_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Validates and atomically persists user manual edits into projects.master_json['interior_layout']['designs']['rooms'][room_id].
        """
        self.db.refresh(project)
        master_copy = deepcopy(project.master_json or {})
        interior_layout = master_copy.setdefault("interior_layout", {})
        current_rev = interior_layout.get("design_revision", 0)

        # 1. Optimistic Concurrency Check
        if expected_design_revision is not None and expected_design_revision != current_rev:
            raise DesignRevisionConflictError(
                message=f"Concurrent conflict: expected design revision {expected_design_revision}, but current revision is {current_rev}.",
                project_id=project.id,
                expected_rev=expected_design_revision,
                current_rev=current_rev,
            )

        # 2. Authoritative Geometry & Hard Constraint Validation
        val_res = self.validate_room_edit(project, room_id, edit_data)
        if not val_res["hard_constraints_passed"]:
            error_msgs = [d["message"] for d in val_res["diagnostics"] if d["severity"] == "error"]
            raise InvalidDesignSaveError(
                message=f"Proposed edits violate hard constraints in room '{room_id}': {'; '.join(error_msgs)}",
                room_id=room_id,
                violations=error_msgs,
            )

        # 3. Fetch existing room design
        rooms = interior_layout.setdefault("designs", {}).setdefault("rooms", {})
        existing_room = rooms.get(room_id, {})
        floor_id = edit_data.get("floor_id") or existing_room.get("floor_id")

        new_rev = current_rev + 1
        interior_layout["design_revision"] = new_rev

        # Build updated room structure
        now_iso = datetime.now(timezone.utc).isoformat()
        updated_room = deepcopy(existing_room)
        updated_room["room_id"] = room_id
        if floor_id:
            updated_room["floor_id"] = floor_id
        updated_room["design_revision"] = new_rev
        updated_room["generation_timestamp"] = now_iso
        updated_room["furniture"] = edit_data.get("furniture", existing_room.get("furniture", []))
        updated_room["cabinetry"] = edit_data.get("cabinetry", existing_room.get("cabinetry", []))
        updated_room["appliances"] = edit_data.get("appliances", existing_room.get("appliances", []))
        updated_room["sanitary_fixtures"] = edit_data.get("sanitary_fixtures", existing_room.get("sanitary_fixtures", []))
        updated_room["decorations"] = edit_data.get("decorations", existing_room.get("decorations", []))
        updated_room["lighting"] = edit_data.get("lighting", existing_room.get("lighting", []))
        updated_room["electrical_points"] = edit_data.get("electrical_points", existing_room.get("electrical_points", []))
        updated_room["plumbing_requirements"] = edit_data.get("plumbing_requirements", existing_room.get("plumbing_requirements", []))
        updated_room["service_requirements"] = edit_data.get("service_requirements", existing_room.get("service_requirements", []))

        # Finishes
        if "wall_finishes" in edit_data:
            updated_room["wall_finishes"] = edit_data["wall_finishes"]
        if "floor_finishes" in edit_data:
            updated_room["floor_finishes"] = edit_data["floor_finishes"]
        if "ceiling_finishes" in edit_data:
            updated_room["ceiling_finishes"] = edit_data["ceiling_finishes"]
        if "wall_finish" in edit_data:
            updated_room["wall_finish"] = edit_data["wall_finish"]
        if "wall_color" in edit_data:
            updated_room["wall_color"] = edit_data["wall_color"]
        if "floor_finish" in edit_data:
            updated_room["floor_finish"] = edit_data["floor_finish"]
        if "ceiling_finish" in edit_data:
            updated_room["ceiling_finish"] = edit_data["ceiling_finish"]

        # Validation summary
        updated_room["validation"] = {
            "hard_constraints_passed": val_res["hard_constraints_passed"],
            "diagnostics": [d["message"] for d in val_res["diagnostics"]],
            "overlap_area_sqm": val_res["overlap_area_sqm"],
            "out_of_bounds_area_sqm": val_res["out_of_bounds_area_sqm"],
            "ergonomic_score": val_res["ergonomic_score"],
            "manual_edit": True,
        }

        rooms[room_id] = updated_room

        # Revision history
        interior_layout.setdefault("revisions", []).append({
            "design_revision": new_rev,
            "timestamp": now_iso,
            "scope": "room_manual_edit",
            "room_id": room_id,
        })

        # Check preference consistency for bed replacement
        all_assets = (
            updated_room.get("furniture", []) +
            updated_room.get("cabinetry", []) +
            updated_room.get("appliances", []) +
            updated_room.get("sanitary_fixtures", [])
        )
        for a in all_assets:
            aid = (a.get("asset_id") or "").upper()
            if "BED_QUEEN" in aid:
                try:
                    self.service.patch_room_preferences(project, room_id, {"bedroom": {"bed_type": "queen"}})
                except Exception:
                    pass
                break
            elif "BED_KING" in aid:
                try:
                    self.service.patch_room_preferences(project, room_id, {"bedroom": {"bed_type": "king"}})
                except Exception:
                    pass
                break
            elif "BED_SINGLE" in aid:
                try:
                    self.service.patch_room_preferences(project, room_id, {"bedroom": {"bed_type": "single"}})
                except Exception:
                    pass
                break
            elif "BED_DOUBLE" in aid:
                try:
                    self.service.patch_room_preferences(project, room_id, {"bedroom": {"bed_type": "double"}})
                except Exception:
                    pass
                break

        try:
            project.master_json = master_copy
            project.revision = (getattr(project, "revision", 1) or 1) + 1
            self.db.commit()
            self.db.refresh(project)
        except Exception:
            self.db.rollback()
            raise

        return {
            "success": True,
            "project_id": project.id,
            "room_id": room_id,
            "design_revision": new_rev,
            "updated_at": now_iso,
            "saved_design": updated_room,
        }

    def toggle_asset_lock(
        self,
        project: Project,
        room_id: str,
        instance_id: str,
        is_locked: bool = True,
        lock_type: str = "all",
        expected_design_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Locks or unlocks a specific placed asset in a room.
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
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"No saved design for room '{room_id}'.")

        matched = False
        for bucket_key in ("furniture", "cabinetry", "appliances", "sanitary_fixtures", "decorations"):
            bucket = room_design.get(bucket_key, [])
            for asset in bucket:
                if asset.get("instance_id") == instance_id:
                    asset["is_locked"] = is_locked
                    asset["is_user_locked"] = is_locked
                    asset["lock_type"] = lock_type
                    matched = True
                    break
            if matched:
                break

        if not matched:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Asset instance '{instance_id}' not found in room '{room_id}'.")

        new_rev = current_rev + 1
        interior_layout["design_revision"] = new_rev
        room_design["design_revision"] = new_rev

        now_iso = datetime.now(timezone.utc).isoformat()
        interior_layout.setdefault("revisions", []).append({
            "design_revision": new_rev,
            "timestamp": now_iso,
            "scope": "asset_lock_toggle",
            "room_id": room_id,
            "instance_id": instance_id,
            "is_locked": is_locked,
        })

        try:
            project.master_json = master_copy
            project.revision = (getattr(project, "revision", 1) or 1) + 1
            self.db.commit()
            self.db.refresh(project)
        except Exception:
            self.db.rollback()
            raise

        return {
            "success": True,
            "project_id": project.id,
            "room_id": room_id,
            "instance_id": instance_id,
            "is_locked": is_locked,
            "design_revision": new_rev,
            "updated_at": now_iso,
        }

    def regenerate_unlocked(
        self,
        project: Project,
        room_id: str,
        config: Optional[Any] = None,
        expected_design_revision: Optional[int] = None,
        auto_save: bool = True,
    ) -> Dict[str, Any]:
        """
        Selectively reoptimizes unlocked furniture in a room using the real Genetic Algorithm,
        preserving all locked items at their exact coordinates and rotations.
        """
        saved_design = self.get_room_design(project, room_id)
        if not saved_design:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"No saved design for room '{room_id}'.")

        # Collect locked items
        all_assets = (
            saved_design.get("furniture", []) +
            saved_design.get("cabinetry", []) +
            saved_design.get("appliances", []) +
            saved_design.get("sanitary_fixtures", []) +
            saved_design.get("decorations", [])
        )
        locked_assets = [a for a in all_assets if a.get("is_locked") or a.get("is_user_locked")]

        # Build locked placements mapping for the optimizer
        locked_placements = []
        for la in locked_assets:
            pos = la.get("position", {})
            locked_placements.append({
                "item_id": la.get("instance_id"),
                "asset_id": la.get("asset_id"),
                "category": la.get("category"),
                "x": float(pos.get("x", 0.0)),
                "y": float(pos.get("y", 0.0)),
                "rotation": float(la.get("rotation_deg", 0.0)),
            })

        # Inject locked placements into room preferences
        floor_id = saved_design.get("floor_id")
        effective_prefs = self.service.get_effective_preferences(project, room_id, floor_id)
        pref_dict = deepcopy(effective_prefs.get("effective_preferences", {}) or effective_prefs.get("effective", {}) or {})
        pref_dict["locked_placements"] = locked_placements

        # Resolve design input with locked placements
        room_struct = self.service.get_room_by_id(project, room_id)
        geo_fp = self.service._get_geo_fingerprint(project)
        revision = getattr(project, "revision", 1) or 1

        resolved_input = self.service.resolver.resolve(
            project_id=project.id,
            floor_id=floor_id or room_struct.floor_id,
            room_id=room_id,
            room_name=room_struct.name,
            room_type_str=room_struct.room_type.value if hasattr(room_struct.room_type, "value") else str(room_struct.room_type),
            polygon=room_struct.polygon,
            area_sqm=room_struct.area_sqm,
            ceiling_height_m=room_struct.ceiling_height or 2.8,
            doors=room_struct.doors,
            windows=room_struct.windows,
            fixed_obstructions=room_struct.fixed_obstructions,
            effective_preferences={"effective_preferences": pref_dict},
            geometry_fingerprint=geo_fp,
            geometry_revision=revision,
            elevation_m=room_struct.elevation or 0.0,
        )

        from .generation.room_generator import RoomGenerator
        room_gen = RoomGenerator()
        gen_room_result = room_gen.generate_room(resolved_input, config=config)

        if not gen_room_result.hard_constraints_passed:
            diagnostics = gen_room_result.diagnostics or ["Infeasible spatial configuration with locked items."]
            return {
                "success": False,
                "project_id": project.id,
                "room_id": room_id,
                "design_revision": saved_design.get("design_revision", 0),
                "saved_design": saved_design,
                "diagnostics": diagnostics,
            }

        # Persist if requested
        if auto_save:
            save_res = self.save_generation_result(
                project=project,
                generation_result=gen_room_result,
                scope="room",
                target_room_id=room_id,
                target_floor_id=floor_id,
                expected_design_revision=expected_design_revision,
            )
            updated_design = self.get_room_design(project, room_id)
            return {
                "success": True,
                "project_id": project.id,
                "room_id": room_id,
                "design_revision": save_res.design_revision,
                "saved_design": updated_design,
                "diagnostics": gen_room_result.diagnostics,
            }

        return {
            "success": True,
            "project_id": project.id,
            "room_id": room_id,
            "design_revision": saved_design.get("design_revision", 0),
            "saved_design": gen_room_result.model_dump(mode="json"),
            "diagnostics": gen_room_result.diagnostics,
        }
