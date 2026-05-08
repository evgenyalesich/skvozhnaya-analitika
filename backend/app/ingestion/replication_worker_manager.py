from __future__ import annotations

import asyncio
import threading
from typing import Dict, Optional, Set

from app.ingestion.replication_worker_stream import (
    _BotStream,
    _DebouncedRefresher,
    _EXCLUDED_DBS,
    _replication_refresh_loop,
    logger,
)


# ===== Replication worker manager =====
class ReplicationWorker:
    def __init__(self) -> None:
        from app.core.config import settings
        from sqlalchemy.engine import make_url
        dsn = make_url(str(settings.postgres_admin_dsn))
        self._pg_host: str = dsn.host or "localhost"
        self._pg_port: int = dsn.port or 5432
        self._pg_user: str = dsn.username or "postgres"
        self._pg_password: str = dsn.password or ""
        # Sync DSN for psycopg2 upserts into analytics_db
        raw = str(settings.analytics_db_dsn).replace("postgresql+asyncpg://", "postgresql://")
        self._analytics_sync_dsn = raw
        self._refresher = _DebouncedRefresher(delay=8.0)
        self._streams: Dict[str, _BotStream] = {}

    def start(self) -> None:
        loop = asyncio.get_event_loop()
        asyncio.ensure_future(_replication_refresh_loop(), loop=loop)
        asyncio.ensure_future(self._reconcile_loop(), loop=loop)
        t = threading.Thread(target=self._discover, args=(loop,), daemon=True, name="repl-manager")
        t.start()

    def stop(self) -> None:
        for s in self._streams.values():
            s.stop()

    def _discover(self, loop: asyncio.AbstractEventLoop) -> None:
        try:
            future = asyncio.run_coroutine_threadsafe(self._async_discover(), loop)
            future.result()
        except Exception as exc:
            logger.error("ReplicationWorker discovery error: %s", exc)

    async def _desired_dbs(self) -> Set[str]:
        """Return the set of db names that should be replicated right now."""
        from app.db.postgres_explorer import PostgresExplorer
        from app.db.session import async_session
        from app.models.analytics import BotRegistry
        from sqlalchemy import select

        async with async_session() as session:
            registry_entries = (await session.execute(select(BotRegistry))).scalars().all()

        no_replicate: Set[str] = {
            entry.bot_key for entry in registry_entries if not entry.replicate
        }
        all_dbs = await PostgresExplorer().list_bot_databases()
        return {db for db in all_dbs if db not in _EXCLUDED_DBS and db not in no_replicate}

    async def _async_discover(self) -> None:
        from app.services.advertising_company_service import AdvertisingCompanyService
        from app.db.session import async_session

        async with async_session() as session:
            company_map = await AdvertisingCompanyService().bot_to_company_map(session)

        desired = await self._desired_dbs()
        logger.info("ReplicationWorker: starting %d streams", len(desired))

        for db in desired:
            self._start_stream(db, company_map)

    def _start_stream(self, db: str, company_map: Dict[str, str]) -> None:
        if db in self._streams:
            return
        stream = _BotStream(
            db_name=db,
            pg_host=self._pg_host,
            pg_port=self._pg_port,
            pg_user=self._pg_user,
            pg_password=self._pg_password,
            analytics_sync_dsn=self._analytics_sync_dsn,
            refresher=self._refresher,
            company_map=company_map,
        )
        stream.start()
        self._streams[db] = stream
        logger.info("ReplicationWorker: stream started db=%s", db)

    async def _reconcile_loop(self) -> None:
        """Every 30 s: start streams for newly enabled bots, stop for disabled."""
        from app.services.advertising_company_service import AdvertisingCompanyService
        from app.db.session import async_session

        while True:
            await asyncio.sleep(30)
            try:
                desired = await self._desired_dbs()
                running = set(self._streams.keys())

                # Start new
                to_start = desired - running
                if to_start:
                    async with async_session() as session:
                        company_map = await AdvertisingCompanyService().bot_to_company_map(session)
                    for db in to_start:
                        logger.info("ReplicationWorker: reconcile — starting db=%s", db)
                        self._start_stream(db, company_map)

                # Stop removed
                to_stop = running - desired
                for db in to_stop:
                    logger.info("ReplicationWorker: reconcile — stopping db=%s", db)
                    self._streams.pop(db).stop()

            except Exception as exc:
                logger.error("ReplicationWorker: reconcile error: %s", exc)


_worker: Optional[ReplicationWorker] = None


def get_worker() -> ReplicationWorker:
    global _worker
    if _worker is None:
        _worker = ReplicationWorker()
    return _worker


def start_worker() -> None:
    get_worker().start()
