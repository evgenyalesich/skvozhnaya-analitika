import asyncio
import os
import time
from datetime import date, timedelta

from app.api.report_filters import ReportFilters
from app.core.config import settings
from app.core.redis_client import RedisCache
from app.db.session import async_session
from app.ingestion.google_sheets_ingestor import GoogleSheetsIngestor
from app.ingestion.master_ingestion import IngestionCoordinator
from app.ingestion.pokerhub_ingestor import PokerHubIngestor
from app.ingestion.telegram_ingestor import TelegramStatusIngestor
from app.services.aggregate_refresher import AggregateRefresher
from app.services.report_cache_service import ReportCacheService
from app.services.roistat_weekly_report import RoistatWeeklyReport
from app.services.system_settings_service import SyncEventLogger
from app.services.telegram_membership_service import TelegramMembershipService
from app.worker.runtime.tasks_runtime_shared import (
    _CACHE_WARM_LOCK_KEY,
    _INGESTION_LOCK_KEY,
    _POKERHUB_LOCK_KEY,
    _ROISTAT_WEEKLY_LOCK_KEY,
    _SM_LOCK_KEY,
    _TELEGRAM_BATCH_DONE_KEY,
    _TELEGRAM_BATCH_ERRORS_KEY,
    _TELEGRAM_BATCH_PENDING_KEY,
    _TELEGRAM_BATCH_TOTAL_KEY,
    _TELEGRAM_LAST_COMPLETE_KEY,
    _TELEGRAM_LOCK_KEY,
    _TELEGRAM_MEMBERSHIP_LOCK_KEY,
    _TELEGRAM_MEMBERSHIP_REALTIME_LOCK_KEY,
    _TELEGRAM_USERS_CHECKED_KEY,
    _TELEGRAM_USERS_TOTAL_KEY,
    _acquire_sync_serial_lock,
    _logger,
    queue,
    redis_connection,
    telegram_queue,
)


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

    async def _invalidate_report_caches() -> None:
        cache = RedisCache()
        await cache.delete_pattern("reports:roistat_weekly:*")
        await cache.delete_pattern("reports:subscriptions_vs_starts:*")
        await cache.delete_pattern("utm:options:*")

    async def _run() -> None:
        with _acquire_sync_serial_lock("ingestion"):
            try:
                redis_connection.set(_INGESTION_LOCK_KEY, "running", ex=3600)
                await IngestionCoordinator().run(sm_only=settings.google_sheets_only_sm)
                await AggregateRefresher().refresh(days=settings.aggregate_refresh_days)
                await _invalidate_report_caches()
                try:
                    from app.services.main_report_weekly_audit import MainReportWeeklyAuditService

                    async with async_session() as audit_session:
                        issues = await MainReportWeeklyAuditService().run(audit_session, weeks=8)
                        if issues:
                            await SyncEventLogger().log(
                                audit_session,
                                source="main_report_audit",
                                level="warning",
                                message="; ".join(issues[:20]),
                            )
                        else:
                            await SyncEventLogger().log(
                                audit_session,
                                source="main_report_audit",
                                level="info",
                                message="weekly audit passed",
                            )
                        await audit_session.commit()
                except Exception as audit_exc:
                    async with async_session() as audit_session:
                        await SyncEventLogger().log(
                            audit_session,
                            source="main_report_audit",
                            level="warning",
                            message=f"audit skipped: {audit_exc}",
                        )
                        await audit_session.commit()
                if settings.warm_cache_after_sync:
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


def run_telegram_membership_full_sync_job(chat_ids: list[str] | None = None) -> None:
    async def _run() -> None:
        locked = redis_connection.set(
            _TELEGRAM_MEMBERSHIP_LOCK_KEY,
            "running",
            nx=True,
            ex=max(settings.telegram_job_timeout_seconds, 4 * 60 * 60),
        )
        if not locked:
            _logger.warning("Telegram membership full sync already running; skip.")
            return
        try:
            async with async_session() as session:
                results = await TelegramMembershipService().run_full_sync(session, chat_ids=chat_ids)
                await session.commit()
                for result in results:
                    _logger.info(
                        "Telegram membership sync: chat_id=%s seen=%s inserted=%s updated=%s activated=%s deactivated=%s",
                        result.chat_id,
                        result.seen_members,
                        result.inserted,
                        result.updated,
                        result.activated,
                        result.deactivated,
                    )
        except Exception as exc:
            async with async_session() as session:
                await SyncEventLogger().log(session, source="telegram_membership", level="error", message=str(exc))
                await session.commit()
            raise
        finally:
            redis_connection.delete(_TELEGRAM_MEMBERSHIP_LOCK_KEY)

    asyncio.run(_run())


def schedule_telegram_membership_full_sync_job(chat_ids: list[str] | None = None) -> None:
    telegram_queue.enqueue(
        run_telegram_membership_full_sync_job,
        chat_ids,
        job_timeout=max(settings.telegram_job_timeout_seconds, 4 * 60 * 60),
    )


def run_telegram_membership_realtime_job() -> None:
    async def _run() -> None:
        locked = redis_connection.set(
            _TELEGRAM_MEMBERSHIP_REALTIME_LOCK_KEY,
            "running",
            nx=True,
            ex=24 * 60 * 60,
        )
        if not locked:
            _logger.warning("Telegram membership realtime already running; skip.")
            return
        try:
            from app.services.telegram_membership_service import TelegramMembershipRealtimeMonitor

            await TelegramMembershipRealtimeMonitor().run()
        except Exception as exc:
            async with async_session() as session:
                await SyncEventLogger().log(session, source="telegram_membership_realtime", level="error", message=str(exc))
                await session.commit()
            raise
        finally:
            redis_connection.delete(_TELEGRAM_MEMBERSHIP_REALTIME_LOCK_KEY)

    asyncio.run(_run())


def schedule_telegram_membership_realtime_job() -> None:
    telegram_queue.enqueue(run_telegram_membership_realtime_job, job_timeout=7 * 24 * 60 * 60)


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

        async def _invalidate_report_caches() -> None:
            cache = RedisCache()
            await cache.delete_pattern("reports:roistat_weekly:*")
            await cache.delete_pattern("reports:subscriptions_vs_starts:*")
            await cache.delete_pattern("utm:options:*")

        with _acquire_sync_serial_lock("google_sheets"):
            try:
                redis_connection.set(_SM_LOCK_KEY, "running", ex=1200)
                async with async_session() as session:
                    await GoogleSheetsIngestor().ingest(session, sm_only=settings.google_sheets_only_sm)
                    await session.commit()
                await _invalidate_report_caches()
                await _record_status(True, None)
                if settings.warm_cache_after_sync:
                    try:
                        await _warm_report_cache()
                    except Exception as exc:
                        _logger.warning("Warm report cache failed after SM sync: %s", exc)
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
        user_scope=None,
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
    queue.enqueue(run_google_sheets_job, job_timeout=3600)


def run_pokerhub_cache_job() -> None:
    async def _run() -> None:
        async def _record_status(success: bool, error: str | None) -> None:
            payload = {
                "ts": int(time.time()),
                "status": "ok" if success else "error",
                "error": error,
            }
            cache = RedisCache()
            await cache.set_json("sync:last_pokerhub", payload)
            if success:
                await cache.set_json("sync:last_pokerhub_success", payload)

        async def _invalidate_report_caches() -> None:
            cache = RedisCache()
            await cache.delete_pattern("reports:roistat_weekly:*")
            await cache.delete_pattern("reports:subscriptions_vs_starts:*")
            await cache.delete_pattern("utm:options:*")

        with _acquire_sync_serial_lock("pokerhub"):
            try:
                redis_connection.set(_POKERHUB_LOCK_KEY, "running", ex=1800)
                async with async_session() as session:
                    await PokerHubIngestor().ingest(session)
                    await session.commit()
                await _invalidate_report_caches()
                await _record_status(True, None)
                if settings.warm_cache_after_sync:
                    try:
                        await _warm_report_cache()
                    except Exception as exc:
                        _logger.warning("Warm report cache failed after PokerHub sync: %s", exc)
            except Exception as exc:
                await _record_status(False, str(exc))
                async with async_session() as session:
                    await SyncEventLogger().log(session, source="pokerhub", level="error", message=str(exc))
                    await session.commit()
                raise
            finally:
                redis_connection.delete(_POKERHUB_LOCK_KEY)

    asyncio.run(_run())


def schedule_pokerhub_cache_job() -> None:
    locked = redis_connection.set(_POKERHUB_LOCK_KEY, "queued", nx=True, ex=600)
    if not locked:
        _logger.warning("PokerHub cache job already queued/running; skip enqueue.")
        return
    queue.enqueue(run_pokerhub_cache_job, job_timeout=600)


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
    queue.enqueue(run_cache_warm_job, job_timeout=3600)


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
