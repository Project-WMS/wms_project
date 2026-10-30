from typing import List

from pydantic import BaseModel, Field


class TransferItem(BaseModel):
    stock_id: int
    to_location_id: int
    quantity: int = Field(gt=0, le=10000000)


class TransferCreate(BaseModel):
    items: List[TransferItem] = Field(min_length=1, max_length=50)
