import asyncio
import logging
import os
import threading
import time
from datetime import date, timedelta

from redis import Redis
from rq import Queue

from app.core.config import settings
from app.core.redis_client import RedisCache
from app.ingestion.master_ingestion import IngestionCoordinator
from app.ingestion.google_sheets_ingestor import GoogleSheetsIngestor
from app.ingestion.telegram_ingestor import TelegramStatusIngestor
from app.db.session import async_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.aggregate_refresher import AggregateRefresher
from app.services.pokerhub_cache_service import PokerHubCacheService
from app.ingestion.pokerhub_cache_ingestor import PokerHubCacheIngestor
from app.services.report_cache_service import ReportCacheService
from app.api.report_filters import ReportFilters
from app.services.system_settings_service import SystemSettingsService, SyncEventLogger
from app.services.roistat_weekly_report import RoistatWeeklyReport

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


def run_ingestion_job() -> None:
    async def _log_error(message: str) -> None:
        async with async_session() as session:
            await SyncEventLogger().log(session, source="ingestion", level="error", message=message)
            await session.commit()

    async def _record_status(success: bool, error: str | None) -> None:
        payload = {
            "ts": int(time.time()),
            "status": "ok" if success else "error",
            "error": error,
        }
        cache = RedisCache()
        await cache.set_json("sync:last_ingestion", payload)
        if success:
            await cache.set_json("sync:last_ingestion_success", payload)

    async def _run() -> None:
        try:
            redis_connection.set(_INGESTION_LOCK_KEY, "running", ex=3600)
            await IngestionCoordinator().run(sm_only=settings.google_sheets_only_sm)
            await AggregateRefresher().refresh()
            await _warm_report_cache()
            await _record_status(True, None)
        except Exception as exc:
            await _record_status(False, str(exc))
            await _log_error(str(exc))
            raise
        finally:
            redis_connection.delete(_INGESTION_LOCK_KEY)

    asyncio.run(_run())


def schedule_ingestion_job() -> None:
    locked = redis_connection.set(_INGESTION_LOCK_KEY, "queued", nx=True, ex=3600)
    if not locked:
        _logger.warning("Ingestion job already queued/running; skip enqueue.")
        return
    queue.enqueue(run_ingestion_job, job_timeout=3600)


def run_aggregation_job(days: int | None = None) -> None:
    asyncio.run(AggregateRefresher().refresh(days))


def schedule_aggregation_job(days: int | None = None) -> None:
    queue.enqueue(run_aggregation_job, days)


def run_telegram_job() -> None:
    async def _run() -> None:
        locked = redis_connection.set(
            _TELEGRAM_LOCK_KEY,
            "running",
            nx=True,
            ex=settings.telegram_job_timeout_seconds,
        )
        if not locked:
            _logger.warning("Telegram ingest already running; skip.")
            return
        try:
            async with async_session() as session:
                user_ids = await TelegramStatusIngestor().fetch_user_ids(session)
            if not user_ids:
                redis_connection.delete(_TELEGRAM_LOCK_KEY)
                return
            batch_size_setting = settings.telegram_batch_size
            if batch_size_setting <= 0:
                batch_size = len(user_ids)
                _logger.info("Telegram ingest: single-batch mode (batch_size=all users=%s)", batch_size)
            else:
                batch_size = max(1, batch_size_setting)
            batches = [user_ids[i:i + batch_size] for i in range(0, len(user_ids), batch_size)]
            _logger.info("Telegram ingest: total users=%s", len(user_ids))
            progress_ttl = max(settings.telegram_job_timeout_seconds, 6 * 60 * 60)
            redis_connection.set(_TELEGRAM_BATCH_PENDING_KEY, len(batches), ex=progress_ttl)
            redis_connection.set(_TELEGRAM_BATCH_TOTAL_KEY, len(batches), ex=progress_ttl)
            redis_connection.set(_TELEGRAM_BATCH_DONE_KEY, 0, ex=progress_ttl)
            redis_connection.set(_TELEGRAM_USERS_TOTAL_KEY, len(user_ids), ex=progress_ttl)
            redis_connection.set(_TELEGRAM_USERS_CHECKED_KEY, 0, ex=progress_ttl)
            redis_connection.delete(_TELEGRAM_BATCH_ERRORS_KEY)
            _logger.info("Telegram ingest: scheduling %s batches (size=%s)", len(batches), batch_size)
            for batch in batches:
                telegram_queue.enqueue(
                    run_telegram_batch_job,
                    batch,
                    total_users=len(user_ids),
                    total_batches=len(batches),
                    job_timeout=settings.telegram_job_timeout_seconds,
                )
        except Exception as exc:
            async with async_session() as session:
                await SyncEventLogger().log(session, source="telegram", level="error", message=str(exc))
                await session.commit()
            redis_connection.delete(_TELEGRAM_LOCK_KEY)
            raise

    asyncio.run(_run())


def run_telegram_batch_job(
    user_ids: list[int],
    total_users: int | None = None,
    total_batches: int | None = None,
) -> None:
    async def _run() -> None:
        started = time.monotonic()
        total = int(redis_connection.get(_TELEGRAM_BATCH_TOTAL_KEY) or 0) or (total_batches or 0)
        done = int(redis_connection.get(_TELEGRAM_BATCH_DONE_KEY) or 0)
        users_total = int(redis_connection.get(_TELEGRAM_USERS_TOTAL_KEY) or 0) or (total_users or 0)
        users_checked = int(redis_connection.get(_TELEGRAM_USERS_CHECKED_KEY) or 0)
        if users_total == 0:
            users_total = total_users or len(user_ids)
        _logger.info(
            "Telegram batch: start size=%s first_id=%s last_id=%s total_batches=%s done_batches=%s checked_users=%s/%s",
            len(user_ids),
            user_ids[0] if user_ids else None,
            user_ids[-1] if user_ids else None,
            total,
            done,
            users_checked,
            users_total,
        )
        try:
            async with async_session() as session:
                await TelegramStatusIngestor().ingest(session, user_ids=user_ids)
                await session.commit()
        except Exception as exc:
            async with async_session() as session:
                await SyncEventLogger().log(session, source="telegram", level="error", message=str(exc))
                await session.commit()
            redis_connection.incr(_TELEGRAM_BATCH_ERRORS_KEY)
            raise
        finally:
            remaining = redis_connection.decr(_TELEGRAM_BATCH_PENDING_KEY)
            done = redis_connection.incr(_TELEGRAM_BATCH_DONE_KEY)
            total = int(redis_connection.get(_TELEGRAM_BATCH_TOTAL_KEY) or 0)
            checked = redis_connection.incrby(_TELEGRAM_USERS_CHECKED_KEY, len(user_ids))
            users_total = int(redis_connection.get(_TELEGRAM_USERS_TOTAL_KEY) or 0)
            if remaining <= 0:
                errors = int(redis_connection.get(_TELEGRAM_BATCH_ERRORS_KEY) or 0)
                if errors == 0:
                    redis_connection.set("sync:last_telegram", int(time.time()))
                    redis_connection.set(_TELEGRAM_LAST_COMPLETE_KEY, int(time.time()))
                redis_connection.delete(_TELEGRAM_BATCH_PENDING_KEY)
                redis_connection.delete(_TELEGRAM_BATCH_ERRORS_KEY)
                redis_connection.delete(_TELEGRAM_BATCH_TOTAL_KEY)
                redis_connection.delete(_TELEGRAM_BATCH_DONE_KEY)
                redis_connection.delete(_TELEGRAM_USERS_TOTAL_KEY)
                redis_connection.delete(_TELEGRAM_USERS_CHECKED_KEY)
                redis_connection.delete(_TELEGRAM_LOCK_KEY)
            elapsed = time.monotonic() - started
            _logger.info(
                "Telegram batch: done size=%s remaining=%s progress=%s/%s checked_users=%s/%s elapsed=%.1fs",
                len(user_ids),
                max(remaining, 0),
                done,
                total,
                checked,
                users_total,
                elapsed,
            )

    asyncio.run(_run())


def schedule_telegram_job() -> None:
    telegram_queue.enqueue(run_telegram_job, job_timeout=settings.telegram_job_timeout_seconds)


def run_google_sheets_job() -> None:
    async def _run() -> None:
        async def _record_status(success: bool, error: str | None) -> None:
            payload = {
                "ts": int(time.time()),
                "status": "ok" if success else "error",
                "error": error,
            }
            cache = RedisCache()
            await cache.set_json("sync:last_sm", payload)
            if success:
                await cache.set_json("sync:last_sm_success", payload)

        try:
            # The scheduler sets _SM_LOCK_KEY when enqueuing. Refresh it while running and
            # always release it at the end to avoid "stuck" periods after failures.
            redis_connection.set(_SM_LOCK_KEY, "running", ex=1200)
            async with async_session() as session:
                await GoogleSheetsIngestor().ingest(session, sm_only=settings.google_sheets_only_sm)
                await session.commit()
            await _warm_report_cache()
            await _record_status(True, None)
        except Exception as exc:
            await _record_status(False, str(exc))
            async with async_session() as session:
                await SyncEventLogger().log(session, source="google_sheets", level="error", message=str(exc))
                await session.commit()
            raise
        finally:
            redis_connection.delete(_SM_LOCK_KEY)

    asyncio.run(_run())


async def _warm_report_cache() -> None:
    filters = ReportFilters(
        start_date=None,
        end_date=None,
        bots=[],
        advertising_companies=[],
        utm_source=[],
        utm_campaign=[],
        utm_medium=[],
        utm_content=[],
        utm_term=[],
    )
    async with async_session() as session:
        service = ReportCacheService()
        default_start = None
        if settings.subscriptions_compare_default_days > 0:
            default_start = date.today() - timedelta(days=settings.subscriptions_compare_default_days)
        await service.total(session, filters)
        await service.daily(session, filters, limit=None)
        await service.stages(session, filters)
        await service.breakdown(session, filters, group_by="utm_source", limit=20)
        await service.subscriptions_vs_starts(
            session,
            start_date=default_start,
            end_date=None,
            group_by_campaign=True,
            interval="day",
            channel_id=os.getenv("TELEGRAM_CHANNEL_ID"),
            community_id=os.getenv("TELEGRAM_COMMUNITY_ID"),
        )
        await service.subscriptions_vs_starts(
            session,
            start_date=default_start,
            end_date=None,
            group_by_campaign=True,
            interval="week",
            channel_id=os.getenv("TELEGRAM_CHANNEL_ID"),
            community_id=os.getenv("TELEGRAM_COMMUNITY_ID"),
        )


def schedule_google_sheets_job() -> None:
    locked = redis_connection.set(_SM_LOCK_KEY, "queued", nx=True, ex=1200)
    if not locked:
        _logger.warning("Google Sheets job already queued/running; skip enqueue.")
        return
    queue.enqueue(run_google_sheets_job, job_timeout=600)


def run_pokerhub_cache_job() -> None:
    async def _run() -> None:
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
        try:
            redis_connection.set(_POKERHUB_LOCK_KEY, "running", ex=3600)
            await PokerHubCacheService().refresh_cache()
            async with async_session() as session:
                await PokerHubCacheIngestor().ingest(session)
                await session.commit()
            redis_connection.set("sync:last_ph_cache", int(time.time()))
        except Exception as exc:
            async with async_session() as session:
                await SyncEventLogger().log(session, source="pokerhub", level="error", message=str(exc))
                await session.commit()
            raise
        finally:
            redis_connection.delete(_POKERHUB_LOCK_KEY)
    asyncio.run(_run())


def schedule_pokerhub_cache_job() -> None:
    locked = redis_connection.set(_POKERHUB_LOCK_KEY, "queued", nx=True, ex=3600)
    if not locked:
        _logger.warning("PokerHub cache job already queued/running; skip enqueue.")
        return
    queue.enqueue(run_pokerhub_cache_job, job_timeout=3600)


def run_cache_warm_job() -> None:
    async def _run() -> None:
        try:
            redis_connection.set(_CACHE_WARM_LOCK_KEY, "running", ex=600)
            await _warm_report_cache()
        except Exception as exc:
            async with async_session() as session:
                await SyncEventLogger().log(session, source="cache_warm", level="error", message=str(exc))
                await session.commit()
            raise
        finally:
            redis_connection.delete(_CACHE_WARM_LOCK_KEY)
    asyncio.run(_run())


def schedule_cache_warm_job() -> None:
    locked = redis_connection.set(_CACHE_WARM_LOCK_KEY, "queued", nx=True, ex=600)
    if not locked:
        _logger.warning("Cache warm job already queued/running; skip enqueue.")
        return
    queue.enqueue(run_cache_warm_job, job_timeout=300)


def run_roistat_weekly_export_job(
    first_touch_start: str | None = None,
    first_touch_end: str | None = None,
) -> None:
    async def _run() -> None:
        async def _record_status(success: bool, error: str | None) -> None:
            payload = {
                "ts": int(time.time()),
                "status": "ok" if success else "error",
                "error": error,
                "first_touch_start": first_touch_start,
                "first_touch_end": first_touch_end,
            }
            cache = RedisCache()
            await cache.set_json("sync:last_roistat_weekly", payload)
            if success:
                await cache.set_json("sync:last_roistat_weekly_success", payload)

        locked = redis_connection.set(_ROISTAT_WEEKLY_LOCK_KEY, "running", nx=True, ex=1800)
        if not locked:
            _logger.warning("Roistat weekly export already running; skip.")
            return
        try:
            ft_start = date.fromisoformat(first_touch_start) if first_touch_start else None
            ft_end = date.fromisoformat(first_touch_end) if first_touch_end else None
            report = RoistatWeeklyReport()
            header_rows = await asyncio.to_thread(report.load_source_headers)
            async with async_session() as session:
                weekly_rows = await report.build_weekly_rows(session, first_touch_start=ft_start, first_touch_end=ft_end)
            await asyncio.to_thread(report.export_to_sheet, weekly_rows, header_rows)
            await _record_status(True, None)
        except Exception as exc:
            await _record_status(False, str(exc))
            async with async_session() as session:
                await SyncEventLogger().log(session, source="roistat_weekly", level="error", message=str(exc))
                await session.commit()
            raise
        finally:
            redis_connection.delete(_ROISTAT_WEEKLY_LOCK_KEY)

    asyncio.run(_run())


def schedule_roistat_weekly_export_job(
    first_touch_start: str | None = None,
    first_touch_end: str | None = None,
) -> None:
    locked = redis_connection.set(_ROISTAT_WEEKLY_LOCK_KEY, "queued", nx=True, ex=1800)
    if not locked:
        _logger.warning("Roistat weekly export already queued/running; skip enqueue.")
        return
    queue.enqueue(run_roistat_weekly_export_job, first_touch_start, first_touch_end, job_timeout=1800)


def _should_run(last_key: str, interval_seconds: int, run_on_start: bool) -> bool:
    if interval_seconds <= 0:
        return False
    now = int(time.time())
    last = redis_connection.get(last_key)
    if not last:
        return run_on_start
    try:
        last_ts = int(last)
    except (ValueError, TypeError):
        last_ts = 0
        try:
            import json

            payload = json.loads(last)
            if isinstance(payload, dict) and "ts" in payload:
                last_ts = int(payload["ts"])
        except Exception:
            last_ts = 0
    return now - last_ts >= interval_seconds


def _telegram_cooldown_ok() -> bool:
    cooldown = settings.telegram_sync_cooldown_seconds
    if cooldown <= 0:
        return True
    last = redis_connection.get(_TELEGRAM_LAST_COMPLETE_KEY)
    if not last:
        return True
    try:
        last_ts = int(last)
    except (ValueError, TypeError):
        return True
    return (int(time.time()) - last_ts) >= cooldown


def _hourly_scheduler_loop(lock_owner: str) -> None:
    def _load_settings():
        async def _get():
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
            from sqlalchemy.pool import NullPool

            local_engine = create_async_engine(
                str(settings.analytics_db_dsn),
                echo=False,
                pool_pre_ping=True,
                poolclass=NullPool,
            )
            local_session = async_sessionmaker(local_engine, expire_on_commit=False, class_=AsyncSession)
            try:
                async with local_session() as session:
                    return (await SystemSettingsService().get_settings(session)).scheduler
            finally:
                await local_engine.dispose()
        try:
            return asyncio.run(_get())
        except RuntimeError:
            # fallback to env if event loop is running (shouldn't happen in worker thread)
            return None

    scheduler = _load_settings()
    periodic_enabled = scheduler.periodic_enabled if scheduler else _env_bool("PERIODIC_SYNC_ENABLED", True)
    run_on_start = scheduler.run_on_start if scheduler else _env_bool("PERIODIC_SYNC_RUN_ON_START", True)
    warm_on_start = scheduler.warm_cache_on_start if scheduler else _env_bool("WARM_CACHE_ON_START", True)
    if not periodic_enabled:
        _logger.info("Periodic scheduler disabled by PERIODIC_SYNC_ENABLED.")
        return
    if warm_on_start:
        _logger.info("Warm cache on start: enqueue cache warm.")
        schedule_cache_warm_job()
    while True:
        # Refresh the scheduler lock TTL, and stop this scheduler if we lost ownership.
        try:
            current = redis_connection.get(_SCHEDULER_LOCK_KEY)
            if current is None:
                _logger.warning("Periodic scheduler lock expired; stopping scheduler loop.")
                return
            if isinstance(current, (bytes, bytearray)):
                current = current.decode("utf-8", errors="replace")
            if str(current) != lock_owner:
                _logger.warning("Periodic scheduler lock ownership changed; stopping scheduler loop.")
                return
            redis_connection.expire(_SCHEDULER_LOCK_KEY, 3600 + 120)
        except Exception:
            _logger.exception("Periodic scheduler lock refresh failed")

        scheduler = _load_settings()
        periodic_enabled = scheduler.periodic_enabled if scheduler else _env_bool("PERIODIC_SYNC_ENABLED", True)
        run_on_start = scheduler.run_on_start if scheduler else _env_bool("PERIODIC_SYNC_RUN_ON_START", True)
        ingestion_interval = (scheduler.ingestion_interval_minutes if scheduler else _env_int("INGESTION_SYNC_INTERVAL_MINUTES", 60)) * 60
        sm_interval = (scheduler.google_sheets_interval_minutes if scheduler else _env_int("GOOGLE_SHEETS_SYNC_INTERVAL_MINUTES", 60)) * 60
        ph_interval = (scheduler.pokerhub_interval_hours if scheduler else _env_int("POKERHUB_SYNC_INTERVAL_HOURS", 24)) * 60 * 60
        telegram_interval = (scheduler.telegram_interval_minutes if scheduler else _env_int("TELEGRAM_SYNC_INTERVAL_MINUTES", 0)) * 60
        telegram_hour = scheduler.telegram_daily_hour if scheduler else _env_int("TELEGRAM_SYNC_DAILY_HOUR", 4)
        if not periodic_enabled:
            _logger.info("Periodic scheduler disabled by PERIODIC_SYNC_ENABLED.")
            time.sleep(60)
            continue
        try:
            enqueued = False
            if _should_run("sync:last_ingestion", ingestion_interval, run_on_start):
                _logger.info("Periodic sync: enqueue ingestion.")
                schedule_ingestion_job()
                enqueued = True
            if _should_run("sync:last_sm", sm_interval, run_on_start):
                _logger.info("Periodic sync: enqueue SM.")
                schedule_google_sheets_job()
                enqueued = True
            if _should_run("sync:last_ph_cache", ph_interval, run_on_start):
                _logger.info("Periodic sync: enqueue PokerHub cache refresh.")
                schedule_pokerhub_cache_job()
                redis_connection.set("sync:last_ph_cache", int(time.time()))
                enqueued = True
            if telegram_interval > 0:
                if _should_run("sync:last_telegram", telegram_interval, run_on_start):
                    if not _telegram_cooldown_ok():
                        _logger.info("Periodic sync: telegram cooldown active; skip enqueue.")
                    else:
                        _logger.info("Periodic sync: enqueue Telegram interval=%ss.", telegram_interval)
                        schedule_telegram_job()
                        redis_connection.set("sync:last_telegram", int(time.time()))
                        enqueued = True
            else:
                if _should_run_daily("sync:last_telegram", telegram_hour, 0):
                    if not _telegram_cooldown_ok():
                        _logger.info("Periodic sync: telegram cooldown active; skip enqueue.")
                    else:
                        _logger.info("Periodic sync: enqueue Telegram daily.")
                        schedule_telegram_job()
                        redis_connection.set("sync:last_telegram", int(time.time()))
                        enqueued = True
            if not enqueued:
                _logger.info(
                    "Periodic sync: nothing to enqueue (ingestion=%ss, sm=%ss, ph=%ss, telegram=%ss/daily %s).",
                    ingestion_interval,
                    sm_interval,
                    ph_interval,
                    telegram_interval,
                    telegram_hour,
                )
        except Exception:
            _logger.exception("Hourly scheduler error")
        time.sleep(60)


def start_hourly_scheduler() -> None:
    enabled = _env_bool("WORKER_HOURLY_SCHEDULER", True)
    if not enabled:
        _logger.info("Periodic scheduler disabled by WORKER_HOURLY_SCHEDULER.")
        return
    lock_owner = str(os.getpid())
    locked = redis_connection.set(_SCHEDULER_LOCK_KEY, lock_owner, nx=True, ex=3600 + 120)
    if not locked:
        _logger.info("Periodic scheduler already running; skip.")
        return
    thread = threading.Thread(target=_hourly_scheduler_loop, args=(lock_owner,), daemon=True)
    thread.start()


# Start scheduler on import (worker process startup).
start_hourly_scheduler()
