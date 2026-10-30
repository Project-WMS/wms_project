"""Cấu hình hệ thống, đọc từ biến môi trường / file .env ở thư mục gốc dự án."""
import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env", override=True)

FRONTEND_DIR = BASE_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"

# Hệ thống hiện vận hành một kho mặc định WH01 (SRS v3 - bảng warehouses)
DEFAULT_WAREHOUSE_ID = 1

# Giờ địa phương (Việt Nam = UTC+7). Dữ liệu thời gian trong DB luôn lưu theo UTC.
UTC_OFFSET_HOURS = int(os.getenv("WMS_UTC_OFFSET", "7"))

TOKEN_TTL_SECONDS = int(os.getenv("WMS_TOKEN_HOURS", "12")) * 3600

CORS_ORIGINS = [o.strip() for o in os.getenv("WMS_CORS_ORIGINS", "*").split(",") if o.strip()]


def database_url() -> str:
    """Ưu tiên DATABASE_URL (Supabase); nếu không có thì ghép từ DB_HOST/DB_USER/..."""
    url = os.getenv("DATABASE_URL")
    if url:
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql+psycopg2://"):
            url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
        return url
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "wms_db")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


def secret_key() -> bytes:
    """Khóa ký JWT. Khi triển khai thật BẮT BUỘC đặt WMS_SECRET_KEY trong .env."""
    key = os.getenv("WMS_SECRET_KEY")
    if key:
        return key.encode()
    # Dự phòng cho môi trường dev: ổn định qua các lần restart nhưng kém an toàn hơn khóa riêng
    return hashlib.sha256(("wms-dev-secret|" + database_url()).encode()).digest()
