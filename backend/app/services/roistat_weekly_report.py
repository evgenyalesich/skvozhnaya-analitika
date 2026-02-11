from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
import calendar

import os
import httplib2
import google_auth_httplib2
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ingestion.google_sheets_ingestor import GoogleSheetsIngestor


@dataclass
class WeeklyRow:
    week_start: date
    almanah_starts: int
    platform: int
    learning: int
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


class RoistatWeeklyReport:
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
    ) -> List[WeeklyRow]:
        cohort_ids: Optional[set[int]] = None
        if filter_mode == "first_touch":
            cohort_ids = await self._load_first_touch_cohort(
                session,
                first_touch_start=first_touch_start,
                first_touch_end=first_touch_end,
            )
        # Weekly is computed from DB (raw_bot_users + telegram_subscription_events) to avoid
        # overcounting from Google Sheets rows.
        starts_map = await self._load_weekly_starts(
            session,
            event_start=event_start,
            event_end=event_end,
            cohort_ids=cohort_ids,
        )
        platform_map = await self._load_weekly_platform(
            session,
            event_start=event_start,
            event_end=event_end,
            cohort_ids=cohort_ids,
        )
        learning_map, course_map = await self._load_weekly_learning_and_courses(
            session,
            event_start=event_start,
            event_end=event_end,
            cohort_ids=cohort_ids,
        )
        mid_map = await self._load_weekly_mid_funnel(
            session,
            event_start=event_start,
            event_end=event_end,
            cohort_ids=cohort_ids,
        )
        saloon_map = await self._load_subscription_counts(
            session,
            channel_id=os.environ.get("TELEGRAM_COMMUNITY_ID"),
            event_start=event_start,
            event_end=event_end,
            cohort_ids=cohort_ids,
        )
        channel_map = await self._load_subscription_counts(
            session,
            channel_id=os.environ.get("TELEGRAM_CHANNEL_ID"),
            event_start=event_start,
            event_end=event_end,
            cohort_ids=cohort_ids,
        )

        all_week_starts: set[date] = set()
        for mp in (starts_map, platform_map, learning_map, course_map, mid_map, saloon_map, channel_map):
            all_week_starts.update(mp.keys())

        rows: List[WeeklyRow] = []
        for week_start in sorted(all_week_starts):
            platform = int(platform_map.get(week_start, 0))
            learning = int(learning_map.get(week_start, 0))
            if learning > platform:
                platform = learning
            course_counts = course_map.get(week_start, {})
            mid = mid_map.get(week_start, {})
            rows.append(
                WeeklyRow(
                    week_start=week_start,
                    almanah_starts=int(starts_map.get(week_start, 0)),
                    platform=platform,
                    learning=learning,
                    mtt=int(course_counts.get("mtt", 0)),
                    spin=int(course_counts.get("spin", 0)),
                    cash=int(course_counts.get("cash", 0)),
                    not_started=int(course_counts.get("not_started", 0)),
                    channel_subscribed=int(channel_map.get(week_start, 0)),
                    saloon=int(saloon_map.get(week_start, 0)),
                    completed_course=int(mid.get("completed_course", 0)),
                    distance_grinding=int(mid.get("distance_grinding", 0)),
                    contract_signed=int(mid.get("contract_signed", 0)),
                    budget=0.0,
                )
            )
        # Drop completely empty weeks.
        rows = [
            r
            for r in rows
            if (
                r.almanah_starts
                or r.platform
                or r.learning
                or r.mtt
                or r.spin
                or r.cash
                or r.not_started
                or r.channel_subscribed
                or r.saloon
                or r.completed_course
                or r.distance_grinding
                or r.contract_signed
            )
        ]
        budget_map = await self._load_budgets(session)
        for row in rows:
            row.budget = float(budget_map.get(row.week_start, 0.0))
        return rows

    def _load_sm_status_map(self) -> Dict[int, Dict[str, bool]]:
        ingestor = GoogleSheetsIngestor()
        sm_id = ingestor._sm_spreadsheet_id()
        if not sm_id:
            return {}
        creds_path = settings.google_sheets_sm_credentials_path or settings.google_sheets_credentials_path
        if not creds_path:
            return {}
        ranges = ingestor._sm_ranges()
        try:
            rows = ingestor._fetch_sheets(creds_path, sm_id, ranges)
        except Exception:
            return {}
        status_map: Dict[int, Dict[str, bool]] = {}
        for row in rows:
            tg_user_id = (
                row.get("telegram_id")
                or row.get("tg_user_id")
                or row.get("tg_id")
                or row.get("user_id")
                or row.get("id")
            )
            if tg_user_id is None:
                tg_user_id = row.get("__col_1") or row.get("__col_2")
            try:
                user_id = int(str(tg_user_id).strip())
            except Exception:
                continue

            completed_course = ingestor._get_status(
                row,
                ["прошел_курс", "про_шел_курс", "completed_course"],
                true_values={"да"},
                false_values=set(),
            )
            contract_signed = ingestor._get_status(
                row,
                ["contract_signed", "contract", "контракт", "contract_подписан", "подписал_контракт"],
                true_values={"да"},
                false_values=set(),
            )
            distance_grinding = False
            interview_reached_status = ingestor._get_raw_value(
                row,
                [
                    "interview_reached",
                    "interview",
                    "interview_reach",
                    "sobes",
                    "sobes_reached",
                    "собеседование",
                    "собес",
                    "собес_достиг",
                    "дошел_до_собеседования",
                ],
            )
            offer_received_status = ingestor._get_raw_value(
                row,
                [
                    "offer_received",
                    "offer",
                    "offer_get",
                    "оффер",
                    "офер",
                    "offer_получен",
                    "дали_оффер",
                ],
            )
            for status_value in (interview_reached_status, offer_received_status):
                if status_value:
                    normalized = ingestor._normalize_cell(status_value)
                    if normalized in {"наигрывают_дистанцию", "нагрывают_дистанцию"}:
                        distance_grinding = True
                        break

            current = status_map.get(user_id, {"completed_course": False, "distance_grinding": False, "contract_signed": False})
            if completed_course:
                current["completed_course"] = True
            if distance_grinding:
                current["distance_grinding"] = True
            if contract_signed:
                current["contract_signed"] = True
            status_map[user_id] = current
        return status_map

    async def _load_first_touch_cohort(
        self,
        session: AsyncSession,
        first_touch_start: Optional[date],
        first_touch_end: Optional[date],
    ) -> set[int]:
        exclude_keys = ["lead", "almanac", "lead_tests", "lead_test", "lead_dev"]
        query = text(
            """
            WITH first_touch AS (
                SELECT
                    tg_user_id,
                    MIN(created_at)::date AS first_touch_date
                FROM raw_bot_users
                WHERE created_at IS NOT NULL
                  AND bot_key IS NOT NULL
                  AND trim(bot_key) <> ''
                  AND lower(trim(bot_key)) != ALL(CAST(:exclude_keys AS text[]))
                  AND lower(trim(bot_key)) NOT LIKE 'lead%'
                GROUP BY tg_user_id
            )
            SELECT tg_user_id
            FROM first_touch
            WHERE
                (CAST(:start AS date) IS NULL OR first_touch_date >= CAST(:start AS date))
                AND (CAST(:end AS date) IS NULL OR first_touch_date <= CAST(:end AS date))
            """
        )
        params = {
            "exclude_keys": exclude_keys,
            "start": first_touch_start,
            "end": first_touch_end,
        }
        result = await session.execute(query, params)
        return {int(row.tg_user_id) for row in result.fetchall() if row.tg_user_id is not None}

    async def _load_weekly_starts(
        self,
        session: AsyncSession,
        event_start: Optional[date],
        event_end: Optional[date],
        cohort_ids: Optional[set[int]],
    ) -> Dict[date, int]:
        # "Starts in bot": count users by their first non-lead touch date (MIN(created_at)).
        exclude_keys = getattr(settings, "first_touch_exclude_bot_keys", ["lead"])
        conditions = [
            "created_at IS NOT NULL",
            "bot_key IS NOT NULL",
            "trim(bot_key) <> ''",
            "lower(trim(bot_key)) != ALL(CAST(:exclude_keys AS text[]))",
            "lower(trim(bot_key)) NOT LIKE 'lead%'",
        ]
        params: Dict[str, Any] = {"exclude_keys": exclude_keys}
        if cohort_ids:
            conditions.append("tg_user_id = ANY(:cohort_ids)")
            params["cohort_ids"] = list(cohort_ids)
        where_clause = " AND ".join(conditions)
        query = text(
            f"""
            WITH first_touch AS (
                SELECT
                    tg_user_id,
                    MIN(created_at)::date AS first_touch_date
                FROM raw_bot_users
                WHERE {where_clause}
                GROUP BY tg_user_id
            )
            SELECT
                DATE_TRUNC('week', first_touch_date)::date AS week_start,
                COUNT(DISTINCT tg_user_id) AS starts
            FROM first_touch
            WHERE
                (CAST(:start AS date) IS NULL OR first_touch_date >= CAST(:start AS date))
                AND (CAST(:end AS date) IS NULL OR first_touch_date <= CAST(:end AS date))
            GROUP BY week_start
            ORDER BY week_start
            """
        )
        params["start"] = event_start
        params["end"] = event_end
        result = await session.execute(query, params)
        return {row.week_start: int(row.starts or 0) for row in result.fetchall() if row.week_start}

    async def _load_weekly_platform(
        self,
        session: AsyncSession,
        event_start: Optional[date],
        event_end: Optional[date],
        cohort_ids: Optional[set[int]],
    ) -> Dict[date, int]:
        conditions = ["platform_registered_at IS NOT NULL"]
        params: Dict[str, Any] = {}
        if event_start:
            conditions.append("platform_registered_at::date >= :event_start")
            params["event_start"] = event_start
        if event_end:
            conditions.append("platform_registered_at::date <= :event_end")
            params["event_end"] = event_end
        if cohort_ids:
            conditions.append("tg_user_id = ANY(:cohort_ids)")
            params["cohort_ids"] = list(cohort_ids)
        where_clause = " AND ".join(conditions)
        query = text(
            f"""
            SELECT
                DATE_TRUNC('week', platform_registered_at)::date AS week_start,
                COUNT(DISTINCT tg_user_id) AS platform
            FROM raw_bot_users
            WHERE {where_clause}
            GROUP BY week_start
            ORDER BY week_start
            """
        )
        result = await session.execute(query, params)
        return {row.week_start: int(row.platform or 0) for row in result.fetchall() if row.week_start}

    async def _load_weekly_learning_and_courses(
        self,
        session: AsyncSession,
        event_start: Optional[date],
        event_end: Optional[date],
        cohort_ids: Optional[set[int]],
    ) -> tuple[Dict[date, int], Dict[date, Dict[str, int]]]:
        conditions = ["learn_start_date IS NOT NULL"]
        params: Dict[str, Any] = {}
        if event_start:
            conditions.append("learn_start_date::date >= :event_start")
            params["event_start"] = event_start
        if event_end:
            conditions.append("learn_start_date::date <= :event_end")
            params["event_end"] = event_end
        if cohort_ids:
            conditions.append("tg_user_id = ANY(:cohort_ids)")
            params["cohort_ids"] = list(cohort_ids)
        where_clause = " AND ".join(conditions)
        query = text(
            f"""
            SELECT
                DATE_TRUNC('week', learn_start_date)::date AS week_start,
                COUNT(DISTINCT tg_user_id) AS learning,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE LOWER(TRIM(COALESCE(start_course, ''))) = 'mtt') AS mtt,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE LOWER(TRIM(COALESCE(start_course, ''))) = 'spin') AS spin,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE LOWER(TRIM(COALESCE(start_course, ''))) = 'cash') AS cash,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE TRIM(COALESCE(start_course, '')) = '') AS not_started
            FROM raw_bot_users
            WHERE {where_clause}
            GROUP BY week_start
            ORDER BY week_start
            """
        )
        result = await session.execute(query, params)
        learning_map: Dict[date, int] = {}
        course_map: Dict[date, Dict[str, int]] = {}
        for row in result.fetchall():
            if not row.week_start:
                continue
            wk = row.week_start
            learning_map[wk] = int(row.learning or 0)
            course_map[wk] = {
                "mtt": int(row.mtt or 0),
                "spin": int(row.spin or 0),
                "cash": int(row.cash or 0),
                "not_started": int(row.not_started or 0),
            }
        return learning_map, course_map

    async def _load_weekly_mid_funnel(
        self,
        session: AsyncSession,
        event_start: Optional[date],
        event_end: Optional[date],
        cohort_ids: Optional[set[int]],
    ) -> Dict[date, Dict[str, int]]:
        # Bucket mid-funnel statuses by learn_start_date week (funnel-style).
        conditions = ["learn_start_date IS NOT NULL"]
        params: Dict[str, Any] = {}
        if event_start:
            conditions.append("learn_start_date::date >= :event_start")
            params["event_start"] = event_start
        if event_end:
            conditions.append("learn_start_date::date <= :event_end")
            params["event_end"] = event_end
        if cohort_ids:
            conditions.append("tg_user_id = ANY(:cohort_ids)")
            params["cohort_ids"] = list(cohort_ids)
        where_clause = " AND ".join(conditions)
        query = text(
            f"""
            SELECT
                DATE_TRUNC('week', learn_start_date)::date AS week_start,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE completed_course IS TRUE) AS completed_course,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE distance_grinding IS TRUE) AS distance_grinding,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE contract_signed IS TRUE) AS contract_signed
            FROM raw_bot_users
            WHERE {where_clause}
            GROUP BY week_start
            ORDER BY week_start
            """
        )
        result = await session.execute(query, params)
        out: Dict[date, Dict[str, int]] = {}
        for row in result.fetchall():
            if not row.week_start:
                continue
            out[row.week_start] = {
                "completed_course": int(row.completed_course or 0),
                "distance_grinding": int(row.distance_grinding or 0),
                "contract_signed": int(row.contract_signed or 0),
            }
        return out

    async def _load_budgets(self, session: AsyncSession) -> Dict[date, float]:
        query = text(
            """
            WITH budgets AS (
                SELECT
                    DATE_TRUNC('week', week_start)::date AS week_start,
                    SUM(amount) AS budget
                FROM budget_weekly
                GROUP BY DATE_TRUNC('week', week_start)::date
            ),
            spends AS (
                SELECT
                    DATE_TRUNC('week', week_start)::date AS week_start,
                    SUM(spend) AS spend
                FROM ad_metrics_weekly
                GROUP BY DATE_TRUNC('week', week_start)::date
            ),
            all_weeks AS (
                SELECT week_start FROM budgets
                UNION
                SELECT week_start FROM spends
            )
            SELECT
                w.week_start,
                CASE
                    WHEN COALESCE(s.spend, 0) > 0 THEN COALESCE(s.spend, 0)
                    ELSE COALESCE(b.budget, 0)
                END AS budget
            FROM all_weeks w
            LEFT JOIN budgets b ON b.week_start = w.week_start
            LEFT JOIN spends s ON s.week_start = w.week_start
            """
        )
        result = await session.execute(query)
        out: Dict[date, float] = {}
        for row in result.fetchall():
            wk = row.week_start
            out[wk] = float(row.budget or 0.0)
        return out

    async def _load_subscription_counts(
        self,
        session: AsyncSession,
        channel_id: Optional[str],
        event_start: Optional[date],
        event_end: Optional[date],
        cohort_ids: Optional[set[int]],
    ) -> Dict[date, int]:
        if not channel_id:
            return {}
        conditions = [
            "status = 'subscribed'",
            "channel_id = :channel_id",
        ]
        params: Dict[str, Any] = {"channel_id": str(channel_id)}
        if event_start:
            conditions.append("checked_at::date >= :event_start")
            params["event_start"] = event_start
        if event_end:
            conditions.append("checked_at::date <= :event_end")
            params["event_end"] = event_end
        if cohort_ids:
            conditions.append("tg_user_id = ANY(:cohort_ids)")
            params["cohort_ids"] = list(cohort_ids)
        where_clause = " AND ".join(conditions)
        query = text(
            f"""
            SELECT
                DATE_TRUNC('week', checked_at)::date AS week_start,
                COUNT(DISTINCT tg_user_id) AS subscribed
            FROM telegram_subscription_events
            WHERE {where_clause}
            GROUP BY week_start
            """
        )
        result = await session.execute(query, params)
        return {row.week_start: int(row.subscribed or 0) for row in result.fetchall() if row.week_start}

    async def _load_mid_funnel_counts(
        self,
        session: AsyncSession,
        event_start: Optional[date],
        event_end: Optional[date],
        cohort_ids: Optional[set[int]],
    ) -> Dict[date, Dict[str, int]]:
        conditions = ["learn_start_date IS NOT NULL"]
        params: Dict[str, Any] = {}
        if event_start:
            conditions.append("learn_start_date::date >= :event_start")
            params["event_start"] = event_start
        if event_end:
            conditions.append("learn_start_date::date <= :event_end")
            params["event_end"] = event_end
        if cohort_ids:
            conditions.append("tg_user_id = ANY(:cohort_ids)")
            params["cohort_ids"] = list(cohort_ids)
        where_clause = " AND ".join(conditions)
        query = text(
            f"""
            SELECT
                DATE_TRUNC('week', learn_start_date)::date AS week_start,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE completed_course IS TRUE) AS completed_course,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE distance_grinding IS TRUE) AS distance_grinding,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE contract_signed IS TRUE) AS contract_signed
            FROM raw_bot_users
            WHERE {where_clause}
            GROUP BY week_start
            """
        )
        result = await session.execute(query, params)
        out: Dict[date, Dict[str, int]] = {}
        for row in result.fetchall():
            if not row.week_start:
                continue
            out[row.week_start] = {
                "completed_course": int(row.completed_course or 0),
                "distance_grinding": int(row.distance_grinding or 0),
                "contract_signed": int(row.contract_signed or 0),
            }
        return out

    def export_to_sheet(
        self,
        rows: List[WeeklyRow],
        header_rows: List[List[str]],
    ) -> None:
        if not self._sheet_id or not self._creds_path:
            raise RuntimeError("Google Sheets credentials or spreadsheet id is not configured")
        creds = Credentials.from_service_account_file(
            self._creds_path, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        http = google_auth_httplib2.AuthorizedHttp(
            creds, http=httplib2.Http(timeout=60)
        )
        service = build("sheets", "v4", http=http, cache_discovery=False)

        meta = service.spreadsheets().get(spreadsheetId=self._sheet_id).execute()
        sheets = {
            s["properties"]["title"]: {
                "sheet_id": s["properties"]["sheetId"],
                "row_count": int(s["properties"].get("gridProperties", {}).get("rowCount", 1000)),
                "column_count": int(s["properties"].get("gridProperties", {}).get("columnCount", 26)),
            }
            for s in meta.get("sheets", [])
        }
        if self._sheet_title not in sheets:
            service.spreadsheets().batchUpdate(
                spreadsheetId=self._sheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": self._sheet_title}}}]},
            ).execute()
            meta = service.spreadsheets().get(spreadsheetId=self._sheet_id).execute()
            sheets = {
                s["properties"]["title"]: {
                    "sheet_id": s["properties"]["sheetId"],
                    "row_count": int(s["properties"].get("gridProperties", {}).get("rowCount", 1000)),
                    "column_count": int(s["properties"].get("gridProperties", {}).get("columnCount", 26)),
                }
                for s in meta.get("sheets", [])
            }

        # Build rows with month headers + weekly rows + total.
        output: List[List[str]] = []
        output.extend(header_rows)

        def pct(num: int, den: int) -> str:
            if den <= 0:
                return "0,00%"
            return f"{(num / den * 100):.2f}%".replace(".", ",")

        by_month: Dict[str, List[WeeklyRow]] = {}
        for row in rows:
            month_key = row.week_start.strftime("%Y-%m")
            by_month.setdefault(month_key, []).append(row)

        total = WeeklyRow(
            week_start=date.today(),
            almanah_starts=0,
            platform=0,
            learning=0,
            mtt=0,
            spin=0,
            cash=0,
            not_started=0,
            channel_subscribed=0,
            saloon=0,
            completed_course=0,
            distance_grinding=0,
            contract_signed=0,
            budget=0.0,
        )

        ru_months = {
            1: "Январь",
            2: "Февраль",
            3: "Март",
            4: "Апрель",
            5: "Май",
            6: "Июнь",
            7: "Июль",
            8: "Август",
            9: "Сентябрь",
            10: "Октябрь",
            11: "Ноябрь",
            12: "Декабрь",
        }

        for month_key in sorted(by_month.keys()):
            month_rows = sorted(by_month[month_key], key=lambda r: r.week_start)
            year, month = month_key.split("-", 1)
            month_label = ru_months.get(int(month), month_key)
            month_total = WeeklyRow(
                week_start=month_rows[0].week_start,
                almanah_starts=sum(r.almanah_starts for r in month_rows),
                platform=sum(r.platform for r in month_rows),
                learning=sum(r.learning for r in month_rows),
                mtt=sum(r.mtt for r in month_rows),
                spin=sum(r.spin for r in month_rows),
                cash=sum(r.cash for r in month_rows),
                not_started=sum(r.not_started for r in month_rows),
                channel_subscribed=sum(r.channel_subscribed for r in month_rows),
                saloon=sum(r.saloon for r in month_rows),
                completed_course=sum(r.completed_course for r in month_rows),
                distance_grinding=sum(r.distance_grinding for r in month_rows),
                contract_signed=sum(r.contract_signed for r in month_rows),
                budget=sum(r.budget for r in month_rows),
            )

            def row_to_cells(label: str, r: WeeklyRow) -> List[str]:
                return [
                    label,
                    str(r.almanah_starts),
                    str(r.platform),
                    str(r.learning),
                    pct(r.learning, r.platform),
                    str(r.mtt),
                    pct(r.mtt, r.learning),
                    str(r.spin),
                    pct(r.spin, r.mtt),
                    str(r.cash),
                    pct(r.cash, r.spin),
                    str(r.not_started),
                    pct(r.not_started, r.cash),
                    str(r.saloon),
                    pct(r.saloon, r.not_started),
                    f"{r.budget:.2f}",
                ]

            output.append(row_to_cells(month_label, month_total))
            for idx, week in enumerate(month_rows, start=1):
                output.append(row_to_cells(f"{idx} неделя", week))

            total.almanah_starts += month_total.almanah_starts
            total.platform += month_total.platform
            total.learning += month_total.learning
            total.mtt += month_total.mtt
            total.spin += month_total.spin
            total.cash += month_total.cash
            total.not_started += month_total.not_started
            total.channel_subscribed += month_total.channel_subscribed
            total.saloon += month_total.saloon
            total.completed_course += month_total.completed_course
            total.distance_grinding += month_total.distance_grinding
            total.contract_signed += month_total.contract_signed
            total.budget += month_total.budget

        output.append(
            [
                "Total",
                str(total.almanah_starts),
                str(total.platform),
                str(total.learning),
                pct(total.learning, total.platform),
                str(total.mtt),
                pct(total.mtt, total.learning),
                str(total.spin),
                pct(total.spin, total.mtt),
                str(total.cash),
                pct(total.cash, total.spin),
                str(total.not_started),
                pct(total.not_started, total.cash),
                str(total.saloon),
                pct(total.saloon, total.not_started),
                f"{total.budget:.2f}",
            ]
        )

        source_meta = sheets.get(self._source_sheet_title)
        self._copy_source_formatting(
            service=service,
            source_sheet_id=source_meta["sheet_id"] if source_meta else None,
            source_row_count=source_meta["row_count"] if source_meta else 0,
            target_sheet_id=sheets[self._sheet_title]["sheet_id"],
            target_row_count=sheets[self._sheet_title]["row_count"],
            target_column_count=sheets[self._sheet_title]["column_count"],
            rows_to_fill=max(len(output), 2),
        )

        # Clear and write values.
        clear_range = f"{self._sheet_title}!A1:Z"
        service.spreadsheets().values().clear(
            spreadsheetId=self._sheet_id, range=clear_range, body={}
        ).execute()
        service.spreadsheets().values().update(
            spreadsheetId=self._sheet_id,
            range=f"{self._sheet_title}!A1",
            valueInputOption="RAW",
            body={"values": output},
        ).execute()

    def _copy_source_formatting(
        self,
        service: Any,
        source_sheet_id: int | None,
        source_row_count: int,
        target_sheet_id: int,
        target_row_count: int,
        target_column_count: int,
        rows_to_fill: int,
    ) -> None:
        requests: List[dict[str, Any]] = []
        if source_sheet_id is not None:
            source_end_row = min(max(rows_to_fill + 20, 120), max(source_row_count, 2))
            requests.extend(
                [
                    {
                        "copyPaste": {
                            "source": {
                                "sheetId": source_sheet_id,
                                "startRowIndex": 0,
                                "endRowIndex": source_end_row,
                                "startColumnIndex": 0,
                                "endColumnIndex": 15,
                            },
                            "destination": {
                                "sheetId": target_sheet_id,
                                "startRowIndex": 0,
                                "endRowIndex": max(rows_to_fill + 20, 120),
                                "startColumnIndex": 0,
                                "endColumnIndex": 15,
                            },
                            "pasteType": "PASTE_FORMAT",
                            "pasteOrientation": "NORMAL",
                        }
                    },
                    {
                        "copyPaste": {
                            "source": {
                                "sheetId": source_sheet_id,
                                "startRowIndex": 0,
                                "endRowIndex": min(2, max(source_row_count, 2)),
                                "startColumnIndex": 0,
                                "endColumnIndex": 15,
                            },
                            "destination": {
                                "sheetId": target_sheet_id,
                                "startRowIndex": 0,
                                "endRowIndex": 2,
                                "startColumnIndex": 0,
                                "endColumnIndex": 15,
                            },
                            "pasteType": "PASTE_NORMAL",
                            "pasteOrientation": "NORMAL",
                        }
                    },
                ]
            )
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": target_sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": max(rows_to_fill + 20, 120),
                        "startColumnIndex": 15,
                        "endColumnIndex": 16,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"},
                            "horizontalAlignment": "RIGHT",
                        }
                    },
                    "fields": "userEnteredFormat(numberFormat,horizontalAlignment)",
                }
            }
        )
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": target_sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 15,
                        "endIndex": 16,
                    },
                    "properties": {"pixelSize": 110},
                    "fields": "pixelSize",
                }
            }
        )
        service.spreadsheets().batchUpdate(
            spreadsheetId=self._sheet_id,
            body={"requests": requests},
        ).execute()

    def load_source_headers(self) -> List[List[str]]:
        if not self._sheet_id or not self._creds_path:
            raise RuntimeError("Google Sheets credentials or spreadsheet id is not configured")
        creds = Credentials.from_service_account_file(
            self._creds_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        http = google_auth_httplib2.AuthorizedHttp(
            creds, http=httplib2.Http(timeout=60)
        )
        service = build("sheets", "v4", http=http, cache_discovery=False)
        # Read first two rows (note row + header row) from the source sheet.
        resp = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self._sheet_id,
                range=f"'{self._source_sheet_title}'!A1:O2",
                majorDimension="ROWS",
            )
            .execute(num_retries=3)
        )
        values = resp.get("values", [])
        if not values:
            values = [
                [""],
                [
                    "Период",
                    "Старт в бота",
                    "Регистрация на платформе",
                    "Регистрация на курс",
                    "%",
                    "mtt",
                    "%",
                    "spin",
                    "%",
                    "cash",
                    "%",
                    "Не начали курс",
                    "%",
                    "Салун",
                    "%",
                ],
            ]

        if len(values) == 1:
            values.append([])

        padded: List[List[str]] = []
        for row in values[:2]:
            row = list(row)
            if len(row) < 15:
                row.extend([""] * (15 - len(row)))
            padded.append([str(cell) for cell in row[:15]])

        # Add budget column to the right of A-O.
        padded[0].append("")
        padded[1].append("Бюджет")
        return padded
