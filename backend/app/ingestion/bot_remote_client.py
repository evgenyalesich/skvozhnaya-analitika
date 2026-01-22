from datetime import datetime
from typing import List, Dict, Any, Optional

import asyncpg

from app.ingestion.bot_config import BotConfig


class BotRemoteClient:
    async def fetch_rows(
        self, bot_config: BotConfig, since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        if not bot_config.has_dsn():
            return []
        query = self._build_query(bot_config, since)
        conn = await asyncpg.connect(bot_config.dsn)
        try:
            if since:
                rows = await conn.fetch(query, since)
            else:
                rows = await conn.fetch(query)
        finally:
            await conn.close()
        return [self._row_to_dict(record, bot_config) for record in rows]

    def _build_query(self, bot_config: BotConfig, since: Optional[str]) -> str:
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
