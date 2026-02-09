import asyncio
import logging

from app.core.config import settings
from app.worker.tasks import schedule_google_sheets_job, schedule_ingestion_job


class PeriodicSyncManager:
    def __init__(self) -> None:
        self._logger = logging.getLogger("periodic_sync")
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def _loop(self, name: str, interval_seconds: int, enqueue_fn) -> None:
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

    def start(self) -> None:
        if self._tasks:
            return
        ingestion_seconds = max(60, settings.ingestion_sync_interval_minutes * 60)
        sm_seconds = max(60, settings.google_sheets_sync_interval_minutes * 60)
        self._tasks = [
            asyncio.create_task(self._loop("ingestion", ingestion_seconds, schedule_ingestion_job)),
            asyncio.create_task(self._loop("google_sheets_sm", sm_seconds, schedule_google_sheets_job)),
        ]
        self._logger.info("Periodic sync started (ingestion=%ss, sm=%ss)", ingestion_seconds, sm_seconds)

    async def stop(self) -> None:
        if not self._tasks:
            return
        self._stop_event.set()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        self._logger.info("Periodic sync stopped")


periodic_sync_manager = PeriodicSyncManager()
