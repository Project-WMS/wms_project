from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_staff
from app.modules.outbound import service
from app.modules.outbound.schemas import IssueCreate

router = APIRouter(tags=["Xuất kho FEFO"])


@router.get("/outbound")
def list_issues(limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0),
                status: Optional[str] = None, q: Optional[str] = None,
                user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.list_issues(db, limit=limit, offset=offset, status=status, q=q)


@router.post("/outbound")
def create_issue(req: IssueCreate, user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.create_issue(db, user, req.customer_id, [i.model_dump() for i in req.items])


@router.delete("/outbound/{issue_id}")
def cancel_issue(issue_id: int, user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.cancel_issue(db, issue_id)
