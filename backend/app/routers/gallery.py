import math
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..models.gallery_project import GalleryProject
from ..schemas.gallery import GalleryProjectResponse, PaginatedGalleryResponse
from ..config import settings

router = APIRouter(prefix="/gallery", tags=["Gallery"])


def build_cover_url(project: GalleryProject) -> Optional[str]:
    if project.cover_image:
        return f"{settings.backend_url.rstrip('/')}/uploads/{project.cover_image}"
    return None


@router.get("", response_model=PaginatedGalleryResponse)
def list_published_gallery(
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    search: Optional[str] = None,
    category: Optional[str] = None,
    component: Optional[str] = None,
    featured: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(GalleryProject).filter(GalleryProject.published == True)
    
    if search:
        query = query.filter(GalleryProject.title.ilike(f"%{search}%"))
    if category:
        query = query.filter(GalleryProject.category == category)
    if component:
        query = query.filter(GalleryProject.related_components.contains([component]))
    if featured is not None:
        query = query.filter(GalleryProject.featured == featured)
    
    total = query.count()
    total_pages = math.ceil(total / page_size)
    projects = query.order_by(GalleryProject.sort_order.asc(), GalleryProject.created_at.desc()) \
                    .offset((page - 1) * page_size).limit(page_size).all()
    
    items = []
    for p in projects:
        p_dict = {
            **p.__dict__,
            "cover_image_url": build_cover_url(p),
            "gallery_images": [
                {**img.__dict__, "image_url": f"{settings.backend_url.rstrip('/')}/uploads/{img.image_path}"}
                for img in p.images
            ]
        }
        items.append(p_dict)
    
    return {"items": items, "page": page, "page_size": page_size, "total": total, "total_pages": total_pages}


@router.get("/{slug}", response_model=GalleryProjectResponse)
def get_published_project(slug: str, db: Session = Depends(get_db)):
    project = db.query(GalleryProject).filter(
        GalleryProject.slug == slug,
        GalleryProject.published == True
    ).first()
    
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gallery project not found")
    
    result = {
        **project.__dict__,
        "cover_image_url": build_cover_url(project),
        "gallery_images": [
            {**img.__dict__, "image_url": f"{settings.backend_url.rstrip('/')}/uploads/{img.image_path}"}
            for img in project.images
        ]
    }
    return result
