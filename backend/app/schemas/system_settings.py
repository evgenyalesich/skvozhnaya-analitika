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


class MarketingDailySettings(BaseModel):
    enabled: bool = True
    send_hour_msk: int = Field(default=9, ge=0, le=23)
    show_top_growth: int = Field(default=3, ge=1, le=10)
    show_top_decline: int = Field(default=3, ge=1, le=10)
    allowed_subscriber_ids: list[int] = Field(default_factory=list)
    anomaly_drop_threshold_pct: float = Field(default=-50.0, le=0)
    downward_streak_days: int = Field(default=3, ge=2, le=7)


class MarketingDailySettingsUpdate(BaseModel):
    marketing_daily: MarketingDailySettings


class MarketingDailyPreviewOut(BaseModel):
    report_date: str | None = None
    previous_date: str | None = None
    summary: dict
    leaders_growth: list[dict]
    leaders_decline: list[dict]
    anomalies: list[str]
    all_bots: list[dict]
    data_quality: dict = Field(default_factory=dict)
    text: str


class SyncEventLogOut(BaseModel):
    id: int
    source: str
    level: str
    message: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
