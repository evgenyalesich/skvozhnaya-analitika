from __future__ import annotations

from datetime import date
from typing import Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ingestion.google_sheets_ingestor import GoogleSheetsIngestor


class RoistatWeeklyReportDataCohortMixin:
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
                  AND LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
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
            "start": first_touch_start,
            "end": first_touch_end,
            "excluded_bot_keys": normalized_excluded_bot_keys(),
        }
        result = await session.execute(query, params)
        return {int(row.tg_user_id) for row in result.fetchall() if row.tg_user_id is not None}

    async def _load_last_touch_cohort(
        self,
        session: AsyncSession,
        last_touch_start: Optional[date],
        last_touch_end: Optional[date],
    ) -> set[int]:
        # Логика совпадает с attribution_service: last_touch = последний бот ДО
        # регистрации на платформе (platform_registered_at). Пользователи без
        # platform_registered_at исключаются — attribution для них не определена.
        query = text(
            """
            WITH platform_users AS (
                SELECT
                    tg_user_id,
                    MIN(platform_registered_at) AS platform_registered_at
                FROM raw_bot_users
                WHERE ph_user_id IS NOT NULL
                  AND platform_registered_at IS NOT NULL
                GROUP BY tg_user_id
            ),
            last_touch AS (
                SELECT
                    ru.tg_user_id,
                    MAX(ru.created_at)::date AS last_touch_date
                FROM raw_bot_users ru
                JOIN platform_users pu ON pu.tg_user_id = ru.tg_user_id
                WHERE ru.created_at IS NOT NULL
                  AND ru.bot_key IS NOT NULL
                  AND trim(ru.bot_key) <> ''
                  AND LOWER(TRIM(COALESCE(ru.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND ru.tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                  AND ru.created_at <= pu.platform_registered_at
                GROUP BY ru.tg_user_id
            )
            SELECT tg_user_id
            FROM last_touch
            WHERE
                (CAST(:start AS date) IS NULL OR last_touch_date >= CAST(:start AS date))
                AND (CAST(:end AS date) IS NULL OR last_touch_date <= CAST(:end AS date))
            """
        )
        params = {
            "start": last_touch_start,
            "end": last_touch_end,
            "excluded_bot_keys": normalized_excluded_bot_keys(),
        }
        result = await session.execute(query, params)
        return {int(row.tg_user_id) for row in result.fetchall() if row.tg_user_id is not None}

