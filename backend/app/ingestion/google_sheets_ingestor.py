import asyncio
import os
import re
import logging
import time
from typing import List, Optional

import httplib2
import google_auth_httplib2
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import update, or_, func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.analytics import RawBotUser


class GoogleSheetsIngestor:
    def __init__(self, _loader=None):
        self._loader = _loader
        self._logger = logging.getLogger("google_sheets_ingestor")
        self._true_status_values = {
            "да",
            "yes",
            "true",
            "1",
            "ок",
            "ok",
            "пересдача",
            "нагрывают_дистанцию",
            "наигрывают_дистанцию",
            "назначили",
            "направили_на_курс_спины",
        }
        self._false_status_values = {
            "нет",
            "no",
            "false",
            "0",
            "не_отвечает",
            "не_ответил",
            "мы_отказали",
            "мы_отказали_арбитраж",
            "отказали",
            "отказался",
            "отказ",
            "пропал",
            "не_назначали_арбитраж",
            "тех_проблема",
            "отложен",
        }
        try:
            import asyncpg  # type: ignore
        except Exception:  # pragma: no cover - optional dependency
            asyncpg = None
        self._asyncpg = asyncpg

    def _is_deadlock(self, exc: Exception) -> bool:
        if not isinstance(exc, DBAPIError):
            return False
        orig = exc.orig
        if orig is None:
            return False
        asyncpg = self._asyncpg
        if asyncpg is not None and isinstance(orig, asyncpg.exceptions.DeadlockDetectedError):
            return True
        return "DeadlockDetectedError" in str(orig)

    async def _execute_with_retry(self, session: AsyncSession, stmt, retries: int = 3):
        for attempt in range(retries):
            try:
                return await session.execute(stmt)
            except DBAPIError as exc:
                if self._is_deadlock(exc) and attempt < retries - 1:
                    await session.rollback()
                    await asyncio.sleep(0.4 * (2 ** attempt))
                    continue
                raise

    async def ingest(self, session: AsyncSession, sm_only: bool | None = None) -> None:
        only_sm = sm_only if sm_only is not None else settings.google_sheets_only_sm
        sources = self._collect_sources(sm_only=only_sm)
        if not sources:
            return
        sm_id = self._sm_spreadsheet_id()
        for creds_path, spreadsheet_id, ranges in sources:
            if not creds_path:
                continue
            try:
                data = await asyncio.to_thread(self._fetch_sheets, creds_path, spreadsheet_id, ranges)
            except Exception as exc:
                # Transport-level failures (timeouts, DNS, etc.) are not always HttpError.
                # Treat them as non-fatal for the overall job so other sources can still ingest.
                self._logger.error(
                    "GoogleSheets ingestion skipped %s due to error: %s",
                    spreadsheet_id,
                    exc,
                    exc_info=True,
                )
                continue
            await self._apply(session, data, is_sm=bool(sm_id and spreadsheet_id == sm_id))

    def _spreadsheet_id(self) -> Optional[str]:
        if settings.google_sheets_spreadsheet_id:
            return settings.google_sheets_spreadsheet_id
        if settings.google_sheets_spreadsheet_url:
            match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", settings.google_sheets_spreadsheet_url)
            if match:
                return match.group(1)
        return None

    def _ranges(self) -> List[str]:
        if settings.google_sheets_ranges:
            return [item.strip() for item in settings.google_sheets_ranges.split(",") if item.strip()]
        return []

    def _sm_spreadsheet_id(self) -> Optional[str]:
        if settings.google_sheets_sm_spreadsheet_id:
            return settings.google_sheets_sm_spreadsheet_id
        if settings.google_sheets_sm_spreadsheet_url:
            match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", settings.google_sheets_sm_spreadsheet_url)
            if match:
                return match.group(1)
        return None

    def _sm_ranges(self) -> List[str]:
        if settings.google_sheets_sm_ranges:
            return [item.strip() for item in settings.google_sheets_sm_ranges.split(",") if item.strip()]
        return ["БАЗА!A:AH"]

    def _collect_sources(self, sm_only: bool = False) -> List[tuple[str, str, List[str]]]:
        sources: List[tuple[str, str, List[str]]] = []
        if not sm_only:
            primary_id = self._spreadsheet_id()
            if primary_id:
                sources.append((settings.google_sheets_credentials_path, primary_id, self._ranges()))
        sm_id = self._sm_spreadsheet_id()
        if sm_id:
            sources.append((settings.google_sheets_sm_credentials_path or settings.google_sheets_credentials_path, sm_id, self._sm_ranges()))
        return sources

    def _fetch_sheets(self, creds_path: str, spreadsheet_id: str, ranges: List[str]) -> List[dict]:
        creds = Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        timeout_seconds = max(5, int(os.getenv("GOOGLE_SHEETS_TIMEOUT_SECONDS", "60")))
        http = google_auth_httplib2.AuthorizedHttp(
            creds, http=httplib2.Http(timeout=timeout_seconds)
        )
        service = build("sheets", "v4", http=http, cache_discovery=False)
        self._logger.warning(
            "GoogleSheets ingest: spreadsheet_id=%s ranges=%s service_account=%s creds_path=%s",
            spreadsheet_id,
            ranges or "(all)",
            getattr(creds, "service_account_email", "unknown"),
            creds_path,
        )
        rows = []
        if not ranges:
            meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute(num_retries=3)
            ranges = [sheet["properties"]["title"] + "!A:Z" for sheet in meta.get("sheets", [])]
        for data_range in ranges:
            response = self._fetch_range(service, spreadsheet_id, data_range)
            values = response.get("values", [])
            if not values:
                continue
            columns = values[0]
            for row in values[1:]:
                row_dict = {}
                for idx in range(min(len(columns), len(row))):
                    value = row[idx]
                    row_dict[self._normalize_key(columns[idx])] = value
                    row_dict[f"__col_{idx + 1}"] = value
                rows.append(row_dict)
        return rows

    def _fetch_range(self, service, spreadsheet_id: str, data_range: str) -> dict:
        attempts = 0
        max_attempts = 4
        base_backoff = 1
        while True:
            try:
                return (
                    service.spreadsheets()
                    .values()
                    .get(spreadsheetId=spreadsheet_id, range=data_range)
                    .execute(num_retries=5)
                )
            except HttpError as exc:
                status = getattr(exc.resp, "status", None)
                if status in {408, 429, 500, 502, 503, 504} and attempts < max_attempts:
                    wait = base_backoff * (2 ** attempts)
                    self._logger.warning(
                        "GoogleSheets transient error (%s) on %s; retrying in %ss (attempt %s)",
                        status,
                        data_range,
                        wait,
                        attempts + 1,
                    )
                    time.sleep(wait)
                    attempts += 1
                    continue
                self._logger.error("GoogleSheets error for %s: %s", data_range, exc)
                raise
            except Exception as exc:
                # Retry common transient transport errors (timeouts, connection resets, etc.).
                if attempts < max_attempts:
                    wait = base_backoff * (2 ** attempts)
                    self._logger.warning(
                        "GoogleSheets transport error on %s; retrying in %ss (attempt %s): %s",
                        data_range,
                        wait,
                        attempts + 1,
                        exc,
                    )
                    time.sleep(wait)
                    attempts += 1
                    continue
                raise

    async def _apply(self, session: AsyncSession, rows: List[dict], is_sm: bool = False) -> None:
        lead_ids = set()
        lead_result = await session.execute(
            select(func.distinct(RawBotUser.tg_user_id)).where(RawBotUser.bot_key == "lead")
        )
        for row in lead_result.scalars().all():
            if row is not None:
                lead_ids.add(int(row))
        if lead_ids and is_sm:
            sorted_leads = sorted(lead_ids)
            chunk_size = 1000
            for i in range(0, len(sorted_leads), chunk_size):
                chunk = sorted_leads[i : i + chunk_size]
                await self._execute_with_retry(
                    session,
                    update(RawBotUser)
                    .where(RawBotUser.tg_user_id.in_(chunk))
                    .values(
                        interview_reached=False,
                        interview_passed=False,
                        offer_received=False,
                        contract_signed=False,
                        distance_grinding=False,
                        community_member=False,
                        interview_reached_status=None,
                        interview_passed_status=None,
                        offer_received_status=None,
                        contract_signed_status=None,
                        community_member_status=None,
                    )
                    .execution_options(synchronize_session=False),
                )
                await session.commit()
        processed = 0
        matched_predicates = 0
        updated_rows = 0
        for row in rows:
            processed += 1
            tg_user_id = (
                row.get("telegram_id")
                or row.get("tg_user_id")
                or row.get("tg_id")
                or row.get("user_id")
                or row.get("id")
            )
            if tg_user_id is None:
                tg_user_id = row.get("__col_1") or row.get("__col_2")
            username_raw = (
                row.get("tg_юзернейм")
                or row.get("tg_username")
                or row.get("username")
            )
            user_id = None
            if tg_user_id is not None:
                try:
                    user_id = int(str(tg_user_id).strip())
                except ValueError:
                    user_id = None

            if user_id is None:
                continue
            if lead_ids and user_id not in lead_ids:
                continue
            matched_predicates += 1
            predicates = [RawBotUser.tg_user_id == user_id]

            values = {}
            if is_sm:
                interview_reached = self._get_status(
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
                    true_values={"да"},
                    false_values=set(),
                )
                interview_reached_status = self._get_raw_value(
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
                if interview_reached is not None:
                    values["interview_reached"] = interview_reached
                if interview_reached_status is not None:
                    values["interview_reached_status"] = interview_reached_status
                    normalized_interview = self._normalize_cell(interview_reached_status)
                    if normalized_interview in {"наигрывают_дистанцию", "нагрывают_дистанцию"}:
                        values["distance_grinding"] = True

                interview_passed = self._get_status(
                    row,
                    [
                        "interview_passed",
                        "interview_ok",
                        "sobes_passed",
                        "собеседование_пройдено",
                        "собес_пройден",
                        "прошел_собеседование",
                    ],
                    true_values={"да"},
                    false_values=set(),
                )
                interview_passed_status = self._get_raw_value(
                    row,
                    [
                        "interview_passed",
                        "interview_ok",
                        "sobes_passed",
                        "собеседование_пройдено",
                        "собес_пройден",
                        "прошел_собеседование",
                    ],
                )
                if interview_passed is not None:
                    values["interview_passed"] = interview_passed
                if interview_passed_status is not None:
                    values["interview_passed_status"] = interview_passed_status

                offer_received = self._get_status(
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
                    true_values={"да"},
                    false_values=set(),
                )
                offer_received_status = self._get_raw_value(
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
                if offer_received is not None:
                    values["offer_received"] = offer_received
                if offer_received_status is not None:
                    values["offer_received_status"] = offer_received_status
                    normalized_offer = self._normalize_cell(offer_received_status)
                    if normalized_offer in {"наигрывают_дистанцию", "нагрывают_дистанцию"}:
                        values["distance_grinding"] = True

                contract_signed = self._get_status(
                    row,
                    [
                        "contract_signed",
                        "contract",
                        "контракт",
                        "contract_подписан",
                        "подписал_контракт",
                    ],
                    true_values={"да"},
                    false_values=set(),
                )
                contract_signed_status = self._get_raw_value(
                    row,
                    [
                        "contract_signed",
                        "contract",
                        "контракт",
                        "contract_подписан",
                        "подписал_контракт",
                    ],
                )
                if contract_signed is not None:
                    values["contract_signed"] = contract_signed
                if contract_signed_status is not None:
                    values["contract_signed_status"] = contract_signed_status

                saloon_member = self._get_status(
                    row,
                    [
                        "есть_в_салуне",
                        "saloon",
                        "saloon_member",
                    ],
                    true_values={"да"},
                    false_values=set(),
                )
                saloon_member_status = self._get_raw_value(
                    row,
                    [
                        "есть_в_салуне",
                        "saloon",
                        "saloon_member",
                    ],
                )
                if saloon_member is not None:
                    values["community_member"] = saloon_member
                if saloon_member_status is not None:
                    values["community_member_status"] = saloon_member_status

                # completed_course is sourced from PokerHub API only.
            else:
                # Intentionally do not write started_learning from Google Sheets.
                # "Started learning" is derived from PokerHub first-lesson timestamp (learn_start_date).
                pass

            if not values:
                continue

            stmt = (
                update(RawBotUser)
                .where(or_(*predicates))
                .values(**values)
                .execution_options(synchronize_session=False)
            )
            result = await self._execute_with_retry(session, stmt)
            try:
                updated_rows += int(result.rowcount or 0)
            except Exception:
                pass
            if processed % 200 == 0:
                self._logger.warning(
                    "GoogleSheets apply progress: processed=%s matched=%s updated=%s",
                    processed,
                    matched_predicates,
                    updated_rows,
                )
        self._logger.warning(
            "GoogleSheets apply done: processed=%s matched=%s updated=%s",
            processed,
            matched_predicates,
            updated_rows,
        )

    @staticmethod
    def _normalize_key(value: str) -> str:
        value = re.sub(r"\s+", "_", str(value).strip().lower())
        value = re.sub(r"[^\w]+", "_", value, flags=re.UNICODE)
        return re.sub(r"_+", "_", value).strip("_")

    @staticmethod
    def _normalize_username(value: Optional[str]) -> str:
        if not value:
            return ""
        value = str(value).strip()
        if value.startswith("@"):
            value = value[1:]
        return value.lower()

    @staticmethod
    def _to_bool(value: str) -> bool:
        return str(value).strip().lower() in ("1", "true", "yes", "y", "да", "ok")

    def _get_bool(self, row: dict, keys: List[str]) -> Optional[bool]:
        for key in keys:
            if key in row and str(row.get(key)).strip() != "":
                return self._to_bool(row.get(key))
        return None

    @staticmethod
    def _normalize_cell(value: str) -> str:
        value = str(value).strip().lower()
        value = re.sub(r"\s+", " ", value)
        value = re.sub(r"[^\w]+", "_", value, flags=re.UNICODE)
        return re.sub(r"_+", "_", value).strip("_")

    def _get_status(
        self,
        row: dict,
        keys: List[str],
        true_values: set[str],
        false_values: set[str],
    ) -> Optional[bool]:
        for key in keys:
            if key not in row:
                continue
            raw_value = row.get(key)
            if raw_value is None or str(raw_value).strip() == "":
                return None
            normalized = self._normalize_cell(raw_value)
            if normalized in true_values:
                return True
            if normalized in false_values:
                return False
            return False
        return None

    @staticmethod
    def _get_raw_value(row: dict, keys: List[str]) -> Optional[str]:
        for key in keys:
            if key not in row:
                continue
            raw_value = row.get(key)
            if raw_value is None or str(raw_value).strip() == "":
                return None
            return str(raw_value).strip()
        return None
