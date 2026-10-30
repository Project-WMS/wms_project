from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_staff
from app.modules.dashboard import service

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard")
def get_dashboard(user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.get_dashboard(db, user)
