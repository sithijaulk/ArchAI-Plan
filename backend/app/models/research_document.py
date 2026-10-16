import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Text
try:
    from .database import Base
except (ImportError, ValueError):
    from app.database import Base


class ResearchDocument(Base):
    __tablename__ = "research_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    file_path = Column(String(500), nullable=False)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(150), nullable=True)
    file_size = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)