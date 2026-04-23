from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TelegramAccessCreate(BaseModel):
    tg_user_id: int


class TelegramAccessOut(BaseModel):
    tg_user_id: int
    created_at: datetime
    created_by: str | None = None
    model_config = ConfigDict(from_attributes=True)
