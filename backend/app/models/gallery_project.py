import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Integer, JSON, Text, ForeignKey
from sqlalchemy.orm import relationship
from ..database import Base


class GalleryProject(Base):
    __tablename__ = "gallery_projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    short_description = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    tags = Column(JSON, default=list)
    related_components = Column(JSON, default=list)
    project_date = Column(String(50), nullable=True)
    cover_image = Column(String(500), nullable=True)  # relative path
    featured = Column(Boolean, default=False, index=True)
    published = Column(Boolean, default=False, index=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    images = relationship("GalleryImage", back_populates="project", cascade="all, delete-orphan")
