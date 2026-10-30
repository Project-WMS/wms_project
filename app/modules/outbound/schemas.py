from typing import List

from pydantic import BaseModel, Field


class IssueItem(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=10000000)


class IssueCreate(BaseModel):
    customer_id: int
    items: List[IssueItem] = Field(min_length=1, max_length=50)
