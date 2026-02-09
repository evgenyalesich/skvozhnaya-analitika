from datetime import datetime
from pydantic import BaseModel, Field
from pydantic import ConfigDict


class SchedulerSettings(BaseModel):
    periodic_enabled: bool = True
    run_on_start: bool = True
    warm_cache_on_start: bool = True
    ingestion_interval_minutes: int = 60
    google_sheets_interval_minutes: int = 60
    pokerhub_interval_hours: int = 24
    telegram_interval_minutes: int = 0
    telegram_daily_hour: int = 4
    telegram_batch_size: int = 1000
    telegram_job_timeout_seconds: int = 7200


class SystemSettingsOut(BaseModel):
    scheduler: SchedulerSettings


class SystemSettingsUpdate(BaseModel):
    scheduler: SchedulerSettings


class SyncEventLogOut(BaseModel):
    id: int
    source: str
    level: str
    message: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
