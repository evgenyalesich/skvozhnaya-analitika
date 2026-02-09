from datetime import date, timedelta
from collections import defaultdict
from typing import Dict, List

import os

from sqlalchemy import select, func, delete, insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis_client import RedisCache
from app.db.session import async_session
from app.models.analytics import RawBotUser, DailyNewUsersAgg, TgSubsDailyAgg


STAGE_KEYS = [
    "entered",
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


def _stage_counts_stmt(selector, window_start):
    week_start = func.date_trunc("week", RawBotUser.created_at).label("week_start")
    entered = func.count(func.distinct(RawBotUser.tg_user_id)).label("entered")
    lead = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        RawBotUser.converted_to_lead.is_(True)
    ).label("lead")
    platform = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        RawBotUser.registered_platform.is_(True)
    ).label("platform")
    learning = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        RawBotUser.started_learning.is_(True)
    ).label("learning")
    course = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
        RawBotUser.completed_course.is_(True)
    ).label("course")
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
            lead,
            platform,
            learning,
            course,
            interview,
            passed,
            offer,
            contract,
            distance_grinding,
        )
        .group_by(selector, week_start)
        .order_by(selector, week_start)
    )
    if window_start is not None:
        stmt = stmt.where(RawBotUser.created_at >= window_start)
    return stmt


class AggregateRefresher:
    def __init__(self):
        self.cache = RedisCache()

    async def refresh(self, days: int | None = None) -> None:
        async with async_session() as session:
            window_start = await self._resolve_window_start(session, days)
            backup = await self._snapshot_daily(session, window_start)
            try:
                await session.execute(delete(DailyNewUsersAgg).where(DailyNewUsersAgg.day >= window_start))
                await session.commit()
                await self._rebuild_aggregates(session, window_start)
                await self._rebuild_tg_subs_daily(session, window_start)
                await self._cache_reports(session, days if days and days > 0 else 90)
                await self._cache_weekly_bot_stats(session, window_start)
                await self._cache_weekly_company_stats(session, window_start)
            except Exception:
                await session.rollback()
                if backup:
                    await self._restore_backup(session, backup)
                raise

    async def _resolve_window_start(self, session: AsyncSession, days: int | None) -> date:
        if days is not None and days > 0:
            return date.today() - timedelta(days=days - 1)
        stmt = select(func.min(func.date(RawBotUser.created_at)))
        result = await session.execute(stmt)
        min_date = result.scalar_one_or_none()
        return min_date or date.today()

    async def _rebuild_aggregates(self, session: AsyncSession, window_start: date) -> None:
        utm_source = func.coalesce(RawBotUser.utm_source, "").label("utm_source")
        utm_campaign = func.coalesce(RawBotUser.utm_campaign, "").label("utm_campaign")
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
                GROUP BY tg_user_id
            ),
            first_touch AS (
                SELECT
                    ru.tg_user_id,
                    MIN(ru.created_at)::date AS day
                FROM raw_bot_users ru
                WHERE ru.created_at IS NOT NULL
                  AND lower(COALESCE(ru.bot_key, '')) NOT LIKE 'lead%%'
                GROUP BY ru.tg_user_id
            ),
            almanah_touch AS (
                SELECT
                    ru.tg_user_id,
                    MIN(ru.created_at)::date AS day
                FROM raw_bot_users ru
                WHERE ru.created_at IS NOT NULL
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
                    COUNT(*) FILTER (WHERE e.status = 'subscribed') AS channel_subscribed,
                    COUNT(*) FILTER (WHERE e.status = 'unsubscribed') AS channel_unsubscribed
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
                    COUNT(*) FILTER (WHERE e.status = 'subscribed') AS saloon_subscribed,
                    COUNT(*) FILTER (WHERE e.status = 'unsubscribed') AS saloon_unsubscribed
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
        entries: Dict[str, Dict[date, int]] = defaultdict(lambda: defaultdict(int))
        week_start = func.date_trunc("week", DailyNewUsersAgg.day).label("week_start")
        daily_stmt = (
            select(
                DailyNewUsersAgg.bot_key.label("group_key"),
                week_start,
                func.sum(DailyNewUsersAgg.users).label("entered"),
            )
            .where(DailyNewUsersAgg.day >= window_start)
            .group_by(DailyNewUsersAgg.bot_key, week_start)
        )
        daily_result = await session.execute(daily_stmt)
        for row in daily_result:
            if row.group_key and row.week_start:
                entries[row.group_key][row.week_start] = row.entered or 0

        stage_stmt = _stage_counts_stmt(RawBotUser.bot_key, window_start)
        stage_result = await session.execute(stage_stmt)
        stage_data: Dict[str, Dict[date, Dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: {key: 0 for key in STAGE_KEYS})
        )
        for group, weeks in entries.items():
            for week_start_value, entered in weeks.items():
                stage_data[group][week_start_value]["entered"] = entered
        for row in stage_result:
            group = row.group_key
            week_start_value = row.week_start
            if not group or not week_start_value:
                continue
            values = stage_data[group][week_start_value]
            for key in STAGE_KEYS:
                values[key] = getattr(row, key, 0) or 0
            values["entered"] = entries[group].get(week_start_value, values["entered"])

        for bot_key, weeks in stage_data.items():
            base_key = f"reports:weekly:bot:{bot_key}"
            month_keys = []
            monthly_rows: Dict[str, List[Dict[str, Dict]]] = defaultdict(list)
            for week_start_value, values in weeks.items():
                month_key = week_start_value.strftime("%Y-%m")
                week_end = (week_start_value + timedelta(days=6)).date().isoformat()
                monthly_rows[month_key].append(
                    {
                        "week_start": week_start_value.date().isoformat(),
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
        entries: Dict[str, Dict[date, int]] = defaultdict(lambda: defaultdict(int))
        week_start = func.date_trunc("week", DailyNewUsersAgg.day).label("week_start")
        daily_stmt = (
            select(
                DailyNewUsersAgg.advertising_company.label("group_key"),
                week_start,
                func.sum(DailyNewUsersAgg.users).label("entered"),
            )
            .where(
                DailyNewUsersAgg.day >= window_start,
                DailyNewUsersAgg.advertising_company.isnot(None),
                DailyNewUsersAgg.advertising_company != "",
            )
            .group_by(DailyNewUsersAgg.advertising_company, week_start)
        )
        daily_result = await session.execute(daily_stmt)
        for row in daily_result:
            if row.group_key and row.week_start:
                entries[row.group_key][row.week_start] = row.entered or 0

        stage_stmt = _stage_counts_stmt(RawBotUser.advertising_company, window_start)
        stage_result = await session.execute(stage_stmt)
        stage_data: Dict[str, Dict[date, Dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: {key: 0 for key in STAGE_KEYS})
        )
        for group, weeks in entries.items():
            for week_start_value, entered in weeks.items():
                stage_data[group][week_start_value]["entered"] = entered
        for row in stage_result:
            group = row.group_key
            week_start_value = row.week_start
            if not group or not week_start_value:
                continue
            if group == "":
                continue
            values = stage_data[group][week_start_value]
            for key in STAGE_KEYS:
                values[key] = getattr(row, key, 0) or 0
            values["entered"] = entries[group].get(week_start_value, values["entered"])

        for company, weeks in stage_data.items():
            base_key = f"reports:weekly:company:{company}"
            month_keys = []
            monthly_rows: Dict[str, List[Dict[str, Dict]]] = defaultdict(list)
            for week_start_value, values in weeks.items():
                month_key = week_start_value.strftime("%Y-%m")
                week_end = (week_start_value + timedelta(days=6)).date().isoformat()
                monthly_rows[month_key].append(
                    {
                        "week_start": week_start_value.date().isoformat(),
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
