from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.api.routers.reports_roistat_logic import roistat_weekly_by_company
from app.core.redis_client import RedisCache
from app.db.session import async_session

_HOT_PROFILES_KEY = "reports:roistat_weekly:companies:hot_profiles:v1"


def _as_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except Exception:
        return None


def _normalize_profile(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_start": _as_date(item.get("event_start")),
        "event_end": _as_date(item.get("event_end")),
        "mode": str(item.get("mode") or "event"),
        "first_touch_start": _as_date(item.get("first_touch_start")),
        "first_touch_end": _as_date(item.get("first_touch_end")),
        "display_mode": str(item.get("display_mode") or "weekly"),
        "bots": list(item.get("bots") or []),
        "advertising_companies": list(item.get("advertising_companies") or []),
        "utm_source": list(item.get("utm_source") or []),
        "utm_campaign": list(item.get("utm_campaign") or []),
        "utm_medium": list(item.get("utm_medium") or []),
        "utm_content": list(item.get("utm_content") or []),
        "utm_term": list(item.get("utm_term") or []),
    }


def _default_profiles() -> list[dict[str, Any]]:
    today = date.today()
    start_90 = today - timedelta(days=90)
    return [
        {
            "event_start": start_90,
            "event_end": today,
            "mode": "event",
            "first_touch_start": None,
            "first_touch_end": None,
            "display_mode": "weekly",
            "bots": [],
            "advertising_companies": [],
            "utm_source": [],
            "utm_campaign": [],
            "utm_medium": [],
            "utm_content": [],
            "utm_term": [],
        },
        {
            "event_start": start_90,
            "event_end": today,
            "mode": "event",
            "first_touch_start": None,
            "first_touch_end": None,
            "display_mode": "cohort",
            "bots": [],
            "advertising_companies": [],
            "utm_source": [],
            "utm_campaign": [],
            "utm_medium": [],
            "utm_content": [],
            "utm_term": [],
        },
    ]


async def warm_main_report_cache(max_profiles: int = 20) -> int:
    cache = RedisCache()
    raw = await cache.get_json(_HOT_PROFILES_KEY)
    profiles: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                profiles.append(_normalize_profile(item))
    profiles.extend(_default_profiles())
    profiles = profiles[:max_profiles]

    warmed = 0
    async with async_session() as session:
        for profile in profiles:
            await roistat_weekly_by_company(
                event_start=profile["event_start"],
                event_end=profile["event_end"],
                mode=profile["mode"],
                first_touch_start=profile["first_touch_start"],
                first_touch_end=profile["first_touch_end"],
                display_mode=profile["display_mode"],
                bots=profile["bots"],
                advertising_companies=profile["advertising_companies"],
                utm_source=profile["utm_source"],
                utm_campaign=profile["utm_campaign"],
                utm_medium=profile["utm_medium"],
                utm_content=profile["utm_content"],
                utm_term=profile["utm_term"],
                session=session,
            )
            warmed += 1
    return warmed

