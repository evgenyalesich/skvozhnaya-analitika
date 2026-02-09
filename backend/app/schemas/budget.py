from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class BudgetWeeklyBase(BaseModel):
    week_start: date
    campaign: str = Field(..., max_length=128)
    bot_key: Optional[str] = Field(default=None, max_length=64)
    amount: float = Field(..., ge=0)
    currency: str = Field(default="USD", max_length=8)


class BudgetWeeklyCreate(BudgetWeeklyBase):
    pass


class BudgetWeeklyUpdate(BaseModel):
    week_start: Optional[date] = None
    campaign: Optional[str] = Field(default=None, max_length=128)
    bot_key: Optional[str] = Field(default=None, max_length=64)
    amount: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, max_length=8)


class BudgetWeeklyOut(BudgetWeeklyBase):
    id: int

    class Config:
        from_attributes = True
