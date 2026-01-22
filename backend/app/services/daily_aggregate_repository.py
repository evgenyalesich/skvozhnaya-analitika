from typing import List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import DailyNewUsersAgg


class DailyAggregateRepository:
    FIELD_MAP = {
        "utm_source": DailyNewUsersAgg.utm_source,
        "utm_campaign": DailyNewUsersAgg.utm_campaign,
        "advertising_company": DailyNewUsersAgg.advertising_company,
    }

    async def fetch_daily(self, session: AsyncSession, limit: int = 30) -> List[dict[str, Optional[float]]]:
        stmt = (
            select(
                DailyNewUsersAgg.date,
                DailyNewUsersAgg.users,
                DailyNewUsersAgg.budget,
                DailyNewUsersAgg.cac,
            )
            .order_by(DailyNewUsersAgg.date.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [self._row_to_dict(row) for row in result.all()]

    async def fetch_breakdown(
        self, session: AsyncSession, field: str, limit: int = 20
    ) -> List[dict[str, Optional[float]]]:
        column = self.FIELD_MAP.get(field)
        if not column:
            return []
        stmt = (
            select(
                column.label("group_value"),
                func.sum(DailyNewUsersAgg.users).label("users"),
                func.sum(DailyNewUsersAgg.budget).label("budget"),
            )
            .group_by(column)
            .order_by(desc("users"))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [self._breakdown_row(row) for row in result.all()]

    async def total_budget(self, session: AsyncSession) -> float:
        stmt = select(func.sum(DailyNewUsersAgg.budget))
        result = await session.execute(stmt)
        return result.scalar_one() or 0.0

    @staticmethod
    def _row_to_dict(row) -> dict[str, Optional[float]]:
        return {
            "date": row.date.isoformat() if row.date else None,
            "users": row.users,
            "budget": row.budget,
            "cac": row.cac,
        }

    @staticmethod
    def _breakdown_row(row) -> dict[str, Optional[float]]:
        return {
            "group": row.group_value,
            "users": row.users,
            "budget": row.budget,
        }
