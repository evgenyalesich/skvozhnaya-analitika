from typing import List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import BudgetWeekly


class BudgetService:
    async def list_budgets(
        self,
        session: AsyncSession,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[BudgetWeekly]:
        stmt = select(BudgetWeekly).order_by(BudgetWeekly.week_start.desc(), BudgetWeekly.campaign.asc())
        if start_date:
            stmt = stmt.where(BudgetWeekly.week_start >= start_date)
        if end_date:
            stmt = stmt.where(BudgetWeekly.week_start <= end_date)
        return (await session.execute(stmt)).scalars().all()

    async def create_budget(self, session: AsyncSession, payload: BudgetWeekly) -> BudgetWeekly:
        session.add(payload)
        return payload

    async def update_budget(
        self, session: AsyncSession, budget_id: int, patch: dict
    ) -> BudgetWeekly | None:
        if not patch:
            return await self.get_budget(session, budget_id)
        stmt = (
            update(BudgetWeekly)
            .where(BudgetWeekly.id == budget_id)
            .values(**patch)
            .returning(BudgetWeekly)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_budget(self, session: AsyncSession, budget_id: int) -> None:
        await session.execute(delete(BudgetWeekly).where(BudgetWeekly.id == budget_id))

    async def get_budget(self, session: AsyncSession, budget_id: int) -> BudgetWeekly | None:
        stmt = select(BudgetWeekly).where(BudgetWeekly.id == budget_id)
        return (await session.execute(stmt)).scalar_one_or_none()
