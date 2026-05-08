from app.services.roistat_weekly_parts.roistat_weekly_report_core import RoistatWeeklyReportCoreMixin, WeeklyRow
from app.services.roistat_weekly_parts.roistat_weekly_report_data import RoistatWeeklyReportDataMixin
from app.services.roistat_weekly_parts.roistat_weekly_report_export import RoistatWeeklyReportExportMixin


class RoistatWeeklyReport(
    RoistatWeeklyReportCoreMixin,
    RoistatWeeklyReportDataMixin,
    RoistatWeeklyReportExportMixin,
):
    """Еженедельный Roistat-отчёт: данные по воронке + выгрузка в Google Sheets.

    Слои:
    - Core   — конфигурация Sheets, сборка WeeklyRow (build_weekly_rows)
    - Data   — SQL-запросы: когорты, воронка, mid-funnel, подписки, бюджеты
    - Export — запись WeeklyRow в Google Sheets
    """


__all__ = ["RoistatWeeklyReport", "WeeklyRow"]
