from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_staff
from app.modules.lookups import service

router = APIRouter(tags=["Tra cứu"])


@router.get("/lookups")
def get_lookups(user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.get_lookups(db)
