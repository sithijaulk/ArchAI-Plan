import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text
from ..database import Base


class SiteSetting(Base):
    __tablename__ = "site_settings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    setting_key = Column(String(100), unique=True, nullable=False, index=True)
    setting_value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
