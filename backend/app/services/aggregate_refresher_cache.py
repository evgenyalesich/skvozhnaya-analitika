from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.analytics import DailyNewUsersAgg, WeeklyFunnelBotAgg, WeeklyFunnelCompanyAgg
from app.services.aggregate_refresher_utils import STAGE_KEYS, _resolve_group_week_range, _week_floor


class AggregateRefresherCacheMixin:
    """Прогревает Redis-кеш после пересчёта агрегатов.

    Все методы читают из уже свежих агрегатных таблиц (не из raw_bot_users),
    чтобы прогрев был быстрым и не грузил основную таблицу.
    """

    async def _cache_reports(self, session: AsyncSession, days: int) -> None:
        """Прогревает ключи reports:total, reports:daily (последние days дней),
        reports:breakdown:utm_source — самые часто запрашиваемые срезы."""
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
        """Кеширует недельную воронку по каждому боту в Redis.

        Структура ключей: reports:weekly:bot:{bot_key}:{YYYY-MM} → список недель месяца,
        reports:weekly:bot:{bot_key}:months → список доступных месяцев.
        Такая разбивка по месяцам позволяет фронту загружать данные постранично.
        TTL = weekly_cache_ttl_seconds (default 24h).
        """
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
        """Аналог _cache_weekly_bot_stats, но для рекламных компаний.

        Ключи: reports:weekly:company:{company}:{YYYY-MM}.
        """
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
