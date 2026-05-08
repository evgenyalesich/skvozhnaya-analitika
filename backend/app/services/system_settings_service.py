from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.analytics import SystemSetting, SyncEventLog
from app.schemas.system_settings import SchedulerSettings, SystemSettingsOut


class SystemSettingsService:
    """Управляет системными настройками через таблицу SystemSetting (key→JSON).

    Сейчас хранит только один ключ "scheduler" — настройки периодической синхронизации.
    Позволяет менять их через admin API без деплоя.
    """
    SETTINGS_KEY = "scheduler"

    def _default_scheduler(self) -> SchedulerSettings:
        """Возвращает дефолтные настройки планировщика из settings (env-переменных)."""
        return SchedulerSettings(
            periodic_enabled=True,
            run_on_start=True,
            warm_cache_on_start=True,
            ingestion_interval_minutes=settings.ingestion_sync_interval_minutes,
            google_sheets_interval_minutes=settings.google_sheets_sync_interval_minutes,
            pokerhub_interval_hours=settings.pokerhub_sync_interval_hours,
            telegram_interval_minutes=settings.telegram_sync_interval_minutes,
            telegram_daily_hour=settings.telegram_sync_daily_hour,
            telegram_batch_size=settings.telegram_batch_size,
            telegram_job_timeout_seconds=settings.telegram_job_timeout_seconds,
        )

    async def get_settings(self, session: AsyncSession) -> SystemSettingsOut:
        """Читает настройки из БД, мёрджит с дефолтами (поля из env как fallback)."""
        row = (
            await session.execute(
                select(SystemSetting).where(SystemSetting.key == self.SETTINGS_KEY)
            )
        ).scalar_one_or_none()
        if not row:
            return SystemSettingsOut(scheduler=self._default_scheduler())
        value = row.value or {}
        scheduler = SchedulerSettings(**{**self._default_scheduler().model_dump(), **value})
        return SystemSettingsOut(scheduler=scheduler)

    async def update_settings(self, session: AsyncSession, payload: Dict[str, Any]) -> SystemSettingsOut:
        """Upsert настроек: обновляет если ключ есть, создаёт если нет."""
        row = (
            await session.execute(
                select(SystemSetting).where(SystemSetting.key == self.SETTINGS_KEY)
            )
        ).scalar_one_or_none()
        if row:
            row.value = payload
        else:
            row = SystemSetting(key=self.SETTINGS_KEY, value=payload)
            session.add(row)
        return SystemSettingsOut(scheduler=SchedulerSettings(**payload))

    async def list_logs(self, session: AsyncSession, limit: int = 100) -> List[SyncEventLog]:
        """Последние N записей из sync_event_logs, отсортированных по убыванию времени."""
        rows = (
            await session.execute(
                select(SyncEventLog).order_by(SyncEventLog.created_at.desc()).limit(limit)
            )
        ).scalars().all()
        return rows


class SyncEventLogger:
    """Хелпер для записи событий синхронизации в sync_event_logs."""

    async def log(self, session: AsyncSession, source: str, level: str, message: str) -> None:
        """Добавляет запись в SyncEventLog. Обрезает message до 1024 символов."""
        session.add(SyncEventLog(source=source, level=level, message=message[:1024]))
