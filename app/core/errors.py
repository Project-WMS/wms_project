"""NFR3: chuẩn hóa lỗi 422/400/500 thành thông báo tiếng Việt, không lộ chi tiết kỹ thuật."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger("wms")

FIELD_LABELS = {
    "username": "Tên đăng nhập", "password": "Mật khẩu", "full_name": "Họ và tên", "role": "Vai trò",
    "old_password": "Mật khẩu hiện tại", "new_password": "Mật khẩu mới",
    "sku": "Mã SKU", "barcode": "Mã vạch", "product_name": "Tên sản phẩm", "unit": "Đơn vị tính",
    "unit_weight_kg": "Trọng lượng đơn vị", "min_safety_stock": "Tồn tối thiểu", "max_safety_stock": "Tồn tối đa",
    "zone": "Khu", "aisle": "Dãy", "rack": "Kệ", "shelf_level": "Tầng", "bin": "Ô", "max_capacity_kg": "Sức chứa tối đa",
    "partner_code": "Mã đối tác", "partner_name": "Tên đối tác", "type": "Loại", "phone": "Điện thoại",
    "supplier_id": "Nhà cung cấp", "customer_id": "Khách hàng", "product_id": "Sản phẩm", "batch_no": "Số lô",
    "expiry_date": "Hạn sử dụng", "quantity": "Số lượng", "to_location_id": "Ô kệ đích", "location_id": "Ô kệ",
    "stock_id": "Lô tồn kho", "actual_qty": "Số lượng thực tế", "scanned_qr": "Mã QR ô kệ",
    "scanned_barcode": "Mã vạch sản phẩm", "task_id": "Nhiệm vụ", "items": "Danh sách hàng", "lines": "Danh sách dòng",
}


def _issue_text(issue: dict) -> str:
    loc = [str(p) for p in issue.get("loc", []) if p not in ("body", "query", "path")]
    field = next((FIELD_LABELS[p] for p in reversed(loc) if p in FIELD_LABELS), "Thông tin")
    kind = issue.get("type", "")
    ctx = issue.get("ctx") or {}
    if kind == "missing":
        return f"{field}: vui lòng nhập thông tin bắt buộc."
    if kind == "greater_than":
        return f"{field}: phải lớn hơn {ctx.get('gt', 0)}."
    if kind == "greater_than_equal":
        return f"{field}: không được nhỏ hơn {ctx.get('ge', 0)}."
    if kind in ("less_than", "less_than_equal"):
        return f"{field}: vượt quá giá trị cho phép."
    if kind == "string_too_short":
        return f"{field}: cần ít nhất {ctx.get('min_length', 1)} ký tự."
    if kind == "string_too_long":
        return f"{field}: không được vượt quá {ctx.get('max_length', '')} ký tự."
    if kind in ("too_short",):
        return f"{field}: cần có ít nhất {ctx.get('min_length', 1)} dòng."
    if kind in ("too_long",):
        return f"{field}: có quá nhiều dòng."
    if kind in ("int_parsing", "int_from_float", "int_type"):
        return f"{field}: vui lòng nhập số nguyên hợp lệ."
    if kind in ("decimal_parsing", "float_parsing", "decimal_type", "float_type"):
        return f"{field}: vui lòng nhập số hợp lệ."
    if kind.startswith("date"):
        return f"{field}: vui lòng chọn ngày hợp lệ."
    if kind in ("literal_error", "enum"):
        return f"{field}: giá trị không hợp lệ."
    return f"{field}: thông tin không hợp lệ."


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        messages = []
        for issue in exc.errors():
            text_ = _issue_text(issue)
            if text_ not in messages:
                messages.append(text_)
        return JSONResponse(status_code=422, content={"detail": " ".join(messages)})

    @app.exception_handler(IntegrityError)
    async def integrity_handler(request: Request, exc: IntegrityError):
        logger.warning("IntegrityError: %s", exc)
        return JSONResponse(status_code=400, content={
            "detail": "Dữ liệu bị trùng hoặc đang được sử dụng ở nơi khác nên không thể thực hiện thao tác này."})

    @app.exception_handler(Exception)
    async def unexpected_handler(request: Request, exc: Exception):
        logger.exception("Lỗi không xác định tại %s", request.url.path)
        return JSONResponse(status_code=500, content={
            "detail": "Hệ thống gặp lỗi bất ngờ. Vui lòng thử lại hoặc liên hệ quản trị viên."})
