from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class AdMetricsWeeklyBase(BaseModel):
    week_start: date
    campaign: str = Field(..., max_length=128)
    bot_key: Optional[str] = Field(default=None, max_length=64)
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    spend: float = Field(default=0, ge=0)


class AdMetricsWeeklyCreate(AdMetricsWeeklyBase):
    pass


class AdMetricsWeeklyUpdate(BaseModel):
    week_start: Optional[date] = None
    campaign: Optional[str] = Field(default=None, max_length=128)
    bot_key: Optional[str] = Field(default=None, max_length=64)
    impressions: Optional[int] = Field(default=None, ge=0)
    clicks: Optional[int] = Field(default=None, ge=0)
    spend: Optional[float] = Field(default=None, ge=0)


class AdMetricsWeeklyOut(AdMetricsWeeklyBase):
    id: int

    class Config:
        from_attributes = True
