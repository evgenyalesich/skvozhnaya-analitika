from app.services.roistat_weekly_parts.roistat_weekly_report_data_cohort import RoistatWeeklyReportDataCohortMixin
from app.services.roistat_weekly_parts.roistat_weekly_report_data_funnel import RoistatWeeklyReportDataFunnelMixin
from app.services.roistat_weekly_parts.roistat_weekly_report_data_metrics import RoistatWeeklyReportDataMetricsMixin


class RoistatWeeklyReportDataMixin(
    RoistatWeeklyReportDataCohortMixin,
    RoistatWeeklyReportDataFunnelMixin,
    RoistatWeeklyReportDataMetricsMixin,
):
    """Composed Roistat weekly data layer split by cohort/funnel/metrics slices."""
