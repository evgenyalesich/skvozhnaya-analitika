# ===== Subscriptions: funnel helpers =====
class ReportRepositorySubscriptionsFunnelMixin:
    """Funnel-related helpers for subscription reports."""

    @staticmethod
    def _safe_cost(spend_value: float, cnt: int) -> float | None:
        if cnt <= 0:
            return None
        return round(spend_value / cnt, 2)
