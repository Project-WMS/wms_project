from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class InboundCreateRequest(BaseModel):
    supplier_id: int = 1
    product_id: int
    batch_no: str = Field(min_length=1, max_length=50)
    expiry_date: date
    expected_qty: int = Field(gt=0)
    to_location_id: int


class OutboundCreateRequest(BaseModel):
    customer_id: int = 3
    product_id: int
    requested_qty: int = Field(gt=0)


class ScanConfirmRequest(BaseModel):
    task_id: int
    scanned_qr: str
    actual_qty: int = Field(gt=0)
    # Mã vạch sản phẩm: bắt buộc khi Lấy hàng (UC6), không dùng khi Xếp kệ (UC5)
    scanned_barcode: Optional[str] = None


class TransferRequest(BaseModel):
    stock_id: int
    to_location_id: int
    transfer_qty: int = Field(gt=0)


class StockCountRequest(BaseModel):
    stock_id: int
    actual_qty: int = Field(ge=0)
