from typing import Any, Dict, List, Optional

import asyncpg
from sqlalchemy.engine import make_url

from app.core.config import settings


class PostgresExplorer:
    def __init__(self, url: Optional[str] = None):
        self._url = str(url or settings.postgres_admin_dsn)
        self._parsed = make_url(self._url)

    def _connection_kwargs(self, database: Optional[str] = None) -> Dict[str, Any]:
        return {
            "user": self._parsed.username,
            "password": self._parsed.password,
            "host": self._parsed.host or "localhost",
            "port": self._parsed.port or 5432,
            "database": database or self._parsed.database,
        }

    async def list_databases(self) -> List[str]:
        kwargs = self._connection_kwargs(database="postgres")
        conn = await asyncpg.connect(**kwargs)
        try:
            rows = await conn.fetch(
                "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname"
            )
        finally:
            await conn.close()
        return [row["datname"] for row in rows]

    async def list_bot_databases(self) -> List[str]:
        databases = await self.list_databases()
        ignore = {"postgres", "template0", "template1", "analytics_db"}
        result: List[str] = []
        for db in databases:
            if db in ignore:
                continue
            kwargs = self._connection_kwargs(database=db)
            try:
                conn = await asyncpg.connect(**kwargs)
            except Exception:
                continue
            try:
                has_users = await conn.fetchval(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name='users' LIMIT 1"
                )
                if has_users:
                    result.append(db)
            finally:
                await conn.close()
        return result

    async def execute_query(self, database: str, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        normalized = query.strip().lower()
        if not normalized.startswith("select"):
            raise ValueError("Only SELECT queries are permitted")
        if ";" in query.strip().rstrip(";"):
            raise ValueError("Query must not contain semicolons")
        kwargs = self._connection_kwargs(database=database)
        conn = await asyncpg.connect(**kwargs)
        try:
            rows = await conn.fetch(f"{query.strip()} LIMIT $1", limit)
        finally:
            await conn.close()
        return [dict(row) for row in rows]
