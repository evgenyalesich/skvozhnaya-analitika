from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import BotRegistry, DailyNewUsersAgg


class MarketingDailyDigestMixin:
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
        top_growth = growth[: max(1, int(settings_payload.get("show_top_growth") or 3))]
        top_decline = decline[: max(1, int(settings_payload.get("show_top_decline") or 3))]
        text = self._format_digest_text(
            report_date=target_date,
            previous_date=previous_date,
            summary=summary,
            leaders_growth=top_growth,
            leaders_decline=top_decline,
            anomalies=anomaly_lines,
            all_bots=active_bots,
            data_quality=data_quality,
        )
        return {
            "report_date": target_date.isoformat(),
            "previous_date": previous_date.isoformat(),
            "summary": summary,
            "leaders_growth": top_growth,
            "leaders_decline": top_decline,
            "anomalies": anomaly_lines,
            "all_bots": active_bots,
            "data_quality": data_quality,
            "text": text,
        }
