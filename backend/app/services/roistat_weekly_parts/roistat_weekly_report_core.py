from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


@dataclass
class WeeklyRow:
    """Одна строка недельного отчёта — все метрики за одну неделю.

    week_start — понедельник недели. Поля: входящие боты (almanah_starts),
    этапы воронки (new/old in system, platform, learning, course, contract),
    разбивка по типам курса (mtt/spin/cash), Telegram-подписки, бюджет.
    """
    week_start: date
    almanah_starts: int
    new_in_system: int
    old_in_system: int
    platform: int
    learning: int
    started_learning: int
    mtt: int
    spin: int
    cash: int
    not_started: int
    channel_subscribed: int
    saloon: int
    completed_course: int
    distance_grinding: int
    contract_signed: int
    budget: float
    direct_source_cnt: int = 0
    base: int = 0
    entered_all: int = 0
    interview_reached: int = 0
    offer_received: int = 0
    completed_mtt: int = 0
    completed_spin: int = 0
    completed_cash: int = 0
    contract_mtt: int = 0
    contract_spin: int = 0
    contract_cash: int = 0


class RoistatWeeklyReportCoreMixin:
    """Ядро сервиса Roistat Weekly Report: конфигурация Google Sheets и сборка строк отчёта.

    Поддерживает три режима фильтрации cohort:
    - "event"       — по дате события (when user entered the funnel stage)
    - "first_touch" — по дате первого касания (когда впервые попал в бота)
    - "last_touch"  — по дате последнего касания перед обучением
    """

    def __init__(self) -> None:
        self._sheet_id = (
            getattr(settings, "roistat_weekly_sheet_id", None)
            or settings.google_sheets_spreadsheet_id
        )
        self._sheet_title = (
            getattr(settings, "roistat_weekly_sheet_title", None)
            or "Weekly"
        )
        self._source_sheet_title = "Итоговые результаты студенты"
        self._creds_path = settings.google_sheets_credentials_path

    async def build_weekly_rows(
        self,
        session: AsyncSession,
        event_start: Optional[date] = None,
        event_end: Optional[date] = None,
        first_touch_start: Optional[date] = None,
        first_touch_end: Optional[date] = None,
        filter_mode: str = "event",
        bots: Optional[List[str]] = None,
    ) -> List[WeeklyRow]:
        """Собирает список WeeklyRow за период.

        Порядок: загружает когорту (если first/last touch) -> основные строки воронки ->
        mid-funnel метрики (course, interview, offer) -> подписки (channel + saloon) ->
        общие starts -> бюджеты. Недели без данных заполняются нулевыми строками.
        """
        cohort_ids: Optional[set[int]] = None
        if filter_mode == "first_touch":
            cohort_ids = await self._load_first_touch_cohort(
                session,
                first_touch_start=first_touch_start,
                first_touch_end=first_touch_end,
            )
        elif filter_mode == "last_touch":
            cohort_ids = await self._load_last_touch_cohort(
                session,
                last_touch_start=first_touch_start,
                last_touch_end=first_touch_end,
            )
        rows = await self._load_weekly_cohort_funnel(
            session,
            event_start=event_start,
            event_end=event_end,
            cohort_ids=cohort_ids,
            bots=bots,
        )
        rows_by_week = {row.week_start: row for row in rows}

        def ensure_row(week_start: date) -> WeeklyRow:
            row = rows_by_week.get(week_start)
            if row is None:
                row = WeeklyRow(
                    week_start=week_start,
                    almanah_starts=0,
                    direct_source_cnt=0,
                    new_in_system=0,
                    old_in_system=0,
                    platform=0,
                    learning=0,
                    started_learning=0,
                    mtt=0,
                    spin=0,
                    cash=0,
                    base=0,
                    not_started=0,
                    channel_subscribed=0,
                    saloon=0,
                    completed_course=0,
                    distance_grinding=0,
                    contract_signed=0,
                    budget=0.0,
                )
                rows_by_week[week_start] = row
            return row

        mid_funnel = await self._load_mid_funnel_counts(
            session,
            event_start=event_start,
            event_end=event_end,
            cohort_ids=cohort_ids,
        )
        for week_start, values in mid_funnel.items():
            row = ensure_row(week_start)
            row.completed_course = values.get("completed_course", 0)
            row.distance_grinding = values.get("distance_grinding", 0)
            row.contract_signed = values.get("contract_signed", 0)
            row.interview_reached = values.get("interview_reached", 0)
            row.offer_received = values.get("offer_received", 0)
            row.completed_mtt = values.get("completed_mtt", 0)
            row.completed_spin = values.get("completed_spin", 0)
            row.completed_cash = values.get("completed_cash", 0)
            row.contract_mtt = values.get("contract_mtt", 0)
            row.contract_spin = values.get("contract_spin", 0)
            row.contract_cash = values.get("contract_cash", 0)

        channel_counts = await self._load_subscription_counts(
            session,
            channel_id=settings.telegram_channel_id,
            event_start=event_start,
            event_end=event_end,
            cohort_ids=cohort_ids,
        )
        for week_start, value in channel_counts.items():
            ensure_row(week_start).channel_subscribed = value

        saloon_counts = await self._load_subscription_counts(
            session,
            channel_id=settings.telegram_community_id,
            event_start=event_start,
            event_end=event_end,
            cohort_ids=cohort_ids,
        )
        for week_start, value in saloon_counts.items():
            ensure_row(week_start).saloon = value

        total_starts_map = await self._load_total_bot_starts(
            session,
            event_start=event_start,
            event_end=event_end,
            cohort_ids=cohort_ids,
        )
        for week_start, value in total_starts_map.items():
            ensure_row(week_start).entered_all = value

        budget_map = await self._load_budgets(session)
        rows = sorted(rows_by_week.values(), key=lambda row: row.week_start)
        for row in rows:
            row.budget = float(budget_map.get(row.week_start, 0.0))
        return rows
