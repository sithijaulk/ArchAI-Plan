from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ResearchDocumentBase(BaseModel):
    title: str
    description: Optional[str] = None


class ResearchDocumentUpdate(ResearchDocumentBase):
    title: Optional[str] = None


class TeamMemberBase(BaseModel):
    name: str
    role: str
    category: str = "member"
    bio: Optional[str] = None
    sort_order: int = 0


class TeamMemberUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    category: Optional[str] = None
    bio: Optional[str] = None
    sort_order: Optional[int] = None


class ResearchDocumentResponse(ResearchDocumentBase):
    id: str
    original_filename: str
    mime_type: Optional[str]
    file_size: Optional[int]
    file_url: str
    created_at: datetime

    class Config:
        from_attributes = True


class TeamMemberResponse(TeamMemberBase):
    id: str
    image_url: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True