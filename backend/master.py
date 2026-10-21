"""FR1 - Quản lý danh mục động: Sản phẩm, Ô kệ (Bin), Đối tác. Chỉ Admin/Manager được ghi."""
import re
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth import require_staff
from backend.database import get_db

router = APIRouter(prefix="/api")

TOKEN_RE = re.compile(r"^[A-Z0-9]{1,10}$")


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=50)
    barcode: str = Field(min_length=1, max_length=50)
    product_name: str = Field(min_length=1, max_length=200)
    unit: str = Field(min_length=1, max_length=20)
    unit_weight_kg: Decimal = Field(gt=0, le=100000)
    min_safety_stock: int = Field(ge=0, default=10)
    max_safety_stock: int = Field(ge=0, default=1000)


class ProductUpdate(BaseModel):
    product_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=20)
    unit_weight_kg: Optional[Decimal] = Field(default=None, gt=0, le=100000)
    min_safety_stock: Optional[int] = Field(default=None, ge=0)
    max_safety_stock: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


class LocationCreate(BaseModel):
    warehouse_id: int = 1
    zone: str
    aisle: str
    rack: str
    shelf_level: str
    bin: str
    max_capacity_kg: Decimal = Field(gt=0, le=1000000)
    status: str = "active"


class LocationUpdate(BaseModel):
    max_capacity_kg: Optional[Decimal] = Field(default=None, gt=0, le=1000000)
    status: Optional[str] = None


class PartnerCreate(BaseModel):
    partner_code: str = Field(min_length=1, max_length=30)
    partner_name: str = Field(min_length=1, max_length=150)
    type: str
    phone: Optional[str] = Field(default=None, max_length=20)
    address: Optional[str] = None


def _dup(e: IntegrityError, msg: str):
    raise HTTPException(status_code=400, detail=msg) from e


# ---------------- Sản phẩm ----------------
@router.post("/products")
def create_product(req: ProductCreate, user=Depends(require_staff), db: Session = Depends(get_db)):
    if req.max_safety_stock < req.min_safety_stock:
        raise HTTPException(status_code=400, detail="Ngưỡng tồn tối đa phải lớn hơn hoặc bằng ngưỡng tối thiểu!")
    try:
        pid = db.execute(text("""
            INSERT INTO products (sku, barcode, product_name, unit, unit_weight_kg, min_safety_stock,
                                  max_safety_stock, approval_status, created_by, approved_by, is_active)
            VALUES (:sku, :bc, :n, :u, :w, :mn, :mx, 'approved', :uid, :uid, TRUE) RETURNING id
        """), {"sku": req.sku.strip(), "bc": req.barcode.strip(), "n": req.product_name.strip(),
               "u": req.unit.strip(), "w": req.unit_weight_kg, "mn": req.min_safety_stock,
               "mx": req.max_safety_stock, "uid": user["id"]}).scalar()
        db.commit()
    except IntegrityError as e:
        db.rollback()
        _dup(e, "Mã SKU hoặc Mã vạch đã tồn tại!")
    return {"message": f"Đã lưu sản phẩm {req.sku.strip()}!", "id": pid}


@router.put("/products/{product_id}")
def update_product(product_id: int, req: ProductUpdate, user=Depends(require_staff), db: Session = Depends(get_db)):
    cur = db.execute(text("SELECT * FROM products WHERE id = :id FOR UPDATE"), {"id": product_id}).mappings().first()
    if not cur:
        raise HTTPException(status_code=404, detail="Sản phẩm không tồn tại!")
    data = req.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Không có thông tin nào để cập nhật!")

    new_min = data.get("min_safety_stock", cur["min_safety_stock"])
    new_max = data.get("max_safety_stock", cur["max_safety_stock"])
    if new_max < new_min:
        raise HTTPException(status_code=400, detail="Ngưỡng tồn tối đa phải lớn hơn hoặc bằng ngưỡng tối thiểu!")

    if "unit_weight_kg" in data and Decimal(data["unit_weight_kg"] or 0) != cur["unit_weight_kg"]:
        on_hand = db.execute(text("SELECT COALESCE(SUM(quantity_on_hand),0) FROM inventory_stocks WHERE product_id = :id"),
                             {"id": product_id}).scalar()
        if (on_hand or 0) > 0:
            raise HTTPException(status_code=400,
                                detail="Sản phẩm đang có tồn kho nên không được đổi trọng lượng đơn vị (sẽ làm sai tải trọng Bin - BR04)!")

    sets = ", ".join(f"{k} = :{k}" for k in data)
    db.execute(text(f"UPDATE products SET {sets} WHERE id = :id"), {**data, "id": product_id})
    db.commit()
    return {"message": f"Đã cập nhật sản phẩm {cur['sku']}!"}


# ---------------- Ô kệ (Bin) ----------------
@router.post("/locations")
def create_location(req: LocationCreate, user=Depends(require_staff), db: Session = Depends(get_db)):
    if req.status not in ("active", "maintenance", "locked"):
        raise HTTPException(status_code=400, detail="Trạng thái ô kệ không hợp lệ!")
    parts = {"Khu": req.zone, "Dãy": req.aisle, "Kệ": req.rack, "Tầng": req.shelf_level, "Ô": req.bin}
    clean = {}
    for label, v in parts.items():
        v = v.strip().upper()
        if not TOKEN_RE.match(v):
            raise HTTPException(status_code=400, detail=f"{label} chỉ gồm chữ/số không dấu (tối đa 10 ký tự), ví dụ Z01, A01, R01, L1, B01!")
        clean[label] = v
    wh_code = db.execute(text("SELECT warehouse_code FROM warehouses WHERE id = :id"), {"id": req.warehouse_id}).scalar()
    if not wh_code:
        raise HTTPException(status_code=404, detail="Kho không tồn tại!")
    code = "-".join([wh_code, clean["Khu"], clean["Dãy"], clean["Kệ"], clean["Tầng"], clean["Ô"]])
    try:
        lid = db.execute(text("""
            INSERT INTO locations (warehouse_id, location_code, zone, aisle, rack, shelf_level, bin, max_capacity_kg, status)
            VALUES (:wh, :code, :z, :a, :r, :l, :b, :cap, :st) RETURNING id
        """), {"wh": req.warehouse_id, "code": code, "z": clean["Khu"], "a": clean["Dãy"], "r": clean["Kệ"],
               "l": clean["Tầng"], "b": clean["Ô"], "cap": req.max_capacity_kg, "st": req.status}).scalar()
        db.commit()
    except IntegrityError as e:
        db.rollback()
        _dup(e, f"Mã ô kệ {code} đã tồn tại!")
    return {"message": f"Đã tạo ô kệ {code} và sinh mã QR tương ứng!", "id": lid}


@router.put("/locations/{location_id}")
def update_location(location_id: int, req: LocationUpdate, user=Depends(require_staff), db: Session = Depends(get_db)):
    loc = db.execute(text("SELECT id, location_code FROM locations WHERE id = :id FOR UPDATE"),
                     {"id": location_id}).mappings().first()
    if not loc:
        raise HTTPException(status_code=404, detail="Ô kệ không tồn tại!")
    data = req.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Không có thông tin nào để cập nhật!")
    if "status" in data and data["status"] not in ("active", "maintenance", "locked"):
        raise HTTPException(status_code=400, detail="Trạng thái ô kệ không hợp lệ!")
    if "max_capacity_kg" in data:
        cur_w = db.execute(text("""
            SELECT COALESCE(SUM(s.quantity_on_hand * p.unit_weight_kg), 0)
            FROM inventory_stocks s JOIN products p ON s.product_id = p.id WHERE s.location_id = :id
        """), {"id": location_id}).scalar()
        if Decimal(data["max_capacity_kg"] or 0) < Decimal(cur_w or 0):
            raise HTTPException(status_code=400,
                                detail=f"Không thể giảm sức chứa xuống dưới tải trọng hiện tại của ô ({cur_w} kg)!")
    sets = ", ".join(f"{k} = :{k}" for k in data)
    db.execute(text(f"UPDATE locations SET {sets} WHERE id = :id"), {**data, "id": location_id})
    db.commit()
    return {"message": f"Đã cập nhật ô kệ {loc['location_code']}!"}


# ---------------- Đối tác ----------------
@router.get("/partners")
def list_partners(user=Depends(require_staff), db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT id, partner_code, partner_name, type, phone, address FROM partners ORDER BY type, partner_name")).mappings().all()
    return {"partners": [dict(r) for r in rows]}


@router.post("/partners")
def create_partner(req: PartnerCreate, user=Depends(require_staff), db: Session = Depends(get_db)):
    if req.type not in ("supplier", "customer"):
        raise HTTPException(status_code=400, detail="Loại đối tác phải là supplier (Nhà cung cấp) hoặc customer (Khách hàng)!")
    try:
        pid = db.execute(text("""
            INSERT INTO partners (partner_code, partner_name, type, phone, address)
            VALUES (:c, :n, :t, :p, :a) RETURNING id
        """), {"c": req.partner_code.strip().upper(), "n": req.partner_name.strip(), "t": req.type,
               "p": (req.phone or "").strip() or None, "a": (req.address or "").strip() or None}).scalar()
        db.commit()
    except IntegrityError as e:
        db.rollback()
        _dup(e, "Mã đối tác đã tồn tại!")
    return {"message": f"Đã thêm đối tác {req.partner_name.strip()}!", "id": pid}
