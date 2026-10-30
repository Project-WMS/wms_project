"""FR1 - Danh mục Ô kệ (Bin) + BR04 kiểm soát tải trọng."""
import re
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.utils import first, rows, to_decimal

STATUSES = ("active", "maintenance", "locked")
TOKEN_RE = re.compile(r"^[A-Z0-9]{1,10}$")


def list_locations(db: Session) -> list:
    items = rows(db.execute(text("""
        SELECT l.id, l.warehouse_id, l.location_code, l.zone, l.aisle, l.rack, l.shelf_level, l.bin,
               l.max_capacity_kg, l.status,
               COALESCE(SUM(s.quantity_on_hand * p.unit_weight_kg), 0) AS current_weight_kg,
               COUNT(CASE WHEN s.quantity_on_hand > 0 THEN 1 END) AS lot_count
        FROM locations l
        LEFT JOIN inventory_stocks s ON s.location_id = l.id
        LEFT JOIN products p ON s.product_id = p.id
        GROUP BY l.id
        ORDER BY l.location_code
    """)))
    pending = {r["location_id"]: r["w"] for r in rows(db.execute(text("""
        SELECT pt.to_location_id AS location_id, SUM(pt.assigned_qty * p.unit_weight_kg) AS w
        FROM putaway_tasks pt
        JOIN goods_receipt_details grd ON pt.receipt_detail_id = grd.id
        JOIN products p ON grd.product_id = p.id
        WHERE pt.status = 'pending' GROUP BY pt.to_location_id
    """)))}
    for it in items:
        it["pending_weight_kg"] = pending.get(it["id"], 0)
    return items


def check_bin_capacity(db: Session, location_id: int, add_qty: int, product_id: int,
                       include_pending_putaway: bool = False) -> None:
    """BR04: Bin phải 'active' và tổng (SL tồn * trọng lượng đơn vị) không vượt max_capacity_kg.
    include_pending_putaway=True: tính cả hàng đã chỉ định vào Bin nhưng công nhân chưa xếp."""
    loc = first(db.execute(text("SELECT location_code, max_capacity_kg, status FROM locations WHERE id = :id"),
                           {"id": location_id}))
    if not loc:
        raise HTTPException(404, "Ô Bin không tồn tại!")
    if loc["status"] != "active":
        raise HTTPException(400, f"Ô Bin {loc['location_code']} đang ở trạng thái '{loc['status']}', không thể nhận hàng!")

    unit_w = db.execute(text("SELECT unit_weight_kg FROM products WHERE id = :id"), {"id": product_id}).scalar()
    if unit_w is None:
        raise HTTPException(404, "Sản phẩm không tồn tại!")

    current = db.execute(text("""
        SELECT COALESCE(SUM(s.quantity_on_hand * p.unit_weight_kg), 0)
        FROM inventory_stocks s JOIN products p ON s.product_id = p.id
        WHERE s.location_id = :loc
    """), {"loc": location_id}).scalar()

    pending = Decimal(0)
    if include_pending_putaway:
        pending = to_decimal(db.execute(text("""
            SELECT COALESCE(SUM(pt.assigned_qty * p.unit_weight_kg), 0)
            FROM putaway_tasks pt
            JOIN goods_receipt_details grd ON pt.receipt_detail_id = grd.id
            JOIN products p ON grd.product_id = p.id
            WHERE pt.to_location_id = :loc AND pt.status = 'pending'
        """), {"loc": location_id}).scalar())

    new_total = to_decimal(current) + pending + Decimal(add_qty) * to_decimal(unit_w)
    max_cap = to_decimal(loc["max_capacity_kg"])
    if new_total > max_cap:
        raise HTTPException(400, f"Vượt tải trọng ô {loc['location_code']}! Sau khi thêm: {new_total:.2f} kg "
                                 f"> tối đa {max_cap:.2f} kg (BR04).")


def create_location(db: Session, data: dict) -> dict:
    if data["status"] not in STATUSES:
        raise HTTPException(400, "Trạng thái ô kệ không hợp lệ!")
    parts = {"Khu": data["zone"], "Dãy": data["aisle"], "Kệ": data["rack"], "Tầng": data["shelf_level"], "Ô": data["bin"]}
    clean = {}
    for label, v in parts.items():
        v = v.strip().upper()
        if not TOKEN_RE.match(v):
            raise HTTPException(400, f"{label} chỉ gồm chữ/số không dấu (tối đa 10 ký tự), ví dụ Z01, A01, R01, L1, B01!")
        clean[label] = v
    wh_code = db.execute(text("SELECT warehouse_code FROM warehouses WHERE id = :id"), {"id": data["warehouse_id"]}).scalar()
    if not wh_code:
        raise HTTPException(404, "Kho không tồn tại!")
    code = "-".join([wh_code, clean["Khu"], clean["Dãy"], clean["Kệ"], clean["Tầng"], clean["Ô"]])  # BR01
    if db.execute(text("SELECT 1 FROM locations WHERE location_code = :c"), {"c": code}).first():
        raise HTTPException(400, f"Mã ô kệ {code} đã tồn tại!")
    lid = db.execute(text("""
        INSERT INTO locations (warehouse_id, location_code, zone, aisle, rack, shelf_level, bin, max_capacity_kg, status)
        VALUES (:wh, :code, :z, :a, :r, :l, :b, :cap, :st) RETURNING id
    """), {"wh": data["warehouse_id"], "code": code, "z": clean["Khu"], "a": clean["Dãy"], "r": clean["Kệ"],
           "l": clean["Tầng"], "b": clean["Ô"], "cap": data["max_capacity_kg"], "st": data["status"]}).scalar()
    db.commit()
    return {"message": f"Đã tạo ô kệ {code} và sinh mã QR tương ứng!", "id": lid}


def update_location(db: Session, location_id: int, data: dict) -> dict:
    loc = first(db.execute(text("SELECT id, location_code FROM locations WHERE id = :id FOR UPDATE"), {"id": location_id}))
    if not loc:
        raise HTTPException(404, "Ô kệ không tồn tại!")
    fields = {k: v for k, v in data.items() if k in ("max_capacity_kg", "status") and v is not None}
    if not fields:
        raise HTTPException(400, "Không có thông tin nào để cập nhật!")
    if "status" in fields and fields["status"] not in STATUSES:
        raise HTTPException(400, "Trạng thái ô kệ không hợp lệ!")
    if "max_capacity_kg" in fields:
        cur_w = db.execute(text("""
            SELECT COALESCE(SUM(s.quantity_on_hand * p.unit_weight_kg), 0)
            FROM inventory_stocks s JOIN products p ON s.product_id = p.id WHERE s.location_id = :id
        """), {"id": location_id}).scalar()
        if to_decimal(fields["max_capacity_kg"]) < to_decimal(cur_w):
            raise HTTPException(400, f"Không thể giảm sức chứa xuống dưới tải trọng hiện tại của ô ({to_decimal(cur_w):.2f} kg)!")
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    db.execute(text(f"UPDATE locations SET {sets} WHERE id = :id"), {**fields, "id": location_id})
    db.commit()
    return {"message": f"Đã cập nhật ô kệ {loc['location_code']}!"}
