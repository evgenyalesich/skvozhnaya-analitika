from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EmployeeRegistryCreate(BaseModel):
    tg_user_id: int


class EmployeeRegistryBulkCreate(BaseModel):
    tg_user_ids: list[int]


class EmployeeRegistryReplace(BaseModel):
    tg_user_ids: list[int]


class EmployeeRegistryOut(BaseModel):
    tg_user_id: int
    username: str | None = None
    created_at: datetime
    created_by: str | None = None
    model_config = ConfigDict(from_attributes=True)
