from __future__ import annotations

import os
from datetime import date
from datetime import timedelta
from typing import Dict, List

from sqlalchemy import and_, delete, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import async_session
from app.core.redis_client import RedisCache
from app.models.analytics import DailyNewUsersAgg, RawBotUser, TgSubsDailyAgg, WeeklyFunnelBotAgg, WeeklyFunnelCompanyAgg
from app.services.aggregate_refresher_utils import (
    SUMMARY_KEYS,
    _generate_all_weeks,
    _normalize_week_key,
    _resolve_group_week_range,
    _stage_counts_stmt,
    _week_floor,
)
from app.services.employee_registry_service import apply_employee_exclusion


class AggregateRefresherRebuildMixin:
    def __init__(self):
        self.cache = RedisCache()

    async def refresh(self, days: int | None = None) -> None:
        """Главный метод — полный цикл пересчёта агрегатов за последние days дней.

        Порядок:
        1. Делает snapshot текущих данных (резервная копия на случай ошибки).
        2. Удаляет старые агрегаты за окно.
        3. Пересчитывает agg_daily_new_users → agg_tg_subs_daily → agg_weekly_funnel_*.
        4. Прогревает кеш.
        При исключении — откатывает и восстанавливает из snapshot.
        """
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
        """Определяет начало окна пересчёта: today - days или самая ранняя дата в raw_bot_users."""
        effective_days = days if days is not None and days > 0 else settings.aggregate_refresh_days
        if effective_days and effective_days > 0:
            return date.today() - timedelta(days=effective_days - 1)
        stmt = select(func.min(func.date(RawBotUser.created_at)))
        stmt = apply_employee_exclusion(stmt, RawBotUser.tg_user_id)
        result = await session.execute(stmt)
        min_date = result.scalar_one_or_none()
        return min_date or date.today()

    async def _rebuild_aggregates(self, session: AsyncSession, window_start: date) -> None:
        """Заполняет agg_daily_new_users: группирует raw_bot_users по дню/боту/utm/компании,
        считает users + budget + CAC. Исключает сотрудников."""
        utm_source = func.coalesce(RawBotUser.platform_utm_source, RawBotUser.utm_source, "").label("utm_source")
        utm_campaign = func.coalesce(RawBotUser.platform_utm_campaign, RawBotUser.utm_campaign, "").label("utm_campaign")
        advertising_company = func.coalesce(RawBotUser.advertising_company, "").label(
            "advertising_company"
        )
        # Вычисляем один раз — иначе SQLAlchemy создаёт два разных bindparam для одного
        # и того же литерала 'Europe/Moscow', и PostgreSQL не может отождествить SELECT и GROUP BY.
        day_msk = func.date(func.timezone(text("'Europe/Moscow'"), RawBotUser.created_at))
        stmt = (
            select(
                day_msk.label("day"),
                RawBotUser.bot_key,
                utm_source,
                utm_campaign,
                advertising_company,
                func.count().label("users"),
                func.coalesce(func.sum(RawBotUser.budget), 0).label("budget"),
            )
            .group_by(
                day_msk,
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
        """Читает текущие agg_daily_new_users за окно в память — резервная копия перед удалением."""
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
        """Восстанавливает snapshot в agg_daily_new_users после ошибки пересчёта."""
        if not backup:
            return
        insert_stmt = insert(DailyNewUsersAgg)
        await session.execute(insert_stmt, backup)
        await session.commit()

    async def _rebuild_tg_subs_daily(self, session: AsyncSession, window_start: date) -> None:
        """Заполняет agg_tg_subs_daily одним большим SQL-запросом (CTE + FULL OUTER JOIN).

        Объединяет 4 источника:
        - bot_starts: первый старт в не-лид боте (first_touch)
        - almanah_starts: первый старт в лид-боте (almanah)
        - channel_events: подписки/отписки из TELEGRAM_CHANNEL_ID
        - community_events: подписки/отписки из TELEGRAM_COMMUNITY_ID
        Если ни один из каналов не настроен — очищает таблицу и выходит.
        """
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
                    (MIN(ru.created_at) AT TIME ZONE 'Europe/Moscow')::date AS day
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
                    (MIN(ru.created_at) AT TIME ZONE 'Europe/Moscow')::date AS day
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
                    (e.checked_at AT TIME ZONE 'Europe/Moscow')::date AS day,
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
                  AND (e.checked_at AT TIME ZONE 'Europe/Moscow')::date >= :window_start
                GROUP BY
                    (e.checked_at AT TIME ZONE 'Europe/Moscow')::date, ud.campaign, ud.bot_key, ud.advertising_company,
                    ud.utm_source, ud.utm_campaign, ud.utm_medium, ud.utm_content, ud.utm_term
            ),
            community_events AS (
                SELECT
                    (e.checked_at AT TIME ZONE 'Europe/Moscow')::date AS day,
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
                  AND (e.checked_at AT TIME ZONE 'Europe/Moscow')::date >= :window_start
                GROUP BY
                    (e.checked_at AT TIME ZONE 'Europe/Moscow')::date, ud.campaign, ud.bot_key, ud.advertising_company,
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
        """Считает уникальных ph_user_id, зарегистрированных на платформе, по неделям.

        Используется как отдельный источник для поля platform в воронке —
        он считается глобально (без группировки по боту/компании), т.к. один
        пользователь может прийти из разных каналов.
        Берёт только bot_key='lead' и tg_user_id < 0 (синтетические лид-записи).
        """
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
        """Заполняет agg_weekly_funnel_bot: воронка за каждую неделю в разбивке по bot_key."""
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
        """Заполняет agg_weekly_funnel_company: аналог _rebuild_weekly_funnel_bot, но по advertising_company."""
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
