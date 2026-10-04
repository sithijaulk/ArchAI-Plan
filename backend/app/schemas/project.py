from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class ProjectCreate(BaseModel):
    project_name: str
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    project_name: Optional[str] = None
    description: Optional[str] = None
    current_component: Optional[str] = None
    master_json: Optional[Dict[str, Any]] = None


class ProjectResponse(BaseModel):
    id: str
    project_name: str
    description: Optional[str]
    current_component: Optional[str]
    master_json: Optional[Dict[str, Any]]
    revision: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
