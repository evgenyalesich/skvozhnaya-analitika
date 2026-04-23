import asyncpg
from sqlalchemy import update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.analytics import RawBotUser


class LeadIngestor:
    def __init__(self):
        pass

    async def ingest(self, session: AsyncSession) -> None:
        if not getattr(settings, "lead_db_dsn", None):
            return
        lead_users = await self._fetch_lead_users()
        if not lead_users:
            return
        chunk_size = 10000
        lead_ids = [row["id"] for row in lead_users]
        for i in range(0, len(lead_ids), chunk_size):
            chunk = lead_ids[i : i + chunk_size]
            stmt = (
                update(RawBotUser)
                .where(RawBotUser.tg_user_id.in_(chunk))
                .values(converted_to_lead=True)
            )
            await session.execute(stmt)
        lead_usernames = [
            self._normalize_username(row["username"])
            for row in lead_users
            if row.get("username")
        ]
        lead_usernames = [name for name in lead_usernames if name]
        if lead_usernames:
            for i in range(0, len(lead_usernames), chunk_size):
                chunk = lead_usernames[i : i + chunk_size]
                stmt = (
                    update(RawBotUser)
                    .where(func.lower(func.ltrim(RawBotUser.username, "@")).in_(chunk))
                    .values(converted_to_lead=True)
                )
                await session.execute(stmt)

    async def _fetch_lead_users(self) -> list[dict]:
        dsn = str(settings.lead_db_dsn)
        if dsn.startswith("postgresql+asyncpg://"):
            dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(
                "SELECT id, username FROM users WHERE id IS NOT NULL"
            )
            return [dict(row) for row in rows]
        finally:
            await conn.close()

    def _normalize_username(self, value: str) -> str:
        return value.strip().lstrip("@").lower() if value else ""
