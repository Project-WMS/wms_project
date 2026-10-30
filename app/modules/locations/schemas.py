from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class LocationCreate(BaseModel):
    warehouse_id: int = 1
    zone: str = Field(min_length=1, max_length=10)
    aisle: str = Field(min_length=1, max_length=10)
    rack: str = Field(min_length=1, max_length=10)
    shelf_level: str = Field(min_length=1, max_length=10)
    bin: str = Field(min_length=1, max_length=10)
    max_capacity_kg: Decimal = Field(gt=0, le=1000000)
    status: str = "active"


class LocationUpdate(BaseModel):
    max_capacity_kg: Optional[Decimal] = Field(default=None, gt=0, le=1000000)
    status: Optional[str] = None
