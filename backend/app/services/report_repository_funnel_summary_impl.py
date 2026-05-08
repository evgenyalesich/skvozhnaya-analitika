from app.services.report_repository_funnel_summary_aggregate import ReportRepositoryFunnelSummaryAggregateMixin
from app.services.report_repository_funnel_summary_touch import ReportRepositoryFunnelSummaryTouchMixin


class ReportRepositoryFunnelSummaryMixin(
    ReportRepositoryFunnelSummaryTouchMixin,
    ReportRepositoryFunnelSummaryAggregateMixin,
):
    """Composed funnel summary slice split by touch + aggregate logic."""
