from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=50)
    barcode: str = Field(min_length=1, max_length=50)
    product_name: str = Field(min_length=1, max_length=200)
    unit: str = Field(min_length=1, max_length=20)
    unit_weight_kg: Decimal = Field(gt=0, le=100000)
    min_safety_stock: int = Field(ge=0, default=10)
    max_safety_stock: int = Field(ge=0, default=1000)


class ProductUpdate(BaseModel):
    product_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=20)
    unit_weight_kg: Optional[Decimal] = Field(default=None, gt=0, le=100000)
    min_safety_stock: Optional[int] = Field(default=None, ge=0)
    max_safety_stock: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
