from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_staff
from app.modules.inbound import service
from app.modules.inbound.schemas import ReceiptCreate

router = APIRouter(tags=["Nhập kho"])


@router.get("/inbound")
def list_receipts(limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0),
                  status: Optional[str] = None, q: Optional[str] = None,
                  user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.list_receipts(db, limit=limit, offset=offset, status=status, q=q)


@router.post("/inbound")
def create_receipt(req: ReceiptCreate, user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.create_receipt(db, user, req.supplier_id, [i.model_dump() for i in req.items])


@router.delete("/inbound/{receipt_id}")
def cancel_receipt(receipt_id: int, user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.cancel_receipt(db, receipt_id)
