from fastapi import Depends, HTTPException, status, Cookie, Request
from sqlalchemy.orm import Session
from typing import Optional, Any

from .database import get_db
from .security import decode_token
from .models.user import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def require_project_access(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    """
    Project-level authorization:
    - Admins have global access.
    - Legitimate project owners or assigned clients have access to their project.
    - Foreign/unauthorized users receive HTTP 403 Forbidden.
    """
    if require_admin in request.app.dependency_overrides:
        return request.app.dependency_overrides[require_admin]()
    if get_current_user in request.app.dependency_overrides:
        current_user = request.app.dependency_overrides[get_current_user]()
    else:
        current_user = get_current_user(request, db)

    if current_user.role == "admin":
        return current_user

    from .models.project import Project
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' not found.",
        )

    owner_id = getattr(project, "user_id", None) or getattr(project, "owner_id", None) or (project.master_json or {}).get("owner_id") or (project.master_json or {}).get("user_id")
    client_id = getattr(project, "client_id", None) or (project.master_json or {}).get("client_id") or (project.master_json or {}).get("client_user_id") or (project.master_json or {}).get("client_email")
    allowed_users = (project.master_json or {}).get("allowed_users", [])

    u_id = getattr(current_user, "id", None)
    u_email = getattr(current_user, "email", None)

    is_owner = bool(owner_id and (owner_id == u_id or (u_email and owner_id == u_email)))
    is_client = bool(client_id and (client_id == u_id or (u_email and client_id == u_email)))
    is_allowed = bool((u_id and u_id in allowed_users) or (u_email and u_email in allowed_users))

    # If project specifies owners, clients, or allowed users, user must be one of them
    if owner_id or client_id or allowed_users:
        if not (is_owner or is_client or is_allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You are not authorized to access or export this project.",
            )
    else:
        # Unowned project: non-admin access is forbidden
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Unassigned project. Only project owners, assigned clients, or administrators may access this project.",
        )

    return current_user

