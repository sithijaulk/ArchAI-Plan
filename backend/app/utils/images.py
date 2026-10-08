import os
import uuid
from typing import Optional
from fastapi import HTTPException, UploadFile, status

ALLOWED_MIME_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/avif"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}


def validate_image(file: UploadFile, max_mb: int = 10) -> None:
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid file type. Allowed: {ALLOWED_EXTENSIONS}")
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MIME type")


async def save_upload(file: UploadFile, subdir: str, base_upload_dir: str) -> str:
    """
    Saves an uploaded file under base_upload_dir/subdir with a UUID filename.
    Returns the relative path from base_upload_dir.
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    filename = f"{uuid.uuid4()}{ext}"
    
    full_dir = os.path.join(base_upload_dir, subdir)
    os.makedirs(full_dir, exist_ok=True)
    
    # Prevent path traversal
    full_path = os.path.realpath(os.path.join(full_dir, filename))
    base_real = os.path.realpath(base_upload_dir)
    if not full_path.startswith(base_real):
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    content = await file.read()
    with open(full_path, "wb") as f:
        f.write(content)
    
    return os.path.join(subdir, filename).replace("\\", "/")
