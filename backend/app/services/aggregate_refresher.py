from datetime import date, datetime, timedelta
from collections import defaultdict
from typing import Dict, List

import os

from sqlalchemy import select, func, delete, insert, text, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis_client import RedisCache
from app.db.session import async_session
from app.models.analytics import (
    RawBotUser,
    DailyNewUsersAgg,
    TgSubsDailyAgg,
    WeeklyFunnelBotAgg,
    WeeklyFunnelCompanyAgg,
)
from app.services.employee_registry_service import apply_employee_exclusion


STAGE_KEYS = [
    "entered",
    "new_in_system",
    "old_in_system",
    "lead",
    "platform",
    "learning",
    "course",
    "interview",
    "passed",
    "offer",
    "contract",
    "distance_grinding",
]

SUMMARY_KEYS = [
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
    week_start = func.date_trunc("week", RawBotUser.created_at).label("week_start")
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


class AggregateRefresher:
    def __init__(self):
        self.cache = RedisCache()

    async def refresh(self, days: int | None = None) -> None:
        async with async_session() as session:
            window_start = await self._resolve_window_start(session, days)
            backup = await self._snapshot_daily(session, window_start)
            try:
                await session.execute(delete(DailyNewUsersAgg).where(DailyNewUsersAgg.day >= window_start))
                week_start = _week_floor(window_start)
                await session.execute(delete(WeeklyFunnelBotAgg).where(WeeklyFunnelBotAgg.week_start >= week_start))
                await session.execute(
                    delete(WeeklyFunnelCompanyAgg).where(WeeklyFunnelCompanyAgg.week_start >= week_start)
                )
                await session.commit()
                await self._rebuild_aggregates(session, window_start)
                await self._rebuild_tg_subs_daily(session, window_start)
                await self._rebuild_weekly_funnel_bot(session, week_start)
                await self._rebuild_weekly_funnel_company(session, week_start)
                await self._cache_reports(session, days if days and days > 0 else settings.aggregate_refresh_days)
                await self._cache_weekly_bot_stats(session, window_start)
                await self._cache_weekly_company_stats(session, window_start)
            except Exception:
                await session.rollback()
                if backup:
                    await self._restore_backup(session, backup)
                raise

    async def _resolve_window_start(self, session: AsyncSession, days: int | None) -> date:
        effective_days = days if days is not None and days > 0 else settings.aggregate_refresh_days
        if effective_days and effective_days > 0:
            return date.today() - timedelta(days=effective_days - 1)
        stmt = select(func.min(func.date(RawBotUser.created_at)))
        stmt = apply_employee_exclusion(stmt, RawBotUser.tg_user_id)
        result = await session.execute(stmt)
        min_date = result.scalar_one_or_none()
        return min_date or date.today()

    async def _rebuild_aggregates(self, session: AsyncSession, window_start: date) -> None:
        utm_source = func.coalesce(RawBotUser.platform_utm_source, RawBotUser.utm_source, "").label("utm_source")
        utm_campaign = func.coalesce(RawBotUser.platform_utm_campaign, RawBotUser.utm_campaign, "").label("utm_campaign")
        advertising_company = func.coalesce(RawBotUser.advertising_company, "").label(
            "advertising_company"
        )
        stmt = (
            select(
                func.date(RawBotUser.created_at).label("day"),
                RawBotUser.bot_key,
                utm_source,
                utm_campaign,
                advertising_company,
                func.count().label("users"),
                func.coalesce(func.sum(RawBotUser.budget), 0).label("budget"),
            )
            .group_by(
                func.date(RawBotUser.created_at),
                RawBotUser.bot_key,
                utm_source,
                utm_campaign,
                advertising_company,
            )
        )
        if window_start is not None:
            stmt = stmt.where(RawBotUser.created_at >= window_start)
        stmt = apply_employee_exclusion(stmt, RawBotUser.tg_user_id)
        result = await session.execute(stmt)
        records = []
        for row in result.all():
            users = row.users or 0
            budget = row.budget or 0.0
            cac = budget / users if users else None
            records.append(
                {
                    "day": row.day,
                    "bot_key": row.bot_key,
                    "utm_source": row.utm_source,
                    "utm_campaign": row.utm_campaign,
                    "advertising_company": row.advertising_company,
                    "users": users,
                    "budget": budget,
                    "cac": cac,
                }
            )
        if records:
            insert_stmt = insert(DailyNewUsersAgg)
            await session.execute(insert_stmt, records)
            await session.commit()

    async def _snapshot_daily(self, session: AsyncSession, window_start: date) -> List[dict]:
        stmt = (
            select(
                DailyNewUsersAgg.day,
                DailyNewUsersAgg.bot_key,
                DailyNewUsersAgg.utm_source,
                DailyNewUsersAgg.utm_campaign,
                DailyNewUsersAgg.advertising_company,
                DailyNewUsersAgg.users,
                DailyNewUsersAgg.budget,
                DailyNewUsersAgg.cac,
            )
            .where(DailyNewUsersAgg.day >= window_start)
        )
        result = await session.execute(stmt)
        rows = result.fetchall()
        payload = []
        for row in rows:
            payload.append(
                {
                    "day": row.day,
                    "bot_key": row.bot_key,
                    "utm_source": row.utm_source,
                    "utm_campaign": row.utm_campaign,
                    "advertising_company": row.advertising_company,
                    "users": row.users,
                    "budget": row.budget,
                    "cac": row.cac,
                }
            )
        return payload

    async def _restore_backup(self, session: AsyncSession, backup: List[dict]) -> None:
        if not backup:
            return
        insert_stmt = insert(DailyNewUsersAgg)
        await session.execute(insert_stmt, backup)
        await session.commit()

    async def _rebuild_tg_subs_daily(self, session: AsyncSession, window_start: date) -> None:
        channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
        community_id = os.getenv("TELEGRAM_COMMUNITY_ID")
        if not channel_id and not community_id:
            await session.execute(delete(TgSubsDailyAgg).where(TgSubsDailyAgg.day >= window_start))
            await session.commit()
            return

        await session.execute(delete(TgSubsDailyAgg).where(TgSubsDailyAgg.day >= window_start))
        channel_filter = "1=0"
        community_filter = "1=0"
        params: dict[str, object] = {"window_start": window_start}
        if channel_id:
            channel_filter = "e.channel_id = :channel_id"
            params["channel_id"] = str(channel_id)
        if community_id:
            community_filter = "e.channel_id = :community_id"
            params["community_id"] = str(community_id)

        query = text(
            f"""
            WITH user_dim AS (
                SELECT
                    tg_user_id,
                    COALESCE(MAX(first_touch_campaign), 'нет метки') AS campaign,
                    COALESCE(MAX(bot_key), '') AS bot_key,
                    COALESCE(MAX(advertising_company), '') AS advertising_company,
                    COALESCE(MAX(utm_source), '') AS utm_source,
                    COALESCE(MAX(utm_campaign), '') AS utm_campaign,
                    COALESCE(MAX(utm_medium), '') AS utm_medium,
                    COALESCE(MAX(utm_content), '') AS utm_content,
                    COALESCE(MAX(utm_term), '') AS utm_term
                FROM raw_bot_users
                WHERE tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                GROUP BY tg_user_id
            ),
            first_touch AS (
                SELECT
                    ru.tg_user_id,
                    MIN(ru.created_at)::date AS day
                FROM raw_bot_users ru
                WHERE ru.created_at IS NOT NULL
                  AND ru.tg_user_id > 0
                  AND ru.tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                  AND lower(COALESCE(ru.bot_key, '')) NOT LIKE 'lead%%'
                GROUP BY ru.tg_user_id
            ),
            almanah_touch AS (
                SELECT
                    ru.tg_user_id,
                    MIN(ru.created_at)::date AS day
                FROM raw_bot_users ru
                WHERE ru.created_at IS NOT NULL
                  AND ru.tg_user_id > 0
                  AND ru.tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                  AND lower(COALESCE(ru.bot_key, '')) LIKE 'lead%%'
                GROUP BY ru.tg_user_id
            ),
            bot_starts AS (
                SELECT
                    ft.day,
                    ud.campaign,
                    ud.bot_key,
                    ud.advertising_company,
                    ud.utm_source,
                    ud.utm_campaign,
                    ud.utm_medium,
                    ud.utm_content,
                    ud.utm_term,
                    COUNT(*) AS bot_starts
                FROM first_touch ft
                JOIN user_dim ud ON ud.tg_user_id = ft.tg_user_id
                WHERE ft.day >= :window_start
                GROUP BY
                    ft.day, ud.campaign, ud.bot_key, ud.advertising_company,
                    ud.utm_source, ud.utm_campaign, ud.utm_medium, ud.utm_content, ud.utm_term
            ),
            almanah_starts AS (
                SELECT
                    at.day,
                    ud.campaign,
                    ud.bot_key,
                    ud.advertising_company,
                    ud.utm_source,
                    ud.utm_campaign,
                    ud.utm_medium,
                    ud.utm_content,
                    ud.utm_term,
                    COUNT(*) AS almanah_starts
                FROM almanah_touch at
                JOIN user_dim ud ON ud.tg_user_id = at.tg_user_id
                WHERE at.day >= :window_start
                GROUP BY
                    at.day, ud.campaign, ud.bot_key, ud.advertising_company,
                    ud.utm_source, ud.utm_campaign, ud.utm_medium, ud.utm_content, ud.utm_term
            ),
            channel_events AS (
                SELECT
                    e.checked_at::date AS day,
                    ud.campaign,
                    ud.bot_key,
                    ud.advertising_company,
                    ud.utm_source,
                    ud.utm_campaign,
                    ud.utm_medium,
                    ud.utm_content,
                    ud.utm_term,
                    COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.status = 'subscribed') AS channel_subscribed,
                    COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.status = 'unsubscribed') AS channel_unsubscribed
                FROM telegram_subscription_events e
                JOIN user_dim ud ON ud.tg_user_id = e.tg_user_id
                WHERE {channel_filter}
                  AND e.checked_at::date >= :window_start
                GROUP BY
                    e.checked_at::date, ud.campaign, ud.bot_key, ud.advertising_company,
                    ud.utm_source, ud.utm_campaign, ud.utm_medium, ud.utm_content, ud.utm_term
            ),
            community_events AS (
                SELECT
                    e.checked_at::date AS day,
                    ud.campaign,
                    ud.bot_key,
                    ud.advertising_company,
                    ud.utm_source,
                    ud.utm_campaign,
                    ud.utm_medium,
                    ud.utm_content,
                    ud.utm_term,
                    COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.status = 'subscribed') AS saloon_subscribed,
                    COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.status = 'unsubscribed') AS saloon_unsubscribed
                FROM telegram_subscription_events e
                JOIN user_dim ud ON ud.tg_user_id = e.tg_user_id
                WHERE {community_filter}
                  AND e.checked_at::date >= :window_start
                GROUP BY
                    e.checked_at::date, ud.campaign, ud.bot_key, ud.advertising_company,
                    ud.utm_source, ud.utm_campaign, ud.utm_medium, ud.utm_content, ud.utm_term
            ),
            merged AS (
                SELECT
                    COALESCE(bs.day, als.day, ce.day, cme.day) AS day,
                    COALESCE(bs.campaign, als.campaign, ce.campaign, cme.campaign) AS campaign,
                    COALESCE(bs.bot_key, als.bot_key, ce.bot_key, cme.bot_key) AS bot_key,
                    COALESCE(bs.advertising_company, als.advertising_company, ce.advertising_company, cme.advertising_company) AS advertising_company,
                    COALESCE(bs.utm_source, als.utm_source, ce.utm_source, cme.utm_source) AS utm_source,
                    COALESCE(bs.utm_campaign, als.utm_campaign, ce.utm_campaign, cme.utm_campaign) AS utm_campaign,
                    COALESCE(bs.utm_medium, als.utm_medium, ce.utm_medium, cme.utm_medium) AS utm_medium,
                    COALESCE(bs.utm_content, als.utm_content, ce.utm_content, cme.utm_content) AS utm_content,
                    COALESCE(bs.utm_term, als.utm_term, ce.utm_term, cme.utm_term) AS utm_term,
                    COALESCE(bs.bot_starts, 0) AS bot_starts,
                    COALESCE(als.almanah_starts, 0) AS almanah_starts,
                    COALESCE(ce.channel_subscribed, 0) AS channel_subscribed,
                    COALESCE(ce.channel_unsubscribed, 0) AS channel_unsubscribed,
                    COALESCE(cme.saloon_subscribed, 0) AS saloon_subscribed,
                    COALESCE(cme.saloon_unsubscribed, 0) AS saloon_unsubscribed
                FROM bot_starts bs
                FULL OUTER JOIN almanah_starts als ON
                    bs.day = als.day AND bs.campaign = als.campaign AND bs.bot_key = als.bot_key
                    AND bs.advertising_company = als.advertising_company
                    AND bs.utm_source = als.utm_source AND bs.utm_campaign = als.utm_campaign
                    AND bs.utm_medium = als.utm_medium AND bs.utm_content = als.utm_content
                    AND bs.utm_term = als.utm_term
                FULL OUTER JOIN channel_events ce ON
                    COALESCE(bs.day, als.day) = ce.day
                    AND COALESCE(bs.campaign, als.campaign) = ce.campaign
                    AND COALESCE(bs.bot_key, als.bot_key) = ce.bot_key
                    AND COALESCE(bs.advertising_company, als.advertising_company) = ce.advertising_company
                    AND COALESCE(bs.utm_source, als.utm_source) = ce.utm_source
                    AND COALESCE(bs.utm_campaign, als.utm_campaign) = ce.utm_campaign
                    AND COALESCE(bs.utm_medium, als.utm_medium) = ce.utm_medium
                    AND COALESCE(bs.utm_content, als.utm_content) = ce.utm_content
                    AND COALESCE(bs.utm_term, als.utm_term) = ce.utm_term
                FULL OUTER JOIN community_events cme ON
                    COALESCE(bs.day, als.day, ce.day) = cme.day
                    AND COALESCE(bs.campaign, als.campaign, ce.campaign) = cme.campaign
                    AND COALESCE(bs.bot_key, als.bot_key, ce.bot_key) = cme.bot_key
                    AND COALESCE(bs.advertising_company, als.advertising_company, ce.advertising_company) = cme.advertising_company
                    AND COALESCE(bs.utm_source, als.utm_source, ce.utm_source) = cme.utm_source
                    AND COALESCE(bs.utm_campaign, als.utm_campaign, ce.utm_campaign) = cme.utm_campaign
                    AND COALESCE(bs.utm_medium, als.utm_medium, ce.utm_medium) = cme.utm_medium
                    AND COALESCE(bs.utm_content, als.utm_content, ce.utm_content) = cme.utm_content
                    AND COALESCE(bs.utm_term, als.utm_term, ce.utm_term) = cme.utm_term
            )
            INSERT INTO agg_tg_subs_daily (
                day, campaign, bot_key, advertising_company,
                utm_source, utm_campaign, utm_medium, utm_content, utm_term,
                bot_starts, almanah_starts,
                channel_subscribed, channel_unsubscribed,
                saloon_subscribed, saloon_unsubscribed
            )
            SELECT
                day, campaign, bot_key, advertising_company,
                utm_source, utm_campaign, utm_medium, utm_content, utm_term,
                bot_starts, almanah_starts,
                channel_subscribed, channel_unsubscribed,
                saloon_subscribed, saloon_unsubscribed
            FROM merged
            WHERE day IS NOT NULL
            """
        )
        await session.execute(query, params)
        await session.commit()

    async def _get_platform_by_week(self, session: AsyncSession, week_start: date) -> dict:
        """Global deduplicated PH registration count per week (by platform_registered_at)."""
        result = await session.execute(
            text("""
                SELECT
                    DATE_TRUNC('week', platform_registered_at AT TIME ZONE 'Europe/Moscow')::date AS wk,
                    COUNT(DISTINCT ph_user_id) AS cnt
                FROM raw_bot_users
                WHERE ph_user_id IS NOT NULL
                  AND platform_registered_at IS NOT NULL
                  AND bot_key = 'lead'
                  AND tg_user_id < 0
                  AND (platform_registered_at AT TIME ZONE 'Europe/Moscow')::date >= :week_start
                GROUP BY 1
            """),
            {"week_start": week_start},
        )
        return {row.wk: int(row.cnt) for row in result}

    async def _rebuild_weekly_funnel_bot(self, session: AsyncSession, week_start: date) -> None:
        platform_by_week = await self._get_platform_by_week(session, week_start)
        stage_stmt = _stage_counts_stmt(RawBotUser.bot_key, week_start)
        result = await session.execute(stage_stmt)
        records = []
        for row in result:
            if not row.group_key or not row.week_start:
                continue
            wk = _normalize_week_key(row.week_start)
            record = {
                "week_start": wk,
                "bot_key": row.group_key,
            }
            for key in SUMMARY_KEYS:
                record[key] = getattr(row, key, 0) or 0
            record["platform"] = platform_by_week.get(wk, 0)
            records.append(record)
        if records:
            await session.execute(insert(WeeklyFunnelBotAgg), records)
            await session.commit()

    async def _rebuild_weekly_funnel_company(self, session: AsyncSession, week_start: date) -> None:
        platform_by_week = await self._get_platform_by_week(session, week_start)
        stage_stmt = _stage_counts_stmt(RawBotUser.advertising_company, week_start).where(
            RawBotUser.advertising_company.is_not(None),
            RawBotUser.advertising_company != "",
        )
        result = await session.execute(stage_stmt)
        records = []
        for row in result:
            if not row.group_key or not row.week_start:
                continue
            wk = _normalize_week_key(row.week_start)
            record = {
                "week_start": wk,
                "advertising_company": row.group_key,
            }
            for key in SUMMARY_KEYS:
                record[key] = getattr(row, key, 0) or 0
            record["platform"] = platform_by_week.get(wk, 0)
            records.append(record)
        if records:
            await session.execute(insert(WeeklyFunnelCompanyAgg), records)
            await session.commit()

    async def _cache_reports(self, session: AsyncSession, days: int) -> None:
        total_stmt = select(func.coalesce(func.sum(DailyNewUsersAgg.users), 0).label("users"), func.coalesce(func.sum(DailyNewUsersAgg.budget), 0).label("budget"))
        total_result = await session.execute(total_stmt)
        total_row = total_result.one()
        total_users = total_row.users
        total_budget = total_row.budget
        total_cac = (total_budget / total_users) if total_users else None
        await self.cache.set_json(
            "reports:total",
            {"total_users": total_users, "total_budget": total_budget, "cac": total_cac},
            ttl=settings.cache_ttl_seconds,
        )

        daily_stmt = (
            select(
                DailyNewUsersAgg.day,
                func.sum(DailyNewUsersAgg.users).label("users"),
            )
            .group_by(DailyNewUsersAgg.day)
            .order_by(DailyNewUsersAgg.day.desc())
            .limit(days)
        )
        daily_result = await session.execute(daily_stmt)
        daily_data = [
            {"date": row.day.isoformat(), "users": row.users}
            for row in daily_result.all()
        ]
        await self.cache.set_json("reports:daily", daily_data, ttl=settings.cache_ttl_seconds)

        breakdown_stmt = (
            select(
                DailyNewUsersAgg.utm_source.label("group"),
                func.sum(DailyNewUsersAgg.users).label("users"),
                func.sum(DailyNewUsersAgg.budget).label("budget"),
            )
            .group_by(DailyNewUsersAgg.utm_source)
            .order_by(func.sum(DailyNewUsersAgg.users).desc())
            .limit(20)
        )
        breakdown_result = await session.execute(breakdown_stmt)
        breakdown_data = [
            {"group": row.group, "users": row.users, "budget": row.budget}
            for row in breakdown_result.all()
        ]
        await self.cache.set_json(
            "reports:breakdown:utm_source",
            breakdown_data,
            ttl=settings.cache_ttl_seconds,
        )

    async def _cache_weekly_bot_stats(self, session: AsyncSession, window_start: date) -> None:
        stage_data: Dict[str, Dict[date, Dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: {key: 0 for key in STAGE_KEYS})
        )
        result = await session.execute(
            select(WeeklyFunnelBotAgg).where(WeeklyFunnelBotAgg.week_start >= _week_floor(window_start))
        )
        for row in result.scalars():
            if not row.bot_key or not row.week_start:
                continue
            values = stage_data[row.bot_key][row.week_start]
            for key in STAGE_KEYS:
                values[key] = getattr(row, key, 0) or 0

        for bot_key, weeks in stage_data.items():
            base_key = f"reports:weekly:bot:{bot_key}"
            month_keys = []
            monthly_rows: Dict[str, List[Dict[str, Dict]]] = defaultdict(list)
            for week_start_value in _resolve_group_week_range(weeks, date.today()):
                values = weeks.get(week_start_value, {key: 0 for key in STAGE_KEYS})
                month_key = week_start_value.strftime("%Y-%m")
                week_end = (week_start_value + timedelta(days=6)).isoformat()
                monthly_rows[month_key].append(
                    {
                        "week_start": week_start_value.isoformat(),
                        "week_end": week_end,
                        "values": values,
                    }
                )
                month_keys.append(month_key)
            for month_key, rows in monthly_rows.items():
                await self.cache.set_json(
                    f"{base_key}:{month_key}", rows, ttl=settings.weekly_cache_ttl_seconds
                )
            await self.cache.set_json(
                f"{base_key}:months", sorted(set(month_keys)), ttl=settings.weekly_cache_ttl_seconds
            )

    async def _cache_weekly_company_stats(self, session: AsyncSession, window_start: date) -> None:
        stage_data: Dict[str, Dict[date, Dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: {key: 0 for key in STAGE_KEYS})
        )
        result = await session.execute(
            select(WeeklyFunnelCompanyAgg).where(WeeklyFunnelCompanyAgg.week_start >= _week_floor(window_start))
        )
        for row in result.scalars():
            if not row.advertising_company or not row.week_start:
                continue
            values = stage_data[row.advertising_company][row.week_start]
            for key in STAGE_KEYS:
                values[key] = getattr(row, key, 0) or 0

        for company, weeks in stage_data.items():
            base_key = f"reports:weekly:company:{company}"
            month_keys = []
            monthly_rows: Dict[str, List[Dict[str, Dict]]] = defaultdict(list)
            for week_start_value in _resolve_group_week_range(weeks, date.today()):
                values = weeks.get(week_start_value, {key: 0 for key in STAGE_KEYS})
                month_key = week_start_value.strftime("%Y-%m")
                week_end = (week_start_value + timedelta(days=6)).isoformat()
                monthly_rows[month_key].append(
                    {
                        "week_start": week_start_value.isoformat(),
                        "week_end": week_end,
                        "values": values,
                    }
                )
                month_keys.append(month_key)
            for month_key, rows in monthly_rows.items():
                await self.cache.set_json(
                    f"{base_key}:{month_key}", rows, ttl=settings.weekly_cache_ttl_seconds
                )
            await self.cache.set_json(
                f"{base_key}:months", sorted(set(month_keys)), ttl=settings.weekly_cache_ttl_seconds
            )
