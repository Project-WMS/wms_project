from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_staff
from app.modules.partners import service
from app.modules.partners.schemas import PartnerCreate, PartnerUpdate

router = APIRouter(tags=["Đối tác"])


@router.get("/partners")
def list_partners(type: Optional[str] = None, user=Depends(require_staff), db: Session = Depends(get_db)):
    return {"items": service.list_partners(db, type)}


@router.post("/partners")
def create_partner(req: PartnerCreate, user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.create_partner(db, req.model_dump())


@router.put("/partners/{partner_id}")
def update_partner(partner_id: int, req: PartnerUpdate, user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.update_partner(db, partner_id, req.model_dump(exclude_unset=True))
