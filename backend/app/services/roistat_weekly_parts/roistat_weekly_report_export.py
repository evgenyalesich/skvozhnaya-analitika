from __future__ import annotations

from datetime import timedelta
from typing import List

import google_auth_httplib2
import httplib2
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from app.ingestion.google_sheets_ingestor import GoogleSheetsIngestor


class RoistatWeeklyReportExportMixin:
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
            direct_source_cnt=0,
            platform=0,
            learning=0,
            started_learning=0,
            base=0,
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
                direct_source_cnt=sum(r.direct_source_cnt for r in month_rows),
                platform=sum(r.platform for r in month_rows),
                learning=sum(r.learning for r in month_rows),
                started_learning=sum(r.started_learning for r in month_rows),
                base=sum(r.base for r in month_rows),
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
                    str(r.direct_source_cnt),
                    str(r.platform),
                    str(r.learning),
                    pct(r.learning, r.platform),
                    str(r.base),
                    pct(r.base, r.learning),
                    str(r.mtt),
                    pct(r.mtt, r.learning),
                    str(r.spin),
                    pct(r.spin, r.learning),
                    str(r.cash),
                    pct(r.cash, r.learning),
                    str(r.not_started),
                    pct(r.not_started, r.platform),
                    str(r.saloon),
                    pct(r.saloon, r.almanah_starts),
                    f"{r.budget:.2f}",
                ]

            output.append(row_to_cells(month_label, month_total))
            for idx, week in enumerate(month_rows, start=1):
                output.append(row_to_cells(f"{idx} неделя", week))

            total.almanah_starts += month_total.almanah_starts
            total.direct_source_cnt += month_total.direct_source_cnt
            total.platform += month_total.platform
            total.learning += month_total.learning
            total.started_learning += month_total.started_learning
            total.base += month_total.base
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
                str(total.direct_source_cnt),
                str(total.platform),
                str(total.learning),
                pct(total.learning, total.platform),
                str(total.base),
                pct(total.base, total.learning),
                str(total.mtt),
                pct(total.mtt, total.learning),
                str(total.spin),
                pct(total.spin, total.learning),
                str(total.cash),
                pct(total.cash, total.learning),
                str(total.not_started),
                pct(total.not_started, total.platform),
                str(total.saloon),
                pct(total.saloon, total.almanah_starts),
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
                        "startColumnIndex": 18,
                        "endColumnIndex": 19,
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
                        "startIndex": 18,
                        "endIndex": 19,
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
                range=f"'{self._source_sheet_title}'!A1:R2",
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
                    "Прямой источник",
                    "Регистрация на платформе",
                    "Регистрация на курс",
                    "%",
                    "base",
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
            if len(row) < 18:
                row.extend([""] * (18 - len(row)))
            padded.append([str(cell) for cell in row[:18]])

        # Add budget column to the right of A-O.
        padded[0].append("")
        padded[1].append("Бюджет")
        return padded
