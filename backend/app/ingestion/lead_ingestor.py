import asyncio
import logging
import random

import asyncpg
from sqlalchemy import select, update, func
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.analytics import RawBotUser


class LeadIngestor:
    _UPDATE_CHUNK_SIZE = 1000
    _USERNAME_SELECT_CHUNK_SIZE = 250
    _UPDATE_MAX_RETRIES = 5

    def __init__(self):
        self._logger = logging.getLogger("lead_ingestor")

    async def ingest(self, session: AsyncSession) -> None:
        if not getattr(settings, "lead_db_dsn", None):
            return
        lead_users = await self._fetch_lead_users()
        if not lead_users:
            return
        lead_ids = sorted({int(row["id"]) for row in lead_users if row.get("id") is not None})
        for i in range(0, len(lead_ids), self._UPDATE_CHUNK_SIZE):
            chunk = lead_ids[i : i + self._UPDATE_CHUNK_SIZE]
            stmt = (
                update(RawBotUser)
                .where(RawBotUser.tg_user_id.in_(chunk))
                .values(converted_to_lead=True)
            )
            await self._execute_update_with_retry(session, stmt, f"tg_ids[{i}:{i + len(chunk)}]")
        lead_usernames = [
            self._normalize_username(row["username"])
            for row in lead_users
            if row.get("username")
        ]
        lead_usernames = sorted({name for name in lead_usernames if name})
        if lead_usernames:
            await self._mark_leads_by_username(session, lead_usernames)

    async def _mark_leads_by_username(self, session: AsyncSession, lead_usernames: list[str]) -> None:
        target_ids: list[int] = []
        for i in range(0, len(lead_usernames), self._USERNAME_SELECT_CHUNK_SIZE):
            chunk = lead_usernames[i : i + self._USERNAME_SELECT_CHUNK_SIZE]
            query = (
                select(RawBotUser.id)
                .where(func.lower(func.ltrim(RawBotUser.username, "@")).in_(chunk))
                .where(RawBotUser.converted_to_lead.is_not(True))
                .order_by(RawBotUser.id.asc())
            )
            result = await session.execute(query)
            target_ids.extend(int(row_id) for row_id in result.scalars().all())

        target_ids = sorted(set(target_ids))
        for i in range(0, len(target_ids), self._UPDATE_CHUNK_SIZE):
            chunk = target_ids[i : i + self._UPDATE_CHUNK_SIZE]
            stmt = (
                update(RawBotUser)
                .where(RawBotUser.id.in_(chunk))
                .values(converted_to_lead=True)
                .execution_options(synchronize_session=False)
            )
            await self._execute_update_with_retry(session, stmt, f"username_ids[{i}:{i + len(chunk)}]")

    async def _execute_update_with_retry(self, session: AsyncSession, stmt, label: str) -> None:
        for attempt in range(1, self._UPDATE_MAX_RETRIES + 1):
            try:
                await session.execute(stmt)
                await session.commit()
                return
            except DBAPIError as exc:
                if not self._is_retryable_lock_error(exc) or attempt >= self._UPDATE_MAX_RETRIES:
                    raise
                await session.rollback()
                delay = (0.15 * (2 ** (attempt - 1))) + random.uniform(0.0, 0.2)
                self._logger.warning(
                    "Lead ingestor deadlock/lock_timeout on %s; retry %s/%s in %.2fs",
                    label,
                    attempt,
                    self._UPDATE_MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)

    @staticmethod
    def _is_retryable_lock_error(exc: DBAPIError) -> bool:
        msg = str(getattr(exc, "orig", exc)).lower()
        return (
            "deadlock detected" in msg
            or "could not obtain lock" in msg
            or "lock timeout" in msg
            or "serialization" in msg
        )

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
