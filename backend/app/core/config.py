from pathlib import Path
from typing import List

from pydantic import AnyUrl, BaseSettings, PostgresDsn, field_validator

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    analytics_db_dsn: PostgresDsn
    redis_url: AnyUrl
    rq_queue_name: str = "default"
    cors_allow_origins: List[str] = ["*"]
    cache_ttl_seconds: int = 300

    class Config:
        env_file = BASE_DIR / "../.env"
        env_file_encoding = "utf-8"


settings = Settings()
