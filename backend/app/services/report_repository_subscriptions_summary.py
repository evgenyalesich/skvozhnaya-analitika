# ===== Subscriptions: summary payload helpers =====
from datetime import date as dt_date
from typing import Any


class ReportRepositorySubscriptionsSummaryMixin:
    """Summary payload assembly helpers for subscription reports."""

    @staticmethod
    def _build_subscription_rows_payload(
        rows,
        snapshot_map: dict[tuple[str, str], dict[str, int]],
        subs_map: dict[tuple[str, str, dt_date], dict[str, int]],
    ) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for row in rows:
            snapshot_key = (row.campaign or "", row.bot_key or "")
            snapshot_totals = snapshot_map.get(snapshot_key, {"channel_total": 0, "saloon_total": 0})
            day_key = (row.campaign or "", row.bot_key or "", row.day)
            event_override = subs_map.get(day_key, {})
            channel_subscribed = int(event_override.get("channel_subscribed", 0))
            saloon_subscribed = int(event_override.get("saloon_subscribed", 0))
            channel_unsubscribed = int(event_override.get("channel_unsubscribed", 0))
            saloon_unsubscribed = int(event_override.get("saloon_unsubscribed", 0))
            payload.append(
                {
                    "date": row.day.isoformat() if row.day else None,
                    "campaign": row.campaign,
                    "bot_key": row.bot_key or "",
                    "bot_starts": int(row.bot_starts or 0),
                    "almanah_starts": int(row.almanah_starts or 0),
                    "channel_subscribed": channel_subscribed,
                    "channel_unsubscribed": channel_unsubscribed,
                    "channel_total": int(snapshot_totals["channel_total"]),
                    "saloon_subscribed": saloon_subscribed,
                    "saloon_unsubscribed": saloon_unsubscribed,
                    "saloon_total": int(snapshot_totals["saloon_total"]),
                }
            )
        return payload

    @staticmethod
    def _build_overall_rows_payload(
        overall_rows,
        overall_subs_map: dict[dt_date, dict[str, int]],
    ) -> list[dict[str, Any]]:
        overall_payload: list[dict[str, Any]] = []
        for row in overall_rows:
            event_totals = overall_subs_map.get(row.day, {}) if row.day else {}
            overall_payload.append(
                {
                    "date": row.day.isoformat() if row.day else None,
                    "bot_starts": int(row.bot_starts or 0),
                    "almanah_starts": int(row.almanah_starts or 0),
                    "channel_subscribed": int(event_totals.get("channel_subscribed", 0)),
                    "channel_unsubscribed": int(event_totals.get("channel_unsubscribed", 0)),
                    "saloon_subscribed": int(event_totals.get("saloon_subscribed", 0)),
                    "saloon_unsubscribed": int(event_totals.get("saloon_unsubscribed", 0)),
                }
            )
        return overall_payload
