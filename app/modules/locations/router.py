from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_staff
from app.modules.locations import service
from app.modules.locations.schemas import LocationCreate, LocationUpdate

router = APIRouter(tags=["Ô kệ (Bin)"])


@router.get("/locations")
def list_locations(user=Depends(require_staff), db: Session = Depends(get_db)):
    return {"items": service.list_locations(db)}


@router.post("/locations")
def create_location(req: LocationCreate, user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.create_location(db, req.model_dump())


@router.put("/locations/{location_id}")
def update_location(location_id: int, req: LocationUpdate, user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.update_location(db, location_id, req.model_dump(exclude_unset=True))
