import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from ..database import Base


class ComponentRun(Base):
    __tablename__ = "component_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    component_name = Column(String(50), nullable=False)
    status = Column(String(20), default="pending")  # pending, processing, completed, failed, skipped
    input_json = Column(JSON, nullable=True)
    output_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="component_runs")


class ProjectOutput(Base):
    __tablename__ = "project_outputs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    component_name = Column(String(50), nullable=False)
    output_type = Column(String(20), nullable=False)  # json, png, pdf
    file_path = Column(String(500), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="outputs")
