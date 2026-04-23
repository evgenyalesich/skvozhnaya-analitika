from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func


REPORT_EXCLUDED_BOT_KEYS: tuple[str, ...] = (
    "costyl1_bot",
    "lead_dev",
    "lead_test",
    "lead_tests",
    "heath_checker",
)


def normalized_excluded_bot_keys() -> list[str]:
    return [bot_key.strip().lower() for bot_key in REPORT_EXCLUDED_BOT_KEYS]


def apply_excluded_bot_filter(stmt, bot_col):
    normalized_col = func.lower(func.trim(func.coalesce(bot_col, "")))
    return stmt.where(normalized_col.notin_(normalized_excluded_bot_keys()))


def is_excluded_bot_key(bot_key: str | None) -> bool:
    if not bot_key:
        return False
    return bot_key.strip().lower() in normalized_excluded_bot_keys()


def visible_bot_keys(bot_keys: Iterable[str] | None) -> list[str]:
    if not bot_keys:
        return []
    return [bot_key for bot_key in bot_keys if not is_excluded_bot_key(bot_key)]
