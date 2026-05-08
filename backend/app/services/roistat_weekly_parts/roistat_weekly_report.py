"""Facade for Roistat weekly report service."""

from app.services.roistat_weekly_parts.roistat_weekly_report_impl import RoistatWeeklyReport, WeeklyRow

__all__ = ["RoistatWeeklyReport", "WeeklyRow"]
