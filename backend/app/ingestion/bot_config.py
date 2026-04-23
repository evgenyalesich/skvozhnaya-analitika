from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

DEFAULT_FETCH_COLUMNS = [
    "tg_user_id",
    "user_block",
    "created_at",
    "utm_source",
    "utm_campaign",
    "utm_medium",
    "utm_content",
    "utm_term",
    "advertising_company",
    "budget",
    "converted_to_lead",
    "registered_platform",
    "started_learning",
    "completed_course",
    "used_simulator",
    "interview_reached",
    "interview_passed",
    "offer_received",
    "contract_signed",
    "channel_subscribed",
    "community_member",
    "team_member",
    "internal_status",
]


@dataclass
class BotConfig:
    bot_key: str
    database_name: str
    source_table: str = "users"
    batch_size: int = 1000
    cursor_column: str = "created_at"
    fetch_columns: List[str] = field(default_factory=lambda: DEFAULT_FETCH_COLUMNS.copy())
    custom_query: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BotConfig":
        return cls(
            bot_key=data.get("bot_key"),
            database_name=data.get("database_name"),
            source_table=data.get("source_table", "users"),
            batch_size=data.get("batch_size", 1000),
            cursor_column=data.get("cursor_column", "created_at"),
            fetch_columns=data.get("fetch_columns", DEFAULT_FETCH_COLUMNS.copy()),
            custom_query=data.get("custom_query"),
        )
