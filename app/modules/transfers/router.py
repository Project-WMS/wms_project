from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_staff
from app.modules.transfers import service
from app.modules.transfers.schemas import TransferCreate

router = APIRouter(tags=["Điều chuyển"])


@router.get("/transfers")
def list_transfers(limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0),
                   user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.list_transfers(db, limit=limit, offset=offset)


@router.post("/transfers")
def create_transfer(req: TransferCreate, user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.create_transfer(db, user, [i.model_dump() for i in req.items])
