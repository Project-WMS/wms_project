"""Tồn kho chi tiết theo lô/Bin (FEFO) và Thẻ kho bất biến (BR06)."""
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.utils import first, local_day_start_utc, rows, today

NEAR_EXPIRY_DAYS = 30


def add_ledger(db: Session, *, ttype: str, ref: str, task_id, product_id: int, batch_no: str,
               from_loc, to_loc, change: int, balance_after: int, user_id: int) -> None:
    """Chỉ INSERT vào stock_ledger (BR06 - bất biến; DB còn có trigger chặn UPDATE/DELETE/TRUNCATE)."""
    db.execute(text("""
        INSERT INTO stock_ledger (transaction_type, reference_code, task_id, product_id, batch_no,
                                  from_location_id, to_location_id, quantity_change, balance_after, performed_by)
        VALUES (:t, :ref, :tid, :p, :b, :fl, :tl, :chg, :bal, :u)
    """), {"t": ttype, "ref": ref, "tid": task_id, "p": product_id, "b": batch_no,
           "fl": from_loc, "tl": to_loc, "chg": change, "bal": balance_after, "u": user_id})


def _expiry_info(expiry_date, today_) -> dict:
    days = (expiry_date - today_).days
    status = "expired" if days < 0 else ("near" if days <= NEAR_EXPIRY_DAYS else "ok")
    return {"days_left": days, "expiry_status": status}


def list_stocks(db: Session, q: str = None, product_id: int = None, location_id: int = None,
                expiry: str = None, include_empty: bool = False) -> list:
    where, params = [], {}
    if not include_empty:
        where.append("s.quantity_on_hand > 0")
    if q:
        where.append("(LOWER(p.sku) LIKE :q OR LOWER(p.product_name) LIKE :q OR LOWER(s.batch_no) LIKE :q "
                     "OR LOWER(l.location_code) LIKE :q)")
        params["q"] = f"%{q.strip().lower()}%"
    if product_id:
        where.append("s.product_id = :pid")
        params["pid"] = product_id
    if location_id:
        where.append("s.location_id = :lid")
        params["lid"] = location_id
    t = today()
    if expiry == "expired":
        where.append("s.expiry_date < :today")
        params["today"] = t
    elif expiry == "near":
        where.append("s.expiry_date >= :today AND s.expiry_date <= :soon")
        params.update({"today": t, "soon": t + timedelta(days=NEAR_EXPIRY_DAYS)})
    elif expiry == "ok":
        where.append("s.expiry_date > :soon")
        params["soon"] = t + timedelta(days=NEAR_EXPIRY_DAYS)
    sql = f"""
        SELECT s.id, s.location_id, s.product_id, l.location_code, l.status AS location_status,
               p.sku, p.barcode, p.product_name, p.unit, p.unit_weight_kg,
               s.batch_no, s.expiry_date, s.quantity_on_hand, s.quantity_allocated, s.quantity_available,
               s.created_at
        FROM inventory_stocks s
        JOIN locations l ON s.location_id = l.id
        JOIN products p ON s.product_id = p.id
        {('WHERE ' + ' AND '.join(where)) if where else ''}
        ORDER BY s.expiry_date ASC, s.created_at ASC, l.location_code ASC, s.id ASC
    """
    items = rows(db.execute(text(sql), params))
    for it in items:
        it.update(_expiry_info(it["expiry_date"], t))
        it["weight_kg"] = float(it["quantity_on_hand"]) * float(it["unit_weight_kg"])
    return items


def list_ledger(db: Session, *, limit: int = 20, offset: int = 0, product_id: int = None, ttype: str = None,
                date_from=None, date_to=None, q: str = None) -> dict:
    where, params = [], {}
    if product_id:
        where.append("sl.product_id = :pid")
        params["pid"] = product_id
    if ttype:
        where.append("sl.transaction_type = :tt")
        params["tt"] = ttype
    if date_from:
        where.append("sl.created_at >= :df")
        params["df"] = local_day_start_utc(date_from)
    if date_to:
        where.append("sl.created_at < :dt")
        params["dt"] = local_day_start_utc(date_to + timedelta(days=1))
    if q:
        where.append("(LOWER(sl.reference_code) LIKE :q OR LOWER(sl.batch_no) LIKE :q OR LOWER(p.sku) LIKE :q "
                     "OR LOWER(p.product_name) LIKE :q)")
        params["q"] = f"%{q.strip().lower()}%"
    cond = ('WHERE ' + ' AND '.join(where)) if where else ''
    total = db.execute(text(f"""
        SELECT COUNT(*) FROM stock_ledger sl JOIN products p ON sl.product_id = p.id {cond}
    """), params).scalar()
    items = rows(db.execute(text(f"""
        SELECT sl.id, sl.transaction_type, sl.reference_code, p.sku, p.product_name, p.unit, sl.batch_no,
               lf.location_code AS from_loc, lt.location_code AS to_loc,
               sl.quantity_change, sl.balance_after, u.full_name AS performer, sl.created_at
        FROM stock_ledger sl
        JOIN products p ON sl.product_id = p.id
        LEFT JOIN locations lf ON sl.from_location_id = lf.id
        LEFT JOIN locations lt ON sl.to_location_id = lt.id
        JOIN users u ON sl.performed_by = u.id
        {cond}
        ORDER BY sl.id DESC
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": limit, "offset": offset}))
    return {"items": items, "total": total or 0}
