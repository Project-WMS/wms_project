"""Gom toàn bộ router nghiệp vụ dưới tiền tố /api (tương đương urls.py của dự án Django)."""
from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import engine
from app.modules.accounts.router import router as accounts_router
from app.modules.counts.router import router as counts_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.inbound.router import router as inbound_router
from app.modules.locations.router import router as locations_router
from app.modules.lookups.router import router as lookups_router
from app.modules.outbound.router import router as outbound_router
from app.modules.partners.router import router as partners_router
from app.modules.products.router import router as products_router
from app.modules.stocks.router import router as stocks_router
from app.modules.tasks.router import router as tasks_router
from app.modules.transfers.router import router as transfers_router

api_router = APIRouter(prefix="/api")

for _router in (accounts_router, dashboard_router, lookups_router, products_router, locations_router,
                partners_router, inbound_router, outbound_router, transfers_router, counts_router,
                stocks_router, tasks_router):
    api_router.include_router(_router)


@api_router.get("/health", tags=["Hệ thống"])
def health():
    return {"status": "ok", "message": "FastAPI hoạt động thành công"}


@api_router.get("/health/database", tags=["Hệ thống"])
def health_database():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "message": "Kết nối PostgreSQL thành công"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": "Không thể kết nối PostgreSQL", "detail": str(exc)[:200]}
