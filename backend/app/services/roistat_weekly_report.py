from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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
    saloon: int
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
        saloon_map = await self._load_saloon_counts(
            session,
            event_start=event_start,
            event_end=event_end,
            cohort_ids=cohort_ids,
        )
        rows = self._build_from_pokerhub_sheet(
            event_start=event_start,
            event_end=event_end,
            first_touch_start=first_touch_start,
            first_touch_end=first_touch_end,
            filter_mode=filter_mode,
            cohort_ids=cohort_ids,
            saloon_map=saloon_map,
        )
        budget_map = await self._load_budgets(session)
        for row in rows:
            row.budget = float(budget_map.get(row.week_start, 0.0))
        return rows

    def _build_from_pokerhub_sheet(
        self,
        event_start: Optional[date] = None,
        event_end: Optional[date] = None,
        first_touch_start: Optional[date] = None,
        first_touch_end: Optional[date] = None,
        filter_mode: str = "event",
        cohort_ids: Optional[set[int]] = None,
        saloon_map: Optional[Dict[date, int]] = None,
    ) -> List[WeeklyRow]:
        if not self._sheet_id or not self._creds_path:
            return []
        creds = Credentials.from_service_account_file(
            self._creds_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        http = google_auth_httplib2.AuthorizedHttp(
            creds, http=httplib2.Http(timeout=60)
        )
        service = build("sheets", "v4", http=http, cache_discovery=False)
        resp = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self._sheet_id,
                range="'pokerhub_robot'!A:U",
                majorDimension="ROWS",
            )
            .execute(num_retries=3)
        )
        values = resp.get("values", [])
        if len(values) <= 1:
            return []

        prepared_rows: List[dict[str, Any]] = []

        def parse_dt(value: str | None) -> Optional[datetime]:
            if not value:
                return None
            raw = str(value).strip()
            if not raw:
                return None
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%fZ",
            ):
                try:
                    return datetime.strptime(raw, fmt)
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00").replace(" ", "T"))
            except ValueError:
                return None

        def in_bucket(dt_value: Optional[datetime], week_start: date) -> bool:
            if dt_value is None:
                return False
            ws = datetime(week_start.year, week_start.month, week_start.day, 0, 0, 0)
            month_last_day = calendar.monthrange(week_start.year, week_start.month)[1]
            end_day = min(week_start.day + 6, month_last_day)
            we = datetime(week_start.year, week_start.month, end_day, 0, 0, 0)
            return ws <= dt_value <= we

        def in_range(dt_value: Optional[datetime], start: Optional[date], end: Optional[date]) -> bool:
            if dt_value is None:
                return False
            d = dt_value.date()
            if start and d < start:
                return False
            if end and d > end:
                return False
            return True

        def event_in_range(dt_value: Optional[datetime]) -> bool:
            if not (event_start or event_end):
                return True
            return in_range(dt_value, event_start, event_end)

        for raw_row in values[1:]:
            row = list(raw_row)
            if len(row) < 21:
                row.extend([""] * (21 - len(row)))
            tg_user_id = None
            if row[0] is not None and str(row[0]).strip() != "":
                try:
                    tg_user_id = int(str(row[0]).strip())
                except ValueError:
                    tg_user_id = None
            start_dt = parse_dt(row[4])   # E: start in bot
            platform_dt = parse_dt(row[17])  # R: platform auth
            learning_dt = parse_dt(row[18])  # S: registration on course
            h_dt = parse_dt(row[7])  # H: used by source formulas for some weeks
            group_value = (row[19] or "").lower()  # T
            courses_value = (row[20] or "").strip()  # U

            # When mode=first_touch, apply cohort filter by tg_user_id.
            if filter_mode == "first_touch" and cohort_ids is not None:
                if tg_user_id is None or tg_user_id not in cohort_ids:
                    continue

            prepared_rows.append(
                {
                    "tg_user_id": tg_user_id,
                    "start_dt": start_dt,
                    "platform_dt": platform_dt,
                    "learning_dt": learning_dt,
                    "h_dt": h_dt,
                    "group": group_value,
                    "courses": courses_value,
                }
            )

        months = {
            (d["start_dt"] or d["platform_dt"] or d["learning_dt"]).date().replace(day=1)
            for d in prepared_rows
            if (d["start_dt"] or d["platform_dt"] or d["learning_dt"]) is not None
        }
        if saloon_map:
            for wk in saloon_map.keys():
                months.add(wk.replace(day=1))
        output: List[WeeklyRow] = []
        for month_start in sorted(months):
            year = month_start.year
            month = month_start.month
            month_last_day = calendar.monthrange(year, month)[1]
            for week_index, start_day in enumerate((1, 8, 15, 22, 29), start=1):
                if start_day > month_last_day:
                    continue
                week_start = date(year, month, start_day)
                row = WeeklyRow(
                    week_start=week_start,
                    almanah_starts=0,
                    platform=0,
                    learning=0,
                    mtt=0,
                    spin=0,
                    cash=0,
                    not_started=0,
                    saloon=(saloon_map or {}).get(week_start, 0),
                    budget=0.0,
                )

                extra_spin_start = None
                extra_spin_end = None
                if week_index == 2:
                    extra_spin_start = date(year, month, 3)
                    extra_spin_end = date(year, month, min(9, month_last_day))

                for item in prepared_rows:
                    if in_bucket(item["start_dt"], week_start) and event_in_range(item["start_dt"]):
                        row.almanah_starts += 1

                    platform_hit = in_bucket(item["platform_dt"], week_start) and event_in_range(item["platform_dt"])
                    learning_hit = in_bucket(item["learning_dt"], week_start) and event_in_range(item["learning_dt"])

                    if platform_hit:
                        row.platform += 1

                    if learning_hit:
                        row.learning += 1
                        # Ensure platform is not lower than learning within the same bucket.
                        if not platform_hit:
                            row.platform += 1

                        if item["courses"] == "":
                            row.not_started += 1

                        course = None
                        if "mtt" in item["group"]:
                            course = "mtt"
                        elif "spin" in item["group"]:
                            course = "spin"
                        elif "cash" in item["group"]:
                            course = "cash"
                        elif "лендинг. основная воронка" in item["group"]:
                            # Legacy rule kept for landing group, but only within learning bucket.
                            ld = item["learning_dt"].date() if item["learning_dt"] else None
                            if week_index == 2 and ld and extra_spin_start and extra_spin_end and extra_spin_start <= ld <= extra_spin_end:
                                course = "spin"
                            elif week_index == 3 and in_bucket(item["start_dt"], week_start):
                                course = "spin"
                            elif week_index == 4 and in_bucket(item["h_dt"], week_start):
                                course = "spin"
                            elif week_index == 5 and ld and in_bucket(item["learning_dt"], week_start):
                                course = "spin"

                        if course == "mtt":
                            row.mtt += 1
                        elif course == "spin":
                            row.spin += 1
                        elif course == "cash":
                            row.cash += 1

                if row.almanah_starts or row.platform or row.learning or row.not_started or row.saloon:
                    output.append(row)

        return output

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

    async def _load_budgets(self, session: AsyncSession) -> Dict[date, float]:
        query = text(
            """
            WITH budgets AS (
                SELECT
                    (
                        DATE_TRUNC('month', week_start)::date
                        + (((EXTRACT(DAY FROM week_start)::int - 1) / 7) * 7)
                    )::date AS week_start,
                    SUM(amount) AS budget
                FROM budget_weekly
                GROUP BY
                    (
                        DATE_TRUNC('month', week_start)::date
                        + (((EXTRACT(DAY FROM week_start)::int - 1) / 7) * 7)
                    )::date
            ),
            spends AS (
                SELECT
                    (
                        DATE_TRUNC('month', week_start)::date
                        + (((EXTRACT(DAY FROM week_start)::int - 1) / 7) * 7)
                    )::date AS week_start,
                    SUM(spend) AS spend
                FROM ad_metrics_weekly
                GROUP BY
                    (
                        DATE_TRUNC('month', week_start)::date
                        + (((EXTRACT(DAY FROM week_start)::int - 1) / 7) * 7)
                    )::date
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

    async def _load_saloon_counts(
        self,
        session: AsyncSession,
        event_start: Optional[date],
        event_end: Optional[date],
        cohort_ids: Optional[set[int]],
    ) -> Dict[date, int]:
        community_id = os.environ.get("TELEGRAM_COMMUNITY_ID")
        if not community_id:
            return {}
        conditions = [
            "status = 'subscribed'",
            "channel_id = :community_id",
        ]
        params: Dict[str, Any] = {"community_id": str(community_id)}
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
            SELECT tg_user_id, checked_at::date AS event_date
            FROM telegram_subscription_events
            WHERE {where_clause}
            """
        )
        result = await session.execute(query, params)

        def week_bucket_start(d: date) -> date:
            if d.day <= 7:
                day = 1
            elif d.day <= 14:
                day = 8
            elif d.day <= 21:
                day = 15
            elif d.day <= 28:
                day = 22
            else:
                day = 29
            return date(d.year, d.month, day)

        buckets: Dict[date, set[int]] = {}
        for row in result.fetchall():
            if row.tg_user_id is None or row.event_date is None:
                continue
            wk = week_bucket_start(row.event_date)
            buckets.setdefault(wk, set()).add(int(row.tg_user_id))
        return {wk: len(ids) for wk, ids in buckets.items()}

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
            saloon=0,
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
                saloon=sum(r.saloon for r in month_rows),
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
            total.saloon += month_total.saloon
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
