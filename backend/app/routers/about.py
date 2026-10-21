import os
import shutil
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dependencies import require_admin
from ..models.research_document import ResearchDocument
from ..models.team_member import TeamMember
from ..models.user import User
from ..schemas.about import ResearchDocumentResponse, TeamMemberResponse, TeamMemberUpdate
from ..utils.images import save_upload, validate_image

router = APIRouter(prefix="/about", tags=["About"])
admin_router = APIRouter(prefix="/admin/about", tags=["Admin About"])

DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".md", ".json", ".zip"}


def document_response(document: ResearchDocument) -> dict:
    return {
        **{column.name: getattr(document, column.name) for column in document.__table__.columns},
        "file_url": f"{settings.backend_url.rstrip('/')}/uploads/{document.file_path}",
    }


def member_response(member: TeamMember) -> dict:
    data = {column.name: getattr(member, column.name) for column in member.__table__.columns}
    data["category"] = getattr(member, "category", "member") or "member"
    data["image_url"] = f"{settings.backend_url.rstrip('/')}/uploads/{member.image_path}" if member.image_path else None
    return data


@router.get("/content")
def get_about_content(db: Session = Depends(get_db)):
    documents = db.query(ResearchDocument).order_by(ResearchDocument.created_at.desc()).all()
    members = db.query(TeamMember).order_by(TeamMember.sort_order.asc(), TeamMember.created_at.asc()).all()
    all_members = [member_response(member) for member in members]
    return {
        "documents": [document_response(document) for document in documents],
        "members": all_members,
        "supervisors": [m for m in all_members if m.get("category") == "supervisor"],
        "co_supervisors": [m for m in all_members if m.get("category") == "co_supervisor"],
        "team_members": [m for m in all_members if m.get("category") in ("member", None, "")],
    }


@admin_router.get("/documents", response_model=list[ResearchDocumentResponse])
def list_documents(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return [document_response(document) for document in db.query(ResearchDocument).order_by(ResearchDocument.created_at.desc()).all()]


@admin_router.post("/documents", response_model=ResearchDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in DOCUMENT_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Invalid document type. Allowed: {sorted(DOCUMENT_EXTENSIONS)}")
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds the {settings.max_upload_mb}MB limit")
    await file.seek(0)
    path = await save_upload(file, "research", settings.upload_dir)
    document = ResearchDocument(
        title=title.strip(), description=description, file_path=path,
        original_filename=file.filename or "document", mime_type=file.content_type,
        file_size=len(content),
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document_response(document)


@admin_router.put("/documents/{document_id}", response_model=ResearchDocumentResponse)
def update_document(document_id: str, title: Optional[str] = Form(None), description: Optional[str] = Form(None), db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    document = db.query(ResearchDocument).filter(ResearchDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if title is not None:
        document.title = title.strip()
    if description is not None:
        document.description = description
    db.commit()
    db.refresh(document)
    return document_response(document)


@admin_router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    document = db.query(ResearchDocument).filter(ResearchDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    path = os.path.join(settings.upload_dir, document.file_path)
    if os.path.exists(path):
        os.remove(path)
    db.delete(document)
    db.commit()


@admin_router.get("/members", response_model=list[TeamMemberResponse])
def list_members(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return [member_response(member) for member in db.query(TeamMember).order_by(TeamMember.sort_order.asc(), TeamMember.created_at.asc()).all()]


@admin_router.post("/members", response_model=TeamMemberResponse, status_code=status.HTTP_201_CREATED)
async def create_member(
    name: str = Form(...),
    role: str = Form(...),
    category: str = Form("member"),
    bio: Optional[str] = Form(None),
    sort_order: int = Form(0),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    image_path = None
    if image and image.filename:
        validate_image(image)
        image_path = await save_upload(image, "team", settings.upload_dir)
    member = TeamMember(
        name=name.strip(),
        role=role.strip(),
        category=category.strip().lower() if category else "member",
        bio=bio,
        sort_order=sort_order,
        image_path=image_path
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member_response(member)


@admin_router.put("/members/{member_id}", response_model=TeamMemberResponse)
async def update_member(
    member_id: str,
    name: Optional[str] = Form(None),
    role: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    bio: Optional[str] = Form(None),
    sort_order: Optional[int] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    member = db.query(TeamMember).filter(TeamMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    if name is not None: member.name = name.strip()
    if role is not None: member.role = role.strip()
    if category is not None: member.category = category.strip().lower()
    if bio is not None: member.bio = bio
    if sort_order is not None: member.sort_order = sort_order
    if image and image.filename:
        validate_image(image)
        if member.image_path:
            old_path = os.path.join(settings.upload_dir, member.image_path)
            if os.path.exists(old_path): os.remove(old_path)
        member.image_path = await save_upload(image, "team", settings.upload_dir)
    db.commit()
    db.refresh(member)
    return member_response(member)


@admin_router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(member_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    member = db.query(TeamMember).filter(TeamMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    if member.image_path:
        path = os.path.join(settings.upload_dir, member.image_path)
        if os.path.exists(path): os.remove(path)
    db.delete(member)
    db.commit()