from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_staff
from app.modules.counts import service
from app.modules.counts.schemas import CountCreate, CountSave

router = APIRouter(tags=["Kiểm kê"])


@router.get("/counts")
def list_counts(limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0), status: Optional[str] = None,
                user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.list_counts(db, limit=limit, offset=offset, status=status)


@router.post("/counts")
def create_count(req: CountCreate, user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.create_count(db, user, req.location_id)


@router.put("/counts/{count_id}")
def save_count(count_id: int, req: CountSave, user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.save_count(db, user, count_id, [ln.model_dump() for ln in req.lines])


@router.post("/counts/{count_id}/approve")
def approve_count(count_id: int, user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.approve_count(db, user, count_id)


@router.delete("/counts/{count_id}")
def delete_count(count_id: int, user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.delete_count(db, count_id)
