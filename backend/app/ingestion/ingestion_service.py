from datetime import datetime
from typing import List, Dict, Any, Optional

import asyncpg
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.ingestion.bot_config import BotConfig
from app.ingestion.bot_remote_client import BotRemoteClient
from app.models.analytics import RawBotUser
from app.services.postgres_registry import PostgresRegistry
from app.services.advertising_company_service import AdvertisingCompanyService
from app.db.postgres_explorer import PostgresExplorer


class BotIngestionService:
    def __init__(self, client: Optional[BotRemoteClient] = None):
        self.client = client or BotRemoteClient()
        self.registry = PostgresRegistry()
        self.explorer = PostgresExplorer()
        self.ad_companies = AdvertisingCompanyService()

    async def ingest_all(self) -> None:
        bot_databases = await self.explorer.list_bot_databases()
        configs = [await self._config_for_database(db) for db in bot_databases]
        async with async_session() as session:
            for config in configs:
                if not config.database_name:
                    continue
                dsn = self.registry.dsn_for(config.database_name)
                await self.ingest_bot(session, config, dsn)
                await session.commit()

    async def ingest_bot(self, session: AsyncSession, config: BotConfig, dsn: str) -> None:
        last = await self._last_created(session, config.bot_key)
        full_refresh = await self._needs_username_backfill(session, config.bot_key)
        cursor = None if full_refresh else last
        company_map = await self.ad_companies.bot_to_company_map(session)
        company_name = company_map.get(config.bot_key)

        while True:
            rows = await self.client.fetch_rows(config, dsn, cursor)
            if not rows:
                break
            if company_name:
                for row in rows:
                    row["advertising_company"] = company_name
            await self._upsert_rows(session, rows)
            if len(rows) < config.batch_size:
                break
            next_cursor = max(
                (row.get(config.cursor_column) for row in rows if row.get(config.cursor_column) is not None),
                default=None,
            )
            if next_cursor is None or next_cursor == cursor:
                break
            cursor = next_cursor

    async def _last_created(self, session: AsyncSession, bot_key: str) -> Optional[datetime]:
        stmt = select(func.max(RawBotUser.created_at)).where(RawBotUser.bot_key == bot_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _needs_username_backfill(self, session: AsyncSession, bot_key: str) -> bool:
        stmt = (
            select(func.count())
            .where(RawBotUser.bot_key == bot_key)
            .where((RawBotUser.username.is_(None)) | (RawBotUser.username == ""))
        )
        result = await session.execute(stmt)
        return (result.scalar_one() or 0) > 0

    async def _upsert_rows(self, session: AsyncSession, rows: List[Dict[str, Any]]) -> None:
        insert_stmt = insert(RawBotUser).values(rows)
        excluded = {column: insert_stmt.excluded.get(column) for column in rows[0].keys() if column != "bot_key"}
        insert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["bot_key", "tg_user_id"],
            set_=excluded,
        )
        await session.execute(insert_stmt)

    async def _config_for_database(self, database_name: str) -> BotConfig:
        has_lead_resources = False
        created_at_column: Optional[str] = None
        has_username = False
        has_user_block = False
        try:
            kwargs = self.explorer._connection_kwargs(database=database_name)
            conn = await asyncpg.connect(**kwargs)
            try:
                users_columns = await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='users'"
                )
                users_cols = {row["column_name"] for row in users_columns}
                if "id" not in users_cols:
                    return BotConfig(bot_key="", database_name="")
                has_username = "username" in users_cols
                has_user_block = "user_block" in users_cols
                for candidate in (
                    "timestamp_registration",
                    "created_at",
                    "created",
                    "registered_at",
                    "reg_date",
                ):
                    if candidate in users_cols:
                        created_at_column = candidate
                        break
                has_lead_resources = bool(
                    await conn.fetchval(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema='public' AND table_name='lead_resources' LIMIT 1"
                    )
                )
            finally:
                await conn.close()
        except Exception:
            return BotConfig(bot_key="", database_name="")

        if not created_at_column:
            return BotConfig(bot_key="", database_name="")

        fetch_columns = [
            "tg_user_id",
            "username",
            "created_at",
            "utm_source",
            "utm_campaign",
            "utm_medium",
            "utm_content",
            "utm_term",
        ]
        user_block_expr = None
        if has_user_block and database_name != "lead":
            user_block_expr = "users.user_block AS user_block"
            fetch_columns.insert(1, "user_block")

        if has_lead_resources:
            custom_query = (
                "SELECT users.id AS tg_user_id, "
                f"{user_block_expr + ', ' if user_block_expr else ''}"
                f"{'users.username' if has_username else 'NULL::text'} AS username, "
                f"users.{created_at_column} AS created_at, "
                "lead_resources.source AS utm_source, "
                "lead_resources.campaign AS utm_campaign, "
                "lead_resources.medium AS utm_medium, "
                "lead_resources.content AS utm_content, "
                "lead_resources.term AS utm_term "
                "FROM users "
                "LEFT JOIN lead_resources ON users.id = lead_resources.user_id"
            )
        else:
            custom_query = (
                "SELECT users.id AS tg_user_id, "
                f"{user_block_expr + ', ' if user_block_expr else ''}"
                f"{'users.username' if has_username else 'NULL::text'} AS username, "
                f"users.{created_at_column} AS created_at, "
                "NULL::text AS utm_source, "
                "NULL::text AS utm_campaign, "
                "NULL::text AS utm_medium, "
                "NULL::text AS utm_content, "
                "NULL::text AS utm_term "
                "FROM users"
            )
        return BotConfig(
            bot_key=database_name,
            database_name=database_name,
            cursor_column="created_at",
            fetch_columns=fetch_columns,
            custom_query=custom_query,
        )
