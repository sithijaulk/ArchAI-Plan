from pydantic import BaseModel, EmailStr
from typing import Optional


class ContactCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    subject: str
    message: str


class ContactResponse(BaseModel):
    id: str
    full_name: str
    email: str
    phone: Optional[str]
    subject: str
    message: str
    is_read: bool
    created_at: str

    class Config:
        from_attributes = True
