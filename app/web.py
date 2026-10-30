"""Các trang giao diện (HTML) - mỗi URL render một template kế thừa base.html (giống urls.py + views của Django)."""
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.core.config import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
web_router = APIRouter(include_in_schema=False)

# (đường dẫn, template, khóa menu đang chọn, tiêu đề trang, các đường dẫn tương thích SRS v3)
PAGES = [
    ("/", "pages/dashboard.html", "dashboard", "Tổng quan", ["/index.html"]),
    ("/products", "pages/products.html", "products", "Sản phẩm", []),
    ("/locations", "pages/locations.html", "locations", "Ô kệ & mã QR", []),
    ("/partners", "pages/partners.html", "partners", "Đối tác", []),
    ("/inbound", "pages/inbound.html", "inbound", "Nhập kho", []),
    ("/outbound", "pages/outbound.html", "outbound", "Xuất kho FEFO", []),
    ("/transfers", "pages/transfers.html", "transfers", "Điều chuyển", []),
    ("/counts", "pages/counts.html", "counts", "Kiểm kê", []),
    ("/stocks", "pages/stocks.html", "stocks", "Tồn kho", []),
    ("/ledger", "pages/ledger.html", "ledger", "Thẻ kho", []),
    ("/users", "pages/users.html", "users", "Nhân sự & duyệt tài khoản", []),
    ("/profile", "pages/profile.html", "profile", "Hồ sơ cá nhân", []),
    ("/login", "pages/login.html", "login", "Đăng nhập", ["/login.html"]),
    ("/mobile", "pages/mobile.html", "mobile", "WMS Mobile", ["/mobile.html"]),
]


def _register(path: str, template: str, key: str, title: str, aliases: list) -> None:
    def view(request: Request):
        return templates.TemplateResponse(request, template, {"page": key, "page_title": title})
    view.__name__ = f"page_{key}"
    for p in [path, *aliases]:
        web_router.add_api_route(p, view, methods=["GET"])


for _args in PAGES:
    _register(*_args)
