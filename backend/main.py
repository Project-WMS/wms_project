import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import text

from backend.database import engine
from backend.auth import router as auth_router
from backend.master import router as master_router
from backend.routers import router

app = FastAPI(title="Hệ thống Quản lý Kho WMS - FEFO & QR")

# 1. Cấu hình CORS (Cho phép mọi nguồn để dễ dàng test giữa Frontend và Backend)
# Lưu ý: allow_origins=["*"] không đi cùng allow_credentials=True (trình duyệt sẽ từ chối)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Đăng ký các API chính của hệ thống
app.include_router(auth_router)
app.include_router(master_router)
app.include_router(router)

# 3. Các API Health Check (Kiểm tra trạng thái Backend và Database)
@app.get("/api/health")
def kiem_tra_he_thong():
    return {
        "status": "ok",
        "message": "FastAPI hoạt động thành công"
    }

@app.get("/api/health/database")
def kiem_tra_database():
    try:
        with engine.connect() as ket_noi:
            ket_noi.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "message": "Kết nối PostgreSQL thành công"
        }
    except Exception as loi:
        return {
            "status": "error",
            "message": "Không thể kết nối PostgreSQL",
            "detail": str(loi)
        }

# 4. Phục vụ giao diện Frontend (HTML, CSS, JS)
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

# Mount thư mục static (CSS, JS, Hình ảnh) nếu thư mục frontend tồn tại
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
def serve_desktop():
    """Trang chủ mặc định phục vụ giao diện Desktop. Nếu chưa có file HTML, trả về JSON."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "message": "Chào mừng đến với hệ thống WMS",
        "status": "Backend đang hoạt động (Chưa tìm thấy file index.html)"
    }

@app.get("/login")
def serve_login():
    """Trang đăng nhập / đăng ký (FR0)."""
    return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))


@app.get("/mobile")
def serve_mobile():
    """Giao diện dành riêng cho máy quét mã QR / Điện thoại di động"""
    return FileResponse(os.path.join(FRONTEND_DIR, "mobile.html"))
