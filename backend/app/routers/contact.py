from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.contact_message import ContactMessage
from ..schemas.contact import ContactCreate, ContactResponse
from ..dependencies import require_admin
from ..models.user import User

router = APIRouter(prefix="/contact", tags=["Contact"])


@router.post("", status_code=status.HTTP_201_CREATED)
def submit_contact(data: ContactCreate, db: Session = Depends(get_db)):
    msg = ContactMessage(**data.model_dump())
    db.add(msg)
    db.commit()
    return {"message": "Your message has been received. We will respond shortly."}


# Admin endpoints
admin_router = APIRouter(prefix="/admin/messages", tags=["Admin Messages"])


@admin_router.get("")
def list_messages(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    messages = db.query(ContactMessage).order_by(ContactMessage.created_at.desc()).all()
    return [
        {
            **{c.name: getattr(m, c.name) for c in m.__table__.columns},
            "created_at": m.created_at.isoformat()
        }
        for m in messages
    ]


@admin_router.get("/{message_id}")
def get_message(message_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    msg = db.query(ContactMessage).filter(ContactMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return {**{c.name: getattr(msg, c.name) for c in msg.__table__.columns}, "created_at": msg.created_at.isoformat()}


@admin_router.patch("/{message_id}/read")
def mark_read(message_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    msg = db.query(ContactMessage).filter(ContactMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.is_read = True
    db.commit()
    return {"is_read": True}


@admin_router.patch("/{message_id}/unread")
def mark_unread(message_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    msg = db.query(ContactMessage).filter(ContactMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.is_read = False
    db.commit()
    return {"is_read": False}


@admin_router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(message_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    msg = db.query(ContactMessage).filter(ContactMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    db.delete(msg)
    db.commit()
