import asyncio
import logging
import time

from app.db.session import async_session

from app.core.config import settings
from app.worker.tasks import schedule_google_sheets_job, schedule_pokerhub_cache_job
from app.services.marketing_daily_service import MarketingDailyDeliveryError, MarketingDailyService

# Менеджер фоновых периодических задач, запускаемых внутри FastAPI-процесса.
# Ингестия ботов заменена real-time логической репликацией — здесь только:
#   1. Google Sheets sync  — каждые GOOGLE_SHEETS_SYNC_INTERVAL_MINUTES (default 60)
#   2. PokerHub API cache  — каждые POKERHUB_SYNC_INTERVAL_MINUTES (default 5)
#   3. Marketing Daily     — проверяет каждые 5 мин, отправляет в нужный час по МСК


class PeriodicSyncManager:
    """Менеджер asyncio-задач для периодических фоновых синхронизаций."""

    def __init__(self) -> None:
        self._logger = logging.getLogger("periodic_sync")
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def _loop(self, name: str, interval_seconds: int, enqueue_fn) -> None:
        """Универсальный цикл: вызывает enqueue_fn каждые interval_seconds.

        При periodic_sync_run_on_start=True запускает задачу сразу при старте.
        Завершается когда выставлен _stop_event.
        """
        if settings.periodic_sync_run_on_start:
            try:
                enqueue_fn()
                self._logger.info("Scheduled %s on startup", name)
            except Exception as exc:
                self._logger.exception("Failed to schedule %s on startup: %s", name, exc)
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                try:
                    enqueue_fn()
                    self._logger.info("Scheduled %s", name)
                except Exception as exc:
                    self._logger.exception("Failed to schedule %s: %s", name, exc)

    async def _marketing_daily_loop(self) -> None:
        """Цикл отправки Marketing Daily дайджеста.

        Просыпается каждые 5 минут, проверяет:
        - включена ли фича в SystemSetting
        - совпадает ли текущий МСК-час с send_hour_msk из настроек
        Если да — вызывает send_digest. При MarketingDailyDeliveryError (нет данных)
        опционально отправляет алерт в Telegram, если send_data_warning_alerts=True.
        """
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=300)
                continue
            except asyncio.TimeoutError:
                pass
            try:
                async with async_session() as session:
                    config = await MarketingDailyService().get_settings(session)
                    if not config.get("enabled"):
                        continue
                    target_hour = int(config.get("send_hour_msk") or 9)
                    now_msk = time.gmtime(time.time() + 3 * 60 * 60)
                    if now_msk.tm_hour != target_hour:
                        continue
                    try:
                        result = await MarketingDailyService().send_digest(session)
                        self._logger.info("Marketing Daily delivery result: %s", result.get("delivery", {}))
                    except MarketingDailyDeliveryError as exc:
                        self._logger.warning("Marketing Daily skipped: %s", exc)
                        if config.get("send_data_warning_alerts"):
                            try:
                                digest = await MarketingDailyService().build_digest(session)
                                await MarketingDailyService().send_alert(
                                    text=(
                                        "Alert | Marketing Daily\n\n"
                                        f"Дайджест за {digest.get('report_date') or 'unknown'} не был отправлен.\n"
                                        f"Причина: {exc}"
                                    ),
                                    report_date=digest.get("report_date") or "unknown",
                                )
                            except Exception as alert_exc:
                                self._logger.exception("Failed to send Marketing Daily alert: %s", alert_exc)
                    await session.commit()
            except Exception as exc:
                self._logger.exception("Failed in marketing_daily scheduler: %s", exc)

    def start(self) -> None:
        """Запускает все asyncio-задачи. Повторный вызов — no-op (защита от двойного старта).

        Marketing Daily запускается всегда.
        Google Sheets и PokerHub — только если periodic_sync_enabled=True.
        """
        if self._tasks:
            return
        self._tasks = [asyncio.create_task(self._marketing_daily_loop())]
        sheets_seconds = max(60, settings.google_sheets_sync_interval_minutes * 60)
        pokerhub_seconds = max(60, settings.pokerhub_sync_interval_minutes * 60)
        if settings.periodic_sync_enabled:
            self._tasks.extend(
                [
                    asyncio.create_task(self._loop("google_sheets_sm", sheets_seconds, schedule_google_sheets_job)),
                    asyncio.create_task(self._loop("pokerhub_cache", pokerhub_seconds, schedule_pokerhub_cache_job)),
                ]
            )
        self._logger.info(
            "Periodic sync started (marketing_daily=300s-check sheets=%ss pokerhub=%ss enabled=%s)",
            sheets_seconds, pokerhub_seconds,
            settings.periodic_sync_enabled,
        )

    async def stop(self) -> None:
        """Останавливает все задачи: выставляет stop_event и ждёт их завершения."""
        if not self._tasks:
            return
        self._stop_event.set()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        self._logger.info("Periodic sync stopped")


# Синглтон — создаётся при старте приложения, запускается в lifespan FastAPI.
periodic_sync_manager = PeriodicSyncManager()
