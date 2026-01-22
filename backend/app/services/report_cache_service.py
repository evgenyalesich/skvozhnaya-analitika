from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis_client import RedisCache
from app.services.daily_aggregate_repository import DailyAggregateRepository
from app.services.raw_user_repository import RawUserRepository


class ReportCacheService:
    def __init__(self):
        self.cache = RedisCache()
        self.agg_repo = DailyAggregateRepository()
        self.raw_repo = RawUserRepository()

    async def total(self, session: AsyncSession) -> dict:
        key = "reports:total"
        cached = await self.cache.get_json(key)
        if cached:
            return cached
        total_users = await self.raw_repo.count_total(session)
        total_budget = await self.agg_repo.total_budget(session)
        payload = {
            "total_users": total_users,
            "total_budget": total_budget,
            "cac": (total_budget / total_users) if total_users else None,
        }
        await self.cache.set_json(key, payload, ttl=settings.cache_ttl_seconds)
        return payload

    async def daily(self, session: AsyncSession, limit: int = 30) -> Sequence[dict]:
        key = "reports:daily"
        cached = await self.cache.get_json(key)
        if cached:
            if len(cached) >= limit:
                return cached[:limit]
            return cached
        data = await self.agg_repo.fetch_daily(session, limit)
        await self.cache.set_json(key, data, ttl=settings.cache_ttl_seconds)
        return data

    async def breakdown(self, session: AsyncSession, group_by: str, limit: int = 20) -> Sequence[dict]:
        key = f"reports:breakdown:{group_by}"
        cached = await self.cache.get_json(key)
        if cached:
            if len(cached) >= limit:
                return cached[:limit]
            return cached
        data = await self.agg_repo.fetch_breakdown(session, group_by, limit)
        await self.cache.set_json(key, data, ttl=settings.cache_ttl_seconds)
        return data
