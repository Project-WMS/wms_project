from typing import List

from pydantic import BaseModel, Field


class CountCreate(BaseModel):
    location_id: int


class CountLine(BaseModel):
    detail_id: int
    actual_qty: int = Field(ge=0, le=100000000)


class CountSave(BaseModel):
    lines: List[CountLine] = Field(min_length=1, max_length=500)
