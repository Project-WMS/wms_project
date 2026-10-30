from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_staff
from app.modules.stocks import service

router = APIRouter(tags=["Tồn kho & Thẻ kho"])


@router.get("/stocks")
def list_stocks(q: Optional[str] = None, product_id: Optional[int] = None, location_id: Optional[int] = None,
                expiry: Optional[str] = None, user=Depends(require_staff), db: Session = Depends(get_db)):
    return {"items": service.list_stocks(db, q, product_id, location_id, expiry)}


@router.get("/ledger")
def list_ledger(limit: int = Query(20, ge=1, le=2000), offset: int = Query(0, ge=0),
                product_id: Optional[int] = None, transaction_type: Optional[str] = None,
                date_from: Optional[date] = None, date_to: Optional[date] = None, q: Optional[str] = None,
                user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.list_ledger(db, limit=limit, offset=offset, product_id=product_id, ttype=transaction_type,
                               date_from=date_from, date_to=date_to, q=q)
