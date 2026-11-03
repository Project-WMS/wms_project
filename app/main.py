"""Điểm khởi chạy FastAPI:  uvicorn app.main:app --reload"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.core.config import BRAND_DIR, CORS_ORIGINS, STATIC_DIR
from app.core.errors import register_exception_handlers
from app.web import web_router


def create_app() -> FastAPI:
    app = FastAPI(title="Digital Warehouse", version="3.0.0")

    # allow_origins=["*"] không đi cùng allow_credentials=True; token gửi bằng header Authorization nên không cần cookie
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"])
    register_exception_handlers(app)

    app.include_router(api_router)
    app.include_router(web_router)

    @app.get("/brand/logo_avt.png", include_in_schema=False)
    def brand_symbol():
        return FileResponse(BRAND_DIR / "logo_avt.png", media_type="image/png")

    @app.get("/brand/logo_ten.png", include_in_schema=False)
    def brand_wordmark():
        return FileResponse(BRAND_DIR / "logo_ten.png", media_type="image/png")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


app = create_app()
