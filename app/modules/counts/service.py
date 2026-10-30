"""FR4 - Kiểm kê (STOCK_COUNTS): lập phiếu theo Ô kệ -> nhập số đếm thực tế -> duyệt cân bằng (BR05)."""
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import DEFAULT_WAREHOUSE_ID
from app.core.utils import first, make_code, placeholders, rows
from app.modules.locations.service import check_bin_capacity
from app.modules.stocks.service import add_ledger

OPEN_STATUSES = ("draft", "counting")


def create_count(db: Session, user: dict, location_id: int) -> dict:
    loc = first(db.execute(text("SELECT id, location_code FROM locations WHERE id = :id"), {"id": location_id}))
    if not loc:
        raise HTTPException(404, "Ô kệ không tồn tại!")
    stocks = rows(db.execute(text("""
        SELECT product_id, batch_no, quantity_on_hand FROM inventory_stocks
        WHERE location_id = :id AND quantity_on_hand > 0 ORDER BY expiry_date, id
    """), {"id": location_id}))
    if not stocks:
        raise HTTPException(400, f"Ô kệ {loc['location_code']} hiện không có hàng để kiểm kê!")
    open_sheet = first(db.execute(text("""
        SELECT sc.count_code FROM stock_counts sc JOIN stock_count_details d ON d.count_id = sc.id
        WHERE d.location_id = :id AND sc.status IN ('draft', 'counting') LIMIT 1
    """), {"id": location_id}))
    if open_sheet:
        raise HTTPException(400, f"Ô kệ {loc['location_code']} đang có phiếu kiểm kê {open_sheet['count_code']} chưa duyệt!")

    code = make_code("PKK")
    count_id = db.execute(text("""
        INSERT INTO stock_counts (count_code, warehouse_id, created_by, status) VALUES (:c, :wh, :u, 'draft') RETURNING id
    """), {"c": code, "wh": DEFAULT_WAREHOUSE_ID, "u": user["id"]}).scalar()
    for s in stocks:  # chụp số liệu hệ thống (system_qty); số đếm thực tế mặc định = số hệ thống, người kiểm kê sửa lại
        db.execute(text("""
            INSERT INTO stock_count_details (count_id, location_id, product_id, batch_no, system_qty, actual_qty)
            VALUES (:c, :l, :p, :b, :q, :q)
        """), {"c": count_id, "l": location_id, "p": s["product_id"], "b": s["batch_no"], "q": s["quantity_on_hand"]})
    db.commit()
    return {"message": f"Đã lập phiếu kiểm kê {code} cho ô {loc['location_code']} ({len(stocks)} lô hàng).",
            "id": count_id, "count_code": code}


def _lock_open_count(db: Session, count_id: int) -> dict:
    c = first(db.execute(text("SELECT id, count_code, status FROM stock_counts WHERE id = :id FOR UPDATE"),
                         {"id": count_id}))
    if not c:
        raise HTTPException(404, "Phiếu kiểm kê không tồn tại!")
    if c["status"] not in OPEN_STATUSES:
        raise HTTPException(400, f"Phiếu {c['count_code']} đã được duyệt cân bằng, không thể thay đổi!")
    return c


def save_count(db: Session, user: dict, count_id: int, lines: list) -> dict:
    c = _lock_open_count(db, count_id)
    for ln in lines:
        res = db.execute(text("""
            UPDATE stock_count_details SET actual_qty = :a, counted_by = :u WHERE id = :d AND count_id = :c
        """), {"a": ln["actual_qty"], "u": user["id"], "d": ln["detail_id"], "c": count_id})
        if res.rowcount == 0:
            raise HTTPException(400, "Có dòng kiểm kê không thuộc phiếu này!")
    db.execute(text("UPDATE stock_counts SET status = 'counting' WHERE id = :id"), {"id": count_id})
    db.commit()
    return {"message": f"Đã lưu số liệu kiểm kê của phiếu {c['count_code']}. Chờ duyệt cân bằng kho."}


def approve_count(db: Session, user: dict, count_id: int) -> dict:
    """BR05: tồn kho vật lý chỉ thay đổi khi Quản lý duyệt cân bằng."""
    c = _lock_open_count(db, count_id)
    details = rows(db.execute(text("""
        SELECT id, location_id, product_id, batch_no, actual_qty FROM stock_count_details WHERE count_id = :id ORDER BY id
    """), {"id": count_id}))
    adjusted = 0
    for d in details:
        s = first(db.execute(text("""
            SELECT id, quantity_on_hand, quantity_allocated FROM inventory_stocks
            WHERE location_id = :l AND product_id = :p AND batch_no = :b
            FOR UPDATE
        """), {"l": d["location_id"], "p": d["product_id"], "b": d["batch_no"]}))
        if not s:
            raise HTTPException(400, f"Lô {d['batch_no']} không còn tồn tại trong ô kệ, hãy xóa phiếu và lập lại!")
        current, actual = s["quantity_on_hand"], d["actual_qty"]
        # BR02: On_hand >= Allocated
        if actual < s["quantity_allocated"]:
            raise HTTPException(400, f"Lô {d['batch_no']}: số thực đếm ({actual}) thấp hơn số đang giữ chỗ "
                                     f"({s['quantity_allocated']}). Hãy xử lý các lệnh lấy hàng đang chờ trước khi cân bằng kho!")
        delta = actual - current
        if delta > 0:  # BR04: kiểm kê thừa hàng cũng phải kiểm tra tải trọng
            check_bin_capacity(db, d["location_id"], delta, d["product_id"])
        # Cập nhật lại số hệ thống tại thời điểm duyệt để chênh lệch (variance_qty) phản ánh đúng thực tế
        db.execute(text("UPDATE stock_count_details SET system_qty = :q WHERE id = :id"), {"q": current, "id": d["id"]})
        if delta != 0:
            db.execute(text("UPDATE inventory_stocks SET quantity_on_hand = :q WHERE id = :id"),
                       {"q": actual, "id": s["id"]})
            add_ledger(db, ttype="COUNT_ADJUST", ref=c["count_code"], task_id=d["id"], product_id=d["product_id"],
                       batch_no=d["batch_no"], from_loc=None, to_loc=d["location_id"],
                       change=delta, balance_after=actual, user_id=user["id"])
            adjusted += 1
    db.execute(text("UPDATE stock_counts SET status = 'reconciled', approved_by = :u WHERE id = :id"),
               {"u": user["id"], "id": count_id})
    db.commit()
    if adjusted:
        return {"message": f"Đã duyệt cân bằng {c['count_code']}: điều chỉnh {adjusted}/{len(details)} lô có chênh lệch."}
    return {"message": f"Đã duyệt {c['count_code']}: số liệu khớp hoàn toàn, không có chênh lệch."}


def delete_count(db: Session, count_id: int) -> dict:
    c = _lock_open_count(db, count_id)
    db.execute(text("DELETE FROM stock_counts WHERE id = :id"), {"id": count_id})
    db.commit()
    return {"message": f"Đã xóa phiếu kiểm kê {c['count_code']}."}


def list_counts(db: Session, *, limit: int = 20, offset: int = 0, status: str = None) -> dict:
    params = {}
    cond = ""
    if status:
        cond = "WHERE sc.status = :st"
        params["st"] = status
    total = db.execute(text(f"SELECT COUNT(*) FROM stock_counts sc {cond}"), params).scalar()
    counts = rows(db.execute(text(f"""
        SELECT sc.id, sc.count_code, sc.status, sc.created_at, u.full_name AS created_by_name,
               a.full_name AS approved_by_name
        FROM stock_counts sc JOIN users u ON sc.created_by = u.id LEFT JOIN users a ON sc.approved_by = a.id
        {cond} ORDER BY sc.id DESC LIMIT :limit OFFSET :offset
    """), {**params, "limit": limit, "offset": offset}))
    if counts:
        clause, id_params = placeholders("cid", [c["id"] for c in counts])
        lines = rows(db.execute(text(f"""
            SELECT d.id AS detail_id, d.count_id, l.location_code, p.sku, p.product_name, p.unit, d.batch_no,
                   d.system_qty, d.actual_qty, d.variance_qty
            FROM stock_count_details d
            JOIN locations l ON d.location_id = l.id
            JOIN products p ON d.product_id = p.id
            WHERE d.count_id IN ({clause}) ORDER BY d.id
        """), id_params))
        by_c = {}
        for ln in lines:
            by_c.setdefault(ln["count_id"], []).append(ln)
        for c in counts:
            c["items"] = by_c.get(c["id"], [])
            c["location_code"] = c["items"][0]["location_code"] if c["items"] else None
            c["variance_total"] = sum(i["variance_qty"] for i in c["items"])
    return {"items": counts, "total": total or 0}
