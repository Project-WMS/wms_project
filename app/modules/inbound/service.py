"""FR2 - Phiếu nhập kho: lập & duyệt phiếu -> sinh nhiệm vụ xếp kệ (putaway) cho Mobile."""
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import DEFAULT_WAREHOUSE_ID
from app.core.utils import make_code, placeholders, rows, today
from app.modules.locations.service import check_bin_capacity
from app.modules.partners.service import ensure_partner
from app.modules.products.service import ensure_active


def _check_batch_expiry(db: Session, product_id: int, batch_no: str, expiry_date) -> None:
    """Cùng một lô (sản phẩm + số lô) phải có cùng hạn sử dụng ở mọi Bin / mọi phiếu đang chờ xếp."""
    known = db.execute(text("""
        SELECT expiry_date FROM inventory_stocks
        WHERE product_id = :p AND batch_no = :b AND quantity_on_hand > 0
        UNION
        SELECT grd.expiry_date FROM goods_receipt_details grd
        JOIN putaway_tasks pt ON pt.receipt_detail_id = grd.id
        WHERE grd.product_id = :p AND grd.batch_no = :b AND pt.status = 'pending'
    """), {"p": product_id, "b": batch_no}).all()
    for (d,) in known:
        if d != expiry_date:
            raise HTTPException(400, f"Lô '{batch_no}' đã tồn tại với hạn sử dụng {d}. "
                                     "Cùng một số lô phải có cùng hạn sử dụng!")


def create_receipt(db: Session, user: dict, supplier_id: int, items: list) -> dict:
    ensure_partner(db, supplier_id, "supplier")
    if not items:
        raise HTTPException(400, "Phiếu nhập cần có ít nhất 1 dòng hàng!")
    t = today()
    code = make_code("PNK")
    receipt_id = db.execute(text("""
        INSERT INTO goods_receipts (receipt_code, supplier_id, warehouse_id, created_by, approved_by, status, approved_at)
        VALUES (:code, :sup, :wh, :u, :u, 'approved', CURRENT_TIMESTAMP) RETURNING id
    """), {"code": code, "sup": supplier_id, "wh": DEFAULT_WAREHOUSE_ID, "u": user["id"]}).scalar()

    for line_no, it in enumerate(items, 1):
        prod = ensure_active(db, it["product_id"])
        batch = it["batch_no"].strip()
        if it["expiry_date"] < t:
            raise HTTPException(400, f"Dòng {line_no}: hạn sử dụng {it['expiry_date']} đã qua, không thể nhập kho hàng hết hạn!")
        _check_batch_expiry(db, it["product_id"], batch, it["expiry_date"])
        # BR04: kiểm tra tải trọng ngay khi phân bổ (tính cả nhiệm vụ xếp kệ đang chờ, kể cả các dòng trước trong phiếu này)
        try:
            check_bin_capacity(db, it["to_location_id"], it["quantity"], it["product_id"], include_pending_putaway=True)
        except HTTPException as e:
            raise HTTPException(e.status_code, f"Dòng {line_no} ({prod['sku']}): {e.detail}")
        detail_id = db.execute(text("""
            INSERT INTO goods_receipt_details (receipt_id, product_id, batch_no, expiry_date, expected_qty)
            VALUES (:r, :p, :b, :e, :q) RETURNING id
        """), {"r": receipt_id, "p": it["product_id"], "b": batch, "e": it["expiry_date"], "q": it["quantity"]}).scalar()
        db.execute(text("""
            INSERT INTO putaway_tasks (receipt_detail_id, to_location_id, assigned_qty, status)
            VALUES (:d, :loc, :q, 'pending')
        """), {"d": detail_id, "loc": it["to_location_id"], "q": it["quantity"]})

    db.commit()
    return {"message": f"Đã duyệt phiếu {code} và gửi {len(items)} nhiệm vụ xếp kệ xuống Mobile!",
            "id": receipt_id, "receipt_code": code}


def list_receipts(db: Session, *, limit: int = 20, offset: int = 0, status: str = None, q: str = None) -> dict:
    where, params = [], {}
    if status:
        where.append("gr.status = :st")
        params["st"] = status
    if q:
        where.append("(LOWER(gr.receipt_code) LIKE :q OR LOWER(pr.partner_name) LIKE :q)")
        params["q"] = f"%{q.strip().lower()}%"
    cond = ('WHERE ' + ' AND '.join(where)) if where else ''
    base = "FROM goods_receipts gr JOIN partners pr ON gr.supplier_id = pr.id JOIN users u ON gr.created_by = u.id"
    total = db.execute(text(f"SELECT COUNT(*) {base} {cond}"), params).scalar()
    receipts = rows(db.execute(text(f"""
        SELECT gr.id, gr.receipt_code, gr.status, gr.created_at, gr.approved_at,
               pr.partner_name AS supplier_name, u.full_name AS created_by_name
        {base} {cond} ORDER BY gr.id DESC LIMIT :limit OFFSET :offset
    """), {**params, "limit": limit, "offset": offset}))

    if receipts:
        clause, id_params = placeholders("rid", [r["id"] for r in receipts])
        lines = rows(db.execute(text(f"""
            SELECT grd.id AS detail_id, grd.receipt_id, p.sku, p.product_name, p.unit, grd.batch_no, grd.expiry_date,
                   grd.expected_qty, grd.putaway_qty, l.location_code, pt.id AS task_id, pt.status AS task_status,
                   pt.actual_qty
            FROM goods_receipt_details grd
            JOIN products p ON grd.product_id = p.id
            LEFT JOIN putaway_tasks pt ON pt.receipt_detail_id = grd.id
            LEFT JOIN locations l ON pt.to_location_id = l.id
            WHERE grd.receipt_id IN ({clause})
            ORDER BY grd.id
        """), id_params))
        by_receipt = {}
        for ln in lines:
            by_receipt.setdefault(ln["receipt_id"], []).append(ln)
        for r in receipts:
            r["items"] = by_receipt.get(r["id"], [])
            r["can_cancel"] = r["status"] == "approved"
    return {"items": receipts, "total": total or 0}


def cancel_receipt(db: Session, receipt_id: int) -> dict:
    """Hủy phiếu nhập còn nguyên (chưa có dòng hàng nào được xếp lên kệ). Thẻ kho không bị ảnh hưởng."""
    r = db.execute(text("SELECT id, receipt_code, status FROM goods_receipts WHERE id = :id FOR UPDATE"),
                   {"id": receipt_id}).mappings().first()
    if not r:
        raise HTTPException(404, "Phiếu nhập không tồn tại!")
    done = db.execute(text("""
        SELECT COUNT(*) FROM putaway_tasks pt JOIN goods_receipt_details grd ON pt.receipt_detail_id = grd.id
        WHERE grd.receipt_id = :id AND pt.status = 'completed'
    """), {"id": receipt_id}).scalar()
    if r["status"] != "approved" or done:
        raise HTTPException(400, "Phiếu đã có hàng được xếp lên kệ nên không thể hủy. Hãy dùng Điều chuyển/Kiểm kê để điều chỉnh!")
    db.execute(text("DELETE FROM goods_receipts WHERE id = :id"), {"id": receipt_id})
    db.commit()
    return {"message": f"Đã hủy phiếu nhập {r['receipt_code']} và thu hồi các nhiệm vụ xếp kệ."}
