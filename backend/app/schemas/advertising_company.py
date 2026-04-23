from typing import List, Optional

from pydantic import BaseModel, Field


class UtmRule(BaseModel):
    bot_keys: List[str] = Field(default_factory=list)
    utm_source: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    priority: int = 0
    match_mode: Optional[str] = "all"


class AdvertisingCompanyBase(BaseModel):
    company_id: Optional[str] = Field(default=None)
    company_name: str
    platform: Optional[str] = None
    is_active: bool = True
    bot_keys: List[str] = Field(default_factory=list)
    utm_rules: List[UtmRule] = Field(default_factory=list)


class AdvertisingCompanyUpsert(AdvertisingCompanyBase):
    pass


class AdvertisingCompanyOut(AdvertisingCompanyBase):
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
