from typing import Optional

from pydantic import BaseModel, Field


class ScanConfirmRequest(BaseModel):
    task_id: int
    scanned_qr: str = Field(min_length=1, max_length=100)
    actual_qty: int = Field(gt=0, le=10000000)
    # Mã vạch sản phẩm: bắt buộc khi Lấy hàng (UC6), không dùng khi Xếp kệ (UC5)
    scanned_barcode: Optional[str] = Field(default=None, max_length=100)
