import hashlib
import json
from datetime import date
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.report_filters import ReportFilters
from app.core.config import settings
from app.core.redis_client import RedisCache
from app.services.report_repository import ReportRepository


class ReportCacheService:
    def __init__(self):
        self.cache = RedisCache()
        self.repo = ReportRepository()

    async def total(self, session: AsyncSession, filters: ReportFilters) -> dict:
        key = "reports:total"
        if not filters.has_filters():
            cached = await self.cache.get_json(key)
            if cached:
                return cached
        payload = await self.repo.total(session, filters)
        if not filters.has_filters():
            await self.cache.set_json(key, payload, ttl=settings.cache_ttl_seconds)
        return payload

    async def daily(self, session: AsyncSession, filters: ReportFilters, limit: int | None = None) -> Sequence[dict]:
        key = "reports:daily"
        if not filters.has_filters():
            cached = await self.cache.get_json(key)
            if cached:
                if limit and len(cached) >= limit:
                    return cached[:limit]
                return cached
        data = await self.repo.daily(session, filters, limit)
        if not filters.has_filters():
            await self.cache.set_json(key, data, ttl=settings.cache_ttl_seconds)
        return data

    async def breakdown(
        self, session: AsyncSession, filters: ReportFilters, group_by: str, limit: int = 20
    ) -> Sequence[dict]:
        key = f"reports:breakdown:{group_by}"
        if not filters.has_filters() and group_by == "utm_source":
            cached = await self.cache.get_json(key)
            if cached:
                if len(cached) >= limit:
                    return cached[:limit]
                return cached
        breakdown_data = await self.repo.breakdown(session, filters, group_by, limit)
        payload = [
            {"group": result.group, "users": result.users, "budget": result.budget}
            for result in breakdown_data
        ]
        if not filters.has_filters() and group_by == "utm_source":
            await self.cache.set_json(key, payload, ttl=settings.cache_ttl_seconds)
        return payload

    async def conversions(self, session: AsyncSession, filters: ReportFilters) -> Sequence[dict]:
        data = await self.repo.conversions(session, filters)
        return data

    async def stages(self, session: AsyncSession, filters: ReportFilters) -> dict:
        key = "reports:stages"
        if not filters.has_filters():
            cached = await self.cache.get_json(key)
            if cached:
                return cached
        payload = await self.repo.stages(session, filters)
        if not filters.has_filters():
            await self.cache.set_json(key, payload, ttl=settings.cache_ttl_seconds)
        return payload

    async def summary(self, session: AsyncSession, filters: ReportFilters, group_by: str) -> Sequence[dict]:
        key = f"reports:summary:{group_by}"
        if not filters.has_filters():
            cached = await self.cache.get_json(key)
            if cached:
                return cached
        payload = await self.repo.summary(session, filters, group_by)
        if not filters.has_filters():
            await self.cache.set_json(key, payload, ttl=settings.cache_ttl_seconds)
        return payload

    async def subscriptions_vs_starts(
        self,
        session: AsyncSession,
        start_date: str | date | None = None,
        end_date: str | date | None = None,
        group_by_campaign: bool = False,
        interval: str = "day",
        channel_id: str | None = None,
        community_id: str | None = None,
        bots: list[str] | None = None,
        advertising_companies: list[str] | None = None,
        utm_source: list[str] | None = None,
        utm_campaign: list[str] | None = None,
        utm_medium: list[str] | None = None,
        utm_content: list[str] | None = None,
        utm_term: list[str] | None = None,
    ) -> Sequence[dict]:
        cache_payload = {
            "start_date": start_date.isoformat() if isinstance(start_date, date) else start_date,
            "end_date": end_date.isoformat() if isinstance(end_date, date) else end_date,
            "group_by_campaign": group_by_campaign,
            "interval": interval,
            "channel_id": channel_id,
            "community_id": community_id,
            "bots": sorted(bots or []),
            "advertising_companies": sorted(advertising_companies or []),
            "utm_source": sorted(utm_source or []),
            "utm_campaign": sorted(utm_campaign or []),
            "utm_medium": sorted(utm_medium or []),
            "utm_content": sorted(utm_content or []),
            "utm_term": sorted(utm_term or []),
        }
        fingerprint = hashlib.sha1(
            json.dumps(cache_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        # Versioned key to invalidate old payload shape/logic without manual Redis cleanup.
        cache_key = f"reports:subscriptions_vs_starts:v3:{fingerprint}"
        cached = await self.cache.get_json(cache_key)
        if cached is not None:
            return cached

        payload = await self.repo.subscriptions_vs_starts(
            session,
            start_date,
            end_date,
            group_by_campaign=group_by_campaign,
            interval=interval,
            channel_id=channel_id,
            community_id=community_id,
            bots=bots,
            advertising_companies=advertising_companies,
            utm_source=utm_source,
            utm_campaign=utm_campaign,
            utm_medium=utm_medium,
            utm_content=utm_content,
            utm_term=utm_term,
        )
        # Avoid overwriting the last good payload with an empty result.
        if payload:
            await self.cache.set_json(cache_key, payload, ttl=settings.cache_ttl_seconds)
            await self.cache.set_json(f"{cache_key}:last_good", payload)
            return payload

        last_good = await self.cache.get_json(f"{cache_key}:last_good")
        if last_good is not None:
            return last_good
        return payload

    async def course_mix(
        self,
        session: AsyncSession,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[dict]:
        return await self.repo.course_mix(session, start_date, end_date)

    async def touch_summary(
        self,
        session: AsyncSession,
        start_date: str | None = None,
        end_date: str | None = None,
        mode: str = "first",
    ) -> Sequence[dict]:
        return await self.repo.touch_summary(session, start_date, end_date, mode)

    async def touch_funnel_summary(
        self,
        session: AsyncSession,
        filters: ReportFilters,
        mode: str = "last",
    ) -> Sequence[dict]:
        return await self.repo.touch_funnel_summary(session, filters, mode)

    async def touch_weekly(
        self,
        session: AsyncSession,
        group_key: str,
        mode: str = "last",
    ) -> dict:
        months, data = await self.repo.touch_weekly(session, group_key, mode)
        return {"months": months, "data": data}

    async def budget_weekly_report(
        self,
        session: AsyncSession,
        start_date: str | None = None,
        end_date: str | None = None,
        interval: str = "week",
    ) -> Sequence[dict]:
        return await self.repo.budget_weekly_report(session, start_date, end_date, interval)
