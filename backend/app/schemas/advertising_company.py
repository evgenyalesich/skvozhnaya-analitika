from typing import List, Optional

from pydantic import BaseModel, Field


class AdvertisingCompanyBase(BaseModel):
    company_id: Optional[str] = Field(default=None)
    company_name: str
    is_active: bool = True
    bot_keys: List[str] = Field(default_factory=list)


class AdvertisingCompanyUpsert(AdvertisingCompanyBase):
    pass


class AdvertisingCompanyOut(AdvertisingCompanyBase):
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
