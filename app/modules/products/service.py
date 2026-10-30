"""FR1 - Quản lý danh mục Sản phẩm (có khóa/mở khóa)."""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.utils import first, rows, to_decimal


def list_products(db: Session) -> list:
    return rows(db.execute(text("""
        SELECT p.id, p.sku, p.barcode, p.product_name, p.unit, p.unit_weight_kg,
               p.min_safety_stock, p.max_safety_stock, p.is_active,
               COALESCE(t.on_hand, 0) AS total_on_hand, COALESCE(t.available, 0) AS total_available
        FROM products p
        LEFT JOIN (SELECT product_id, SUM(quantity_on_hand) AS on_hand, SUM(quantity_available) AS available
                   FROM inventory_stocks GROUP BY product_id) t ON t.product_id = p.id
        ORDER BY p.sku
    """)))


def ensure_active(db: Session, product_id: int) -> dict:
    """Dùng khi lập chứng từ: sản phẩm phải tồn tại và đang hoạt động."""
    p = first(db.execute(text("SELECT id, sku, product_name, unit, unit_weight_kg, is_active FROM products WHERE id = :id"),
                         {"id": product_id}))
    if not p:
        raise HTTPException(404, "Sản phẩm không tồn tại!")
    if not p["is_active"]:
        raise HTTPException(400, f"Sản phẩm {p['sku']} đang bị khóa, không thể lập phiếu!")
    return p


def create_product(db: Session, user: dict, data: dict) -> dict:
    if data["max_safety_stock"] < data["min_safety_stock"]:
        raise HTTPException(400, "Ngưỡng tồn tối đa phải lớn hơn hoặc bằng ngưỡng tối thiểu!")
    sku, barcode = data["sku"].strip(), data["barcode"].strip()
    dup = db.execute(text("SELECT 1 FROM products WHERE sku = :s OR barcode = :b"), {"s": sku, "b": barcode}).first()
    if dup:
        raise HTTPException(400, "Mã SKU hoặc Mã vạch đã tồn tại!")
    pid = db.execute(text("""
        INSERT INTO products (sku, barcode, product_name, unit, unit_weight_kg, min_safety_stock,
                              max_safety_stock, approval_status, created_by, approved_by, is_active)
        VALUES (:sku, :bc, :n, :u, :w, :mn, :mx, 'approved', :uid, :uid, TRUE) RETURNING id
    """), {"sku": sku, "bc": barcode, "n": data["product_name"].strip(), "u": data["unit"].strip(),
           "w": data["unit_weight_kg"], "mn": data["min_safety_stock"], "mx": data["max_safety_stock"],
           "uid": user["id"]}).scalar()
    db.commit()
    return {"message": f"Đã lưu sản phẩm {sku}!", "id": pid}


def update_product(db: Session, product_id: int, data: dict) -> dict:
    cur = first(db.execute(text("SELECT * FROM products WHERE id = :id FOR UPDATE"), {"id": product_id}))
    if not cur:
        raise HTTPException(404, "Sản phẩm không tồn tại!")
    if not data:
        raise HTTPException(400, "Không có thông tin nào để cập nhật!")

    new_min = data.get("min_safety_stock", cur["min_safety_stock"])
    new_max = data.get("max_safety_stock", cur["max_safety_stock"])
    if new_max < new_min:
        raise HTTPException(400, "Ngưỡng tồn tối đa phải lớn hơn hoặc bằng ngưỡng tối thiểu!")

    # SRS 3.1: chỉ sửa trọng lượng khi không còn tồn kho (tránh sai lệch tải trọng Bin - BR04)
    if "unit_weight_kg" in data and to_decimal(data["unit_weight_kg"]) != to_decimal(cur["unit_weight_kg"]):
        on_hand = db.execute(text("SELECT COALESCE(SUM(quantity_on_hand), 0) FROM inventory_stocks WHERE product_id = :id"),
                             {"id": product_id}).scalar()
        pending = db.execute(text("""
            SELECT COUNT(*) FROM putaway_tasks pt JOIN goods_receipt_details grd ON pt.receipt_detail_id = grd.id
            WHERE grd.product_id = :id AND pt.status = 'pending'
        """), {"id": product_id}).scalar()
        if (on_hand or 0) > 0 or (pending or 0) > 0:
            raise HTTPException(400, "Sản phẩm đang có tồn kho hoặc hàng chờ xếp kệ nên không được đổi trọng lượng đơn vị (sẽ làm sai tải trọng Bin - BR04)!")

    allowed = {"product_name", "unit", "unit_weight_kg", "min_safety_stock", "max_safety_stock", "is_active"}
    fields = {k: v for k, v in data.items() if k in allowed}
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    db.execute(text(f"UPDATE products SET {sets} WHERE id = :id"), {**fields, "id": product_id})
    db.commit()
    if fields.keys() == {"is_active"}:
        return {"message": f"Đã {'mở khóa' if fields['is_active'] else 'khóa'} sản phẩm {cur['sku']}!"}
    return {"message": f"Đã cập nhật sản phẩm {cur['sku']}!"}