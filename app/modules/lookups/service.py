"""Dữ liệu cho các ô chọn (select) trong biểu mẫu: sản phẩm đang hoạt động, ô kệ, nhà cung cấp, khách hàng."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.utils import rows, today
from app.modules.locations.service import list_locations
from app.modules.partners.service import list_partners


def get_lookups(db: Session) -> dict:
    avail = {r["product_id"]: r["available"] for r in rows(db.execute(text("""
        SELECT s.product_id, SUM(s.quantity_available) AS available
        FROM inventory_stocks s JOIN locations l ON s.location_id = l.id
        WHERE s.expiry_date >= :today AND l.status = 'active'
        GROUP BY s.product_id
    """), {"today": today()}))}
    products = rows(db.execute(text("""
        SELECT id, sku, barcode, product_name, unit, unit_weight_kg
        FROM products WHERE is_active = TRUE ORDER BY sku
    """)))
    for p in products:
        p["available"] = avail.get(p["id"], 0)
    locations = [{"id": l["id"], "location_code": l["location_code"], "status": l["status"],
                  "max_capacity_kg": l["max_capacity_kg"], "current_weight_kg": l["current_weight_kg"],
                  "pending_weight_kg": l["pending_weight_kg"], "lot_count": l["lot_count"]}
                 for l in list_locations(db)]
    return {
        "products": products,
        "locations": locations,
        "suppliers": list_partners(db, "supplier"),
        "customers": list_partners(db, "customer"),
    }
