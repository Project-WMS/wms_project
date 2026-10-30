"""Hàm tiện ích dùng chung: thời gian, sinh mã chứng từ, chuyển kiểu dữ liệu."""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.core.config import UTC_OFFSET_HOURS

LOCAL_TZ = timezone(timedelta(hours=UTC_OFFSET_HOURS))


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def today() -> date:
    """Ngày hiện tại theo giờ địa phương (dùng để so sánh hạn sử dụng)."""
    return now_local().date()


def local_day_start_utc(d: date) -> datetime:
    """00:00 của ngày địa phương `d`, quy đổi sang UTC (naive) để so sánh với cột TIMESTAMP trong DB."""
    return datetime(d.year, d.month, d.day) - timedelta(hours=UTC_OFFSET_HOURS)


def make_code(prefix: str) -> str:
    """BR01: [PNK|PXK|PDC|PKK]-[YYYYMMDD]-[HHMMSS]-[4 ký tự ngẫu nhiên]."""
    return f"{prefix}-{now_local():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4].upper()}"


def to_decimal(value) -> Decimal:
    return Decimal(str(value if value is not None else 0))


def rows(result) -> list:
    return [dict(r) for r in result.mappings().all()]


def first(result):
    r = result.mappings().first()
    return dict(r) if r else None


def placeholders(prefix: str, values: list):
    """Sinh mệnh đề IN (:p0, :p1, ...) và dict tham số tương ứng (portable, không cần expanding bindparam)."""
    params = {f"{prefix}{i}": v for i, v in enumerate(values)}
    clause = ", ".join(f":{k}" for k in params) or "NULL"
    return clause, params
