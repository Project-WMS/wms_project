import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas import (
    InboundCreateRequest,
    OutboundCreateRequest,
    ScanConfirmRequest,
    StockCountRequest,
    TransferRequest,
)

router = APIRouter(prefix="/api")

# Chưa có đăng nhập/RBAC nên tạm gán cố định theo dữ liệu mẫu trong init_db.py.
# Khi làm chức năng đăng nhập, thay các hằng số này bằng user lấy từ token.
DEFAULT_WAREHOUSE_ID = 1
MANAGER_ID = 2   # thukho  (Thủ kho - Web PC)
WORKER_ID = 3    # congnhan (Công nhân - Mobile)


def make_code(prefix: str) -> str:
    """Sinh mã chứng từ, vd PNK-261020153045-A3F9 (không trùng khi 2 phiếu tạo cùng giây)."""
    return f"{prefix}-{datetime.now():%y%m%d%H%M%S}-{uuid.uuid4().hex[:4].upper()}"


def check_bin_capacity(db: Session, location_id: int, add_qty: int, product_id: int,
                       include_pending_putaway: bool = False):
    """BR04: Tổng (SL tồn tại Bin * unit_weight_kg) <= locations.max_capacity_kg.
    Đồng thời chặn Bin không ở trạng thái 'active'."""
    loc = db.execute(text("""
        SELECT location_code, max_capacity_kg, status FROM locations WHERE id = :id
    """), {"id": location_id}).mappings().first()
    if not loc:
        raise HTTPException(status_code=404, detail="Ô Bin không tồn tại!")
    if loc["status"] != "active":
        raise HTTPException(status_code=400, detail=f"Ô Bin {loc['location_code']} đang ở trạng thái '{loc['status']}', không thể nhận hàng!")

    unit_w = db.execute(text("SELECT unit_weight_kg FROM products WHERE id = :id"),
                        {"id": product_id}).scalar()
    if unit_w is None:
        raise HTTPException(status_code=404, detail="Sản phẩm không tồn tại!")

    current = db.execute(text("""
        SELECT COALESCE(SUM(s.quantity_on_hand * p.unit_weight_kg), 0)
        FROM inventory_stocks s JOIN products p ON s.product_id = p.id
        WHERE s.location_id = :loc
    """), {"loc": location_id}).scalar()

    pending = Decimal(0)
    if include_pending_putaway:
        # Hàng đã được chỉ định vào Bin nhưng công nhân chưa xếp: vẫn phải giữ chỗ tải trọng
        pending = db.execute(text("""
            SELECT COALESCE(SUM(pt.assigned_qty * p.unit_weight_kg), 0)
            FROM putaway_tasks pt
            JOIN goods_receipt_details grd ON pt.receipt_detail_id = grd.id
            JOIN products p ON grd.product_id = p.id
            WHERE pt.to_location_id = :loc AND pt.status = 'pending'
        """), {"loc": location_id}).scalar()

    new_total = Decimal(current) + Decimal(pending) + Decimal(add_qty) * Decimal(unit_w)
    if new_total > loc["max_capacity_kg"]:
        raise HTTPException(
            status_code=400,
            detail=(f"Vượt tải trọng ô {loc['location_code']}! Sau khi thêm: {new_total} kg "
                    f"> tối đa {loc['max_capacity_kg']} kg (BR04)."),
        )


def add_ledger(db: Session, *, ttype: str, ref: str, task_id, product_id: int, batch_no: str,
               from_loc, to_loc, change: int, balance_after: int, user_id: int):
    """Chỉ INSERT vào stock_ledger (BR06 - bất biến; DB còn có trigger chặn UPDATE/DELETE)."""
    db.execute(text("""
        INSERT INTO stock_ledger (transaction_type, reference_code, task_id, product_id, batch_no,
                                  from_location_id, to_location_id, quantity_change, balance_after, performed_by)
        VALUES (:t, :ref, :tid, :p, :b, :fl, :tl, :chg, :bal, :u)
    """), {"t": ttype, "ref": ref, "tid": task_id, "p": product_id, "b": batch_no,
           "fl": from_loc, "tl": to_loc, "chg": change, "bal": balance_after, "u": user_id})


# 1. API Lấy toàn bộ dữ liệu Dashboard, Cảnh báo FEFO, Sơ đồ kệ QR, Kiểm kê và Thẻ kho
@router.get("/dashboard")
def get_dashboard_data(db: Session = Depends(get_db)):
    kpi = db.execute(text("""
        SELECT
            COALESCE(SUM(quantity_on_hand), 0) AS total_on_hand,
            COALESCE(SUM(quantity_allocated), 0) AS total_allocated,
            COALESCE(SUM(quantity_available), 0) AS total_available
        FROM inventory_stocks
    """)).mappings().first()

    low_stock = db.execute(text("""
        SELECT p.id, p.sku, p.product_name, p.unit, p.min_safety_stock,
               COALESCE(SUM(s.quantity_available), 0) AS total_available
        FROM products p
        LEFT JOIN inventory_stocks s ON p.id = s.product_id
        GROUP BY p.id, p.sku, p.product_name, p.unit, p.min_safety_stock
        HAVING COALESCE(SUM(s.quantity_available), 0) <= p.min_safety_stock
    """)).mappings().all()

    # ERD: max_safety_stock = ngưỡng cảnh báo vượt định mức
    over_stock = db.execute(text("""
        SELECT p.id, p.sku, p.product_name, p.unit, p.max_safety_stock,
               COALESCE(SUM(s.quantity_on_hand), 0) AS total_on_hand
        FROM products p
        LEFT JOIN inventory_stocks s ON p.id = s.product_id
        GROUP BY p.id, p.sku, p.product_name, p.unit, p.max_safety_stock
        HAVING COALESCE(SUM(s.quantity_on_hand), 0) > p.max_safety_stock
    """)).mappings().all()

    expiring_fefo = db.execute(text("""
        SELECT s.id, p.sku, p.product_name, l.location_code, s.batch_no, s.expiry_date,
               s.quantity_on_hand, s.quantity_available,
               (s.expiry_date - CURRENT_DATE) AS days_left
        FROM inventory_stocks s
        JOIN products p ON s.product_id = p.id
        JOIN locations l ON s.location_id = l.id
        WHERE s.quantity_on_hand > 0 AND s.expiry_date <= CURRENT_DATE + INTERVAL '30 days'
        ORDER BY s.expiry_date ASC
    """)).mappings().all()

    locations = db.execute(text("""
        SELECT l.id, l.location_code, l.zone, l.aisle, l.rack, l.shelf_level, l.bin,
               l.max_capacity_kg, l.status,
               COALESCE(SUM(s.quantity_on_hand * p.unit_weight_kg), 0) AS current_weight_kg
        FROM locations l
        LEFT JOIN inventory_stocks s ON l.id = s.location_id
        LEFT JOIN products p ON s.product_id = p.id
        GROUP BY l.id
        ORDER BY l.location_code ASC
    """)).mappings().all()

    stocks = db.execute(text("""
        SELECT s.id, l.location_code, p.sku, p.barcode, p.product_name, p.unit,
               s.batch_no, s.expiry_date, s.quantity_on_hand, s.quantity_allocated, s.quantity_available
        FROM inventory_stocks s
        JOIN locations l ON s.location_id = l.id
        JOIN products p ON s.product_id = p.id
        WHERE s.quantity_on_hand > 0
        ORDER BY s.expiry_date ASC, l.location_code ASC
    """)).mappings().all()

    # Báo cáo chênh lệch kiểm kê (frontend đọc data.counts)
    counts = db.execute(text("""
        SELECT scd.id, sc.count_code, l.location_code, p.sku, scd.batch_no,
               scd.system_qty, scd.actual_qty, scd.variance_qty, sc.status
        FROM stock_count_details scd
        JOIN stock_counts sc ON scd.count_id = sc.id
        JOIN locations l ON scd.location_id = l.id
        JOIN products p ON scd.product_id = p.id
        ORDER BY scd.id DESC
        LIMIT 15
    """)).mappings().all()

    ledger = db.execute(text("""
        SELECT sl.id, sl.transaction_type, sl.reference_code, p.sku, p.product_name,
               sl.batch_no, lf.location_code AS from_loc, lt.location_code AS to_loc,
               sl.quantity_change, sl.balance_after, u.full_name AS performer, sl.created_at
        FROM stock_ledger sl
        JOIN products p ON sl.product_id = p.id
        LEFT JOIN locations lf ON sl.from_location_id = lf.id
        LEFT JOIN locations lt ON sl.to_location_id = lt.id
        JOIN users u ON sl.performed_by = u.id
        ORDER BY sl.id DESC
        LIMIT 25
    """)).mappings().all()

    products = db.execute(text("SELECT * FROM products ORDER BY id ASC")).mappings().all()

    return {
        "kpi": dict(kpi),
        "low_stock_alerts": [dict(r) for r in low_stock],
        "over_stock_alerts": [dict(r) for r in over_stock],
        "expiring_alerts": [dict(r) for r in expiring_fefo],
        "locations": [dict(r) for r in locations],
        "stocks": [dict(r) for r in stocks],
        "counts": [dict(r) for r in counts],
        "ledger": [dict(r) for r in ledger],
        "products": [dict(r) for r in products],
    }


# 2. API Thủ kho tạo & duyệt Phiếu Nhập -> Đẩy nhiệm vụ Putaway xuống Điện thoại
@router.post("/inbound/create")
def create_inbound(req: InboundCreateRequest, db: Session = Depends(get_db)):
    # BR04: kiểm tra tải trọng ngay khi phân bổ (tính cả các task xếp kệ đang chờ)
    check_bin_capacity(db, req.to_location_id, req.expected_qty, req.product_id,
                       include_pending_putaway=True)

    receipt_code = make_code("PNK")
    r_id = db.execute(text("""
        INSERT INTO goods_receipts (receipt_code, supplier_id, warehouse_id, created_by, approved_by, status, approved_at)
        VALUES (:code, :sup, :wh, :mgr, :mgr, 'approved', CURRENT_TIMESTAMP) RETURNING id
    """), {"code": receipt_code, "sup": req.supplier_id, "wh": DEFAULT_WAREHOUSE_ID, "mgr": MANAGER_ID}).scalar()

    d_id = db.execute(text("""
        INSERT INTO goods_receipt_details (receipt_id, product_id, batch_no, expiry_date, expected_qty)
        VALUES (:r_id, :p_id, :batch, :exp, :qty) RETURNING id
    """), {"r_id": r_id, "p_id": req.product_id, "batch": req.batch_no,
           "exp": req.expiry_date, "qty": req.expected_qty}).scalar()

    db.execute(text("""
        INSERT INTO putaway_tasks (receipt_detail_id, to_location_id, assigned_qty, status)
        VALUES (:d_id, :loc_id, :qty, 'pending')
    """), {"d_id": d_id, "loc_id": req.to_location_id, "qty": req.expected_qty})

    db.commit()
    return {"message": f"Đã duyệt phiếu {receipt_code} và gửi nhiệm vụ xếp kệ xuống Mobile!"}


# 3. API Thủ kho tạo & duyệt Phiếu Xuất -> Tự động chạy FEFO khóa giữ chỗ (Allocated)
@router.post("/outbound/create")
def create_outbound_fefo(req: OutboundCreateRequest, db: Session = Depends(get_db)):
    # BR03: Ưu tiên 1 FEFO (expiry_date ASC), ưu tiên 2 FIFO (created_at ASC).
    # FOR UPDATE khóa các dòng tồn kho để 2 đơn xuất duyệt cùng lúc không giữ chỗ trùng (NFR2 - ACID).
    batches = db.execute(text("""
        SELECT s.id, s.location_id, s.batch_no, s.expiry_date, s.quantity_available
        FROM inventory_stocks s
        JOIN locations l ON s.location_id = l.id
        WHERE s.product_id = :p_id AND s.quantity_available > 0
          AND l.status = 'active' AND l.warehouse_id = :wh
        ORDER BY s.expiry_date ASC, s.created_at ASC, s.id ASC
        FOR UPDATE OF s
    """), {"p_id": req.product_id, "wh": DEFAULT_WAREHOUSE_ID}).mappings().all()

    total_avail = sum(b["quantity_available"] for b in batches)
    if total_avail < req.requested_qty:
        raise HTTPException(status_code=400, detail=f"Tồn khả dụng không đủ! Hiện chỉ còn {total_avail} đơn vị.")

    issue_code = make_code("PXK")
    i_id = db.execute(text("""
        INSERT INTO goods_issues (issue_code, customer_id, warehouse_id, created_by, approved_by, status, approved_at)
        VALUES (:code, :cus, :wh, :mgr, :mgr, 'allocated', CURRENT_TIMESTAMP) RETURNING id
    """), {"code": issue_code, "cus": req.customer_id, "wh": DEFAULT_WAREHOUSE_ID, "mgr": MANAGER_ID}).scalar()

    d_id = db.execute(text("""
        INSERT INTO goods_issue_details (issue_id, product_id, requested_qty)
        VALUES (:i_id, :p_id, :qty) RETURNING id
    """), {"i_id": i_id, "p_id": req.product_id, "qty": req.requested_qty}).scalar()

    remain = req.requested_qty
    for b in batches:
        if remain <= 0:
            break
        take = min(remain, b["quantity_available"])
        db.execute(text("""
            UPDATE inventory_stocks SET quantity_allocated = quantity_allocated + :take WHERE id = :s_id
        """), {"take": take, "s_id": b["id"]})

        db.execute(text("""
            INSERT INTO picking_tasks (issue_detail_id, from_location_id, stock_id, batch_no, allocated_qty, status)
            VALUES (:d_id, :loc_id, :s_id, :batch, :take, 'allocated')
        """), {"d_id": d_id, "loc_id": b["location_id"], "s_id": b["id"], "batch": b["batch_no"], "take": take})
        remain -= take

    db.commit()
    return {"message": f"Đã duyệt đơn {issue_code}, tự động khóa giữ chỗ theo FEFO và gửi lệnh xuống Mobile!"}


# 4. API Lấy danh sách nhiệm vụ trên màn hình Điện thoại của Công nhân
@router.get("/mobile/tasks")
def get_mobile_tasks(db: Session = Depends(get_db)):
    putaway = db.execute(text("""
        SELECT pt.id AS task_id, gr.receipt_code, p.sku, p.barcode, p.product_name, p.unit,
               grd.batch_no, grd.expiry_date, l.location_code, pt.assigned_qty
        FROM putaway_tasks pt
        JOIN goods_receipt_details grd ON pt.receipt_detail_id = grd.id
        JOIN goods_receipts gr ON grd.receipt_id = gr.id
        JOIN products p ON grd.product_id = p.id
        JOIN locations l ON pt.to_location_id = l.id
        WHERE pt.status = 'pending'
        ORDER BY pt.id DESC
    """)).mappings().all()

    picking = db.execute(text("""
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
    """)).mappings().all()

    return {
        "putaway_tasks": [dict(r) for r in putaway],
        "picking_tasks": [dict(r) for r in picking],
    }


# 5. API Công nhân bấm Xác nhận Quét QR Xếp kệ (Putaway) trên Điện thoại
@router.post("/mobile/putaway/confirm")
def confirm_putaway(req: ScanConfirmRequest, db: Session = Depends(get_db)):
    task = db.execute(text("""
        SELECT pt.id, pt.to_location_id, pt.assigned_qty, pt.receipt_detail_id, l.location_code,
               grd.product_id, grd.batch_no, grd.expiry_date, grd.receipt_id, gr.receipt_code
        FROM putaway_tasks pt
        JOIN locations l ON pt.to_location_id = l.id
        JOIN goods_receipt_details grd ON pt.receipt_detail_id = grd.id
        JOIN goods_receipts gr ON grd.receipt_id = gr.id
        WHERE pt.id = :tid AND pt.status = 'pending'
        FOR UPDATE OF pt
    """), {"tid": req.task_id}).mappings().first()

    if not task:
        raise HTTPException(status_code=404, detail="Nhiệm vụ không tồn tại hoặc đã hoàn tất!")
    if req.scanned_qr.strip().upper() != task["location_code"].upper():
        raise HTTPException(status_code=400, detail=f"Quét sai ô kệ! Hệ thống yêu cầu ô {task['location_code']}")
    if req.actual_qty > task["assigned_qty"]:
        raise HTTPException(status_code=400, detail=f"Số lượng xếp ({req.actual_qty}) vượt số lượng được phân bổ ({task['assigned_qty']})!")

    # UC5: không vượt max_capacity_kg (BR04) - tính trên tồn thực tế hiện có tại Bin
    check_bin_capacity(db, task["to_location_id"], req.actual_qty, task["product_id"])

    # Cộng tồn kho vào bảng inventory_stocks (Upsert)
    stock = db.execute(text("""
        INSERT INTO inventory_stocks (location_id, product_id, batch_no, expiry_date, quantity_on_hand, quantity_allocated)
        VALUES (:loc, :prod, :batch, :exp, :qty, 0)
        ON CONFLICT (location_id, product_id, batch_no)
        DO UPDATE SET quantity_on_hand = inventory_stocks.quantity_on_hand + EXCLUDED.quantity_on_hand
        RETURNING id, quantity_on_hand
    """), {
        "loc": task["to_location_id"], "prod": task["product_id"],
        "batch": task["batch_no"], "exp": task["expiry_date"], "qty": req.actual_qty,
    }).mappings().first()

    # Cập nhật nhiệm vụ (gắn stock_id theo ERD) và số lượng đã xếp của dòng phiếu nhập
    db.execute(text("""
        UPDATE putaway_tasks
        SET actual_qty = :qty, status = 'completed', stock_id = :sid,
            performed_by = :w, completed_at = CURRENT_TIMESTAMP
        WHERE id = :tid
    """), {"qty": req.actual_qty, "sid": stock["id"], "w": WORKER_ID, "tid": req.task_id})

    db.execute(text("""
        UPDATE goods_receipt_details SET putaway_qty = putaway_qty + :qty WHERE id = :did
    """), {"qty": req.actual_qty, "did": task["receipt_detail_id"]})

    # Trạng thái phiếu nhập: approved -> putting_away -> completed
    remaining = db.execute(text("""
        SELECT COUNT(*) FROM putaway_tasks pt
        JOIN goods_receipt_details grd ON pt.receipt_detail_id = grd.id
        WHERE grd.receipt_id = :rid AND pt.status = 'pending'
    """), {"rid": task["receipt_id"]}).scalar()
    db.execute(text("UPDATE goods_receipts SET status = :st WHERE id = :rid"),
               {"st": "completed" if remaining == 0 else "putting_away", "rid": task["receipt_id"]})

    add_ledger(db, ttype="PUTAWAY", ref=task["receipt_code"], task_id=req.task_id,
               product_id=task["product_id"], batch_no=task["batch_no"],
               from_loc=None, to_loc=task["to_location_id"],
               change=req.actual_qty, balance_after=stock["quantity_on_hand"], user_id=WORKER_ID)

    db.commit()
    return {"message": f"Đã xếp thành công +{req.actual_qty} vào kệ {task['location_code']}!"}


# 6. API Công nhân bấm Xác nhận Quét QR Lấy hàng FEFO (Picking) trên Điện thoại
@router.post("/mobile/picking/confirm")
def confirm_picking(req: ScanConfirmRequest, db: Session = Depends(get_db)):
    task = db.execute(text("""
        SELECT pkt.id, pkt.stock_id, pkt.from_location_id, pkt.allocated_qty, pkt.batch_no,
               pkt.issue_detail_id, l.location_code, gid.product_id, gid.issue_id,
               gi.issue_code, p.barcode
        FROM picking_tasks pkt
        JOIN locations l ON pkt.from_location_id = l.id
        JOIN goods_issue_details gid ON pkt.issue_detail_id = gid.id
        JOIN goods_issues gi ON gid.issue_id = gi.id
        JOIN products p ON gid.product_id = p.id
        WHERE pkt.id = :tid AND pkt.status = 'allocated'
        FOR UPDATE OF pkt
    """), {"tid": req.task_id}).mappings().first()

    if not task:
        raise HTTPException(status_code=404, detail="Nhiệm vụ lấy hàng không tồn tại hoặc đã xong!")
    if req.scanned_qr.strip().upper() != task["location_code"].upper():
        raise HTTPException(status_code=400, detail=f"Sai vị trí! Phải lấy hàng tại ô {task['location_code']} theo chuẩn FEFO.")
    # UC6: xác thực đúng sản phẩm/lô bằng mã vạch bao bì
    if not req.scanned_barcode or req.scanned_barcode.strip() != task["barcode"]:
        raise HTTPException(status_code=400, detail="Sai mã vạch sản phẩm / lô hàng! Hãy quét lại mã vạch trên bao bì đúng lô chỉ định.")
    if req.actual_qty > task["allocated_qty"]:
        raise HTTPException(status_code=400, detail=f"Số lượng lấy ({req.actual_qty}) vượt số lượng giữ chỗ ({task['allocated_qty']})!")

    # Trừ tồn thực tế (On-hand) và giải phóng toàn bộ giữ chỗ (Allocated) của task
    stock = db.execute(text("""
        UPDATE inventory_stocks
        SET quantity_on_hand = quantity_on_hand - :qty,
            quantity_allocated = quantity_allocated - :alloc
        WHERE id = :sid
        RETURNING quantity_on_hand
    """), {"qty": req.actual_qty, "alloc": task["allocated_qty"], "sid": task["stock_id"]}).mappings().first()

    db.execute(text("""
        UPDATE picking_tasks SET picked_qty = :qty, status = 'picked', performed_by = :w, picked_at = CURRENT_TIMESTAMP
        WHERE id = :tid
    """), {"qty": req.actual_qty, "w": WORKER_ID, "tid": req.task_id})

    db.execute(text("""
        UPDATE goods_issue_details SET picked_qty = picked_qty + :qty WHERE id = :did
    """), {"qty": req.actual_qty, "did": task["issue_detail_id"]})

    # Trạng thái phiếu xuất: allocated -> picking -> completed
    remaining = db.execute(text("""
        SELECT COUNT(*) FROM picking_tasks pkt
        JOIN goods_issue_details gid ON pkt.issue_detail_id = gid.id
        WHERE gid.issue_id = :iid AND pkt.status = 'allocated'
    """), {"iid": task["issue_id"]}).scalar()
    db.execute(text("UPDATE goods_issues SET status = :st WHERE id = :iid"),
               {"st": "completed" if remaining == 0 else "picking", "iid": task["issue_id"]})

    add_ledger(db, ttype="PICK", ref=task["issue_code"], task_id=req.task_id,
               product_id=task["product_id"], batch_no=task["batch_no"],
               from_loc=task["from_location_id"], to_loc=None,
               change=-req.actual_qty, balance_after=stock["quantity_on_hand"], user_id=WORKER_ID)

    db.commit()
    return {"message": f"Đã xuất thành công -{req.actual_qty} từ kệ {task['location_code']}!"}


# 7. API Điều chuyển hàng giữa các Bin (FR4 - STOCK_TRANSFERS)
@router.post("/transfer/execute")
def execute_transfer(req: TransferRequest, db: Session = Depends(get_db)):
    src = db.execute(text("""
        SELECT s.id, s.location_id, s.product_id, s.batch_no, s.expiry_date, s.created_at,
               s.quantity_on_hand, s.quantity_allocated, s.quantity_available, l.location_code
        FROM inventory_stocks s JOIN locations l ON s.location_id = l.id
        WHERE s.id = :sid
        FOR UPDATE OF s
    """), {"sid": req.stock_id}).mappings().first()
    if not src:
        raise HTTPException(status_code=404, detail="Lô tồn kho nguồn không tồn tại!")
    if src["location_id"] == req.to_location_id:
        raise HTTPException(status_code=400, detail="Ô Bin đích phải khác ô Bin nguồn!")
    # BR02: chỉ được chuyển phần khả dụng, không động vào hàng đang giữ chỗ cho đơn xuất
    if req.transfer_qty > src["quantity_available"]:
        raise HTTPException(status_code=400,
                            detail=f"Chỉ chuyển được tối đa {src['quantity_available']} (phần còn lại đang giữ chỗ cho đơn xuất)!")

    check_bin_capacity(db, req.to_location_id, req.transfer_qty, src["product_id"])

    to_code = db.execute(text("SELECT location_code FROM locations WHERE id = :id"),
                         {"id": req.to_location_id}).scalar()

    transfer_code = make_code("PDC")
    t_id = db.execute(text("""
        INSERT INTO stock_transfers (transfer_code, warehouse_id, created_by, approved_by, status)
        VALUES (:code, :wh, :mgr, :mgr, 'completed') RETURNING id
    """), {"code": transfer_code, "wh": DEFAULT_WAREHOUSE_ID, "mgr": MANAGER_ID}).scalar()

    d_id = db.execute(text("""
        INSERT INTO stock_transfer_details (transfer_id, product_id, batch_no, from_location_id,
                                            to_location_id, transfer_qty, performed_by)
        VALUES (:t, :p, :b, :fl, :tl, :q, :u) RETURNING id
    """), {"t": t_id, "p": src["product_id"], "b": src["batch_no"], "fl": src["location_id"],
           "tl": req.to_location_id, "q": req.transfer_qty, "u": MANAGER_ID}).scalar()

    # Trừ Bin nguồn
    src_after = db.execute(text("""
        UPDATE inventory_stocks SET quantity_on_hand = quantity_on_hand - :q WHERE id = :sid
        RETURNING quantity_on_hand
    """), {"q": req.transfer_qty, "sid": req.stock_id}).scalar()

    # Cộng Bin đích; giữ nguyên created_at gốc của lô để không làm sai thứ tự FIFO (BR03)
    dst_after = db.execute(text("""
        INSERT INTO inventory_stocks (location_id, product_id, batch_no, expiry_date,
                                      quantity_on_hand, quantity_allocated, created_at)
        VALUES (:loc, :p, :b, :exp, :q, 0, :cat)
        ON CONFLICT (location_id, product_id, batch_no)
        DO UPDATE SET quantity_on_hand = inventory_stocks.quantity_on_hand + EXCLUDED.quantity_on_hand,
                      created_at = LEAST(inventory_stocks.created_at, EXCLUDED.created_at)
        RETURNING quantity_on_hand
    """), {"loc": req.to_location_id, "p": src["product_id"], "b": src["batch_no"],
           "exp": src["expiry_date"], "q": req.transfer_qty, "cat": src["created_at"]}).scalar()

    # Thẻ kho: 2 dòng (trừ ở Bin nguồn, cộng ở Bin đích) để balance_after đúng theo từng Bin
    add_ledger(db, ttype="TRANSFER", ref=transfer_code, task_id=d_id, product_id=src["product_id"],
               batch_no=src["batch_no"], from_loc=src["location_id"], to_loc=req.to_location_id,
               change=-req.transfer_qty, balance_after=src_after, user_id=MANAGER_ID)
    add_ledger(db, ttype="TRANSFER", ref=transfer_code, task_id=d_id, product_id=src["product_id"],
               batch_no=src["batch_no"], from_loc=src["location_id"], to_loc=req.to_location_id,
               change=req.transfer_qty, balance_after=dst_after, user_id=MANAGER_ID)

    db.commit()
    return {"message": f"Đã điều chuyển {req.transfer_qty} từ {src['location_code']} sang {to_code} (phiếu {transfer_code})!"}


# 8. API Kiểm kê & Duyệt cân bằng tồn kho (FR4 - STOCK_COUNTS, BR05)
@router.post("/count/reconcile")
def reconcile_count(req: StockCountRequest, db: Session = Depends(get_db)):
    s = db.execute(text("""
        SELECT s.id, s.location_id, s.product_id, s.batch_no, s.quantity_on_hand, s.quantity_allocated,
               l.location_code
        FROM inventory_stocks s JOIN locations l ON s.location_id = l.id
        WHERE s.id = :sid
        FOR UPDATE OF s
    """), {"sid": req.stock_id}).mappings().first()
    if not s:
        raise HTTPException(status_code=404, detail="Lô tồn kho cần kiểm kê không tồn tại!")

    system_qty = s["quantity_on_hand"]
    variance = req.actual_qty - system_qty   # BR05: variance_qty = actual_qty - system_qty

    # BR02: On_hand >= Allocated
    if req.actual_qty < s["quantity_allocated"]:
        raise HTTPException(
            status_code=400,
            detail=f"Số thực đếm ({req.actual_qty}) thấp hơn số đang giữ chỗ ({s['quantity_allocated']}). Hãy xử lý các lệnh lấy hàng đang chờ trước khi cân bằng kho!",
        )
    if variance > 0:
        check_bin_capacity(db, s["location_id"], variance, s["product_id"])

    count_code = make_code("PKK")
    c_id = db.execute(text("""
        INSERT INTO stock_counts (count_code, warehouse_id, created_by, approved_by, status)
        VALUES (:code, :wh, :mgr, :mgr, 'reconciled') RETURNING id
    """), {"code": count_code, "wh": DEFAULT_WAREHOUSE_ID, "mgr": MANAGER_ID}).scalar()

    d_id = db.execute(text("""
        INSERT INTO stock_count_details (count_id, location_id, product_id, batch_no,
                                         system_qty, actual_qty, counted_by)
        VALUES (:c, :loc, :p, :b, :sys, :act, :u) RETURNING id
    """), {"c": c_id, "loc": s["location_id"], "p": s["product_id"], "b": s["batch_no"],
           "sys": system_qty, "act": req.actual_qty, "u": MANAGER_ID}).scalar()

    if variance == 0:
        db.commit()
        return {"message": f"Kiểm kê {count_code} tại {s['location_code']}: số liệu khớp, không có chênh lệch."}

    # BR05: tồn kho chỉ cân bằng khi Quản lý duyệt phiếu (ở đây duyệt ngay khi bấm nút)
    db.execute(text("UPDATE inventory_stocks SET quantity_on_hand = :q WHERE id = :sid"),
               {"q": req.actual_qty, "sid": req.stock_id})

    add_ledger(db, ttype="COUNT_ADJUST", ref=count_code, task_id=d_id, product_id=s["product_id"],
               batch_no=s["batch_no"], from_loc=None, to_loc=s["location_id"],
               change=variance, balance_after=req.actual_qty, user_id=MANAGER_ID)

    db.commit()
    sign = "+" if variance > 0 else ""
    return {"message": f"Đã duyệt cân bằng {count_code} tại {s['location_code']}: hệ thống {system_qty}, thực đếm {req.actual_qty}, chênh lệch {sign}{variance}."}
