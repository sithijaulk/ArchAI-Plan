from sqlalchemy import Column, String, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.database import Base

class EsaiRoomRequirement(Base):
    __tablename__ = "esai_room_requirements"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    floor_id = Column(String(255), nullable=False)
    room_id = Column(String(255), nullable=False)
    requirements_json = Column(JSON, nullable=False)
    status = Column(String(50), default="draft")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project")

class EsaiDesignPreference(Base):
    __tablename__ = "esai_design_preferences"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False, unique=True)
    preferences_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project")

class EsaiSavedConfig(Base):
    __tablename__ = "esai_saved_configs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    configuration_name = Column(String(255), nullable=False)
    room_ids_json = Column(JSON, nullable=False)
    settings_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project")
