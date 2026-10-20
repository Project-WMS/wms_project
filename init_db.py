import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# 1. Nạp cấu hình từ file .env
load_dotenv()

db_url = os.getenv("DATABASE_URL")

# Nếu trong .env bạn đặt từng biến lẻ thay vì DATABASE_URL thì hệ thống tự ghép lại
if not db_url:
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME", "wms_db")
    db_url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}"
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

# 2. Toàn bộ câu lệnh tạo 17 bảng chuẩn PostgreSQL 18 và Nạp dữ liệu mẫu
SQL_FULL_INIT = """
DROP TABLE IF EXISTS stock_ledger, inventory_stocks, stock_count_details, stock_counts,
                     stock_transfer_details, stock_transfers, picking_tasks, goods_issue_details,
                     goods_issues, putaway_tasks, goods_receipt_details, goods_receipts,
                     products, locations, warehouses, partners, users CASCADE;

CREATE TABLE users (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL DEFAULT '123456',
    full_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'manager', 'worker')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE partners (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    partner_code VARCHAR(30) NOT NULL UNIQUE,
    partner_name VARCHAR(150) NOT NULL,
    type VARCHAR(20) NOT NULL CHECK (type IN ('supplier', 'customer')),
    phone VARCHAR(20),
    address TEXT
);

CREATE TABLE warehouses (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    warehouse_code VARCHAR(20) NOT NULL UNIQUE,
    warehouse_name VARCHAR(100) NOT NULL,
    address VARCHAR(255)
);

CREATE TABLE locations (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    warehouse_id INT NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    location_code VARCHAR(50) NOT NULL UNIQUE,
    zone VARCHAR(10) NOT NULL,
    aisle VARCHAR(10) NOT NULL,
    rack VARCHAR(10) NOT NULL,
    shelf_level VARCHAR(5) NOT NULL,
    bin VARCHAR(5) NOT NULL,
    max_capacity_kg DECIMAL(10,2) DEFAULT 500.00,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'maintenance', 'locked'))
);

CREATE TABLE products (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    barcode VARCHAR(50) NOT NULL UNIQUE,
    product_name VARCHAR(200) NOT NULL,
    unit VARCHAR(20) NOT NULL,
    unit_weight_kg DECIMAL(10,2) DEFAULT 1.00,
    min_safety_stock INT DEFAULT 10,
    max_safety_stock INT DEFAULT 1000
);

CREATE TABLE inventory_stocks (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    location_id INT NOT NULL REFERENCES locations(id),
    product_id INT NOT NULL REFERENCES products(id),
    batch_no VARCHAR(50) NOT NULL,
    expiry_date DATE NOT NULL,
    quantity_on_hand INT NOT NULL DEFAULT 0 CHECK (quantity_on_hand >= 0),
    quantity_allocated INT NOT NULL DEFAULT 0 CHECK (quantity_allocated >= 0 AND quantity_allocated <= quantity_on_hand),
    quantity_available INT GENERATED ALWAYS AS (quantity_on_hand - quantity_allocated) STORED,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (location_id, product_id, batch_no)
);

CREATE TABLE goods_receipts (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    receipt_code VARCHAR(30) NOT NULL UNIQUE,
    supplier_id INT NOT NULL REFERENCES partners(id),
    warehouse_id INT NOT NULL REFERENCES warehouses(id),
    created_by INT NOT NULL REFERENCES users(id),
    approved_by INT NULL REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'putting_away', 'completed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP NULL
);

CREATE TABLE goods_receipt_details (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    receipt_id INT NOT NULL REFERENCES goods_receipts(id) ON DELETE CASCADE,
    product_id INT NOT NULL REFERENCES products(id),
    batch_no VARCHAR(50) NOT NULL,
    expiry_date DATE NOT NULL,
    expected_qty INT NOT NULL CHECK (expected_qty > 0),
    putaway_qty INT DEFAULT 0
);

CREATE TABLE putaway_tasks (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    receipt_detail_id INT NOT NULL REFERENCES goods_receipt_details(id) ON DELETE CASCADE,
    to_location_id INT NOT NULL REFERENCES locations(id),
    stock_id INT NULL REFERENCES inventory_stocks(id),
    assigned_qty INT NOT NULL,
    actual_qty INT DEFAULT 0,
    performed_by INT NULL REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'completed')),
    completed_at TIMESTAMP NULL
);

CREATE TABLE goods_issues (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    issue_code VARCHAR(30) NOT NULL UNIQUE,
    customer_id INT NOT NULL REFERENCES partners(id),
    warehouse_id INT NOT NULL REFERENCES warehouses(id),
    created_by INT NOT NULL REFERENCES users(id),
    approved_by INT NULL REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'allocated', 'picking', 'completed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP NULL
);

CREATE TABLE goods_issue_details (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    issue_id INT NOT NULL REFERENCES goods_issues(id) ON DELETE CASCADE,
    product_id INT NOT NULL REFERENCES products(id),
    requested_qty INT NOT NULL CHECK (requested_qty > 0),
    picked_qty INT DEFAULT 0
);

CREATE TABLE picking_tasks (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    issue_detail_id INT NOT NULL REFERENCES goods_issue_details(id) ON DELETE CASCADE,
    from_location_id INT NOT NULL REFERENCES locations(id),
    stock_id INT NOT NULL REFERENCES inventory_stocks(id),
    batch_no VARCHAR(50) NOT NULL,
    allocated_qty INT NOT NULL,
    picked_qty INT DEFAULT 0,
    performed_by INT NULL REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'allocated' CHECK (status IN ('allocated', 'picked')),
    picked_at TIMESTAMP NULL
);

CREATE TABLE stock_transfers (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transfer_code VARCHAR(30) NOT NULL UNIQUE,
    warehouse_id INT NOT NULL REFERENCES warehouses(id),
    created_by INT NOT NULL REFERENCES users(id),
    approved_by INT NULL REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'completed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE stock_transfer_details (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transfer_id INT NOT NULL REFERENCES stock_transfers(id) ON DELETE CASCADE,
    product_id INT NOT NULL REFERENCES products(id),
    batch_no VARCHAR(50) NOT NULL,
    from_location_id INT NOT NULL REFERENCES locations(id),
    to_location_id INT NOT NULL REFERENCES locations(id),
    transfer_qty INT NOT NULL CHECK (transfer_qty > 0),
    performed_by INT NULL REFERENCES users(id)
);

CREATE TABLE stock_counts (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    count_code VARCHAR(30) NOT NULL UNIQUE,
    warehouse_id INT NOT NULL REFERENCES warehouses(id),
    created_by INT NOT NULL REFERENCES users(id),
    approved_by INT NULL REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'counting', 'reconciled')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE stock_count_details (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    count_id INT NOT NULL REFERENCES stock_counts(id) ON DELETE CASCADE,
    location_id INT NOT NULL REFERENCES locations(id),
    product_id INT NOT NULL REFERENCES products(id),
    batch_no VARCHAR(50) NOT NULL,
    system_qty INT NOT NULL,
    actual_qty INT NOT NULL DEFAULT 0,
    variance_qty INT GENERATED ALWAYS AS (actual_qty - system_qty) STORED,
    counted_by INT NULL REFERENCES users(id)
);

CREATE TABLE stock_ledger (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_type VARCHAR(20) NOT NULL CHECK (transaction_type IN ('PUTAWAY', 'PICK', 'TRANSFER', 'COUNT_ADJUST')),
    reference_code VARCHAR(50) NOT NULL,
    task_id INT NULL,
    product_id INT NOT NULL REFERENCES products(id),
    batch_no VARCHAR(50) NOT NULL,
    from_location_id INT NULL REFERENCES locations(id),
    to_location_id INT NULL REFERENCES locations(id),
    quantity_change INT NOT NULL,
    balance_after INT NOT NULL,
    performed_by INT NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- NẠP DỮ LIỆU MẪU (SEED DATA)
-- ==========================================
INSERT INTO users (username, full_name, role) VALUES
('admin', 'Quản trị hệ thống', 'admin'),
('thukho', 'Nguyễn Văn A (Thủ kho PC)', 'manager'),
('congnhan', 'Trần Văn B (Công nhân QR)', 'worker');

INSERT INTO partners (partner_code, partner_name, type, phone, address) VALUES
('SUP-TH', 'Công ty CP Thực phẩm Sữa TH', 'supplier', '02838123456', 'Nghệ An'),
('SUP-MS', 'Công ty CP Hàng tiêu dùng Masan', 'supplier', '02838654321', 'TP.HCM'),
('CUS-BHX', 'Hệ thống Siêu thị Bách Hóa Xanh', 'customer', '02839998888', 'TP.HCM'),
('CUS-WM', 'Chuỗi Siêu thị WinMart+', 'customer', '02837776666', 'TP.HCM');

INSERT INTO warehouses (warehouse_code, warehouse_name, address) VALUES
('WH01', 'Kho Trung Tâm Tân Bình', 'KCN Tân Bình, TP.HCM');

INSERT INTO locations (warehouse_id, location_code, zone, aisle, rack, shelf_level, bin, max_capacity_kg, status) VALUES
(1, 'WH01-Z01-A01-R01-L1-B01', 'Z01', 'A01', 'R01', 'L1', 'B01', 600.00, 'active'),
(1, 'WH01-Z01-A01-R01-L1-B02', 'Z01', 'A01', 'R01', 'L1', 'B02', 600.00, 'active'),
(1, 'WH01-Z01-A01-R01-L2-B03', 'Z01', 'A01', 'R01', 'L2', 'B03', 500.00, 'active'),
(1, 'WH01-Z01-A01-R02-L1-B01', 'Z01', 'A01', 'R02', 'L1', 'B01', 800.00, 'active'),
(1, 'WH01-Z01-A01-R02-L2-B02', 'Z01', 'A01', 'R02', 'L2', 'B02', 500.00, 'active');

INSERT INTO products (sku, barcode, product_name, unit, unit_weight_kg, min_safety_stock, max_safety_stock) VALUES
('SKU-MILK-01', '8935001234561', 'Sữa tươi tiệt trùng TH True Milk 180ml', 'Thùng', 10.0, 50, 500),
('SKU-NOODLE-02', '8935001234562', 'Mì Hảo Hảo Tôm Chua Cay (30 gói)', 'Thùng', 4.5, 40, 400),
('SKU-WATER-03', '8935001234563', 'Nước khoáng LaVie 500ml (24 chai)', 'Thùng', 12.5, 45, 600),
('SKU-COFFEE-04', '8935001234564', 'Cà phê hòa tan G7 3in1', 'Thùng', 6.0, 30, 300);

-- Tồn kho mẫu: Có lô cận date (7 ngày nữa hết hạn) và mặt hàng dưới mức an toàn để Dashboard báo đỏ
INSERT INTO inventory_stocks (location_id, product_id, batch_no, expiry_date, quantity_on_hand, quantity_allocated) VALUES
(1, 1, 'LOT-MILK-01', CURRENT_DATE + INTERVAL '7 days', 40, 0),
(2, 1, 'LOT-MILK-02', CURRENT_DATE + INTERVAL '90 days', 80, 0),
(3, 2, 'LOT-HAOHAO-01', CURRENT_DATE + INTERVAL '120 days', 110, 0),
(4, 3, 'LOT-LAVIE-01', CURRENT_DATE + INTERVAL '180 days', 20, 0),
(5, 4, 'LOT-G7-01', CURRENT_DATE + INTERVAL '240 days', 65, 0);

-- Nhật ký thẻ kho mẫu ban đầu
INSERT INTO stock_ledger (transaction_type, reference_code, product_id, batch_no, to_location_id, quantity_change, balance_after, performed_by) VALUES
('PUTAWAY', 'PNK-202610-001', 1, 'LOT-MILK-01', 1, 40, 40, 3),
('PUTAWAY', 'PNK-202610-001', 1, 'LOT-MILK-02', 2, 80, 80, 3),
('PUTAWAY', 'PNK-202610-002', 2, 'LOT-HAOHAO-01', 3, 110, 110, 3),
('PUTAWAY', 'PNK-202610-002', 3, 'LOT-LAVIE-01', 4, 20, 20, 3),
('PUTAWAY', 'PNK-202610-003', 4, 'LOT-G7-01', 5, 65, 65, 3);
"""

# 3. Thực thi tạo bảng
if __name__ == "__main__":
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(SQL_FULL_INIT))
        print("✅ Đã khởi tạo thành công 17 bảng và nạp xong dữ liệu mẫu Kho Tân Bình vào PostgreSQL (wms_db)!")