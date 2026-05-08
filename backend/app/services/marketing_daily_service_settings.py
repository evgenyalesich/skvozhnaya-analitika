from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.analytics import SystemSetting

from .marketing_daily_service_errors import MarketingDailyAccessError


class MarketingDailySettingsMixin:
    SETTINGS_KEY = "marketing_daily"

    def default_settings(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "send_hour_msk": 9,
            "show_top_growth": 3,
            "show_top_decline": 3,
            "allowed_subscriber_ids": [],
            "anomaly_drop_threshold_pct": -50.0,
            "downward_streak_days": 3,
            "send_data_warning_alerts": True,
        }

    async def get_settings(self, session: AsyncSession) -> dict[str, Any]:
        row = await session.get(SystemSetting, self.SETTINGS_KEY)
        stored = row.value if row and isinstance(row.value, dict) else {}
        defaults = self.default_settings()
        merged = {**defaults, **stored}
        merged["allowed_subscriber_ids"] = self._normalize_ids(merged.get("allowed_subscriber_ids"))
        return merged

    async def update_settings(self, session: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            **self.default_settings(),
            **payload,
            "allowed_subscriber_ids": self._normalize_ids(payload.get("allowed_subscriber_ids")),
        }
        row = await session.get(SystemSetting, self.SETTINGS_KEY)
        if row:
            row.value = normalized
        else:
            row = SystemSetting(key=self.SETTINGS_KEY, value=normalized)
            session.add(row)
        await session.flush()
        await self.sync_bot_config(normalized)
        return normalized

    def assert_admin(self, tg_user_id: int | None) -> None:
        if int(tg_user_id or 0) not in settings.marketing_daily_admin_ids:
            raise MarketingDailyAccessError("Marketing Daily доступен только супер-админам")
