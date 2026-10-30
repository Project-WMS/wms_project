"""Nhiệm vụ trên Mobile: Xếp kệ (Putaway - UC5) và Lấy hàng FEFO (Picking - UC6)."""
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.utils import first, rows
from app.modules.locations.service import check_bin_capacity
from app.modules.stocks.service import add_ledger


def list_tasks(db: Session) -> dict:
    putaway = rows(db.execute(text("""
        SELECT pt.id AS task_id, gr.receipt_code, p.sku, p.barcode, p.product_name, p.unit,
               grd.batch_no, grd.expiry_date, l.location_code, pt.assigned_qty
        FROM putaway_tasks pt
        JOIN goods_receipt_details grd ON pt.receipt_detail_id = grd.id
        JOIN goods_receipts gr ON grd.receipt_id = gr.id
        JOIN products p ON grd.product_id = p.id
        JOIN locations l ON pt.to_location_id = l.id
        WHERE pt.status = 'pending'
        ORDER BY pt.id DESC
    """)))
    picking = rows(db.execute(text("""
        SELECT pkt.id AS task_id, gi.issue_code, p.sku, p.barcode, p.product_name, p.unit,
               pkt.batch_no, s.expiry_date, l.location_code, pkt.allocated_qty
        FROM picking_tasks pkt
        JOIN goods_issue_details gid ON pkt.issue_detail_id = gid.id
        JOIN goods_issues gi ON gid.issue_id = gi.id
        JOIN products p ON gid.product_id = p.id
        JOIN locations l ON pkt.from_location_id = l.id
        JOIN inventory_stocks s ON pkt.stock_id = s.id
        WHERE pkt.status = 'allocated'
        ORDER BY s.expiry_date ASC, pkt.id ASC
    """)))
    return {"putaway_tasks": putaway, "picking_tasks": picking}


def confirm_putaway(db: Session, user: dict, *, task_id: int, scanned_qr: str, actual_qty: int) -> dict:
    task = first(db.execute(text("""
        SELECT pt.id, pt.to_location_id, pt.assigned_qty, pt.receipt_detail_id, l.location_code,
               grd.product_id, grd.batch_no, grd.expiry_date, grd.receipt_id, gr.receipt_code
        FROM putaway_tasks pt
        JOIN locations l ON pt.to_location_id = l.id
        JOIN goods_receipt_details grd ON pt.receipt_detail_id = grd.id
        JOIN goods_receipts gr ON grd.receipt_id = gr.id
        WHERE pt.id = :tid AND pt.status = 'pending'
        FOR UPDATE OF pt
    """), {"tid": task_id}))
    if not task:
        raise HTTPException(404, "Nhiệm vụ không tồn tại hoặc đã hoàn tất!")
    if scanned_qr.strip().upper() != task["location_code"].upper():
        raise HTTPException(400, f"Quét sai ô kệ! Hệ thống yêu cầu ô {task['location_code']}")
    if actual_qty > task["assigned_qty"]:
        raise HTTPException(400, f"Số lượng xếp ({actual_qty}) vượt số lượng được phân bổ ({task['assigned_qty']})!")

    # BR04 (khâu Putaway): không vượt max_capacity_kg - tính trên tồn thực tế hiện có tại Bin
    check_bin_capacity(db, task["to_location_id"], actual_qty, task["product_id"])

    stock = first(db.execute(text("""
        INSERT INTO inventory_stocks (location_id, product_id, batch_no, expiry_date, quantity_on_hand, quantity_allocated)
        VALUES (:loc, :prod, :batch, :exp, :qty, 0)
        ON CONFLICT (location_id, product_id, batch_no)
        DO UPDATE SET quantity_on_hand = inventory_stocks.quantity_on_hand + EXCLUDED.quantity_on_hand
        RETURNING id, quantity_on_hand
    """), {"loc": task["to_location_id"], "prod": task["product_id"], "batch": task["batch_no"],
           "exp": task["expiry_date"], "qty": actual_qty}))

    db.execute(text("""
        UPDATE putaway_tasks
        SET actual_qty = :qty, status = 'completed', stock_id = :sid, performed_by = :u, completed_at = CURRENT_TIMESTAMP
        WHERE id = :tid
    """), {"qty": actual_qty, "sid": stock["id"], "u": user["id"], "tid": task_id})
    db.execute(text("UPDATE goods_receipt_details SET putaway_qty = putaway_qty + :qty WHERE id = :did"),
               {"qty": actual_qty, "did": task["receipt_detail_id"]})

    # Trạng thái phiếu nhập: approved -> putting_away -> completed
    remaining = db.execute(text("""
        SELECT COUNT(*) FROM putaway_tasks pt JOIN goods_receipt_details grd ON pt.receipt_detail_id = grd.id
        WHERE grd.receipt_id = :rid AND pt.status = 'pending'
    """), {"rid": task["receipt_id"]}).scalar()
    db.execute(text("UPDATE goods_receipts SET status = :st WHERE id = :rid"),
               {"st": "completed" if remaining == 0 else "putting_away", "rid": task["receipt_id"]})

    add_ledger(db, ttype="PUTAWAY", ref=task["receipt_code"], task_id=task_id, product_id=task["product_id"],
               batch_no=task["batch_no"], from_loc=None, to_loc=task["to_location_id"],
               change=actual_qty, balance_after=stock["quantity_on_hand"], user_id=user["id"])
    db.commit()
    return {"message": f"Đã xếp thành công +{actual_qty} vào kệ {task['location_code']}!"}


def confirm_picking(db: Session, user: dict, *, task_id: int, scanned_qr: str, scanned_barcode: str, actual_qty: int) -> dict:
    task = first(db.execute(text("""
        SELECT pkt.id, pkt.stock_id, pkt.from_location_id, pkt.allocated_qty, pkt.batch_no,
               pkt.issue_detail_id, l.location_code, gid.product_id, gid.issue_id, gi.issue_code, p.barcode
        FROM picking_tasks pkt
        JOIN locations l ON pkt.from_location_id = l.id
        JOIN goods_issue_details gid ON pkt.issue_detail_id = gid.id
        JOIN goods_issues gi ON gid.issue_id = gi.id
        JOIN products p ON gid.product_id = p.id
        WHERE pkt.id = :tid AND pkt.status = 'allocated'
        FOR UPDATE OF pkt
    """), {"tid": task_id}))
    if not task:
        raise HTTPException(404, "Nhiệm vụ lấy hàng không tồn tại hoặc đã xong!")
    if scanned_qr.strip().upper() != task["location_code"].upper():
        raise HTTPException(400, f"Sai vị trí! Phải lấy hàng tại ô {task['location_code']} theo chuẩn FEFO.")
    # UC6: xác thực đúng sản phẩm/lô bằng mã vạch bao bì
    if not scanned_barcode or scanned_barcode.strip() != task["barcode"]:
        raise HTTPException(400, "Sai mã vạch sản phẩm / lô hàng! Hãy quét lại mã vạch trên bao bì đúng lô chỉ định.")
    # BR02: picked_qty không vượt allocated_qty
    if actual_qty > task["allocated_qty"]:
        raise HTTPException(400, f"Số lượng lấy ({actual_qty}) vượt số lượng giữ chỗ ({task['allocated_qty']})!")

    # Trừ tồn thực tế (On-hand) và giải phóng toàn bộ giữ chỗ (Allocated) của task
    stock = first(db.execute(text("""
        UPDATE inventory_stocks
        SET quantity_on_hand = quantity_on_hand - :qty, quantity_allocated = quantity_allocated - :alloc
        WHERE id = :sid
        RETURNING quantity_on_hand
    """), {"qty": actual_qty, "alloc": task["allocated_qty"], "sid": task["stock_id"]}))

    db.execute(text("""
        UPDATE picking_tasks SET picked_qty = :qty, status = 'picked', performed_by = :u, picked_at = CURRENT_TIMESTAMP
        WHERE id = :tid
    """), {"qty": actual_qty, "u": user["id"], "tid": task_id})
    db.execute(text("UPDATE goods_issue_details SET picked_qty = picked_qty + :qty WHERE id = :did"),
               {"qty": actual_qty, "did": task["issue_detail_id"]})

    # Trạng thái phiếu xuất: allocated -> picking -> completed
    remaining = db.execute(text("""
        SELECT COUNT(*) FROM picking_tasks pkt JOIN goods_issue_details gid ON pkt.issue_detail_id = gid.id
        WHERE gid.issue_id = :iid AND pkt.status = 'allocated'
    """), {"iid": task["issue_id"]}).scalar()
    db.execute(text("UPDATE goods_issues SET status = :st WHERE id = :iid"),
               {"st": "completed" if remaining == 0 else "picking", "iid": task["issue_id"]})

    add_ledger(db, ttype="PICK", ref=task["issue_code"], task_id=task_id, product_id=task["product_id"],
               batch_no=task["batch_no"], from_loc=task["from_location_id"], to_loc=None,
               change=-actual_qty, balance_after=stock["quantity_on_hand"], user_id=user["id"])
    db.commit()
    return {"message": f"Đã xuất thành công -{actual_qty} từ kệ {task['location_code']}!"}
