from sqlalchemy import Column, String, Integer, Boolean, JSON, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from app.database import Base


def _utc_now():
    return datetime.now(timezone.utc)


class EsaiRoomRequirement(Base):
    __tablename__ = "esai_room_requirements"
    __table_args__ = (
        UniqueConstraint("project_id", "room_id", name="uq_esai_room_requirements_project_room"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    floor_id = Column(String(255), nullable=False)
    room_id = Column(String(255), nullable=False)
    requirements_json = Column(JSON, nullable=False)
    status = Column(String(50), default="draft")
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    project = relationship("Project")


class EsaiDesignPreference(Base):
    __tablename__ = "esai_design_preferences"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False, unique=True)
    preferences_json = Column(JSON, nullable=False)
    geometry_fingerprint = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    project = relationship("Project")


class EsaiSavedConfig(Base):
    __tablename__ = "esai_saved_configs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    configuration_name = Column(String(255), nullable=False)
    room_ids_json = Column(JSON, nullable=False)
    settings_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    project = relationship("Project")


class EsaiFloorPreference(Base):
    """Per-floor preference overrides — override building defaults for all rooms on this floor."""
    __tablename__ = "esai_floor_preferences"
    __table_args__ = (
        UniqueConstraint("project_id", "floor_id", name="uq_esai_floor_preferences_project_floor"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    floor_id = Column(String(255), nullable=False)
    preferences_json = Column(JSON, nullable=False)
    geometry_fingerprint = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    project = relationship("Project")


class EsaiRoomPreference(Base):
    """Per-room full preference record — highest priority in the resolution hierarchy."""
    __tablename__ = "esai_room_preferences"
    __table_args__ = (
        UniqueConstraint("project_id", "room_id", name="uq_esai_room_preferences_project_room"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    floor_id = Column(String(255), nullable=False)
    room_id = Column(String(255), nullable=False)
    room_type = Column(String(64), nullable=False)
    preferences_json = Column(JSON, nullable=False)
    preference_revision = Column(Integer, default=1, nullable=False)
    geometry_fingerprint = Column(String(64), nullable=True)
    is_orphaned = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    project = relationship("Project")
