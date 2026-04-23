from datetime import datetime
from typing import List, Dict, Any, Optional

import asyncpg

from app.ingestion.bot_config import BotConfig


class BotRemoteClient:
    async def fetch_rows(
        self, bot_config: BotConfig, dsn: str, since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        if not dsn:
            return []
        if dsn.startswith("postgresql+asyncpg://"):
            dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
        if since and since.tzinfo is not None:
            # Normalize to naive datetime for DBs storing timestamp without time zone.
            since = since.replace(tzinfo=None)
        query = self._build_query(bot_config, since)
        conn = await asyncpg.connect(dsn, timeout=10)
        try:
            if since:
                rows = await conn.fetch(query, since, timeout=30)
            else:
                rows = await conn.fetch(query, timeout=30)
        except asyncpg.UndefinedTableError:
            # Skip DBs without expected schema.
            return []
        finally:
            await conn.close()
        return [self._row_to_dict(record, bot_config) for record in rows]

    def _build_query(self, bot_config: BotConfig, since: Optional[str]) -> str:
        if bot_config.custom_query:
            # Wrap to make alias columns (created_at) usable in WHERE/ORDER.
            query = f"SELECT * FROM ({bot_config.custom_query}) AS sub"
        else:
            columns = ", ".join(bot_config.fetch_columns)
            query = f"SELECT {columns} FROM {bot_config.source_table}"
        if since:
            query += f" WHERE {bot_config.cursor_column} > $1"
        query += f" ORDER BY {bot_config.cursor_column} ASC LIMIT {bot_config.batch_size}"
        return query

    def _row_to_dict(self, record: asyncpg.Record, bot_config: BotConfig) -> Dict[str, Any]:
        row = {column: record.get(column) for column in bot_config.fetch_columns}
        row["bot_key"] = bot_config.bot_key
        return row
