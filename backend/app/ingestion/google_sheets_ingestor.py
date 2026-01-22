import asyncio
import os
from typing import List

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config_loader import ConfigLoader
from app.models.analytics import RawBotUser


class GoogleSheetsIngestor:
    def __init__(self, loader: ConfigLoader):
        self.loader = loader

    async def ingest(self, session: AsyncSession) -> None:
        config = self.loader.data_sources().get("google_sheets", {})
        creds_path = os.environ.get(config.get("credentials_env", ""))
        if not creds_path:
            return
        data = await asyncio.to_thread(self._fetch_sheets, creds_path, config.get("sheets", []))
        await self._apply(session, data)

    def _fetch_sheets(self, creds_path: str, sheets: List[dict]) -> List[dict]:
        creds = Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        service = build("sheets", "v4", credentials=creds)
        rows = []
        for info in sheets:
            spreadsheet_id = os.environ.get(info.get("id_env", ""))
            data_range = info.get("range")
            if not spreadsheet_id or not data_range:
                continue
            response = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=data_range).execute()
            values = response.get("values", [])
            if not values:
                continue
            columns = values[0]
            for row in values[1:]:
                row_dict = {columns[idx]: row[idx] for idx in range(min(len(columns), len(row)))}
                rows.append(row_dict)
        return rows

    async def _apply(self, session: AsyncSession, rows: List[dict]) -> None:
        for row in rows:
            tg_user_id = row.get("tg_user_id")
            if not tg_user_id:
                continue
            try:
                user_id = int(tg_user_id)
            except ValueError:
                continue
            stmt = (
                update(RawBotUser)
                .where(RawBotUser.tg_user_id == user_id)
                .values(
                    interview_reached=self._to_bool(row.get("interview_reached")),
                    interview_passed=self._to_bool(row.get("interview_passed")),
                    offer_received=self._to_bool(row.get("offer_received")),
                    contract_signed=self._to_bool(row.get("contract_signed")),
                )
            )
            await session.execute(stmt)

    @staticmethod
    def _to_bool(value: str) -> bool:
        return str(value).lower() in ("1", "true", "yes")
