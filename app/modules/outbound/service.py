"""FR3 - Phiếu xuất kho: duyệt đơn -> tự chạy FEFO/FIFO khóa giữ chỗ (allocated) -> sinh lệnh lấy hàng."""
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import DEFAULT_WAREHOUSE_ID
from app.core.utils import make_code, placeholders, rows, today
from app.modules.partners.service import ensure_partner
from app.modules.products.service import ensure_active


def create_issue(db: Session, user: dict, customer_id: int, items: list) -> dict:
    ensure_partner(db, customer_id, "customer")
    if not items:
        raise HTTPException(400, "Phiếu xuất cần có ít nhất 1 dòng hàng!")
    t = today()
    code = make_code("PXK")
    issue_id = db.execute(text("""
        INSERT INTO goods_issues (issue_code, customer_id, warehouse_id, created_by, approved_by, status, approved_at)
        VALUES (:code, :cus, :wh, :u, :u, 'allocated', CURRENT_TIMESTAMP) RETURNING id
    """), {"code": code, "cus": customer_id, "wh": DEFAULT_WAREHOUSE_ID, "u": user["id"]}).scalar()

    task_count = 0
    for line_no, it in enumerate(items, 1):
        prod = ensure_active(db, it["product_id"])
        # BR03: Ưu tiên 1 FEFO (expiry_date ASC), ưu tiên 2 FIFO (created_at ASC); bỏ qua lô đã hết hạn và Bin không active.
        # FOR UPDATE khóa các dòng tồn kho để 2 đơn xuất duyệt cùng lúc không giữ chỗ trùng (NFR2).
        batches = rows(db.execute(text("""
            SELECT s.id, s.location_id, s.batch_no, s.expiry_date, s.quantity_available
            FROM inventory_stocks s
            JOIN locations l ON s.location_id = l.id
            WHERE s.product_id = :p AND s.quantity_available > 0 AND s.expiry_date >= :today
              AND l.status = 'active' AND l.warehouse_id = :wh
            ORDER BY s.expiry_date ASC, s.created_at ASC, s.id ASC
            FOR UPDATE OF s
        """), {"p": it["product_id"], "today": t, "wh": DEFAULT_WAREHOUSE_ID}))

        total_avail = sum(b["quantity_available"] for b in batches)
        if total_avail < it["quantity"]:
            raise HTTPException(400, f"Dòng {line_no} ({prod['sku']}): tồn khả dụng không đủ! "
                                     f"Cần {it['quantity']}, hiện chỉ còn {total_avail} (chưa hết hạn, Bin đang hoạt động).")

        detail_id = db.execute(text("""
            INSERT INTO goods_issue_details (issue_id, product_id, requested_qty) VALUES (:i, :p, :q) RETURNING id
        """), {"i": issue_id, "p": it["product_id"], "q": it["quantity"]}).scalar()

        remain = it["quantity"]
        for b in batches:
            if remain <= 0:
                break
            take = min(remain, b["quantity_available"])
            db.execute(text("UPDATE inventory_stocks SET quantity_allocated = quantity_allocated + :take WHERE id = :sid"),
                       {"take": take, "sid": b["id"]})
            db.execute(text("""
                INSERT INTO picking_tasks (issue_detail_id, from_location_id, stock_id, batch_no, allocated_qty, status)
                VALUES (:d, :loc, :sid, :batch, :take, 'allocated')
            """), {"d": detail_id, "loc": b["location_id"], "sid": b["id"], "batch": b["batch_no"], "take": take})
            remain -= take
            task_count += 1

    db.commit()
    return {"message": f"Đã duyệt đơn {code}, tự động khóa giữ chỗ theo FEFO và gửi {task_count} lệnh lấy hàng xuống Mobile!",
            "id": issue_id, "issue_code": code}


def list_issues(db: Session, *, limit: int = 20, offset: int = 0, status: str = None, q: str = None) -> dict:
    where, params = [], {}
    if status:
        where.append("gi.status = :st")
        params["st"] = status
    if q:
        where.append("(LOWER(gi.issue_code) LIKE :q OR LOWER(pr.partner_name) LIKE :q)")
        params["q"] = f"%{q.strip().lower()}%"
    cond = ('WHERE ' + ' AND '.join(where)) if where else ''
    base = "FROM goods_issues gi JOIN partners pr ON gi.customer_id = pr.id JOIN users u ON gi.created_by = u.id"
    total = db.execute(text(f"SELECT COUNT(*) {base} {cond}"), params).scalar()
    issues = rows(db.execute(text(f"""
        SELECT gi.id, gi.issue_code, gi.status, gi.created_at, gi.approved_at,
               pr.partner_name AS customer_name, u.full_name AS created_by_name
        {base} {cond} ORDER BY gi.id DESC LIMIT :limit OFFSET :offset
    """), {**params, "limit": limit, "offset": offset}))

    if issues:
        clause, id_params = placeholders("iid", [i["id"] for i in issues])
        lines = rows(db.execute(text(f"""
            SELECT gid.id AS detail_id, gid.issue_id, p.sku, p.product_name, p.unit, gid.requested_qty, gid.picked_qty
            FROM goods_issue_details gid JOIN products p ON gid.product_id = p.id
            WHERE gid.issue_id IN ({clause}) ORDER BY gid.id
        """), id_params))
        tasks = rows(db.execute(text(f"""
            SELECT pkt.id AS task_id, pkt.issue_detail_id, l.location_code, pkt.batch_no, s.expiry_date,
                   pkt.allocated_qty, pkt.picked_qty, pkt.status
            FROM picking_tasks pkt
            JOIN goods_issue_details gid ON pkt.issue_detail_id = gid.id
            JOIN locations l ON pkt.from_location_id = l.id
            JOIN inventory_stocks s ON pkt.stock_id = s.id
            WHERE gid.issue_id IN ({clause})
            ORDER BY s.expiry_date, pkt.id
        """), id_params))
        tasks_by_detail = {}
        for tk in tasks:
            tasks_by_detail.setdefault(tk["issue_detail_id"], []).append(tk)
        by_issue = {}
        for ln in lines:
            ln["tasks"] = tasks_by_detail.get(ln["detail_id"], [])
            by_issue.setdefault(ln["issue_id"], []).append(ln)
        for i in issues:
            i["items"] = by_issue.get(i["id"], [])
            i["can_cancel"] = i["status"] == "allocated"
    return {"items": issues, "total": total or 0}


def cancel_issue(db: Session, issue_id: int) -> dict:
    """Hủy đơn xuất chưa có lệnh lấy hàng nào được thực hiện: giải phóng toàn bộ hàng đã giữ chỗ."""
    gi = db.execute(text("SELECT id, issue_code, status FROM goods_issues WHERE id = :id FOR UPDATE"),
                    {"id": issue_id}).mappings().first()
    if not gi:
        raise HTTPException(404, "Phiếu xuất không tồn tại!")
    tasks = rows(db.execute(text("""
        SELECT pkt.id, pkt.stock_id, pkt.allocated_qty, pkt.status
        FROM picking_tasks pkt JOIN goods_issue_details gid ON pkt.issue_detail_id = gid.id
        WHERE gid.issue_id = :id
    """), {"id": issue_id}))
    if gi["status"] != "allocated" or any(t["status"] != "allocated" for t in tasks):
        raise HTTPException(400, "Đơn đã có hàng được lấy ra khỏi kệ nên không thể hủy!")
    for t in tasks:
        db.execute(text("SELECT id FROM inventory_stocks WHERE id = :id FOR UPDATE"), {"id": t["stock_id"]})
        db.execute(text("UPDATE inventory_stocks SET quantity_allocated = quantity_allocated - :q WHERE id = :id"),
                   {"q": t["allocated_qty"], "id": t["stock_id"]})
    db.execute(text("DELETE FROM goods_issues WHERE id = :id"), {"id": issue_id})
    db.commit()
    return {"message": f"Đã hủy đơn xuất {gi['issue_code']} và giải phóng hàng giữ chỗ."}
