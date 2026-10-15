import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Text
from ..database import Base


class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    role = Column(String(255), nullable=False)
    bio = Column(Text, nullable=True)
    image_path = Column(String(500), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)