from typing import Optional

from pydantic import BaseModel, Field


class PartnerCreate(BaseModel):
    partner_code: str = Field(min_length=1, max_length=30)
    partner_name: str = Field(min_length=1, max_length=150)
    type: str
    phone: Optional[str] = Field(default=None, max_length=20)
    address: Optional[str] = None


class PartnerUpdate(BaseModel):
    partner_name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    phone: Optional[str] = Field(default=None, max_length=20)
    address: Optional[str] = None
