"""Khởi tạo / đồng bộ cấu trúc CSDL PostgreSQL (Supabase) theo SRS v3: 17 bảng + trigger BR06.

  python manage.py init-db            # tạo bảng, trigger, kho WH01 (không xóa dữ liệu thật)
  python manage.py init-db --demo     # thêm dữ liệu mẫu + 3 tài khoản mẫu (chỉ khi CSDL chưa có tài khoản)
  python manage.py init-db --reset    # XÓA SẠCH toàn bộ bảng rồi tạo lại
"""
import os
from datetime import date, timedelta

from sqlalchemy import text

from app.core.security import hash_password, is_hashed

TABLE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        username VARCHAR(50) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        full_name VARCHAR(100) NOT NULL,
        role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'manager', 'worker')),
        approval_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (approval_status IN ('pending', 'approved', 'rejected')),
        approved_by INT NULL REFERENCES users(id),
        approved_at TIMESTAMP NULL,
        is_active BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """
    CREATE TABLE IF NOT EXISTS partners (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        partner_code VARCHAR(30) NOT NULL UNIQUE,
        partner_name VARCHAR(150) NOT NULL,
        type VARCHAR(20) NOT NULL CHECK (type IN ('supplier', 'customer')),
        phone VARCHAR(20) NULL,
        address TEXT NULL
    )""",
    """
    CREATE TABLE IF NOT EXISTS warehouses (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        warehouse_code VARCHAR(20) NOT NULL UNIQUE,
        warehouse_name VARCHAR(100) NOT NULL,
        address TEXT NULL
    )""",
    """
    CREATE TABLE IF NOT EXISTS locations (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        warehouse_id INT NOT NULL REFERENCES warehouses(id),
        location_code VARCHAR(50) NOT NULL UNIQUE,
        zone VARCHAR(10) NOT NULL,
        aisle VARCHAR(10) NOT NULL,
        rack VARCHAR(10) NOT NULL,
        shelf_level VARCHAR(10) NOT NULL,
        bin VARCHAR(10) NOT NULL,
        max_capacity_kg DECIMAL(12,2) NOT NULL CHECK (max_capacity_kg > 0),
        status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'maintenance', 'locked'))
    )""",
    """
    CREATE TABLE IF NOT EXISTS products (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        sku VARCHAR(50) NOT NULL UNIQUE,
        barcode VARCHAR(50) NOT NULL UNIQUE,
        product_name VARCHAR(200) NOT NULL,
        unit VARCHAR(20) NOT NULL,
        unit_weight_kg DECIMAL(10,3) NOT NULL CHECK (unit_weight_kg > 0),
        min_safety_stock INT NOT NULL DEFAULT 0 CHECK (min_safety_stock >= 0),
        max_safety_stock INT NOT NULL DEFAULT 0 CHECK (max_safety_stock >= 0),
        approval_status VARCHAR(20) NOT NULL DEFAULT 'approved' CHECK (approval_status IN ('pending', 'approved', 'rejected')),
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_by INT NULL REFERENCES users(id),
        approved_by INT NULL REFERENCES users(id),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """
    CREATE TABLE IF NOT EXISTS inventory_stocks (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        location_id INT NOT NULL REFERENCES locations(id),
        product_id INT NOT NULL REFERENCES products(id),
        batch_no VARCHAR(50) NOT NULL,
        expiry_date DATE NOT NULL,
        quantity_on_hand INT NOT NULL DEFAULT 0 CHECK (quantity_on_hand >= 0),
        quantity_allocated INT NOT NULL DEFAULT 0 CHECK (quantity_allocated >= 0),
        quantity_available INT GENERATED ALWAYS AS (quantity_on_hand - quantity_allocated) STORED,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT chk_on_hand_ge_allocated CHECK (quantity_on_hand >= quantity_allocated),
        CONSTRAINT uq_stock_location_product_batch UNIQUE (location_id, product_id, batch_no)
    )""",
    """
    CREATE TABLE IF NOT EXISTS goods_receipts (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        receipt_code VARCHAR(40) NOT NULL UNIQUE,
        supplier_id INT NOT NULL REFERENCES partners(id),
        warehouse_id INT NOT NULL REFERENCES warehouses(id),
        created_by INT NOT NULL REFERENCES users(id),
        approved_by INT NULL REFERENCES users(id),
        status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'putting_away', 'completed')),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        approved_at TIMESTAMP NULL
    )""",
    """
    CREATE TABLE IF NOT EXISTS goods_receipt_details (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        receipt_id INT NOT NULL REFERENCES goods_receipts(id) ON DELETE CASCADE,
        product_id INT NOT NULL REFERENCES products(id),
        batch_no VARCHAR(50) NOT NULL,
        expiry_date DATE NOT NULL,
        expected_qty INT NOT NULL CHECK (expected_qty > 0),
        putaway_qty INT NOT NULL DEFAULT 0 CHECK (putaway_qty >= 0)
    )""",
    """
    CREATE TABLE IF NOT EXISTS putaway_tasks (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        receipt_detail_id INT NOT NULL REFERENCES goods_receipt_details(id) ON DELETE CASCADE,
        to_location_id INT NOT NULL REFERENCES locations(id),
        assigned_qty INT NOT NULL CHECK (assigned_qty > 0),
        actual_qty INT NULL CHECK (actual_qty >= 0),
        status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed')),
        stock_id INT NULL REFERENCES inventory_stocks(id),
        performed_by INT NULL REFERENCES users(id),
        completed_at TIMESTAMP NULL
    )""",
    """
    CREATE TABLE IF NOT EXISTS goods_issues (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        issue_code VARCHAR(40) NOT NULL UNIQUE,
        customer_id INT NOT NULL REFERENCES partners(id),
        warehouse_id INT NOT NULL REFERENCES warehouses(id),
        created_by INT NOT NULL REFERENCES users(id),
        approved_by INT NULL REFERENCES users(id),
        status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'allocated', 'picking', 'completed')),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        approved_at TIMESTAMP NULL
    )""",
    """
    CREATE TABLE IF NOT EXISTS goods_issue_details (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        issue_id INT NOT NULL REFERENCES goods_issues(id) ON DELETE CASCADE,
        product_id INT NOT NULL REFERENCES products(id),
        requested_qty INT NOT NULL CHECK (requested_qty > 0),
        picked_qty INT NOT NULL DEFAULT 0 CHECK (picked_qty >= 0)
    )""",
    """
    CREATE TABLE IF NOT EXISTS picking_tasks (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        issue_detail_id INT NOT NULL REFERENCES goods_issue_details(id) ON DELETE CASCADE,
        from_location_id INT NOT NULL REFERENCES locations(id),
        stock_id INT NOT NULL REFERENCES inventory_stocks(id),
        batch_no VARCHAR(50) NOT NULL,
        allocated_qty INT NOT NULL CHECK (allocated_qty > 0),
        picked_qty INT NULL CHECK (picked_qty >= 0),
        status VARCHAR(20) NOT NULL DEFAULT 'allocated' CHECK (status IN ('allocated', 'picked')),
        performed_by INT NULL REFERENCES users(id),
        picked_at TIMESTAMP NULL
    )""",
    """
    CREATE TABLE IF NOT EXISTS stock_transfers (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        transfer_code VARCHAR(40) NOT NULL UNIQUE,
        warehouse_id INT NOT NULL REFERENCES warehouses(id),
        created_by INT NOT NULL REFERENCES users(id),
        approved_by INT NULL REFERENCES users(id),
        status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'completed')),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """
    CREATE TABLE IF NOT EXISTS stock_transfer_details (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        transfer_id INT NOT NULL REFERENCES stock_transfers(id) ON DELETE CASCADE,
        product_id INT NOT NULL REFERENCES products(id),
        batch_no VARCHAR(50) NOT NULL,
        from_location_id INT NOT NULL REFERENCES locations(id),
        to_location_id INT NOT NULL REFERENCES locations(id),
        transfer_qty INT NOT NULL CHECK (transfer_qty > 0),
        performed_by INT NULL REFERENCES users(id)
    )""",
    """
    CREATE TABLE IF NOT EXISTS stock_counts (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        count_code VARCHAR(40) NOT NULL UNIQUE,
        warehouse_id INT NOT NULL REFERENCES warehouses(id),
        created_by INT NOT NULL REFERENCES users(id),
        approved_by INT NULL REFERENCES users(id),
        status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'counting', 'reconciled')),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """
    CREATE TABLE IF NOT EXISTS stock_count_details (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        count_id INT NOT NULL REFERENCES stock_counts(id) ON DELETE CASCADE,
        location_id INT NOT NULL REFERENCES locations(id),
        product_id INT NOT NULL REFERENCES products(id),
        batch_no VARCHAR(50) NOT NULL,
        system_qty INT NOT NULL,
        actual_qty INT NOT NULL DEFAULT 0 CHECK (actual_qty >= 0),
        variance_qty INT GENERATED ALWAYS AS (actual_qty - system_qty) STORED,
        counted_by INT NULL REFERENCES users(id)
    )""",
    """
    CREATE TABLE IF NOT EXISTS stock_ledger (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        transaction_type VARCHAR(30) NOT NULL CHECK (transaction_type IN ('PUTAWAY', 'PICK', 'TRANSFER', 'COUNT_ADJUST')),
        reference_code VARCHAR(40) NOT NULL,
        task_id INT NULL,
        product_id INT NOT NULL REFERENCES products(id),
        batch_no VARCHAR(50) NOT NULL,
        from_location_id INT NULL REFERENCES locations(id),
        to_location_id INT NULL REFERENCES locations(id),
        quantity_change INT NOT NULL,
        balance_after INT NOT NULL,
        performed_by INT NOT NULL REFERENCES users(id),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
]

# Đồng bộ cho CSDL cũ đã tạo từ các phiên bản trước (an toàn khi chạy lặp lại)
MIGRATION_STATEMENTS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20) NOT NULL DEFAULT 'approved'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_by INT NULL REFERENCES users(id)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20) NOT NULL DEFAULT 'approved'",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS created_by INT NULL REFERENCES users(id)",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS approved_by INT NULL REFERENCES users(id)",
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
]

INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_stocks_product ON inventory_stocks(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_stocks_expiry ON inventory_stocks(expiry_date)",
    "CREATE INDEX IF NOT EXISTS idx_putaway_status ON putaway_tasks(status)",
    "CREATE INDEX IF NOT EXISTS idx_picking_status ON picking_tasks(status)",
    "CREATE INDEX IF NOT EXISTS idx_ledger_product ON stock_ledger(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_ledger_created ON stock_ledger(created_at)",
]

# BR06: thẻ kho bất biến - chặn UPDATE / DELETE / TRUNCATE ngay tại tầng CSDL
TRIGGER_STATEMENTS = [
    """
    CREATE OR REPLACE FUNCTION prevent_stock_ledger_mutation() RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION 'BR06 Violation: The kho (stock_ledger) la bat bien, nghiem cam lenh %!', TG_OP;
    END;
    $$ LANGUAGE plpgsql""",
    "DROP TRIGGER IF EXISTS trg_immutable_stock_ledger_row ON stock_ledger",
    """CREATE TRIGGER trg_immutable_stock_ledger_row BEFORE UPDATE OR DELETE ON stock_ledger
       FOR EACH ROW EXECUTE FUNCTION prevent_stock_ledger_mutation()""",
    "DROP TRIGGER IF EXISTS trg_immutable_stock_ledger_truncate ON stock_ledger",
    """CREATE TRIGGER trg_immutable_stock_ledger_truncate BEFORE TRUNCATE ON stock_ledger
       FOR EACH STATEMENT EXECUTE FUNCTION prevent_stock_ledger_mutation()""",
]

DROP_ORDER = ["stock_ledger", "stock_count_details", "stock_counts", "stock_transfer_details", "stock_transfers",
              "picking_tasks", "goods_issue_details", "goods_issues", "putaway_tasks", "goods_receipt_details",
              "goods_receipts", "inventory_stocks", "products", "locations", "warehouses", "partners", "users"]


def create_schema(conn) -> None:
    for stmt in TABLE_STATEMENTS + MIGRATION_STATEMENTS + INDEX_STATEMENTS:
        conn.execute(text(stmt))
    if conn.dialect.name == "postgresql":
        for stmt in TRIGGER_STATEMENTS:
            conn.execute(text(stmt))
    
    # Đảm bảo luôn có đủ cả 2 kho WH01 và WH02 (kể cả khi không chạy --reset)
    conn.execute(text("""
        INSERT INTO warehouses (warehouse_code, warehouse_name, address) 
        VALUES 
            ('WH01', 'Kho WH01 (Hàng Ngắn Hạn)', 'Chứa hàng HSD dưới 6 tháng'),
            ('WH02', 'Kho WH02 (Hàng Dài Hạn)', 'Chứa hàng HSD từ 6 tháng trở lên')
        ON CONFLICT (warehouse_code) DO NOTHING
    """))


def seed_demo(conn, password: str) -> None:
    """Dữ liệu mẫu để chạy thử toàn bộ quy trình. Chỉ nạp khi CSDL chưa có tài khoản nào."""
    pw_hash = hash_password(password)
    ids = {}
    for username, full_name, role in [("admin", "Quản trị viên", "admin"), ("thukho", "Nguyễn Văn A (Thủ kho)", "manager"),
                                      ("congnhan", "Trần Văn B (Công nhân)", "worker")]:
        ids[username] = conn.execute(text("""
            INSERT INTO users (username, password_hash, full_name, role, approval_status, is_active)
            VALUES (:u, :p, :n, :r, 'approved', TRUE) RETURNING id
        """), {"u": username, "p": pw_hash, "n": full_name, "r": role}).scalar()
    conn.execute(text("UPDATE users SET approved_by = :a, approved_at = CURRENT_TIMESTAMP"), {"a": ids["admin"]})

    # ================= 1. TẠO 10 ĐỐI TÁC (5 Nhà cung cấp, 5 Khách hàng) =================
    for code, name, typ, phone in [
        # 5 Nhà cung cấp (Suppliers)
        ("NCC001", "Công ty CP Sữa Việt Nam (Vinamilk)", "supplier", "0901000001"),
        ("NCC002", "Công ty CP Acecook Việt Nam", "supplier", "0901000002"),
        ("NCC003", "Công ty TNHH Nước Giải Khát Suntory Pepsico", "supplier", "0901000003"),
        ("NCC004", "Công ty CP Hàng Tiêu Dùng Masan", "supplier", "0901000004"),
        ("NCC005", "Công ty TNHH Quốc tế Unilever VN", "supplier", "0901000005"),
        # 5 Khách hàng (Customers)
        ("KH001", "Chuỗi Siêu thị Bách Hóa Xanh", "customer", "0902000001"),
        ("KH002", "Hệ thống Siêu thị Co.opmart", "customer", "0902000002"),
        ("KH003", "Cửa hàng Tiện lợi Circle K", "customer", "0902000003"),
        ("KH004", "Cửa hàng Tiện lợi FamilyMart", "customer", "0902000004"),
        ("KH005", "Đại lý Bán buôn Tạp hóa Hòa Bình", "customer", "0902000005")
    ]:
        conn.execute(text("INSERT INTO partners (partner_code, partner_name, type, phone) VALUES (:c, :n, :t, :p)"),
                     {"c": code, "n": name, "t": typ, "p": phone})

# ================= 2. TẠO TỰ ĐỘNG 1800 VỊ TRÍ KHO (900 vị trí / kho) =================
    # Bắt buộc thêm lệnh này để đảm bảo có đủ cả WH01 và WH02, trị dứt điểm lỗi IndexError
    conn.execute(text("""
        INSERT INTO warehouses (warehouse_code, warehouse_name, address) 
        VALUES 
            ('WH01', 'Kho WH01 (Hàng Ngắn Hạn)', 'Chứa hàng HSD dưới 6 tháng'),
            ('WH02', 'Kho WH02 (Hàng Dài Hạn)', 'Chứa hàng HSD từ 6 tháng trở lên')
        ON CONFLICT (warehouse_code) DO NOTHING
    """))

    wh_ids = {}
    for row in conn.execute(text("SELECT id, warehouse_code FROM warehouses")).fetchall():
        wh_ids[row.warehouse_code] = row.id

    locs = {"WH01": [], "WH02": []}
    for wh_code, wh_id in wh_ids.items():
        b_count = 1 # Biến đếm Vị trí (Bin) chạy liên tục từ B001 đến B900 cho mỗi kho
        
        # 3 khu vực (Z01-Z03)
        for z in range(1, 4):
            # 3 dãy (A01-A03)
            for a in range(1, 4):
                # 5 kệ (R01-R05)
                for r in range(1, 6):
                    # 5 tầng (L01-L05) - Giữ nguyên theo đúng bản cập nhật của bạn
                    for l in range(1, 6):
                        # 4 vị trí mỗi tầng
                        for b in range(1, 5):
                            zone = f"Z{z:02d}"
                            aisle = f"A{a:02d}"
                            rack = f"R{r:02d}"
                            level = f"L{l:02d}"
                            bin_no = f"B{b_count:03d}" 
                            
                            # Ghép thành chuỗi (VD: WH01-Z01-A01-R01-L01-B001)
                            loc_code = f"{wh_code}-{zone}-{aisle}-{rack}-{level}-{bin_no}"
                            
                            loc_id = conn.execute(text("""
                                INSERT INTO locations (warehouse_id, location_code, zone, aisle, rack, shelf_level, bin, max_capacity_kg, status)
                                VALUES (:w_id, :code, :z, :a, :r, :l, :b, 1000.0, 'active') RETURNING id
                            """), {"w_id": wh_id, "code": loc_code, "z": zone, "a": aisle, "r": rack, "l": level, "b": bin_no}).scalar()
                            
                            # Lưu lại id vào mảng để lát nữa nạp tồn kho
                            locs[wh_code].append(loc_id)
                            
                            b_count += 1 # Tăng biến đếm vị trí
    # ================= 3. TẠO 25 MẶT HÀNG (5 NCC x 5 Loại) =================
    prods = {}
    products_data = [
        # NCC001: Vinamilk (Sữa)
        ("VNM-01", "89310001", "Sữa tươi tiệt trùng 100% 1L", "Thùng", 12.5, 20, 400),
        ("VNM-02", "89310002", "Sữa đặc Ông Thọ đỏ", "Thùng", 15.0, 15, 300),
        ("VNM-03", "89310003", "Sữa chua ăn Vinamilk có đường", "Thùng", 5.5, 30, 500),
        ("VNM-04", "89310004", "Sữa chua uống Probi 130ml", "Thùng", 6.0, 30, 500),
        ("VNM-05", "89310005", "Sữa hạt Vinamilk Óc chó", "Thùng", 12.0, 10, 200),
        # NCC002: Acecook (Mì)
        ("ACE-01", "89320001", "Mì Hảo Hảo Tôm chua cay (30 gói)", "Thùng", 2.5, 50, 800),
        ("ACE-02", "89320002", "Mì Đệ Nhất Thịt bằm", "Thùng", 2.6, 20, 400),
        ("ACE-03", "89320003", "Miến Phú Hương (24 gói)", "Thùng", 1.8, 30, 500),
        ("ACE-04", "89320004", "Phở Đệ Nhất Gà", "Thùng", 2.2, 20, 400),
        ("ACE-05", "89320005", "Mì ly Modern Lẩu Thái", "Thùng", 1.5, 40, 600),
        # NCC003: Suntory Pepsico (Nước)
        ("PEP-01", "89330001", "Nước ngọt Pepsi Cola 330ml", "Thùng", 8.5, 50, 1000),
        ("PEP-02", "89330002", "Nước khoáng Aquafina 500ml", "Thùng", 12.0, 50, 1000),
        ("PEP-03", "89330003", "Trà Ô Long Tea+ Plus 320ml", "Thùng", 8.0, 30, 600),
        ("PEP-04", "89330004", "Nước tăng lực Sting Dâu", "Thùng", 8.5, 40, 800),
        ("PEP-05", "89330005", "Nước ép Twister Cam", "Thùng", 8.2, 20, 400),
        # NCC004: Masan (Gia vị / Thực phẩm)
        ("MSN-01", "89340001", "Nước mắm Nam Ngư 500ml", "Thùng", 13.0, 30, 600),
        ("MSN-02", "89340002", "Nước tương Chinsu 250ml", "Thùng", 6.5, 20, 500),
        ("MSN-03", "89340003", "Tương ớt Chinsu 250g", "Thùng", 7.0, 40, 800),
        ("MSN-04", "89340004", "Mì Omachi Xốt Vang", "Thùng", 2.8, 50, 800),
        ("MSN-05", "89340005", "Hạt nêm Chinsu 1kg", "Thùng", 10.5, 15, 300),
        # NCC005: Unilever (Hóa mỹ phẩm)
        ("UNI-01", "89350001", "Bột giặt Omo 4.5kg", "Bao", 4.6, 20, 400),
        ("UNI-02", "89350002", "Nước rửa chén Sunlight Chanh", "Thùng", 15.0, 30, 500),
        ("UNI-03", "89350003", "Dầu gội Clear Men 630g", "Thùng", 8.0, 15, 300),
        ("UNI-04", "89350004", "Sữa tắm Lifebuoy 850g", "Thùng", 10.0, 20, 400),
        ("UNI-05", "89350005", "Kem đánh răng P/S 240g", "Thùng", 9.5, 25, 500)
    ]

    for sku, bc, name, unit, w, mn, mx in products_data:
        prods[sku] = conn.execute(text("""
            INSERT INTO products (sku, barcode, product_name, unit, unit_weight_kg, min_safety_stock, max_safety_stock,
                                  approval_status, is_active, created_by, approved_by)
            VALUES (:s, :b, :n, :u, :w, :mn, :mx, 'approved', TRUE, :uid, :uid) RETURNING id
        """), {"s": sku, "b": bc, "n": name, "u": unit, "w": w, "mn": mn, "mx": mx, "uid": ids["admin"]}).scalar()

# ================= 5. TẠO TỒN KHO BAN ĐẦU & PHÂN BỔ TỰ ĐỘNG =================
    t = date.today()
    stock_entries = [
        ("VNM-01", t + timedelta(days=30), 40),
        ("VNM-02", t + timedelta(days=90), 50),
        ("VNM-03", t + timedelta(days=15), 60),
        ("VNM-04", t + timedelta(days=20), 100),
        ("VNM-05", t + timedelta(days=60), 80),
        ("ACE-01", t + timedelta(days=180), 200),
        ("ACE-02", t + timedelta(days=200), 150),
        ("ACE-03", t + timedelta(days=250), 100),
        ("ACE-04", t + timedelta(days=300), 120),
        ("ACE-05", t + timedelta(days=365), 90),
        ("PEP-01", t + timedelta(days=360), 300),
        ("PEP-02", t + timedelta(days=400), 400),
        ("PEP-03", t + timedelta(days=150), 150),
        ("PEP-04", t + timedelta(days=170), 200),
        ("PEP-05", t + timedelta(days=90), 80),
        ("MSN-01", t + timedelta(days=365), 100),
        ("MSN-02", t + timedelta(days=365), 100),
        ("MSN-03", t + timedelta(days=400), 150),
        ("MSN-04", t + timedelta(days=120), 250),
        ("MSN-05", t + timedelta(days=365), 50),
        ("UNI-01", t + timedelta(days=720), 80),
        ("UNI-02", t + timedelta(days=720), 100),
        ("UNI-03", t + timedelta(days=720), 60),
        ("UNI-04", t + timedelta(days=720), 90),
        ("UNI-05", t + timedelta(days=720), 120),
    ]

    loc_idx_wh01 = 0
    loc_idx_wh02 = 0

    for sku, exp, qty in stock_entries:
        days_diff = (exp - t).days
        
        # Tự động chọn kho dựa trên Hạn sử dụng (< 180 ngày vào WH01, >= 180 ngày vào WH02)
        if days_diff < 180:
            target_wh = "WH01"
            loc_id = locs[target_wh][loc_idx_wh01]
            loc_idx_wh01 += 1
        else:
            target_wh = "WH02"
            loc_id = locs[target_wh][loc_idx_wh02]
            loc_idx_wh02 += 1
            
        batch = f"LOT-{sku}-1"

        conn.execute(text("""
            INSERT INTO inventory_stocks (location_id, product_id, batch_no, expiry_date, quantity_on_hand)
            VALUES (:l, :p, :b, :e, :q)
        """), {"l": loc_id, "p": prods[sku], "b": batch, "e": exp, "q": qty})
        
        conn.execute(text("""
            INSERT INTO stock_ledger (transaction_type, reference_code, product_id, batch_no, to_location_id,
                                      quantity_change, balance_after, performed_by)
            VALUES ('PUTAWAY', 'PNK-KHOI-TAO', :p, :b, :l, :q, :q, :u)
        """), {"p": prods[sku], "b": batch, "l": loc_id, "q": qty, "u": ids["congnhan"]})


def reset_schema(conn) -> None:
    if conn.dialect.name == "postgresql":
        conn.execute(text("DROP FUNCTION IF EXISTS prevent_stock_ledger_mutation() CASCADE"))
    for table in DROP_ORDER:
        conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))


def run(demo: bool = False, reset: bool = False, assume_yes: bool = False) -> None:
    from app.core.database import engine
    if reset and not assume_yes:
        if input("CẢNH BÁO: lệnh này XÓA TOÀN BỘ dữ liệu. Gõ 'XOA' để xác nhận: ").strip() != "XOA":
            print("Đã hủy.")
            return
    with engine.begin() as conn:
        if reset:
            reset_schema(conn)
        create_schema(conn)

        users = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
        if demo and users == 0:
            password = os.getenv("SEED_PASSWORD", "Wms@2026")
            seed_demo(conn, password)
            print("Đã nạp dữ liệu mẫu. Tài khoản: admin / thukho / congnhan, "
                  f"mật khẩu: {password}  (hãy đổi ngay khi dùng thật)")
        elif demo:
            print(f"Bỏ qua dữ liệu mẫu vì CSDL đã có {users} tài khoản.")

        upgraded = 0  # băm lại mật khẩu thô cũ (nếu có)
        for uid, pw in conn.execute(text("SELECT id, password_hash FROM users")).all():
            if not is_hashed(pw):
                conn.execute(text("UPDATE users SET password_hash = :h WHERE id = :id"), {"h": hash_password(pw), "id": uid})
                upgraded += 1
    print(f"Đồng bộ CSDL xong (17 bảng, trigger BR06). Đã băm lại {upgraded} mật khẩu thô.")
    if users == 0 and not demo:
        print("Chưa có tài khoản nào. Hãy chạy: python manage.py create-admin")