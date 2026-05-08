from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import List, Optional

import httplib2
import google_auth_httplib2
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)


class GoogleSheetsIngestorCoreMixin:
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
        return ["БАЗА!A:ZZ"]

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
