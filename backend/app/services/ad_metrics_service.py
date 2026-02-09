from typing import List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import AdMetricsWeekly


class AdMetricsService:
    async def get_by_key(
        self,
        session: AsyncSession,
        week_start,
        campaign: str,
        bot_key: str | None,
    ) -> AdMetricsWeekly | None:
        stmt = select(AdMetricsWeekly).where(
            AdMetricsWeekly.week_start == week_start,
            AdMetricsWeekly.campaign == campaign,
            AdMetricsWeekly.bot_key == bot_key,
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def upsert_spend(
        self,
        session: AsyncSession,
        week_start,
        campaign: str,
        bot_key: str | None,
        spend: float,
    ) -> AdMetricsWeekly:
        row = await self.get_by_key(session, week_start, campaign, bot_key)
        if row:
            stmt = (
                update(AdMetricsWeekly)
                .where(AdMetricsWeekly.id == row.id)
                .values(spend=spend)
                .returning(AdMetricsWeekly)
            )
            result = await session.execute(stmt)
            return result.scalar_one()

        row = AdMetricsWeekly(
            week_start=week_start,
            campaign=campaign,
            bot_key=bot_key,
            impressions=0,
            clicks=0,
            spend=spend,
        )
        session.add(row)
        return row
    async def list_rows(
        self,
        session: AsyncSession,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[AdMetricsWeekly]:
        stmt = select(AdMetricsWeekly).order_by(AdMetricsWeekly.week_start.desc(), AdMetricsWeekly.campaign.asc())
        if start_date:
            stmt = stmt.where(AdMetricsWeekly.week_start >= start_date)
        if end_date:
            stmt = stmt.where(AdMetricsWeekly.week_start <= end_date)
        return (await session.execute(stmt)).scalars().all()

    async def create(self, session: AsyncSession, payload: AdMetricsWeekly) -> AdMetricsWeekly:
        session.add(payload)
        return payload

    async def update(self, session: AsyncSession, row_id: int, patch: dict) -> AdMetricsWeekly | None:
        if not patch:
            return await self.get(session, row_id)
        stmt = (
            update(AdMetricsWeekly)
            .where(AdMetricsWeekly.id == row_id)
            .values(**patch)
            .returning(AdMetricsWeekly)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, session: AsyncSession, row_id: int) -> None:
        await session.execute(delete(AdMetricsWeekly).where(AdMetricsWeekly.id == row_id))

    async def get(self, session: AsyncSession, row_id: int) -> AdMetricsWeekly | None:
        stmt = select(AdMetricsWeekly).where(AdMetricsWeekly.id == row_id)
        return (await session.execute(stmt)).scalar_one_or_none()
