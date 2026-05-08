import logging
import os
import time
import uuid
from contextlib import contextmanager

from redis import Redis
from rq import Queue

from app.core.config import settings

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

redis_connection = Redis.from_url(str(settings.redis_url))
queue = Queue(settings.rq_queue_name, connection=redis_connection)
telegram_queue = Queue(settings.telegram_rq_queue_name, connection=redis_connection)
_logger = logging.getLogger("worker_tasks")

_INGESTION_LOCK_KEY = "locks:ingestion"
_SM_LOCK_KEY = "locks:google_sheets"
_SCHEDULER_LOCK_KEY = "locks:periodic_scheduler"
_POKERHUB_LOCK_KEY = "locks:pokerhub_cache"
_CACHE_WARM_LOCK_KEY = "locks:cache_warm"
_TELEGRAM_LOCK_KEY = "locks:telegram_ingest"
_ROISTAT_WEEKLY_LOCK_KEY = "locks:roistat_weekly"
_TELEGRAM_BATCH_PENDING_KEY = "telegram:batch:pending"
_TELEGRAM_BATCH_ERRORS_KEY = "telegram:batch:errors"
_TELEGRAM_BATCH_TOTAL_KEY = "telegram:batch:total"
_TELEGRAM_BATCH_DONE_KEY = "telegram:batch:done"
_TELEGRAM_USERS_TOTAL_KEY = "telegram:users:total"
_TELEGRAM_USERS_CHECKED_KEY = "telegram:users:checked"
_TELEGRAM_LAST_COMPLETE_KEY = "sync:last_telegram_complete"
_TELEGRAM_MEMBERSHIP_LOCK_KEY = "locks:telegram_membership_sync"
_TELEGRAM_MEMBERSHIP_REALTIME_LOCK_KEY = "locks:telegram_membership_realtime"
_SYNC_SERIAL_LOCK_KEY = "locks:sync:serial"
_SYNC_SERIAL_LOCK_TTL_SECONDS = 8 * 60 * 60
_SYNC_SERIAL_LOCK_WAIT_SECONDS = 5


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _decode_redis_value(value: bytes | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value


def _extract_owner_pid(owner_value: bytes | str | None) -> int | None:
    owner = _decode_redis_value(owner_value)
    if not owner:
        return None
    parts = owner.split(":")
    if len(parts) < 3:
        return None
    try:
        return int(parts[-2])
    except ValueError:
        return None


def _release_serial_lock_if_owner_matches(expected_owner: bytes | str | None) -> bool:
    if expected_owner is None:
        return False
    expected = _decode_redis_value(expected_owner) or ""
    if not expected:
        return False
    deleted = redis_connection.eval(
        """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        end
        return 0
        """,
        1,
        _SYNC_SERIAL_LOCK_KEY,
        expected,
    )
    return bool(deleted)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@contextmanager
def _acquire_sync_serial_lock(owner: str):
    if not _env_bool("SYNC_SERIAL_LOCK_ENABLED", True):
        _logger.info("Global sync lock disabled; %s runs without serialization", owner)
        yield
        return
    token = f"{owner}:{os.getpid()}:{uuid.uuid4().hex}"
    waited_seconds = 0
    while True:
        acquired = redis_connection.set(
            _SYNC_SERIAL_LOCK_KEY,
            token,
            nx=True,
            ex=_SYNC_SERIAL_LOCK_TTL_SECONDS,
        )
        if acquired:
            if waited_seconds > 0:
                _logger.info("Global sync lock acquired by %s after waiting %ss", owner, waited_seconds)
            else:
                _logger.info("Global sync lock acquired by %s", owner)
            break
        current_owner = redis_connection.get(_SYNC_SERIAL_LOCK_KEY)
        current_owner_pid = _extract_owner_pid(current_owner)
        if current_owner_pid is not None and not _is_pid_alive(current_owner_pid):
            if _release_serial_lock_if_owner_matches(current_owner):
                _logger.warning(
                    "Global sync lock owner is dead (owner=%s); lock force-released",
                    _decode_redis_value(current_owner),
                )
                continue
        if waited_seconds % 60 == 0:
            _logger.info(
                "Global sync lock busy; %s waits (%ss). Current owner: %s",
                owner,
                waited_seconds,
                _decode_redis_value(current_owner),
            )
        time.sleep(_SYNC_SERIAL_LOCK_WAIT_SECONDS)
        waited_seconds += _SYNC_SERIAL_LOCK_WAIT_SECONDS
    try:
        yield
    finally:
        current_owner = redis_connection.get(_SYNC_SERIAL_LOCK_KEY)
        if _decode_redis_value(current_owner) == token:
            redis_connection.delete(_SYNC_SERIAL_LOCK_KEY)
            _logger.info("Global sync lock released by %s", owner)


def _should_run_daily(key: str, hour: int, minute: int = 0) -> bool:
    now = time.localtime()
    target = time.struct_time(
        (
            now.tm_year,
            now.tm_mon,
            now.tm_mday,
            hour,
            minute,
            0,
            now.tm_wday,
            now.tm_yday,
            now.tm_isdst,
        )
    )
    now_ts = int(time.mktime(now))
    target_ts = int(time.mktime(target))
    if now_ts < target_ts:
        return False
    last = redis_connection.get(key)
    if not last:
        return True
    try:
        last_ts = int(last)
    except ValueError:
        last_ts = 0
    return last_ts < target_ts
