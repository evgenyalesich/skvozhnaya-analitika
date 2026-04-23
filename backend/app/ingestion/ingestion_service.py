import logging
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
        self._logger = logging.getLogger("bot_ingestion_service")

    async def ingest_all(self) -> None:
        bot_databases = await self.explorer.list_bot_databases()
        self._logger.info("Bot ingestion: discovered databases=%s", len(bot_databases))
        configs = [await self._config_for_database(db) for db in bot_databases]
        active_configs = [config for config in configs if config.database_name]
        self._logger.info("Bot ingestion: active configs=%s", len(active_configs))
        async with async_session() as session:
            for index, config in enumerate(active_configs, start=1):
                dsn = self.registry.dsn_for(config.database_name)
                self._logger.info(
                    "Bot ingestion: [%s/%s] start bot=%s database=%s",
                    index,
                    len(active_configs),
                    config.bot_key,
                    config.database_name,
                )
                await self.ingest_bot(session, config, dsn)
                await session.commit()
                self._logger.info(
                    "Bot ingestion: [%s/%s] done bot=%s",
                    index,
                    len(active_configs),
                    config.bot_key,
                )

    async def ingest_bot(self, session: AsyncSession, config: BotConfig, dsn: str) -> None:
        last = await self._last_created(session, config.bot_key)
        full_refresh = await self._needs_username_backfill(session, config.bot_key)
        # Lead rows can be enriched later (for example PH/auth users without telegram_id),
        # so keep it on full refresh to heal historical gaps automatically.
        if config.bot_key == "lead":
            full_refresh = True
        cursor = None if full_refresh else last
        company_map = await self.ad_companies.bot_to_company_map(session)
        company_name = company_map.get(config.bot_key)
        self._logger.info(
            "Bot ingestion: bot=%s full_refresh=%s cursor=%s company=%s",
            config.bot_key,
            full_refresh,
            cursor,
            company_name,
        )

        while True:
            rows = await self.client.fetch_rows(config, dsn, cursor)
            if not rows:
                self._logger.info("Bot ingestion: bot=%s no more rows", config.bot_key)
                break
            if company_name:
                for row in rows:
                    row["advertising_company"] = company_name
            await self._upsert_rows(session, rows)
            self._logger.info("Bot ingestion: bot=%s fetched rows=%s", config.bot_key, len(rows))
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
        deduped_rows = self._dedupe_rows(rows)
        if not deduped_rows:
            return
        insert_stmt = insert(RawBotUser).values(deduped_rows)
        excluded = {
            column: insert_stmt.excluded.get(column)
            for column in deduped_rows[0].keys()
            if column != "bot_key"
        }
        insert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["bot_key", "tg_user_id"],
            set_=excluded,
        )
        await session.execute(insert_stmt)

    def _dedupe_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[tuple[str, int], Dict[str, Any]] = {}
        for row in rows:
            bot_key = row.get("bot_key")
            tg_user_id = row.get("tg_user_id")
            if not bot_key or tg_user_id is None:
                continue
            key = (str(bot_key), int(tg_user_id))
            current = merged.get(key)
            if current is None:
                merged[key] = dict(row)
                continue

            # Keep the freshest created_at row as base, but do not lose non-empty UTM fields.
            current_created = current.get("created_at")
            next_created = row.get("created_at")
            if next_created is not None and (current_created is None or next_created >= current_created):
                merged[key] = {**current, **row}
                current = merged[key]

            for field, value in row.items():
                if field in {"bot_key", "tg_user_id"}:
                    continue
                if value not in (None, "", False):
                    current[field] = value

        return list(merged.values())

    @staticmethod
    def _build_lead_identity_select(
        users_cols: set[str],
        has_lead_resources: bool,
    ) -> tuple[str, str, str]:
        if "telegram_id" in users_cols:
            # Keep TG users by their real telegram_id and store PH/auth users as negative ids,
            # so they can coexist in raw_bot_users without colliding with Telegram identities.
            tg_user_id_expr = "COALESCE(users.telegram_id, -users.id)"
            ph_user_id_expr = (
                "CASE "
                "WHEN users.telegram_id IS NULL AND users.id BETWEEN 1 AND 2147483647 "
                "THEN users.id ELSE NULL END AS ph_user_id"
            )
            users_where_clause = ""
            return tg_user_id_expr, ph_user_id_expr, users_where_clause
        # Real lead DB on prod has no users.telegram_id. In that schema the panel uses
        # users.id as the canonical person identifier, so analytics must ingest the same
        # positive ids instead of synthesizing negative PH-only rows.
        tg_user_id_expr = "users.id"
        ph_user_id_expr = "NULL::integer AS ph_user_id"
        users_where_clause = ""
        return tg_user_id_expr, ph_user_id_expr, users_where_clause

    async def _config_for_database(self, database_name: str) -> BotConfig:
        has_lead_resources = False
        has_ph_user_mirror = False
        created_at_column: Optional[str] = None
        has_username = False
        has_user_block = False
        try:
            kwargs = self.explorer._connection_kwargs(database=database_name)
            conn = await asyncpg.connect(timeout=10, **kwargs)
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
                    "first_seen_at",
                    "created",
                    "registered_at",
                    "reg_date",
                    "last_seen_at",
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
                has_ph_user_mirror = bool(
                    await conn.fetchval(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema='public' AND table_name='ph_user_mirror' LIMIT 1"
                    )
                )
            finally:
                await conn.close()
        except Exception as exc:
            self._logger.warning("Bot ingestion: skip database=%s error=%s", database_name, exc)
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
        if has_user_block:
            user_block_expr = "users.user_block AS user_block"
            fetch_columns.insert(1, "user_block")
        is_lead_db = database_name == "lead"
        ph_user_id_expr = None
        users_where_clause = ""
        created_at_expr = f"users.{created_at_column}"
        if is_lead_db:
            try:
                tg_user_id_expr, ph_user_id_expr, users_where_clause = self._build_lead_identity_select(
                    users_cols,
                    has_lead_resources,
                )
            except ValueError:
                self._logger.warning(
                    "Bot ingestion: skip lead database without users.telegram_id mapping/auth markers"
                )
                return BotConfig(bot_key="", database_name="")
            fetch_columns.insert(1, "ph_user_id")
            # lead stores naive local timestamps; normalize them into the same date buckets
            # the new panel uses ((timestamp_registration + 3h)::date).
            created_at_expr = f"(users.{created_at_column} + INTERVAL '3 hours')"
            if has_ph_user_mirror:
                ph_user_id_expr = (
                    "CASE "
                    "WHEN ph_user_mirror.ph_id ~ '^[0-9]+$' "
                    "AND ph_user_mirror.ph_id::bigint BETWEEN 1 AND 2147483647 "
                    "THEN ph_user_mirror.ph_id::integer "
                    "ELSE NULL END AS ph_user_id"
                )
        else:
            tg_user_id_expr = "COALESCE(users.telegram_id, users.id)" if "telegram_id" in users_cols else "users.id"

        if has_lead_resources:
            custom_query = (
                f"SELECT {tg_user_id_expr} AS tg_user_id, "
                f"{ph_user_id_expr + ', ' if ph_user_id_expr else ''}"
                f"{user_block_expr + ', ' if user_block_expr else ''}"
                f"{'users.username' if has_username else 'NULL::text'} AS username, "
                f"{created_at_expr} AS created_at, "
                "lead_resources.source AS utm_source, "
                "lead_resources.campaign AS utm_campaign, "
                "lead_resources.medium AS utm_medium, "
                "lead_resources.content AS utm_content, "
                "lead_resources.term AS utm_term "
                "FROM users "
                f"{'LEFT JOIN ph_user_mirror ON ph_user_mirror.id = users.id ' if is_lead_db and has_ph_user_mirror else ''}"
                "LEFT JOIN lead_resources ON users.id = lead_resources.user_id"
                f"{users_where_clause}"
            )
        else:
            custom_query = (
                f"SELECT {tg_user_id_expr} AS tg_user_id, "
                f"{ph_user_id_expr + ', ' if ph_user_id_expr else ''}"
                f"{user_block_expr + ', ' if user_block_expr else ''}"
                f"{'users.username' if has_username else 'NULL::text'} AS username, "
                f"{created_at_expr} AS created_at, "
                "NULL::text AS utm_source, "
                "NULL::text AS utm_campaign, "
                "NULL::text AS utm_medium, "
                "NULL::text AS utm_content, "
                "NULL::text AS utm_term "
                f"FROM users "
                f"{'LEFT JOIN ph_user_mirror ON ph_user_mirror.id = users.id ' if is_lead_db and has_ph_user_mirror else ''}"
                f"{users_where_clause}"
            )
        return BotConfig(
            bot_key=database_name,
            database_name=database_name,
            cursor_column="created_at",
            fetch_columns=fetch_columns,
            custom_query=custom_query,
        )
