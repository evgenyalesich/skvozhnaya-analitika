from pathlib import Path
from typing import List, Optional

from pydantic import AnyUrl, PostgresDsn, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_ENV = (BASE_DIR / "../../.env").resolve()
BACKEND_ENV = (BASE_DIR / "../.env").resolve()


class Settings(BaseSettings):
    analytics_db_dsn: PostgresDsn
    postgres_admin_dsn: PostgresDsn
    redis_url: AnyUrl
    rq_queue_name: str = "default"
    telegram_rq_queue_name: str = "telegram"
    cors_allow_origins: List[str] = ["*"]
    cors_allow_origins_csv: Optional[str] = None
    cache_ttl_seconds: int = 300
    subscriptions_compare_default_days: int = 90
    weekly_cache_ttl_seconds: int = 86400
    periodic_sync_enabled: bool = False
    periodic_sync_run_on_start: bool = True
    ingestion_sync_interval_minutes: int = 60
    google_sheets_sync_interval_minutes: int = 60
    pokerhub_sync_interval_hours: int = 24
    telegram_sync_interval_minutes: int = 0
    telegram_sync_daily_hour: int = 4
    telegram_sync_cooldown_seconds: int = 24 * 60 * 60
    telegram_job_timeout_seconds: int = 7200
    telegram_batch_size: int = 200
    pokerhub_api_url: str = "https://pokerhub.pro/api/tg/getusers"
    pokerhub_api_batch_size: int = 500
    google_sheets_credentials_path: Optional[str] = None
    google_sheets_sm_credentials_path: Optional[str] = None
    google_sheets_spreadsheet_url: Optional[str] = None
    google_sheets_spreadsheet_id: Optional[str] = None
    google_sheets_ranges: Optional[str] = None
    google_sheets_sm_spreadsheet_url: Optional[str] = None
    google_sheets_sm_spreadsheet_id: Optional[str] = None
    google_sheets_sm_ranges: Optional[str] = None
    google_sheets_only_sm: bool = False
    roistat_weekly_sheet_id: Optional[str] = None
    roistat_weekly_sheet_title: str = "Weekly"
    lead_db_dsn: Optional[PostgresDsn] = None
    telegram_bot_token: Optional[str] = None
    telegram_bot_username: Optional[str] = None
    telegram_webhook_secret: Optional[str] = None
    auth_jwt_secret: Optional[str] = None
    auth_start_token_ttl_seconds: int = 300
    auth_session_ttl_seconds: int = 60 * 60 * 24 * 7
    auth_allow_unknown_users: bool = False
    last_touch_exclude_bot_key: str = "lead"
    last_touch_exclude_bot_keys_csv: Optional[str] = None
    last_touch_exclude_bot_keys: List[str] = Field(default_factory=lambda: ["lead"])
    first_touch_exclude_bot_keys_csv: Optional[str] = None
    first_touch_exclude_bot_keys: List[str] = Field(default_factory=lambda: ["lead"])
    initial_allowed_telegram_ids: List[int] = Field(
        default_factory=lambda: [542149705, 6717031233],
        description="Telegram IDs that always have access before any manual grants.",
    )

    model_config = SettingsConfigDict(
        env_file=str(ROOT_ENV if ROOT_ENV.exists() else BACKEND_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def model_post_init(self, __context) -> None:
        if self.cors_allow_origins_csv:
            self.cors_allow_origins = [
                item.strip() for item in self.cors_allow_origins_csv.split(",") if item.strip()
            ]
        if self.last_touch_exclude_bot_keys_csv:
            self.last_touch_exclude_bot_keys = [
                item.strip().lower()
                for item in self.last_touch_exclude_bot_keys_csv.split(",")
                if item.strip()
            ]
        else:
            self.last_touch_exclude_bot_keys = [self.last_touch_exclude_bot_key]
        if self.first_touch_exclude_bot_keys_csv:
            self.first_touch_exclude_bot_keys = [
                item.strip().lower()
                for item in self.first_touch_exclude_bot_keys_csv.split(",")
                if item.strip()
            ]
        else:
            self.first_touch_exclude_bot_keys = ["lead"]


settings = Settings()
