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
    if not conn.execute(text("SELECT 1 FROM warehouses LIMIT 1")).first():
        conn.execute(text("INSERT INTO warehouses (warehouse_code, warehouse_name, address) "
                          "VALUES ('WH01', 'Kho tổng WH01', 'Kho mặc định')"))


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

    for code, name, typ, phone in [("NCC001", "Công ty Sữa Việt", "supplier", "0901000001"),
                                   ("NCC002", "Nhà phân phối Thực phẩm Minh Phát", "supplier", "0901000002"),
                                   ("KH001", "Siêu thị Bách Hóa Xanh", "customer", "0902000001"),
                                   ("KH002", "Đại lý Hòa Bình", "customer", "0902000002")]:
        conn.execute(text("INSERT INTO partners (partner_code, partner_name, type, phone) VALUES (:c, :n, :t, :p)"),
                     {"c": code, "n": name, "t": typ, "p": phone})

    locs = {}
    for bin_no, cap in [("B01", 800), ("B02", 1000), ("B03", 500), ("B04", 500)]:
        locs[bin_no] = conn.execute(text("""
            INSERT INTO locations (warehouse_id, location_code, zone, aisle, rack, shelf_level, bin, max_capacity_kg, status)
            VALUES (1, :code, 'Z01', 'A01', 'R01', 'L1', :b, :cap, 'active') RETURNING id
        """), {"code": f"WH01-Z01-A01-R01-L1-{bin_no}", "b": bin_no, "cap": cap}).scalar()

    prods = {}
    for sku, bc, name, unit, w, mn, mx in [("SUA-TH-01", "8935001234561", "Sữa tươi tiệt trùng 1L (thùng 12)", "Thùng", 12.5, 20, 400),
                                           ("MI-HH-02", "8935001234562", "Mì gói Hảo Hảo (thùng 30)", "Thùng", 2.5, 50, 800),
                                           ("NUOC-LV-03", "8935001234563", "Nước suối 500ml (thùng 24)", "Thùng", 12.0, 30, 500),
                                           ("DAU-AN-04", "8935001234564", "Dầu ăn 1L (thùng 12)", "Thùng", 11.0, 10, 200)]:
        prods[sku] = conn.execute(text("""
            INSERT INTO products (sku, barcode, product_name, unit, unit_weight_kg, min_safety_stock, max_safety_stock,
                                  approval_status, is_active, created_by, approved_by)
            VALUES (:s, :b, :n, :u, :w, :mn, :mx, 'approved', TRUE, :uid, :uid) RETURNING id
        """), {"s": sku, "b": bc, "n": name, "u": unit, "w": w, "mn": mn, "mx": mx, "uid": ids["admin"]}).scalar()

    t = date.today()
    # (sku, bin, lô, hạn dùng, số lượng) - Bin B01 = 800 kg, B02 = 1000 kg khớp BR04
    for sku, bin_no, batch, exp, qty in [("SUA-TH-01", "B01", "LOT-SUA-A", t + timedelta(days=10), 40),   # cận date (FEFO)
                                         ("SUA-TH-01", "B02", "LOT-SUA-B", t + timedelta(days=90), 64),   # 800 kg
                                         ("MI-HH-02", "B03", "LOT-MI-A", t + timedelta(days=180), 120),
                                         ("NUOC-LV-03", "B04", "LOT-NUOC-A", t + timedelta(days=200), 30)]:
        conn.execute(text("""
            INSERT INTO inventory_stocks (location_id, product_id, batch_no, expiry_date, quantity_on_hand)
            VALUES (:l, :p, :b, :e, :q)
        """), {"l": locs[bin_no], "p": prods[sku], "b": batch, "e": exp, "q": qty})
        conn.execute(text("""
            INSERT INTO stock_ledger (transaction_type, reference_code, product_id, batch_no, to_location_id,
                                      quantity_change, balance_after, performed_by)
            VALUES ('PUTAWAY', 'PNK-KHOI-TAO', :p, :b, :l, :q, :q, :u)
        """), {"p": prods[sku], "b": batch, "l": locs[bin_no], "q": qty, "u": ids["congnhan"]})


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
