from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any


class MarketingDailyHelpersMixin:
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
