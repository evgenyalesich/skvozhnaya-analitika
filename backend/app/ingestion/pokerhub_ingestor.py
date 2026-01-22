from datetime import datetime
import os

import asyncpg
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config_loader import ConfigLoader
from app.models.analytics import RawBotUser


class PokerHubIngestor:
    def __init__(self, loader: ConfigLoader):
        self.loader = loader

    async def ingest(self, session: AsyncSession) -> None:
        config = self.loader.data_sources().get("postgres_pokerhub", {})
        dsn_env = config.get("dsn_env")
        dsn = os.environ.get(dsn_env or "")
        if not dsn:
            return

        async with asyncpg.connect(dsn) as conn:
            rows = await conn.fetch(
                """
                SELECT tg_user_id, registered_platform, started_learning, completed_course,
                       used_simulator, interview_reached, interview_passed, offer_received, contract_signed
                FROM learner_journey
                WHERE tg_user_id IS NOT NULL
                """
            )
        await self._apply(session, rows)

    async def _apply(self, session: AsyncSession, rows) -> None:
        for row in rows:
            stmt = (
                update(RawBotUser)
                .where(RawBotUser.tg_user_id == row["tg_user_id"])
                .values(
                    registered_platform=row.get("registered_platform"),
                    started_learning=row.get("started_learning"),
                    completed_course=row.get("completed_course"),
                    used_simulator=row.get("used_simulator"),
                    interview_reached=row.get("interview_reached"),
                    interview_passed=row.get("interview_passed"),
                    offer_received=row.get("offer_received"),
                    contract_signed=row.get("contract_signed"),
                    ingested_at=datetime.utcnow(),
                )
            )
            await session.execute(stmt)
