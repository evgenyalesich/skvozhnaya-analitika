"""Compatibility shim. Use app.services.roistat_weekly_report instead."""

from app.services.roistat_weekly_report import RoistatWeeklyReport, WeeklyRow

__all__ = ["RoistatWeeklyReport", "WeeklyRow"]
