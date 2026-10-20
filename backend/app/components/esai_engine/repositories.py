"""
Database Repositories for ESAI Entities
Provides clean CRUD access to MySQL via SQLAlchemy models:
- EsaiRoomRequirement
- EsaiDesignPreference
- EsaiSavedConfig
- EsaiFloorPreference  (Phase 2)
- EsaiRoomPreference   (Phase 2)

Preference resolution order (most specific wins):
  Item-specific → Room → Floor → Building defaults
"""
from copy import deepcopy
from typing import Any, Dict, List, Optional, Set
from sqlalchemy.orm import Session
from app.models.esai import (
    EsaiRoomRequirement,
    EsaiDesignPreference,
    EsaiSavedConfig,
    EsaiFloorPreference,
    EsaiRoomPreference,
)


class EsaiDatabaseRepository:
    """Manages persistence of ESAI-specific room requirements, preferences, and saved configurations."""

    def __init__(self, db: Session):
        self.db = db

    # ─── 1. Room Requirements CRUD ─────────────────────────────────────────────

    def get_room_requirements(self, project_id: str, room_id: Optional[str] = None) -> List[EsaiRoomRequirement]:
        query = self.db.query(EsaiRoomRequirement).filter(EsaiRoomRequirement.project_id == project_id)
        if room_id:
            query = query.filter(EsaiRoomRequirement.room_id == room_id)
        return query.all()

    def get_single_room_requirement(self, project_id: str, room_id: str) -> Optional[EsaiRoomRequirement]:
        return self.db.query(EsaiRoomRequirement).filter(
            EsaiRoomRequirement.project_id == project_id,
            EsaiRoomRequirement.room_id == room_id
        ).first()

    def upsert_room_requirement(
        self,
        project_id: str,
        floor_id: str,
        room_id: str,
        requirements_data: Dict[str, Any],
        status: str = "draft",
        auto_commit: bool = True
    ) -> EsaiRoomRequirement:
        record = self.get_single_room_requirement(project_id, room_id)
        if record:
            record.floor_id = floor_id
            record.requirements_json = requirements_data
            record.status = status
        else:
            record = EsaiRoomRequirement(
                project_id=project_id,
                floor_id=floor_id,
                room_id=room_id,
                requirements_json=requirements_data,
                status=status
            )
            self.db.add(record)
        if auto_commit:
            self.db.commit()
            self.db.refresh(record)
        else:
            self.db.flush()
        return record

    def delete_room_requirement(self, project_id: str, room_id: str) -> bool:
        record = self.get_single_room_requirement(project_id, room_id)
        if record:
            self.db.delete(record)
            self.db.commit()
            return True
        return False

    # ─── 2. Building-level Design Preferences CRUD ────────────────────────────

    def get_design_preference(self, project_id: str) -> Optional[EsaiDesignPreference]:
        return self.db.query(EsaiDesignPreference).filter(EsaiDesignPreference.project_id == project_id).first()

    def upsert_design_preference(
        self,
        project_id: str,
        preferences_data: Dict[str, Any],
        geometry_fingerprint: Optional[str] = None,
        auto_commit: bool = True
    ) -> EsaiDesignPreference:
        record = self.get_design_preference(project_id)
        if record:
            record.preferences_json = preferences_data
            if geometry_fingerprint is not None:
                record.geometry_fingerprint = geometry_fingerprint
        else:
            record = EsaiDesignPreference(
                project_id=project_id,
                preferences_json=preferences_data,
                geometry_fingerprint=geometry_fingerprint
            )
            self.db.add(record)
        if auto_commit:
            self.db.commit()
            self.db.refresh(record)
        else:
            self.db.flush()
        return record

    # ─── 3. Floor-level Preference CRUD ───────────────────────────────────────

    def get_floor_preference(self, project_id: str, floor_id: str) -> Optional[EsaiFloorPreference]:
        return self.db.query(EsaiFloorPreference).filter(
            EsaiFloorPreference.project_id == project_id,
            EsaiFloorPreference.floor_id == floor_id,
        ).first()

    def get_all_floor_preferences(self, project_id: str) -> List[EsaiFloorPreference]:
        return self.db.query(EsaiFloorPreference).filter(
            EsaiFloorPreference.project_id == project_id
        ).all()

    def upsert_floor_preference(
        self,
        project_id: str,
        floor_id: str,
        preferences_data: Dict[str, Any],
        geometry_fingerprint: Optional[str] = None,
        auto_commit: bool = True
    ) -> EsaiFloorPreference:
        record = self.get_floor_preference(project_id, floor_id)
        if record:
            record.preferences_json = preferences_data
            if geometry_fingerprint is not None:
                record.geometry_fingerprint = geometry_fingerprint
        else:
            record = EsaiFloorPreference(
                project_id=project_id,
                floor_id=floor_id,
                preferences_json=preferences_data,
                geometry_fingerprint=geometry_fingerprint,
            )
            self.db.add(record)
        if auto_commit:
            self.db.commit()
            self.db.refresh(record)
        else:
            self.db.flush()
        return record

    def delete_floor_preference(self, project_id: str, floor_id: str) -> bool:
        record = self.get_floor_preference(project_id, floor_id)
        if record:
            self.db.delete(record)
            self.db.commit()
            return True
        return False

    # ─── 4. Room-level Preference CRUD ────────────────────────────────────────

    def get_room_preference(self, project_id: str, room_id: str) -> Optional[EsaiRoomPreference]:
        return self.db.query(EsaiRoomPreference).filter(
            EsaiRoomPreference.project_id == project_id,
            EsaiRoomPreference.room_id == room_id,
        ).first()

    def get_all_room_preferences(self, project_id: str, floor_id: Optional[str] = None) -> List[EsaiRoomPreference]:
        query = self.db.query(EsaiRoomPreference).filter(
            EsaiRoomPreference.project_id == project_id
        )
        if floor_id:
            query = query.filter(EsaiRoomPreference.floor_id == floor_id)
        return query.all()

    def upsert_room_preference(
        self,
        project_id: str,
        floor_id: str,
        room_id: str,
        room_type: str,
        preferences_data: Dict[str, Any],
        geometry_fingerprint: Optional[str] = None,
        auto_commit: bool = True
    ) -> EsaiRoomPreference:
        record = self.get_room_preference(project_id, room_id)
        if record:
            record.floor_id = floor_id
            record.room_type = room_type
            record.preferences_json = preferences_data
            record.preference_revision = (record.preference_revision or 1) + 1
            record.is_orphaned = False
            if geometry_fingerprint is not None:
                record.geometry_fingerprint = geometry_fingerprint
        else:
            record = EsaiRoomPreference(
                project_id=project_id,
                floor_id=floor_id,
                room_id=room_id,
                room_type=room_type,
                preferences_json=preferences_data,
                preference_revision=1,
                geometry_fingerprint=geometry_fingerprint,
                is_orphaned=False,
            )
            self.db.add(record)
        if auto_commit:
            self.db.commit()
            self.db.refresh(record)
        else:
            self.db.flush()
        return record

    def delete_room_preference(self, project_id: str, room_id: str) -> bool:
        """Reset a room's preferences to inherited (delete the override record)."""
        record = self.get_room_preference(project_id, room_id)
        if record:
            self.db.delete(record)
            self.db.commit()
            return True
        return False

    def patch_room_preference(
        self,
        project_id: str,
        room_id: str,
        patch_data: Dict[str, Any],
        auto_commit: bool = True
    ) -> Optional[EsaiRoomPreference]:
        """Shallow-merge patch_data into the room's existing preferences_json."""
        record = self.get_room_preference(project_id, room_id)
        if not record:
            return None
        merged = deepcopy(record.preferences_json or {})
        merged.update(patch_data)
        record.preferences_json = merged
        record.preference_revision = (record.preference_revision or 1) + 1
        if auto_commit:
            self.db.commit()
            self.db.refresh(record)
        else:
            self.db.flush()
        return record

    def mark_orphaned_preferences(
        self,
        project_id: str,
        valid_room_ids: Set[str],
        auto_commit: bool = True
    ) -> List[str]:
        """Mark rooms whose IDs no longer exist in the current geometry as orphaned."""
        orphaned_ids: List[str] = []
        all_prefs = self.get_all_room_preferences(project_id)
        for pref in all_prefs:
            if pref.room_id not in valid_room_ids and not pref.is_orphaned:
                pref.is_orphaned = True
                orphaned_ids.append(pref.room_id)
        if orphaned_ids and auto_commit:
            self.db.commit()
        return orphaned_ids

    # ─── 5. Preference Resolver ────────────────────────────────────────────────

    def resolve_effective_preferences(
        self,
        project_id: str,
        room_id: str,
        floor_id: str,
    ) -> Dict[str, Any]:
        """
        Deterministic 4-level preference resolution.

        Resolution order (most-specific wins):
          Room explicit value > Floor override > Building default > System fallback

        Rules:
        - Explicit False, 0, [], empty string, and "none" are NEVER treated as missing.
        - A field present in the room record always overrides floor/building even if it is False.
        - Only ABSENT keys fall through to the next level.
        - Item-level locked selections and custom constraints are preserved at room level.
        """
        building_rec = self.get_design_preference(project_id)
        building_dict = (building_rec.preferences_json or {}) if building_rec else {}
        building_clean = building_dict.get("preferences", building_dict) if isinstance(building_dict.get("preferences"), dict) else building_dict

        floor_rec = self.get_floor_preference(project_id, floor_id)
        floor_dict = (floor_rec.preferences_json or {}) if floor_rec else {}
        floor_clean = floor_dict.get("preferences", floor_dict) if isinstance(floor_dict.get("preferences"), dict) else floor_dict

        room_rec = self.get_room_preference(project_id, room_id)
        room_dict = (room_rec.preferences_json or {}) if room_rec else {}
        if isinstance(room_dict.get("preferences"), dict):
            room_clean = deepcopy(room_dict["preferences"])
        else:
            room_clean = {k: v for k, v in room_dict.items() if k not in ("specific_assets", "custom_constraints")}

        # Cascade: building -> floor -> room
        effective = deepcopy(building_clean)
        for key, value in floor_clean.items():
            effective[key] = value
        for key, value in room_clean.items():
            effective[key] = value

        sources: Dict[str, str] = {}
        overridden_keys: List[str] = []
        inherited_keys: List[str] = []
        for key in effective.keys():
            if key in room_clean:
                sources[key] = "OVERRIDDEN_ROOM"
                overridden_keys.append(key)
            elif key in floor_clean:
                sources[key] = "INHERITED_FLOOR"
                inherited_keys.append(key)
            elif key in building_clean:
                sources[key] = "INHERITED_BUILDING"
                inherited_keys.append(key)
            else:
                sources[key] = "DEFAULT"

        specific_assets = (
            room_dict.get("specific_assets") or
            (getattr(room_rec, "specific_assets_json", None) if room_rec else None) or
            []
        )
        custom_constraints = (
            room_dict.get("custom_constraints") or
            (getattr(room_rec, "custom_constraints_json", None) if room_rec else None) or
            []
        )

        return {
            "room_id": room_id,
            "floor_id": floor_id,
            "room_type": room_rec.room_type if room_rec else "room",
            "effective_preferences": effective,
            "effective": effective,
            "sources": sources,
            "overridden_keys": overridden_keys,
            "inherited_keys": inherited_keys,
            "specific_assets": specific_assets,
            "custom_constraints": custom_constraints,
            "is_orphaned": room_rec.is_orphaned if room_rec else False,
            "preference_revision": room_rec.preference_revision if room_rec else None,
        }


    # ─── 6. Saved Configurations CRUD ─────────────────────────────────────────

    def list_saved_configs(self, project_id: str) -> List[EsaiSavedConfig]:
        return self.db.query(EsaiSavedConfig).filter(EsaiSavedConfig.project_id == project_id).all()

    def get_saved_config(self, project_id: str, config_id: str) -> Optional[EsaiSavedConfig]:
        return self.db.query(EsaiSavedConfig).filter(
            EsaiSavedConfig.project_id == project_id,
            EsaiSavedConfig.id == config_id
        ).first()

    def create_saved_config(
        self,
        project_id: str,
        configuration_name: str,
        room_ids: List[str],
        settings_data: Dict[str, Any]
    ) -> EsaiSavedConfig:
        config = EsaiSavedConfig(
            project_id=project_id,
            configuration_name=configuration_name,
            room_ids_json=room_ids,
            settings_json=settings_data
        )
        self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return config

    def update_saved_config(
        self,
        project_id: str,
        config_id: str,
        configuration_name: Optional[str] = None,
        room_ids: Optional[List[str]] = None,
        settings_data: Optional[Dict[str, Any]] = None
    ) -> Optional[EsaiSavedConfig]:
        config = self.get_saved_config(project_id, config_id)
        if not config:
            return None
        if configuration_name is not None:
            config.configuration_name = configuration_name
        if room_ids is not None:
            config.room_ids_json = room_ids
        if settings_data is not None:
            config.settings_json = settings_data
        self.db.commit()
        self.db.refresh(config)
        return config

    def delete_saved_config(self, project_id: str, config_id: str) -> bool:
        config = self.get_saved_config(project_id, config_id)
        if not config:
            return False
        self.db.delete(config)
        self.db.commit()
        return True

