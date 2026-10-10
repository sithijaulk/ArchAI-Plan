import math
import uuid
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..dependencies import require_admin
from ..models.user import User
from ..models.gallery_project import GalleryProject
from ..models.gallery_image import GalleryImage
from ..schemas.gallery import GalleryProjectCreate, GalleryProjectUpdate, GalleryProjectResponse, PaginatedGalleryResponse
from ..config import settings
from ..utils.images import save_upload, validate_image

router = APIRouter(prefix="/admin/gallery", tags=["Admin Gallery"])


def project_to_response(p: GalleryProject) -> dict:
    return {
        **{c.name: getattr(p, c.name) for c in p.__table__.columns},
        "cover_image_url": f"{settings.backend_url.rstrip('/')}/uploads/{p.cover_image}" if p.cover_image else None,
        "gallery_images": [
            {
                **{c.name: getattr(img, c.name) for c in img.__table__.columns},
                "image_url": f"{settings.backend_url.rstrip('/')}/uploads/{img.image_path}"
            }
            for img in sorted(p.images, key=lambda x: x.sort_order)
        ]
    }


@router.get("", response_model=PaginatedGalleryResponse)
def list_admin_gallery(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    query = db.query(GalleryProject)
    if search:
        query = query.filter(GalleryProject.title.ilike(f"%{search}%"))
    
    total = query.count()
    total_pages = math.ceil(total / page_size)
    projects = query.order_by(GalleryProject.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return {
        "items": [project_to_response(p) for p in projects],
        "page": page, "page_size": page_size, "total": total, "total_pages": total_pages
    }


@router.post("", response_model=GalleryProjectResponse, status_code=status.HTTP_201_CREATED)
def create_gallery_project(
    data: GalleryProjectCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    existing = db.query(GalleryProject).filter(GalleryProject.slug == data.slug).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")
    
    project = GalleryProject(**data.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project_to_response(project)


@router.get("/{project_id}", response_model=GalleryProjectResponse)
def get_gallery_project(
    project_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    project = db.query(GalleryProject).filter(GalleryProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gallery project not found")
    return project_to_response(project)


@router.put("/{project_id}", response_model=GalleryProjectResponse)
def update_gallery_project(
    project_id: str,
    data: GalleryProjectUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    project = db.query(GalleryProject).filter(GalleryProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gallery project not found")
    
    # Check slug uniqueness if changing
    if data.slug and data.slug != project.slug:
        existing = db.query(GalleryProject).filter(GalleryProject.slug == data.slug).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")
    
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    
    db.commit()
    db.refresh(project)
    return project_to_response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_gallery_project(
    project_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    project = db.query(GalleryProject).filter(GalleryProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gallery project not found")
    
    # Delete physical files
    project_upload_dir = os.path.join(settings.upload_dir, "gallery", project_id)
    if os.path.exists(project_upload_dir):
        shutil.rmtree(project_upload_dir)
    
    db.delete(project)
    db.commit()


@router.post("/{project_id}/images")
async def upload_gallery_image(
    project_id: str,
    file: UploadFile = File(...),
    type: str = "gallery",
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    project = db.query(GalleryProject).filter(GalleryProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    
    # Validate & save
    validate_image(file)
    subdir = f"gallery/{project_id}/{'cover' if type == 'cover' else 'images'}"
    saved_path = await save_upload(file, subdir, settings.upload_dir)
    
    if type == "cover":
        # Delete old cover file
        if project.cover_image:
            old_path = os.path.join(settings.upload_dir, project.cover_image)
            if os.path.exists(old_path):
                os.remove(old_path)
        project.cover_image = saved_path
        db.commit()
        return {"cover_image": saved_path, "cover_image_url": f"{settings.backend_url.rstrip('/')}/uploads/{saved_path}"}
    else:
        img = GalleryImage(project_id=project_id, image_path=saved_path)
        db.add(img)
        db.commit()
        db.refresh(img)
        return {**img.__dict__, "image_url": f"{settings.backend_url.rstrip('/')}/uploads/{img.image_path}"}


@router.delete("/{project_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_gallery_image(
    project_id: str,
    image_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    img = db.query(GalleryImage).filter(GalleryImage.id == image_id, GalleryImage.project_id == project_id).first()
    if not img:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    
    # Delete file
    full_path = os.path.join(settings.upload_dir, img.image_path)
    if os.path.exists(full_path):
        os.remove(full_path)
    
    db.delete(img)
    db.commit()


@router.patch("/{project_id}/publish")
def publish_project(project_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    project = db.query(GalleryProject).filter(GalleryProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.published = True
    db.commit()
    return {"published": True}


@router.patch("/{project_id}/unpublish")
def unpublish_project(project_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    project = db.query(GalleryProject).filter(GalleryProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.published = False
    db.commit()
    return {"published": False}
