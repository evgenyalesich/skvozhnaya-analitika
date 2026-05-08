import asyncio
import os
import threading
import time

from app.core.config import settings
from app.services.system_settings_service import SystemSettingsService
from app.worker.runtime.tasks_runtime_shared import (
    _INGESTION_LOCK_KEY,
    _POKERHUB_LOCK_KEY,
    _SCHEDULER_LOCK_KEY,
    _TELEGRAM_LAST_COMPLETE_KEY,
    _TELEGRAM_MEMBERSHIP_REALTIME_LOCK_KEY,
    _env_bool,
    _env_int,
    _logger,
    _should_run_daily,
    redis_connection,
)


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
    # Import lazily to avoid circular import chain:
    # tasks_runtime_core -> tasks_runtime_scheduler -> tasks_runtime_jobs.
    from app.worker.runtime import tasks_runtime_jobs as jobs_runtime

    def _load_settings():
        async def _get():
            from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
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
        jobs_runtime.schedule_cache_warm_job()

    while True:
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
        membership_enabled = settings.telegram_membership_enabled
        if not periodic_enabled:
            _logger.info("Periodic scheduler disabled by PERIODIC_SYNC_ENABLED.")
            time.sleep(60)
            continue

        try:
            enqueued = False
            if _should_run("sync:last_ingestion", ingestion_interval, run_on_start):
                _logger.info("Periodic sync: enqueue ingestion.")
                jobs_runtime.schedule_ingestion_job()
                enqueued = True
            if _should_run("sync:last_sm", sm_interval, run_on_start):
                _logger.info("Periodic sync: enqueue SM.")
                jobs_runtime.schedule_google_sheets_job()
                enqueued = True
            if _should_run("sync:last_pokerhub", ph_interval, run_on_start):
                _logger.info("Periodic sync: enqueue PokerHub cache.")
                jobs_runtime.schedule_pokerhub_cache_job()
                enqueued = True

            if membership_enabled:
                if settings.telegram_membership_realtime_enabled:
                    realtime_lock = redis_connection.get(_TELEGRAM_MEMBERSHIP_REALTIME_LOCK_KEY)
                    if not realtime_lock:
                        _logger.info("Periodic sync: telegram membership realtime not running — enqueuing.")
                        jobs_runtime.schedule_telegram_membership_realtime_job()
                        enqueued = True
                else:
                    _logger.info("Periodic sync: legacy Telegram bot_poll disabled because membership sync is enabled.")
            else:
                if telegram_interval > 0:
                    if _should_run("sync:last_telegram", telegram_interval, run_on_start):
                        if not _telegram_cooldown_ok():
                            _logger.info("Periodic sync: telegram cooldown active; skip enqueue.")
                        else:
                            _logger.info("Periodic sync: enqueue Telegram interval=%ss.", telegram_interval)
                            jobs_runtime.schedule_telegram_job()
                            redis_connection.set("sync:last_telegram", int(time.time()))
                            enqueued = True
                elif telegram_interval == 0:
                    _logger.info("Periodic sync: legacy Telegram bot_poll disabled (interval=0).")
                else:
                    if _should_run_daily("sync:last_telegram", telegram_hour, 0):
                        if not _telegram_cooldown_ok():
                            _logger.info("Periodic sync: telegram cooldown active; skip enqueue.")
                        else:
                            _logger.info("Periodic sync: enqueue Telegram daily.")
                            jobs_runtime.schedule_telegram_job()
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
    redis_connection.delete(_POKERHUB_LOCK_KEY)
    redis_connection.delete(_INGESTION_LOCK_KEY)
    lock_owner = str(os.getpid())
    locked = redis_connection.set(_SCHEDULER_LOCK_KEY, lock_owner, nx=True, ex=3600 + 120)
    if not locked:
        _logger.info("Periodic scheduler already running; skip.")
        return
    thread = threading.Thread(target=_hourly_scheduler_loop, args=(lock_owner,), daemon=True)
    thread.start()
