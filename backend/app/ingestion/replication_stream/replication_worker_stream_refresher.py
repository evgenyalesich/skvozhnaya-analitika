import threading
from typing import Optional, Set

from app.ingestion.replication_stream.replication_worker_stream_constants import _REFRESH_FLAG_KEY, logger


class _DebouncedRefresher:
    """Sets a Redis flag after quiet period for aggregate refresh loop."""

    def __init__(self, delay: float = 8.0) -> None:
        self._delay = delay
        self._lock = threading.Lock()
        self._dirty: Set[str] = set()
        self._timer: Optional[threading.Timer] = None

    def mark_dirty(self, bot_key: str) -> None:
        with self._lock:
            self._dirty.add(bot_key)
            if self._timer:
                self._timer.cancel()
            t = threading.Timer(self._delay, self._flush)
            t.daemon = True
            self._timer = t
            t.start()

    def _flush(self) -> None:
        with self._lock:
            dirty = self._dirty.copy()
            self._dirty.clear()
            self._timer = None
        if not dirty:
            return
        try:
            import psycopg2
            from app.core.config import settings
            from sqlalchemy.engine import make_url

            make_url(str(settings.analytics_db_dsn))
            dsn = str(settings.analytics_db_dsn).replace("postgresql+asyncpg://", "postgresql://")
            conn = psycopg2.connect(dsn)
            conn.autocommit = True
            conn.cursor().execute("SELECT 1")
            conn.close()
        except Exception:
            pass

        try:
            from redis import Redis
            from app.core.config import settings as s

            r = Redis.from_url(str(s.redis_url))
            r.set(_REFRESH_FLAG_KEY, "1", ex=300)
            logger.info("Debounced: set refresh flag for bots=%s", dirty)
        except Exception as exc:
            logger.error("Debounced flag error: %s", exc)
