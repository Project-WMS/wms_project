"""FR4 - Điều chuyển nội bộ giữa các Bin (STOCK_TRANSFERS)."""
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import DEFAULT_WAREHOUSE_ID
from app.core.utils import first, make_code, placeholders, rows
from app.modules.locations.service import check_bin_capacity
from app.modules.stocks.service import add_ledger


def create_transfer(db: Session, user: dict, items: list) -> dict:
    if not items:
        raise HTTPException(400, "Phiếu điều chuyển cần có ít nhất 1 dòng hàng!")
    code = make_code("PDC")
    transfer_id = db.execute(text("""
        INSERT INTO stock_transfers (transfer_code, warehouse_id, created_by, approved_by, status)
        VALUES (:code, :wh, :u, :u, 'completed') RETURNING id
    """), {"code": code, "wh": DEFAULT_WAREHOUSE_ID, "u": user["id"]}).scalar()

    for line_no, it in enumerate(items, 1):
        src = first(db.execute(text("""
            SELECT s.id, s.location_id, s.product_id, s.batch_no, s.expiry_date, s.created_at,
                   s.quantity_on_hand, s.quantity_allocated, s.quantity_available, l.location_code
            FROM inventory_stocks s JOIN locations l ON s.location_id = l.id
            WHERE s.id = :sid
            FOR UPDATE OF s
        """), {"sid": it["stock_id"]}))
        if not src:
            raise HTTPException(404, f"Dòng {line_no}: lô tồn kho nguồn không tồn tại!")
        if src["location_id"] == it["to_location_id"]:
            raise HTTPException(400, f"Dòng {line_no}: ô Bin đích phải khác ô Bin nguồn!")
        # BR02: chỉ chuyển phần khả dụng, không động vào hàng đang giữ chỗ cho đơn xuất
        if it["quantity"] > src["quantity_available"]:
            raise HTTPException(400, f"Dòng {line_no}: chỉ chuyển được tối đa {src['quantity_available']} "
                                     "(phần còn lại đang giữ chỗ cho đơn xuất)!")
        try:
            # BR04: Bin đích phải active và không vượt tải trọng (tính cả hàng đang chờ xếp)
            check_bin_capacity(db, it["to_location_id"], it["quantity"], src["product_id"], include_pending_putaway=True)
        except HTTPException as e:
            raise HTTPException(e.status_code, f"Dòng {line_no}: {e.detail}")

        detail_id = db.execute(text("""
            INSERT INTO stock_transfer_details (transfer_id, product_id, batch_no, from_location_id,
                                                to_location_id, transfer_qty, performed_by)
            VALUES (:t, :p, :b, :fl, :tl, :q, :u) RETURNING id
        """), {"t": transfer_id, "p": src["product_id"], "b": src["batch_no"], "fl": src["location_id"],
               "tl": it["to_location_id"], "q": it["quantity"], "u": user["id"]}).scalar()

        src_after = db.execute(text("""
            UPDATE inventory_stocks SET quantity_on_hand = quantity_on_hand - :q WHERE id = :sid
            RETURNING quantity_on_hand
        """), {"q": it["quantity"], "sid": it["stock_id"]}).scalar()

        # Giữ nguyên created_at gốc của lô ở Bin đích để không làm sai thứ tự FIFO (BR03)
        dst_after = db.execute(text("""
            INSERT INTO inventory_stocks (location_id, product_id, batch_no, expiry_date,
                                          quantity_on_hand, quantity_allocated, created_at)
            VALUES (:loc, :p, :b, :exp, :q, 0, :cat)
            ON CONFLICT (location_id, product_id, batch_no)
            DO UPDATE SET quantity_on_hand = inventory_stocks.quantity_on_hand + EXCLUDED.quantity_on_hand,
                          created_at = CASE WHEN EXCLUDED.created_at < inventory_stocks.created_at
                                            THEN EXCLUDED.created_at ELSE inventory_stocks.created_at END
            RETURNING quantity_on_hand
        """), {"loc": it["to_location_id"], "p": src["product_id"], "b": src["batch_no"],
               "exp": src["expiry_date"], "q": it["quantity"], "cat": src["created_at"]}).scalar()

        # Thẻ kho: 2 dòng (trừ ở Bin nguồn, cộng ở Bin đích) để balance_after đúng theo từng Bin
        for change, balance in ((-it["quantity"], src_after), (it["quantity"], dst_after)):
            add_ledger(db, ttype="TRANSFER", ref=code, task_id=detail_id, product_id=src["product_id"],
                       batch_no=src["batch_no"], from_loc=src["location_id"], to_loc=it["to_location_id"],
                       change=change, balance_after=balance, user_id=user["id"])

    db.commit()
    return {"message": f"Đã điều chuyển {len(items)} dòng hàng (phiếu {code})!", "id": transfer_id, "transfer_code": code}


def list_transfers(db: Session, *, limit: int = 20, offset: int = 0) -> dict:
    total = db.execute(text("SELECT COUNT(*) FROM stock_transfers")).scalar()
    transfers = rows(db.execute(text("""
        SELECT t.id, t.transfer_code, t.status, t.created_at, u.full_name AS created_by_name
        FROM stock_transfers t JOIN users u ON t.created_by = u.id
        ORDER BY t.id DESC LIMIT :limit OFFSET :offset
    """), {"limit": limit, "offset": offset}))
    if transfers:
        clause, params = placeholders("tid", [t["id"] for t in transfers])
        lines = rows(db.execute(text(f"""
            SELECT d.id AS detail_id, d.transfer_id, p.sku, p.product_name, p.unit, d.batch_no,
                   lf.location_code AS from_loc, lt.location_code AS to_loc, d.transfer_qty
            FROM stock_transfer_details d
            JOIN products p ON d.product_id = p.id
            JOIN locations lf ON d.from_location_id = lf.id
            JOIN locations lt ON d.to_location_id = lt.id
            WHERE d.transfer_id IN ({clause}) ORDER BY d.id
        """), params))
        by_t = {}
        for ln in lines:
            by_t.setdefault(ln["transfer_id"], []).append(ln)
        for t in transfers:
            t["items"] = by_t.get(t["id"], [])
    return {"items": transfers, "total": total or 0}
