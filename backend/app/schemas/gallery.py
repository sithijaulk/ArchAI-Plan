from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class GalleryImageResponse(BaseModel):
    id: str
    image_path: str
    image_url: str
    alt_text: Optional[str]
    sort_order: int
    created_at: datetime

    class Config:
        from_attributes = True


class GalleryProjectBase(BaseModel):
    title: str
    slug: str
    short_description: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = []
    related_components: Optional[List[str]] = []
    project_date: Optional[str] = None
    featured: bool = False
    published: bool = False
    sort_order: int = 0


class GalleryProjectCreate(GalleryProjectBase):
    pass


class GalleryProjectUpdate(GalleryProjectBase):
    title: Optional[str] = None
    slug: Optional[str] = None


class GalleryProjectResponse(GalleryProjectBase):
    id: str
    cover_image: Optional[str]
    cover_image_url: Optional[str]
    gallery_images: Optional[List[GalleryImageResponse]] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaginatedGalleryResponse(BaseModel):
    items: List[GalleryProjectResponse]
    page: int
    page_size: int
    total: int
    total_pages: int
