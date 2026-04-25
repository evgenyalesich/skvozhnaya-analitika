from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict

from sqlalchemy import Integer, and_, func, select, text

from app.models.analytics import RawBotUser
from app.services.employee_registry_service import apply_employee_exclusion


STAGE_KEYS = [
    "entered",
    "new_in_system",
    "old_in_system",
    "lead",
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

# Weekly agg rebuild writes these counters into agg_weekly_funnel_* tables.
SUMMARY_KEYS = STAGE_KEYS


# ===== Aggregate refresher utility helpers =====
def _generate_all_weeks(window_start: date, window_end: date) -> list[date]:
    """Generate Monday-aligned week starts from window_start to window_end (inclusive)."""
    # align to Monday
    monday = window_start - timedelta(days=window_start.weekday())
    weeks = []
    current = monday
    while current <= window_end:
        weeks.append(current)
        current += timedelta(weeks=1)
    return weeks


def _resolve_group_week_range(weeks: Dict[date, Dict[str, int]], fallback_end: date) -> list[date]:
    """Build weekly range only for the actual lifetime of one group.

    This keeps required zero-weeks inside a group's active timeline, but avoids
    rendering years of leading zeroes before the group existed.
    """
    if not weeks:
        return []
    week_starts = sorted(
        week_start.date() if isinstance(week_start, datetime) else week_start
        for week_start in weeks.keys()
    )
    return _generate_all_weeks(week_starts[0], fallback_end)


def _normalize_week_key(value):
    if isinstance(value, datetime):
        return value.date()
    return value


def _week_floor(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _stage_counts_stmt(selector, window_start):
    first_seen_system_sq = (
        select(
            RawBotUser.tg_user_id.label("tg_user_id"),
            func.min(RawBotUser.created_at).label("first_seen_at_system"),
        )
        .group_by(RawBotUser.tg_user_id)
        .subquery()
    )
    week_start = func.date_trunc("week", func.timezone(text("'Europe/Moscow'"), RawBotUser.created_at)).label("week_start")
    entered = func.count(func.distinct(RawBotUser.tg_user_id)).label("entered")
    new_in_system = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        first_seen_system_sq.c.first_seen_at_system == RawBotUser.created_at
    ).label("new_in_system")
    old_in_system = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        first_seen_system_sq.c.first_seen_at_system < RawBotUser.created_at
    ).label("old_in_system")
    lead = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        RawBotUser.converted_to_lead.is_(True)
    ).label("lead")
    subscribed = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        RawBotUser.channel_subscribed.is_(True)
    ).label("subscribed")
    # platform is overridden after the main query with a global deduped count
    platform = func.cast(0, Integer).label("platform")
    learning = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        RawBotUser.started_learning.is_(True)
    ).label("learning")
    course = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        RawBotUser.completed_course.is_(True),
        RawBotUser.completed_course_at.is_not(None),
        RawBotUser.completed_course_at >= RawBotUser.created_at,
    ).label("course")
    simulator = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        RawBotUser.used_simulator.is_(True)
    ).label("simulator")
    interview = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        RawBotUser.interview_reached.is_(True)
    ).label("interview")
    passed = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        RawBotUser.interview_passed.is_(True)
    ).label("passed")
    offer = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        RawBotUser.offer_received.is_(True)
    ).label("offer")
    contract = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        RawBotUser.contract_signed.is_(True)
    ).label("contract")
    distance_grinding = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        RawBotUser.distance_grinding.is_(True)
    ).label("distance_grinding")
    stmt = (
        select(
            selector.label("group_key"),
            week_start,
            entered,
            new_in_system,
            old_in_system,
            lead,
            subscribed,
            platform,
            learning,
            course,
            simulator,
            interview,
            passed,
            offer,
            contract,
            distance_grinding,
        )
        .join(
            first_seen_system_sq,
            first_seen_system_sq.c.tg_user_id == RawBotUser.tg_user_id,
        )
        .group_by(selector, week_start)
        .order_by(selector, week_start)
    )
    if window_start is not None:
        stmt = stmt.where(RawBotUser.created_at >= window_start)
    return apply_employee_exclusion(stmt, RawBotUser.tg_user_id)
