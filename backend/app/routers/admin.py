from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..dependencies import require_admin
from ..models.user import User
from ..models.gallery_project import GalleryProject
from ..models.gallery_image import GalleryImage
from ..models.contact_message import ContactMessage
from ..models.project import Project

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats")
def get_dashboard_stats(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    total_projects = db.query(GalleryProject).count()
    published_projects = db.query(GalleryProject).filter(GalleryProject.published == True).count()
    draft_projects = total_projects - published_projects
    total_images = db.query(GalleryImage).count()
    unread_messages = db.query(ContactMessage).filter(ContactMessage.is_read == False).count()
    total_research_projects = db.query(Project).count()

    recent_projects = db.query(GalleryProject).order_by(GalleryProject.created_at.desc()).limit(5).all()
    recent_messages = db.query(ContactMessage).order_by(ContactMessage.created_at.desc()).limit(5).all()

    return {
        "totalProjects": total_projects,
        "publishedProjects": published_projects,
        "draftProjects": draft_projects,
        "totalImages": total_images,
        "unreadMessages": unread_messages,
        "totalResearchProjects": total_research_projects,
        "recentProjects": [
            {
                "id": p.id,
                "title": p.title,
                "published": p.published,
                "created_at": p.created_at.isoformat()
            }
            for p in recent_projects
        ],
        "recentMessages": [
            {
                "id": m.id,
                "full_name": m.full_name,
                "subject": m.subject,
                "is_read": m.is_read,
                "created_at": m.created_at.isoformat()
            }
            for m in recent_messages
        ]
    }
