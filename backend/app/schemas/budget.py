from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class BudgetWeeklyBase(BaseModel):
    week_start: date
    period_end: Optional[date] = None
    campaign: str = Field(..., max_length=128)
    bot_key: Optional[str] = Field(default=None, max_length=64)
    channel_key: Optional[str] = Field(default=None, max_length=32)
    utm_source: Optional[str] = Field(default=None, max_length=128)
    utm_campaign: Optional[str] = Field(default=None, max_length=128)
    utm_medium: Optional[str] = Field(default=None, max_length=128)
    utm_content: Optional[str] = Field(default=None, max_length=256)
    utm_term: Optional[str] = Field(default=None, max_length=256)
    amount: float = Field(..., ge=0)
    currency: str = Field(default="USD", max_length=8)


class BudgetWeeklyCreate(BudgetWeeklyBase):
    pass


class BudgetWeeklyUpdate(BaseModel):
    week_start: Optional[date] = None
    period_end: Optional[date] = None
    campaign: Optional[str] = Field(default=None, max_length=128)
    bot_key: Optional[str] = Field(default=None, max_length=64)
    channel_key: Optional[str] = Field(default=None, max_length=32)
    utm_source: Optional[str] = Field(default=None, max_length=128)
    utm_campaign: Optional[str] = Field(default=None, max_length=128)
    utm_medium: Optional[str] = Field(default=None, max_length=128)
    utm_content: Optional[str] = Field(default=None, max_length=256)
    utm_term: Optional[str] = Field(default=None, max_length=256)
    amount: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, max_length=8)


class BudgetWeeklyOut(BudgetWeeklyBase):
    id: int

    class Config:
        from_attributes = True
