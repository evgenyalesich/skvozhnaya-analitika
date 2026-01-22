import os
from typing import Optional

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config_loader import ConfigLoader
from app.models.analytics import RawBotUser


class AdvertisingBudgetIngestor:
    def __init__(self, loader: ConfigLoader):
        self.loader = loader

    async def ingest(self, session: AsyncSession) -> None:
        config = self.loader.advertising_companies()
        budget_config = self.loader.data_sources().get("advertising_api", {})
        manual = budget_config.get("manual_budgets", [])
        for entry in manual:
            company_id = entry.get("company_id")
            amount = entry.get("amount")
            if not company_id or amount is None:
                continue
            company = next((comp for comp in config if comp.get("company_id") == company_id), None)
            if not company:
                continue
            await self._distribute_budget(session, company.get("company_name"), amount)

    async def _distribute_budget(self, session: AsyncSession, company_name: Optional[str], amount: float) -> None:
        if not company_name:
            return
        count_stmt = select(func.count()).where(RawBotUser.advertising_company == company_name)
        result = await session.execute(count_stmt)
        total_users = result.scalar_one() or 0
        if not total_users:
            return
        per_user = amount / total_users
        stmt = (
            update(RawBotUser)
            .where(RawBotUser.advertising_company == company_name)
            .values(budget=per_user)
        )
        await session.execute(stmt)
