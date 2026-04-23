from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.analytics import BotRegistry, DailyNewUsersAgg, SystemSetting


class MarketingDailyAccessError(PermissionError):
    pass


class MarketingDailyDeliveryError(RuntimeError):
    pass


class MarketingDailyService:
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

    async def build_digest(self, session: AsyncSession) -> dict[str, Any]:
        target_date = self._target_report_date()
        previous_date = target_date - timedelta(days=1)
        daily_totals_stmt = (
            select(DailyNewUsersAgg.day, DailyNewUsersAgg.bot_key, func.sum(DailyNewUsersAgg.users).label("users"))
            .where(DailyNewUsersAgg.day >= previous_date - timedelta(days=7))
            .group_by(DailyNewUsersAgg.day, DailyNewUsersAgg.bot_key)
            .order_by(DailyNewUsersAgg.day.desc())
        )
        totals_rows = (await session.execute(daily_totals_stmt)).all()
        if not totals_rows:
            return {
                "report_date": None,
                "previous_date": None,
                "summary": {"total_new_users": 0, "change_pct": 0.0, "active_bots": 0, "rising_bots": 0, "falling_bots": 0, "anomaly_bots": 0},
                "leaders_growth": [],
                "leaders_decline": [],
                "anomalies": [],
                "all_bots": [],
                "data_quality": {
                    "ready": False,
                    "status": "failed",
                    "issues": ["Нет данных в agg_daily_new_users"],
                    "latest_data_day": None,
                },
                "text": "Marketing Daily\n\nНет данных для построения дайджеста.",
            }

        latest_available_day = next((row.day for row in totals_rows if row.day is not None), None)

        history_by_bot: dict[str, dict[date, int]] = defaultdict(dict)
        for row in totals_rows:
            if row.day and row.bot_key:
                history_by_bot[str(row.bot_key)] = history_by_bot.get(str(row.bot_key), {})
                history_by_bot[str(row.bot_key)][row.day] = int(row.users or 0)

        registry_rows = (
            await session.execute(
                select(BotRegistry.bot_key, BotRegistry.display_name, BotRegistry.canonical_base)
                .where(BotRegistry.is_active.is_(True))
                .order_by(BotRegistry.display_name.asc().nullslast(), BotRegistry.bot_key.asc())
            )
        ).all()

        active_bots: list[dict[str, Any]] = []
        anomaly_lines: list[str] = []
        rising_bots = 0
        falling_bots = 0
        total_yesterday = 0
        total_previous = 0
        missing_data_bots = 0
        settings_payload = await self.get_settings(session)
        drop_threshold = float(settings_payload.get("anomaly_drop_threshold_pct") or -50.0)
        streak_days = max(2, int(settings_payload.get("downward_streak_days") or 3))

        for row in registry_rows:
            bot_key = str(row.bot_key)
            bot_name = row.display_name or row.canonical_base or bot_key
            per_day = history_by_bot.get(bot_key, {})
            yesterday_value = per_day.get(target_date)
            previous_value = per_day.get(previous_date)

            status = "ok"
            anomalies: list[str] = []
            if yesterday_value is None:
                status = "no_data"
                anomalies.append("нет данных за вчера")
                missing_data_bots += 1
                yesterday_value = 0
            else:
                total_yesterday += yesterday_value
            if previous_value is not None:
                total_previous += previous_value

            change_pct = self._calc_pct(yesterday_value, previous_value)
            if previous_value is not None:
                if yesterday_value > previous_value:
                    rising_bots += 1
                elif yesterday_value < previous_value:
                    falling_bots += 1

            recent_history = self._recent_history(per_day, target_date, streak_days)
            if status != "no_data" and yesterday_value == 0:
                anomalies.append("0 новых за вчера")
            if change_pct is not None and change_pct <= drop_threshold:
                anomalies.append(f"просадка {change_pct:.1f}% к предыдущему дню")
            if self._has_downward_streak(recent_history):
                anomalies.append(f"падение {len(recent_history)}-й день подряд")

            if anomalies:
                anomaly_lines.append(f"- {bot_name}: {anomalies[0]}")

            active_bots.append(
                {
                    "bot_key": bot_key,
                    "bot_name": bot_name,
                    "new_users": int(yesterday_value or 0),
                    "previous_users": int(previous_value or 0) if previous_value is not None else None,
                    "change_pct": change_pct,
                    "status": status,
                    "anomalies": anomalies,
                }
            )

        active_bots.sort(key=lambda item: (-item["new_users"], item["bot_name"].lower()))
        growth = [item for item in active_bots if item["change_pct"] is not None and item["change_pct"] > 0]
        decline = [item for item in active_bots if item["change_pct"] is not None and item["change_pct"] <= 0]
        growth.sort(key=lambda item: (item["change_pct"], item["new_users"]), reverse=True)
        decline.sort(key=lambda item: (item["change_pct"], -item["new_users"]))

        summary = {
            "total_new_users": total_yesterday,
            "change_pct": self._calc_pct(total_yesterday, total_previous),
            "active_bots": len(active_bots),
            "rising_bots": rising_bots,
            "falling_bots": falling_bots,
            "anomaly_bots": sum(1 for item in active_bots if item["anomalies"]),
        }
        data_quality = self._build_data_quality(
            target_date=target_date,
            latest_available_day=latest_available_day,
            active_bots=active_bots,
            missing_data_bots=missing_data_bots,
        )
        text = self._format_digest_text(
            report_date=target_date,
            previous_date=previous_date,
            summary=summary,
            leaders_growth=growth[: max(1, int(settings_payload.get("show_top_growth") or 3))],
            leaders_decline=decline[: max(1, int(settings_payload.get("show_top_decline") or 3))],
            anomalies=anomaly_lines,
            all_bots=active_bots,
            data_quality=data_quality,
        )
        return {
            "report_date": target_date.isoformat(),
            "previous_date": previous_date.isoformat(),
            "summary": summary,
            "leaders_growth": growth[: max(1, int(settings_payload.get("show_top_growth") or 3))],
            "leaders_decline": decline[: max(1, int(settings_payload.get("show_top_decline") or 3))],
            "anomalies": anomaly_lines,
            "all_bots": active_bots,
            "data_quality": data_quality,
            "text": text,
        }

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

    def _format_digest_text(
        self,
        *,
        report_date: date,
        previous_date: date | None,
        summary: dict[str, Any],
        leaders_growth: list[dict[str, Any]],
        leaders_decline: list[dict[str, Any]],
        anomalies: list[str],
        all_bots: list[dict[str, Any]],
        data_quality: dict[str, Any],
    ) -> str:
        lines = [f"Marketing Daily | {report_date.strftime('%d.%m.%Y')}", "", "Итого:"]
        lines.append(f"Новых за вчера: +{summary['total_new_users']}")
        change_pct = summary.get("change_pct")
        change_label = self._fmt_pct(change_pct)
        prev_label = previous_date.strftime("%d.%m.%Y") if previous_date else "предыдущему дню"
        lines.append(f"Изменение к {prev_label}: {change_label}")
        lines.append(f"Активных ботов: {summary['active_bots']}")
        lines.append(f"Растут: {summary['rising_bots']}")
        lines.append(f"Падают: {summary['falling_bots']}")
        lines.append(f"С аномалиями: {summary['anomaly_bots']}")

        if not data_quality.get("ready"):
            lines.extend(["", "Статус данных:", "Данные неполные"])
            for issue in data_quality.get("issues", [])[:5]:
                lines.append(f"- {issue}")

        if leaders_growth:
            lines.extend(["", "Лидеры роста:"])
            for item in leaders_growth:
                lines.append(f"{item['bot_name']}: +{item['new_users']} ({self._fmt_pct(item['change_pct'])})")

        if leaders_decline:
            lines.extend(["", "Просадки:"])
            for item in leaders_decline:
                value_prefix = "+" if item["new_users"] >= 0 else ""
                lines.append(f"{item['bot_name']}: {value_prefix}{item['new_users']} ({self._fmt_pct(item['change_pct'])})")

        if anomalies:
            lines.extend(["", "Аномалии:"])
            lines.extend(anomalies[:10])

        lines.extend(["", "Все боты:"])
        for index, item in enumerate(all_bots, start=1):
            prefix = "+" if item["new_users"] >= 0 else ""
            change = self._fmt_pct(item["change_pct"])
            suffix = " (нет данных)" if item["status"] == "no_data" else ""
            lines.append(f"{index}. {item['bot_name']}: {prefix}{item['new_users']} ({change}){suffix}")
        return "\n".join(lines)

    @staticmethod
    def _target_report_date() -> date:
        return (datetime.now(UTC) + timedelta(hours=3)).date() - timedelta(days=1)

    def _build_data_quality(
        self,
        *,
        target_date: date,
        latest_available_day: date | None,
        active_bots: list[dict[str, Any]],
        missing_data_bots: int,
    ) -> dict[str, Any]:
        issues: list[str] = []
        if latest_available_day is None:
            issues.append(f"Нет данных в аналитике за {target_date.isoformat()} и соседние даты")
        elif latest_available_day < target_date:
            issues.append(
                f"Последние данные в аналитике за {latest_available_day.isoformat() if latest_available_day else 'неизвестно'}, ожидались за {target_date.isoformat()}"
            )
        if missing_data_bots > 0:
            issues.append(f"Нет данных по {missing_data_bots} ботам из {len(active_bots)}")
        zero_count = sum(1 for item in active_bots if item["status"] != "no_data" and int(item["new_users"] or 0) == 0)
        if active_bots and zero_count >= max(3, len(active_bots) // 2):
            issues.append(f"Слишком много ботов с 0 новых: {zero_count}")
        status = "ready" if not issues else "warning"
        return {
            "ready": not issues,
            "status": status,
            "issues": issues,
            "latest_data_day": latest_available_day.isoformat() if latest_available_day else None,
            "target_report_date": target_date.isoformat(),
        }

    @staticmethod
    def _is_fatal_data_quality(data_quality: dict[str, Any]) -> bool:
        issues = list(data_quality.get("issues") or [])
        latest_data_day = data_quality.get("latest_data_day")
        if not latest_data_day:
            return True
        if not issues:
            return False
        joined = " | ".join(issues).lower()
        # Missing target date in analytics is fatal.
        if "нет данных в аналитике" in joined:
            return True
        return False

    @staticmethod
    def _normalize_ids(values: Any) -> list[int]:
        result: list[int] = []
        if isinstance(values, str):
            parts = values.replace("\n", ",").split(",")
        elif isinstance(values, list):
            parts = values
        else:
            parts = []
        for item in parts:
            try:
                value = int(str(item).strip())
            except (TypeError, ValueError):
                continue
            if value > 0 and value not in result:
                result.append(value)
        return result

    @staticmethod
    def _calc_pct(current: int | None, previous: int | None) -> float | None:
        if current is None or previous is None:
            return None
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100, 1)

    @staticmethod
    def _fmt_pct(value: float | None) -> str:
        if value is None:
            return "n/a"
        if value > 0:
            return f"+{value:.1f}%"
        return f"{value:.1f}%"

    @staticmethod
    def _recent_history(per_day: dict[date, int], report_date: date, streak_days: int) -> list[int]:
        ordered_days = sorted((day for day in per_day if day <= report_date), reverse=True)[:streak_days]
        return [per_day[day] for day in ordered_days]

    @staticmethod
    def _has_downward_streak(values: list[int]) -> bool:
        if len(values) < 3:
            return False
        return all(values[index] < values[index + 1] for index in range(len(values) - 1))
