# Хелперы для funnel-эндпоинтов.
# event_funnel_summary_from_main_report — перекладывает поля из roistat_weekly_by_company в унифицированный
#   EVENT_FUNNEL_SUMMARY_KEYS формат, группируя по bot_key или company.
# event_funnel_stages_from_main_report — суммирует по всем группам → единый словарь этапов.
# load_ph_mirror_weekly_counts — counts ph_user_mirror.id по неделям (platform_cnt source).

from datetime import date
from typing import Any, Optional

import asyncpg

from app.api.report_filters import ReportFilters
from app.core.config import settings

EVENT_FUNNEL_SUMMARY_KEYS = [
    "entered",
    "new_in_system",
    "old_in_system",
    "lead",
    "direct_source_cnt",
    "subscribed",
    "platform",
    "learning",
    "course",
    "simulator",
    "interview",
    "passed",
    "offer",
    "contract",
    "distance_grinding",
]


def event_summary_row_from_main_report(row: dict[str, Any], group_value: str) -> dict[str, Any]:
    return {
        "group": group_value,
        "entered": int(row.get("entered_all") or 0),
        "new_in_system": int(row.get("new_in_system") or 0),
        "old_in_system": int(row.get("old_in_system") or 0),
        "lead": int(row.get("almanah_starts") or 0),
        "direct_source_cnt": int(row.get("direct_source_cnt") or 0),
        "subscribed": int(row.get("channel_subscribed") or 0),
        "platform": int(row.get("platform_cnt") or 0),
        "learning": int(row.get("started_learning") or 0),
        "course": int(row.get("completed_course") or 0),
        "simulator": 0,
        "interview": int(row.get("interview_reached") or 0),
        "passed": 0,
        "offer": int(row.get("offer_received") or 0),
        "contract": int(row.get("contract_signed") or 0),
        "distance_grinding": int(row.get("distance_grinding") or 0),
    }


async def load_event_main_report_payload(
    filters: ReportFilters,
    session,
    touch_mode: str = "event",
    display_mode: str = "weekly",
) -> dict[str, Any]:
    from ..reports_roistat_companies import roistat_weekly_by_company

    return await roistat_weekly_by_company(
        event_start=filters.start_date,
        event_end=filters.end_date,
        mode=touch_mode,
        first_touch_start=None,
        first_touch_end=None,
        display_mode=display_mode,
        bots=filters.bots or None,
        advertising_companies=filters.advertising_companies or None,
        utm_source=filters.utm_source or None,
        utm_campaign=filters.utm_campaign or None,
        utm_medium=filters.utm_medium or None,
        utm_content=filters.utm_content or None,
        utm_term=filters.utm_term or None,
        session=session,
    )


async def event_funnel_summary_from_main_report(
    filters: ReportFilters,
    group_by: str,
    session,
    touch_mode: str = "event",
    display_mode: str = "weekly",
) -> list[dict[str, Any]]:
    payload = await load_event_main_report_payload(
        filters,
        session,
        touch_mode=touch_mode,
        display_mode=display_mode,
    )
    source_rows = payload.get("bot_rows" if group_by == "bot_key" else "rows", [])
    grouped: dict[str, dict[str, Any]] = {}
    group_field = "bot_key" if group_by == "bot_key" else "company"
    for row in source_rows:
        group_value = str(row.get(group_field) or "—")
        current = grouped.get(group_value)
        if current is None:
            grouped[group_value] = event_summary_row_from_main_report(row, group_value)
            continue
        current["entered"] += int(row.get("entered_all") or 0)
        current["new_in_system"] += int(row.get("new_in_system") or 0)
        current["old_in_system"] += int(row.get("old_in_system") or 0)
        current["lead"] += int(row.get("almanah_starts") or 0)
        current["direct_source_cnt"] += int(row.get("direct_source_cnt") or 0)
        current["subscribed"] += int(row.get("channel_subscribed") or 0)
        current["platform"] += int(row.get("platform_cnt") or 0)
        current["learning"] += int(row.get("started_learning") or 0)
        current["course"] += int(row.get("completed_course") or 0)
        current["interview"] += int(row.get("interview_reached") or 0)
        current["offer"] += int(row.get("offer_received") or 0)
        current["contract"] += int(row.get("contract_signed") or 0)
        current["distance_grinding"] += int(row.get("distance_grinding") or 0)
    return sorted(grouped.values(), key=lambda item: item["entered"], reverse=True)


async def event_funnel_stages_from_main_report(
    filters: ReportFilters,
    session,
    touch_mode: str = "event",
    display_mode: str = "weekly",
) -> dict[str, int]:
    summary_rows = await event_funnel_summary_from_main_report(
        filters,
        group_by="bot_key",
        session=session,
        touch_mode=touch_mode,
        display_mode=display_mode,
    )
    totals = {key: 0 for key in EVENT_FUNNEL_SUMMARY_KEYS}
    for row in summary_rows:
        for key in EVENT_FUNNEL_SUMMARY_KEYS:
            totals[key] += int(row.get(key) or 0)
    return totals


async def load_ph_mirror_weekly_counts(start_date: Optional[date], end_date: Optional[date]) -> dict[str, int]:
    dsn = getattr(settings, "lead_db_dsn", None)
    if not dsn:
        return {}

    conn = await asyncpg.connect(str(dsn).replace("postgresql+asyncpg://", "postgresql://"))
    try:
        rows = await conn.fetch(
            """
            SELECT
                DATE_TRUNC('week', ph_registration_at::timestamptz)::date AS week_start,
                COUNT(DISTINCT id) AS cnt
            FROM ph_user_mirror
            WHERE NULLIF(ph_registration_at, '') IS NOT NULL
              AND ($1::date IS NULL OR ph_registration_at::timestamptz::date >= $1::date)
              AND ($2::date IS NULL OR ph_registration_at::timestamptz::date <= $2::date)
            GROUP BY 1
            """,
            start_date,
            end_date,
        )
        return {row["week_start"].isoformat(): int(row["cnt"] or 0) for row in rows}
    finally:
        await conn.close()
