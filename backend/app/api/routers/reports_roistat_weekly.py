# Агрегированный Roistat-отчёт: суммирует roistat_weekly_by_company по неделям (без разбивки по компаниям).
# Backward-compat: если client шлёт first_touch_* без mode — переключается на first_touch автоматически.
# ph_mirror_weekly — число platform_cnt из ph_user_mirror (только в event mode без bot-фильтра).
# Кеш: ключ v6, stale-ключ TTL 7× primary. При stale — фоновый refresh через asyncio.create_task.

from datetime import date
import asyncio
from typing import Any, List, Optional

from fastapi import Depends, Query

from app.api.dependencies import get_db_session
from app.core.config import settings
from app.core.redis_client import RedisCache
from app.db.session import async_session
from app.schemas.reports import RoistatWeeklyReportResponse, RoistatWeeklyRow

from .reports_funnel_helpers import load_ph_mirror_weekly_counts
from .reports_roistat_companies import roistat_weekly_by_company


# ===== Roistat aggregated weekly logic =====
async def roistat_weekly(
    event_start: Optional[date] = Query(None),
    event_end: Optional[date] = Query(None),
    first_touch_start: Optional[date] = Query(None),
    first_touch_end: Optional[date] = Query(None),
    mode: str = Query("event", pattern="^(event|first_touch|last_touch)$"),
    bots: List[str] = Query(default=[]),
    session=Depends(get_db_session),
):
    # Backward-compat: if client sends first_touch_* without mode, assume first_touch.
    if mode == "event" and (first_touch_start or first_touch_end):
        mode = "first_touch"
    # If client omits first_touch_* but provides event range in first_touch mode, reuse it.
    if mode == "first_touch" and not (first_touch_start or first_touch_end):
        if event_start or event_end:
            first_touch_start = event_start
            first_touch_end = event_end
    cache = RedisCache()
    bots_key = ",".join(sorted(bots)) if bots else ""
    cache_key = (
        "reports:roistat_weekly:v6:"
        f"{mode}:{event_start}:{event_end}:{first_touch_start}:{first_touch_end}:{bots_key}"
    )
    stale_key = f"{cache_key}:stale"
    lock_key = f"{cache_key}:lock"

    async def build_payload(session_local) -> list[dict[str, Any]]:
        company_payload = await roistat_weekly_by_company(
            event_start=event_start,
            event_end=event_end,
            mode=mode,
            first_touch_start=first_touch_start,
            first_touch_end=first_touch_end,
            display_mode="weekly",
            bots=bots or None,
            advertising_companies=None,
            utm_source=None,
            utm_campaign=None,
            utm_medium=None,
            utm_content=None,
            utm_term=None,
            session=session_local,
        )
        ph_mirror_weekly: dict[str, int] = {}
        if mode == "event" and not bots:
            ph_mirror_weekly = await load_ph_mirror_weekly_counts(event_start, event_end)
        metric_keys = [
            "almanah_starts",
            "direct_source_cnt",
            "new_in_system",
            "old_in_system",
            "platform_cnt",
            "learning",
            "started_learning",
            "mtt",
            "spin",
            "cash",
            "base",
            "not_started",
            "channel_subscribed",
            "saloon",
            "completed_course",
            "completed_base",
            "distance_grinding",
            "contract_signed",
            "entered_all",
            "interview_reached",
            "offer_received",
            "completed_mtt",
            "completed_spin",
            "completed_cash",
            "contract_mtt",
            "contract_spin",
            "contract_cash",
        ]
        weekly_map: dict[str, dict[str, Any]] = {}
        for row in company_payload.get("rows", []):
            week_key = row["week_start"]
            current = weekly_map.setdefault(
                week_key,
                {
                    "week_start": week_key,
                    "budget": 0.0,
                    **{key: 0 for key in metric_keys},
                },
            )
            current["budget"] += float(row.get("budget") or 0.0)
            for key in metric_keys:
                current[key] += int(row.get(key) or 0)

        if ph_mirror_weekly:
            for week_key, value in ph_mirror_weekly.items():
                current = weekly_map.setdefault(
                    week_key,
                    {
                        "week_start": week_key,
                        "budget": 0.0,
                        **{key: 0 for key in metric_keys},
                    },
                )
                current["platform_cnt"] = value

        rows = sorted(weekly_map.values(), key=lambda row: row["week_start"])
        return [
            RoistatWeeklyRow(
                week_start=row["week_start"],
                almanah_starts=row["almanah_starts"],
                direct_source_cnt=row["direct_source_cnt"],
                new_in_system=row["new_in_system"],
                old_in_system=row["old_in_system"],
                platform=row["platform_cnt"],
                learning=row["learning"],
                started_learning=row["started_learning"],
                mtt=row["mtt"],
                spin=row["spin"],
                cash=row["cash"],
                base=row["base"],
                not_started=row["not_started"],
                channel_subscribed=row["channel_subscribed"],
                saloon=row["saloon"],
                completed_course=row["completed_course"],
                completed_base=row["completed_base"],
                distance_grinding=row["distance_grinding"],
                contract_signed=row["contract_signed"],
                budget=row["budget"],
                entered_all=row["entered_all"],
                interview_reached=row["interview_reached"],
                offer_received=row["offer_received"],
                completed_mtt=row["completed_mtt"],
                completed_spin=row["completed_spin"],
                completed_cash=row["completed_cash"],
                contract_mtt=row["contract_mtt"],
                contract_spin=row["contract_spin"],
                contract_cash=row["contract_cash"],
            ).model_dump()
            for row in rows
        ]

    async def store_payload(payload: list[dict[str, Any]]) -> None:
        primary_ttl = settings.weekly_cache_ttl_seconds
        stale_ttl = max(primary_ttl * 7, 7 * 24 * 60 * 60)
        await cache.set_json(cache_key, payload, ttl=primary_ttl)
        await cache.set_json(stale_key, payload, ttl=stale_ttl)

    async def build_and_cache(session_local) -> list[dict[str, Any]]:
        payload = await build_payload(session_local)
        await store_payload(payload)
        return payload

    cached_map = await cache.get_json_many([cache_key, stale_key])
    cached = cached_map.get(cache_key)
    if cached is not None:
        return RoistatWeeklyReportResponse(rows=[RoistatWeeklyRow(**row) for row in cached])

    stale = cached_map.get(stale_key)
    if stale is not None:
        if await cache.set_if_not_exists(lock_key, "1", ttl=60):
            async def refresh_in_background() -> None:
                try:
                    async with async_session() as bg_session:
                        await build_and_cache(bg_session)
                finally:
                    await cache.delete(lock_key)
            asyncio.create_task(refresh_in_background())
        return RoistatWeeklyReportResponse(rows=[RoistatWeeklyRow(**row) for row in stale])

    if await cache.set_if_not_exists(lock_key, "1", ttl=120):
        try:
            payload = await build_and_cache(session)
        finally:
            await cache.delete(lock_key)
        return RoistatWeeklyReportResponse(rows=[RoistatWeeklyRow(**row) for row in payload])

    await asyncio.sleep(0.5)
    cached_map = await cache.get_json_many([cache_key, stale_key])
    fallback = cached_map.get(cache_key) or cached_map.get(stale_key)
    if fallback is not None:
        return RoistatWeeklyReportResponse(rows=[RoistatWeeklyRow(**row) for row in fallback])

    payload = await build_and_cache(session)
    return RoistatWeeklyReportResponse(rows=[RoistatWeeklyRow(**row) for row in payload])


