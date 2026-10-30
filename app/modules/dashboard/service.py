"""FR5 - Dashboard: KPI, cảnh báo 3 cấp (Thiếu hàng / Vượt định mức / Hạn dùng), biểu đồ, thẻ kho gần nhất."""
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.utils import placeholders, rows, today
from app.modules.accounts.service import MANAGEABLE_ROLES
from app.modules.locations.service import list_locations
from app.modules.stocks.service import NEAR_EXPIRY_DAYS, list_ledger


def get_dashboard(db: Session, user: dict) -> dict:
    t = today()
    soon = t + timedelta(days=NEAR_EXPIRY_DAYS)

    kpi_row = db.execute(text("""
        SELECT COALESCE(SUM(quantity_on_hand), 0) AS total_on_hand,
               COALESCE(SUM(quantity_allocated), 0) AS total_allocated,
               COALESCE(SUM(quantity_available), 0) AS total_available
        FROM inventory_stocks
    """)).mappings().first()
    kpi = dict(kpi_row)

    low_stock = rows(db.execute(text("""
        SELECT p.id, p.sku, p.product_name, p.unit, p.min_safety_stock,
               COALESCE(SUM(s.quantity_available), 0) AS total_available
        FROM products p LEFT JOIN inventory_stocks s ON p.id = s.product_id
        WHERE p.is_active = TRUE AND p.min_safety_stock > 0
        GROUP BY p.id
        HAVING COALESCE(SUM(s.quantity_available), 0) <= p.min_safety_stock
        ORDER BY p.sku
    """)))

    over_stock = rows(db.execute(text("""
        SELECT p.id, p.sku, p.product_name, p.unit, p.max_safety_stock,
               COALESCE(SUM(s.quantity_on_hand), 0) AS total_on_hand
        FROM products p LEFT JOIN inventory_stocks s ON p.id = s.product_id
        WHERE p.is_active = TRUE AND p.max_safety_stock > 0
        GROUP BY p.id
        HAVING COALESCE(SUM(s.quantity_on_hand), 0) > p.max_safety_stock
        ORDER BY p.sku
    """)))

    expiring = rows(db.execute(text("""
        SELECT s.id, p.sku, p.product_name, l.location_code, s.batch_no, s.expiry_date,
               s.quantity_on_hand, s.quantity_available
        FROM inventory_stocks s
        JOIN products p ON s.product_id = p.id
        JOIN locations l ON s.location_id = l.id
        WHERE s.quantity_on_hand > 0 AND s.expiry_date <= :soon
        ORDER BY s.expiry_date ASC, s.id ASC LIMIT 50
    """), {"soon": soon}))
    for e in expiring:
        e["days_left"] = (e["expiry_date"] - t).days

    by_product = rows(db.execute(text("""
        SELECT p.sku, p.product_name, SUM(s.quantity_on_hand) AS on_hand, SUM(s.quantity_available) AS available
        FROM inventory_stocks s JOIN products p ON s.product_id = p.id
        GROUP BY p.id
        HAVING SUM(s.quantity_on_hand) > 0
        ORDER BY SUM(s.quantity_on_hand) DESC LIMIT 10
    """)))

    bin_usage = []
    for loc in list_locations(db):
        cap = float(loc["max_capacity_kg"]) or 1
        cur = float(loc["current_weight_kg"])
        bin_usage.append({"location_code": loc["location_code"], "status": loc["status"], "current_kg": cur,
                          "pending_kg": float(loc["pending_weight_kg"] or 0), "max_kg": cap,
                          "percent": round(cur / cap * 100, 1)})
    bin_usage.sort(key=lambda b: b["percent"], reverse=True)

    pending = {
        "putaway_tasks": db.execute(text("SELECT COUNT(*) FROM putaway_tasks WHERE status = 'pending'")).scalar() or 0,
        "picking_tasks": db.execute(text("SELECT COUNT(*) FROM picking_tasks WHERE status = 'allocated'")).scalar() or 0,
        "open_counts": db.execute(text("SELECT COUNT(*) FROM stock_counts WHERE status IN ('draft', 'counting')")).scalar() or 0,
        "pending_users": 0,
    }
    roles = list(MANAGEABLE_ROLES.get(user["role"], ()))
    if roles:
        clause, params = placeholders("r", roles)
        pending["pending_users"] = db.execute(text(
            f"SELECT COUNT(*) FROM users WHERE approval_status = 'pending' AND role IN ({clause})"), params).scalar() or 0

    return {
        "kpi": kpi,
        "alert_total": len(low_stock) + len(over_stock) + len(expiring),
        "low_stock_alerts": low_stock,
        "over_stock_alerts": over_stock,
        "expiring_alerts": expiring,
        "by_product": by_product,
        "bin_usage": bin_usage,
        "pending": pending,
        "recent_ledger": list_ledger(db, limit=8)["items"],
    }
