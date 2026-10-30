# WMS – Hệ thống Quản lý Kho (FEFO & mã QR Bin)

Web quản lý **kho** (không gồm bán hàng) theo đặc tả **SRS v3**: nhập kho → xếp kệ bằng quét QR → xuất kho tự động theo **FEFO** → điều chuyển → kiểm kê → thẻ kho bất biến.

- **Backend:** FastAPI + SQLAlchemy (SQL thuần) + PostgreSQL/Supabase, xác thực JWT HS256, mật khẩu PBKDF2.
- **Frontend:** HTML + Bootstrap 5 + JavaScript thuần, giao diện quản trị nhiều trang (sidebar) và trang Mobile quét QR cho công nhân.

## 1. Cài đặt & chạy

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # rồi điền DATABASE_URL (Supabase) hoặc DB_HOST/DB_USER/..., đặt WMS_SECRET_KEY

python manage.py init-db --demo     # tạo 17 bảng + trigger BR06 + dữ liệu & 3 tài khoản mẫu
# (CSDL thật, không muốn dữ liệu mẫu:)  python manage.py init-db  &&  python manage.py create-admin

python manage.py runserver          # http://127.0.0.1:8000/login
```

Tài khoản mẫu (chỉ khi dùng `--demo`): `admin`, `thukho`, `congnhan` – mật khẩu `Wms@2026` (đổi bằng `SEED_PASSWORD` trong `.env`, **hãy đổi ngay khi dùng thật**).

Các lệnh khác: `python manage.py init-db --reset` (xóa sạch rồi tạo lại, có hỏi xác nhận), `python manage.py runserver --host 0.0.0.0 --port 8000`, `python -m unittest tests.test_security -v`.

> **Camera trên điện thoại** chỉ hoạt động khi trang chạy qua **HTTPS** hoặc `localhost` (quy định của trình duyệt). Truy cập bằng `http://<IP-LAN>:8000` vẫn dùng được nhưng phải nhập mã bằng tay; muốn quét camera hãy chạy sau HTTPS (Cloudflare Tunnel, ngrok, reverse proxy...).

## 2. Cấu trúc thư mục (mỗi chức năng = một module, giống app của Django)

```
wms_project/
├── manage.py                 # runserver | init-db | create-admin   (như manage.py của Django)
├── requirements.txt  .env.example  .gitignore
├── scripts/
│   ├── init_db.py            # 17 bảng, trigger BR06, migration, dữ liệu mẫu
│   └── create_admin.py
├── app/
│   ├── main.py               # tạo FastAPI app, gắn router, static, xử lý lỗi
│   ├── api.py                # gom router /api/*          (≈ urls.py gốc)
│   ├── web.py                # URL các trang HTML          (≈ views trả template)
│   ├── core/                 # config, database, security (JWT/PBKDF2), deps (phân quyền), errors (422→tiếng Việt), utils
│   └── modules/              # MỖI THƯ MỤC = 1 "app": router.py · schemas.py · service.py
│       ├── accounts/   đăng ký, đăng nhập, duyệt tài khoản phân cấp, đổi mật khẩu      (FR0)
│       ├── products/   danh mục sản phẩm, khóa/mở khóa                                 (FR1)
│       ├── locations/  ô kệ (Bin), mã QR, kiểm tra tải trọng BR04                      (FR1)
│       ├── partners/   nhà cung cấp, khách hàng                                        (FR1)
│       ├── inbound/    phiếu nhập nhiều dòng → lệnh xếp kệ; hủy phiếu                  (FR2)
│       ├── outbound/   phiếu xuất nhiều dòng → FEFO giữ chỗ → lệnh lấy hàng; hủy phiếu (FR3)
│       ├── transfers/  điều chuyển giữa các Bin                                        (FR4)
│       ├── counts/     kiểm kê: lập phiếu → nhập số đếm → duyệt cân bằng              (FR4)
│       ├── stocks/     tồn kho theo lô (FEFO) + thẻ kho bất biến                       (FR5)
│       ├── tasks/      API Mobile: xếp kệ & lấy hàng bằng quét QR/mã vạch              (FR2/FR3)
│       ├── dashboard/  KPI, cảnh báo 3 cấp, biểu đồ, biến động gần nhất                (FR5)
│       └── lookups/    dữ liệu cho các ô chọn trong biểu mẫu
└── frontend/
    ├── templates/        # base.html + partials (sidebar, topbar) + pages/*.html (extends base như Django)
    └── static/
        ├── css/          # style.css (quản trị), mobile.css
        └── js/           # core/ (api, ui, layout, lookups)  ·  pages/ (mỗi trang một file)
```

Luồng một yêu cầu: `router.py` (nhận request, kiểm quyền bằng `Depends`) → `service.py` (nghiệp vụ + SQL, `commit` ở cuối) → trả JSON.

## 3. Trang & phân quyền

| URL | Nội dung | Vai trò |
|---|---|---|
| `/login` (`/login.html`) | Đăng nhập / đăng ký (chờ duyệt) | tất cả |
| `/` (`/index.html`) | Dashboard | admin, manager |
| `/products` `/locations` `/partners` | Danh mục (thêm/sửa, khóa, in tem QR) | admin, manager |
| `/inbound` `/outbound` `/transfers` `/counts` | Nghiệp vụ kho | admin, manager |
| `/stocks` `/ledger` | Tồn kho theo lô, thẻ kho (lọc, xuất CSV) | admin, manager |
| `/users` | Duyệt/khóa tài khoản (BR07) | admin, manager |
| `/profile` | Hồ sơ, đổi mật khẩu | tất cả |
| `/mobile` (`/mobile.html`) | Xếp kệ & lấy hàng quét QR | tất cả (công nhân vào thẳng trang này) |

Tài liệu API tự sinh: `/docs`.

## 4. Đối chiếu SRS v3

Đã có: JWT 12 giờ; duyệt tài khoản phân cấp; danh mục động; BR01 (mã chứng từ), BR02 (`on_hand ≥ allocated`), BR03 (FEFO rồi FIFO, bỏ lô hết hạn), BR04 (tải trọng Bin, tính cả hàng chờ xếp), BR05 (kiểm kê chỉ đổi tồn khi duyệt), BR06 (trigger chặn sửa/xóa thẻ kho), BR07; cảnh báo thiếu hàng / vượt định mức / cận date ≤ 30 ngày; thông báo lỗi tiếng Việt; tự làm mới 3–5 giây mà không mất dữ liệu đang nhập; rung khi quét sai.

Bổ sung so với SRS: phiếu nhiều dòng; hủy phiếu nhập/xuất chưa thực hiện; phiếu kiểm kê theo ô kệ có bước duyệt cân bằng; đổi mật khẩu; xuất CSV; lưới QR in tem; kiểm tra cùng số lô phải cùng hạn dùng; chặn nhập hàng đã hết hạn.
Thay đổi CSDL duy nhất: thêm cột `products.is_active` và một số chỉ mục (tự áp dụng khi chạy `init-db`, không mất dữ liệu).

Chưa làm (ngoài phạm vi): quên mật khẩu, giới hạn số lần đăng nhập sai, nhiều kho (hiện cố định WH01), xếp kệ thiếu số lượng không tự tạo lệnh bù (phần thiếu xử lý bằng kiểm kê/phiếu bổ sung).

## 5. Lưu ý bảo mật khi triển khai thật

- Đặt `WMS_SECRET_KEY` riêng và đổi mật khẩu tài khoản mẫu; không commit file `.env`.
- Chạy sau HTTPS; đặt `WMS_CORS_ORIGINS` đúng tên miền thay cho `*`.
- Thời gian lưu trong DB theo **UTC**, giao diện hiển thị giờ Việt Nam (UTC+7).
