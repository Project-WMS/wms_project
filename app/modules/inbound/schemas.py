from datetime import date
from typing import List

from pydantic import BaseModel, Field


class ReceiptItem(BaseModel):
    product_id: int
    batch_no: str = Field(min_length=1, max_length=50)
    expiry_date: date
    quantity: int = Field(gt=0, le=10000000)
    to_location_id: int


class ReceiptCreate(BaseModel):
    supplier_id: int
    items: List[ReceiptItem] = Field(min_length=1, max_length=50)
