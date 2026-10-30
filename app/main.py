"""Điểm khởi chạy FastAPI:  uvicorn app.main:app --reload"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.core.config import CORS_ORIGINS, STATIC_DIR
from app.core.errors import register_exception_handlers
from app.web import web_router


def create_app() -> FastAPI:
    app = FastAPI(title="Hệ thống Quản lý Kho WMS - FEFO & QR Bin", version="3.0.0")

    # allow_origins=["*"] không đi cùng allow_credentials=True; token gửi bằng header Authorization nên không cần cookie
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"])
    register_exception_handlers(app)

    app.include_router(api_router)
    app.include_router(web_router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


app = create_app()
