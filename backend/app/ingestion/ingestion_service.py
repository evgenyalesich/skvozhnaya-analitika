from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config_loader import ConfigLoader
from app.db.session import async_session
from app.ingestion.bot_config import BotConfig
from app.ingestion.bot_remote_client import BotRemoteClient
from app.models.analytics import RawBotUser


class BotIngestionService:
    def __init__(self, client: Optional[BotRemoteClient] = None):
        self.client = client or BotRemoteClient()
        self.loader = ConfigLoader()

    async def ingest_all(self) -> None:
        configs = [BotConfig.from_dict(raw) for raw in self.loader.bots()]
        async with async_session() as session:
            for config in configs:
                if not config.has_dsn():
                    continue
                await self.ingest_bot(session, config)
                await session.commit()

    async def ingest_bot(self, session: AsyncSession, config: BotConfig) -> None:
        last = await self._last_created(session, config.bot_key)
        rows = await self.client.fetch_rows(config, last)
        if not rows:
            return
        await self._upsert_rows(session, rows)

    async def _last_created(self, session: AsyncSession, bot_key: str) -> Optional[datetime]:
        stmt = select(func.max(RawBotUser.created_at)).where(RawBotUser.bot_key == bot_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _upsert_rows(self, session: AsyncSession, rows: List[Dict[str, Any]]) -> None:
        insert_stmt = insert(RawBotUser).values(rows)
        excluded = {column: insert_stmt.excluded.get(column) for column in rows[0].keys() if column != "bot_key"}
        insert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["bot_key", "tg_user_id"],
            set_=excluded,
        )
        await session.execute(insert_stmt)
