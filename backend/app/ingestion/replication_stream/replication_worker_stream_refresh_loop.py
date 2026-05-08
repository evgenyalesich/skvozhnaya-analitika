import asyncio
import os
import random

from app.ingestion.replication_stream.replication_worker_stream_constants import (
    _REFRESH_FLAG_KEY,
    _REPL_REFRESH_LOCK_KEY,
    _REPL_REFRESH_LOCK_TTL_SECONDS,
    logger,
)


async def _replication_refresh_loop() -> None:
    """Checks Redis flag every 10 s and runs aggregate refresh when set."""
    import time as _time

    from redis import Redis

    from app.core.config import settings
    from app.core.redis_client import RedisCache
    from app.db.session import async_session
    from app.ingestion.lead_ingestor import LeadIngestor
    from app.services.aggregate_refresher import AggregateRefresher
    from app.services.attribution_service import AttributionService

    r = Redis.from_url(str(settings.redis_url))
    _KEEPALIVE_INTERVAL = 1200
    last_forced = 0.0
    while True:
        await asyncio.sleep(10)
        try:
            import time as _t

            if _t.time() - last_forced > _KEEPALIVE_INTERVAL:
                r.set(_REFRESH_FLAG_KEY, "1", ex=300)
            if not r.getdel(_REFRESH_FLAG_KEY):
                continue
            refresh_owner = f"{os.getpid()}:{int(_t.time() * 1000)}:{random.randint(1000, 9999)}"
            refresh_locked = r.set(_REPL_REFRESH_LOCK_KEY, refresh_owner, nx=True, ex=_REPL_REFRESH_LOCK_TTL_SECONDS)
            if not refresh_locked:
                logger.info("Replication refresh skipped: another refresh is already running")
                continue
            last_forced = _t.time()
            logger.info("Replication refresh: starting")
            cache = RedisCache()
            try:
                async with async_session() as session:
                    await LeadIngestor().ingest(session)
                    await session.commit()
                await AttributionService().rebuild()
                await AggregateRefresher().refresh(days=settings.aggregate_refresh_days)
                await cache.delete_pattern("report:*")
                await cache.delete_pattern("reports:*")
                ts = int(_time.time())
                payload = {"ts": ts, "status": "ok", "error": None, "source": "replication"}
                await cache.set_json("sync:last_ingestion", payload)
                await cache.set_json("sync:last_ingestion_success", payload)
                logger.info("Replication refresh: done")
            finally:
                try:
                    current_owner = r.get(_REPL_REFRESH_LOCK_KEY)
                    if isinstance(current_owner, bytes):
                        current_owner = current_owner.decode("utf-8", errors="ignore")
                    if current_owner == refresh_owner:
                        r.delete(_REPL_REFRESH_LOCK_KEY)
                except Exception:
                    logger.debug("Failed to release replication refresh lock", exc_info=True)
        except Exception as exc:
            logger.error("Replication refresh error: %s", exc)
