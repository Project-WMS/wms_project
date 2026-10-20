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
(1, 'WH01-Z01-A01-R01-L1-B01', 'Z01', 'A01', 'R01', 'L1', 'B01', 800.00, 'active'),
(1, 'WH01-Z01-A01-R01-L1-B02', 'Z01', 'A01', 'R01', 'L1', 'B02', 1000.00, 'active'),
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
