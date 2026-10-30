from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_any
from app.modules.tasks import service
from app.modules.tasks.schemas import ScanConfirmRequest

router = APIRouter(prefix="/mobile", tags=["Mobile - Quét QR"])


@router.get("/tasks")
def list_tasks(user=Depends(require_any), db: Session = Depends(get_db)):
    return service.list_tasks(db)


@router.post("/putaway/confirm")
def confirm_putaway(req: ScanConfirmRequest, user=Depends(require_any), db: Session = Depends(get_db)):
    return service.confirm_putaway(db, user, task_id=req.task_id, scanned_qr=req.scanned_qr, actual_qty=req.actual_qty)


@router.post("/picking/confirm")
def confirm_picking(req: ScanConfirmRequest, user=Depends(require_any), db: Session = Depends(get_db)):
    return service.confirm_picking(db, user, task_id=req.task_id, scanned_qr=req.scanned_qr,
                                   scanned_barcode=req.scanned_barcode or "", actual_qty=req.actual_qty)
