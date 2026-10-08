from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict

from ..database import get_db
from ..dependencies import require_admin
from ..models.user import User
from ..models.site_setting import SiteSetting

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("/public")
@router.get("")
def get_settings(db: Session = Depends(get_db)):
    settings_list = db.query(SiteSetting).all()
    return {s.setting_key: s.setting_value for s in settings_list}


@router.put("/admin")
@router.put("")
def update_settings(
    data: Dict[str, str],
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    for key, value in data.items():
        setting = db.query(SiteSetting).filter(SiteSetting.setting_key == key).first()
        if setting:
            setting.setting_value = value
        else:
            db.add(SiteSetting(setting_key=key, setting_value=value))
    db.commit()
    return {"message": "Settings updated"}
