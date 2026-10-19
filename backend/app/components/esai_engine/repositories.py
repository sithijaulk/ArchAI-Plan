"""
Database Repositories for ESAI Entities
Provides clean CRUD access to MySQL via SQLAlchemy models:
- EsaiRoomRequirement
- EsaiDesignPreference
- EsaiSavedConfig
"""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.esai import EsaiRoomRequirement, EsaiDesignPreference, EsaiSavedConfig


class EsaiDatabaseRepository:
    """Manages persistence of ESAI-specific room requirements, preferences, and saved configurations."""

    def __init__(self, db: Session):
        self.db = db

    # 1. Room Requirements CRUD
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

    # 2. Design Preferences CRUD
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


    # 3. Saved Configurations CRUD
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
