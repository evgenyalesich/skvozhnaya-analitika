from datetime import date, timedelta
from typing import List

from sqlalchemy import select, func, delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis_client import RedisCache
from app.db.session import async_session
from app.models.analytics import RawBotUser, DailyNewUsersAgg


class AggregateRefresher:
    def __init__(self):
        self.cache = RedisCache()

    async def refresh(self, days: int = 90) -> None:
        window_start = date.today() - timedelta(days=days - 1)
        async with async_session() as session:
            await session.execute(delete(DailyNewUsersAgg).where(DailyNewUsersAgg.date >= window_start))
            await session.commit()
            await self._rebuild_aggregates(session, window_start)
            await self._cache_reports(session, days)

    async def _rebuild_aggregates(self, session: AsyncSession, window_start: date) -> None:
        stmt = (
            select(
                func.date(RawBotUser.created_at).label("date"),
                RawBotUser.bot_key,
                RawBotUser.utm_source,
                RawBotUser.utm_campaign,
                RawBotUser.advertising_company,
                func.count().label("users"),
                func.coalesce(func.sum(RawBotUser.budget), 0).label("budget"),
            )
            .where(RawBotUser.created_at >= window_start)
            .group_by(
                func.date(RawBotUser.created_at),
                RawBotUser.bot_key,
                RawBotUser.utm_source,
                RawBotUser.utm_campaign,
                RawBotUser.advertising_company,
            )
        )
        result = await session.execute(stmt)
        records = []
        for row in result.all():
            users = row.users or 0
            budget = row.budget or 0.0
            cac = budget / users if users else None
            records.append(
                {
                    "date": row.date,
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
                DailyNewUsersAgg.date,
                func.sum(DailyNewUsersAgg.users).label("users"),
            )
            .group_by(DailyNewUsersAgg.date)
            .order_by(DailyNewUsersAgg.date.desc())
            .limit(days)
        )
        daily_result = await session.execute(daily_stmt)
        daily_data = [
            {"date": row.date.isoformat(), "users": row.users}
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
        await self.cache.set_json("reports:breakdown", breakdown_data, ttl=settings.cache_ttl_seconds)
