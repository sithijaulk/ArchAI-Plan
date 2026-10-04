import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from ..database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    current_component = Column(String(50), nullable=True)
    master_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    component_runs = relationship("ComponentRun", back_populates="project", cascade="all, delete-orphan")
    outputs = relationship("ProjectOutput", back_populates="project", cascade="all, delete-orphan")
