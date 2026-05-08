from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

from .marketing_daily_service_errors import MarketingDailyDeliveryError


class MarketingDailyDeliveryMixin:
    async def send_digest(self, session: AsyncSession, initiated_by: int | None = None, *, force: bool = False) -> dict[str, Any]:
        digest = await self.build_digest(session)
        if not digest.get("report_date"):
            raise MarketingDailyDeliveryError("Нет данных для отправки дайджеста")
        if not force and self._is_fatal_data_quality(digest.get("data_quality", {})):
            raise MarketingDailyDeliveryError(
                "Дайджест не готов к отправке: " + ", ".join(digest.get("data_quality", {}).get("issues", []))
            )
        recipients = await self.fetch_bot_recipients()
        if not recipients:
            raise MarketingDailyDeliveryError("В mymeet не найдено ни одного получателя Marketing Daily")
        payload = {
            "text": digest["text"],
            "report_date": digest["report_date"],
            "initiated_by": initiated_by,
            "source": "analytic-system",
            "force": force,
        }
        headers = self._bot_headers()
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{self._bot_base_url()}/internal/marketing-daily/deliver", json=payload, headers=headers)
            response.raise_for_status()
            delivery = response.json()
        return {"digest": digest, "delivery": delivery, "recipients": recipients}

    async def send_alert(self, text: str, report_date: str, initiated_by: int | None = None) -> dict[str, Any]:
        headers = self._bot_headers()
        payload = {
            "text": text,
            "report_date": report_date,
            "initiated_by": initiated_by,
            "source": "analytic-system",
            "force": False,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{self._bot_base_url()}/internal/marketing-daily/alert", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    async def fetch_bot_recipients(self) -> list[int]:
        headers = self._bot_headers()
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{self._bot_base_url()}/internal/marketing-daily/recipients", headers=headers)
            response.raise_for_status()
            payload = response.json()
        return self._normalize_ids(payload.get("recipient_ids"))

    async def fetch_delivery_history(self, limit: int = 20) -> list[dict[str, Any]]:
        headers = self._bot_headers()
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{self._bot_base_url()}/admin/marketing-daily/deliveries",
                params={"requester_user_id": settings.marketing_daily_admin_ids[0], "limit": max(1, min(limit, 50))},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        return list(payload.get("items") or [])

    async def sync_bot_config(self, config_payload: dict[str, Any]) -> dict[str, Any]:
        headers = self._bot_headers()
        payload = {
            "allowed_user_ids": self._normalize_ids(config_payload.get("allowed_subscriber_ids")),
            "super_admin_ids": self._normalize_ids(settings.marketing_daily_admin_ids),
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(f"{self._bot_base_url()}/internal/marketing-daily/config-sync", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    def _bot_base_url(self) -> str:
        if not settings.marketing_daily_bot_api_url:
            raise MarketingDailyDeliveryError("Не задан MARKETING_DAILY_BOT_API_URL")
        return settings.marketing_daily_bot_api_url.rstrip("/")

    def _bot_headers(self) -> dict[str, str]:
        if not settings.marketing_daily_bot_api_token:
            raise MarketingDailyDeliveryError("Не задан MARKETING_DAILY_BOT_API_TOKEN")
        return {"X-Marketing-Daily-Token": settings.marketing_daily_bot_api_token}
