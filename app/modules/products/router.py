from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_staff
from app.modules.products import service
from app.modules.products.schemas import ProductCreate, ProductUpdate

router = APIRouter(tags=["Sản phẩm"])


@router.get("/products")
def list_products(user=Depends(require_staff), db: Session = Depends(get_db)):
    return {"items": service.list_products(db)}


@router.post("/products")
def create_product(req: ProductCreate, user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.create_product(db, user, req.model_dump())


@router.put("/products/{product_id}")
def update_product(product_id: int, req: ProductUpdate, user=Depends(require_staff), db: Session = Depends(get_db)):
    return service.update_product(db, product_id, req.model_dump(exclude_unset=True))
