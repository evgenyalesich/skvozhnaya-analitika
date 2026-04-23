from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

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
    # Extended metrics
    entered_all: int = 0
    interview_reached: int = 0
    offer_received: int = 0
    completed_mtt: int = 0
    completed_spin: int = 0
    completed_cash: int = 0
    contract_mtt: int = 0
    contract_spin: int = 0
    contract_cash: int = 0


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
            channel_id=os.getenv("TELEGRAM_CHANNEL_ID"),
            event_start=event_start,
            event_end=event_end,
            cohort_ids=cohort_ids,
        )
        for week_start, value in channel_counts.items():
            ensure_row(week_start).channel_subscribed = value

        saloon_counts = await self._load_subscription_counts(
            session,
            channel_id=os.getenv("TELEGRAM_COMMUNITY_ID"),
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
        }
        result = await session.execute(query, params)
        return {int(row.tg_user_id) for row in result.fetchall() if row.tg_user_id is not None}

    async def _load_last_touch_cohort(
        self,
        session: AsyncSession,
        last_touch_start: Optional[date],
        last_touch_end: Optional[date],
    ) -> set[int]:
        query = text(
            """
            WITH last_touch AS (
                SELECT
                    tg_user_id,
                    MAX(created_at)::date AS last_touch_date
                FROM raw_bot_users
                WHERE created_at IS NOT NULL
                  AND bot_key IS NOT NULL
                  AND trim(bot_key) <> ''
                GROUP BY tg_user_id
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
        }
        result = await session.execute(query, params)
        return {int(row.tg_user_id) for row in result.fetchall() if row.tg_user_id is not None}

    async def _load_weekly_cohort_funnel(
        self,
        session: AsyncSession,
        event_start: Optional[date],
        event_end: Optional[date],
        cohort_ids: Optional[set[int]],
    ) -> List[WeeklyRow]:
        lead_conditions = [
            "created_at IS NOT NULL",
            "bot_key IS NOT NULL",
            "trim(bot_key) <> ''",
            "lower(trim(bot_key)) LIKE 'lead%'",
        ]
        params: Dict[str, Any] = {}
        if cohort_ids:
            lead_conditions.append("tg_user_id = ANY(:cohort_ids)")
            params["cohort_ids"] = list(cohort_ids)
        lead_where = " AND ".join(lead_conditions)
        params["start"] = event_start
        params["end"] = event_end
        query = text(
            f"""
            WITH almanah_lead_cohort AS (
                SELECT
                    tg_user_id,
                    MIN(created_at)::date AS lead_date
                FROM raw_bot_users
                WHERE {lead_where}
                  AND tg_user_id > 0
                  AND NOT (
                    LOWER(TRIM(COALESCE(bot_key, ''))) = 'lead'
                    AND ph_user_id IS NOT NULL
                    AND ABS(tg_user_id) = ph_user_id
                  )
                  AND (CAST(:start AS date) IS NULL OR created_at::date >= CAST(:start AS date))
                  AND (CAST(:end AS date) IS NULL OR created_at::date <= CAST(:end AS date))
                GROUP BY tg_user_id
            ),
            direct_lead_cohort AS (
                SELECT
                    ph_user_id,
                    MIN(created_at)::date AS lead_date
                FROM raw_bot_users
                WHERE {lead_where}
                  AND ph_user_id IS NOT NULL
                  AND (
                    tg_user_id < 0
                    OR (
                        LOWER(TRIM(COALESCE(bot_key, ''))) = 'lead'
                        AND ABS(tg_user_id) = ph_user_id
                    )
                  )
                  AND (CAST(:start AS date) IS NULL OR created_at::date >= CAST(:start AS date))
                  AND (CAST(:end AS date) IS NULL OR created_at::date <= CAST(:end AS date))
                GROUP BY ph_user_id
            ),
            first_seen_system AS (
                SELECT
                    tg_user_id,
                    MIN(created_at)::date AS first_seen_at_system
                FROM raw_bot_users
                WHERE tg_user_id IN (SELECT tg_user_id FROM almanah_lead_cohort)
                GROUP BY tg_user_id
            ),
            user_flags AS (
                SELECT
                    ru.tg_user_id,
                    BOOL_OR(learn_start_date IS NOT NULL) AS started_learning
                FROM raw_bot_users ru
                WHERE ru.tg_user_id IN (SELECT tg_user_id FROM almanah_lead_cohort)
                GROUP BY ru.tg_user_id
            ),
            platform_touch AS (
                SELECT
                    ru.tg_user_id,
                    MIN(ru.platform_registered_at)::date AS event_date
                FROM raw_bot_users ru
                WHERE ru.tg_user_id IN (SELECT tg_user_id FROM almanah_lead_cohort)
                  AND ru.registered_platform IS TRUE
                  AND ru.platform_registered_at IS NOT NULL
                GROUP BY ru.tg_user_id
            ),
            course_touch AS (
                SELECT
                    ru.tg_user_id,
                    MIN(
                        COALESCE(
                            ru.learn_start_date::date,
                            ru.platform_registered_at::date
                        )
                    ) FILTER (
                        WHERE TRIM(COALESCE(ru.start_course, '')) <> ''
                    ) AS event_date,
                    BOOL_OR(LOWER(TRIM(COALESCE(ru.start_course, ''))) LIKE 'base%') AS base,
                    BOOL_OR(LOWER(TRIM(COALESCE(ru.start_course, ''))) LIKE 'mtt%') AS mtt,
                    BOOL_OR(LOWER(TRIM(COALESCE(ru.start_course, ''))) LIKE 'spin%') AS spin,
                    BOOL_OR(LOWER(TRIM(COALESCE(ru.start_course, ''))) LIKE 'cash%') AS cash
                FROM raw_bot_users ru
                WHERE ru.tg_user_id IN (SELECT tg_user_id FROM almanah_lead_cohort)
                GROUP BY ru.tg_user_id
            ),
            started_touch AS (
                SELECT
                    ru.tg_user_id,
                    MIN(ru.learn_start_date)::date AS event_date
                FROM raw_bot_users ru
                WHERE ru.tg_user_id IN (SELECT tg_user_id FROM almanah_lead_cohort)
                  AND ru.learn_start_date IS NOT NULL
                GROUP BY ru.tg_user_id
            ),
            not_started_touch AS (
                SELECT
                    pt.tg_user_id,
                    pt.event_date
                FROM platform_touch pt
                JOIN user_flags uf ON uf.tg_user_id = pt.tg_user_id
                WHERE COALESCE(uf.started_learning, FALSE) IS FALSE
            ),
            weekly AS (
                SELECT
                    DATE_TRUNC('week', lc.lead_date)::date AS week_start,
                    1::bigint AS starts,
                    0::bigint AS direct_source_cnt,
                    CASE WHEN fss.first_seen_at_system = lc.lead_date THEN 1::bigint ELSE 0::bigint END AS new_in_system,
                    CASE WHEN fss.first_seen_at_system < lc.lead_date THEN 1::bigint ELSE 0::bigint END AS old_in_system,
                    0::bigint AS platform,
                    0::bigint AS learning,
                    0::bigint AS started_learning,
                    0::bigint AS mtt,
                    0::bigint AS spin,
                    0::bigint AS cash,
                    0::bigint AS base,
                    0::bigint AS not_started
                FROM almanah_lead_cohort lc
                JOIN first_seen_system fss ON fss.tg_user_id = lc.tg_user_id

                UNION ALL

                SELECT
                    DATE_TRUNC('week', dlc.lead_date)::date AS week_start,
                    0::bigint AS starts,
                    1::bigint AS direct_source_cnt,
                    0::bigint AS new_in_system,
                    0::bigint AS old_in_system,
                    0::bigint AS platform,
                    0::bigint AS learning,
                    0::bigint AS started_learning,
                    0::bigint AS mtt,
                    0::bigint AS spin,
                    0::bigint AS cash,
                    0::bigint AS base,
                    0::bigint AS not_started
                FROM direct_lead_cohort dlc

                UNION ALL

                SELECT
                    DATE_TRUNC('week', pt.event_date)::date AS week_start,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    1::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint
                FROM platform_touch pt
                WHERE pt.event_date IS NOT NULL

                UNION ALL

                SELECT
                    DATE_TRUNC('week', ct.event_date)::date AS week_start,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    1::bigint,
                    0::bigint,
                    CASE WHEN ct.base THEN 1::bigint ELSE 0::bigint END,
                    CASE WHEN ct.mtt THEN 1::bigint ELSE 0::bigint END,
                    CASE WHEN ct.spin THEN 1::bigint ELSE 0::bigint END,
                    CASE WHEN ct.cash THEN 1::bigint ELSE 0::bigint END,
                    0::bigint
                FROM course_touch ct
                WHERE ct.event_date IS NOT NULL

                UNION ALL

                SELECT
                    DATE_TRUNC('week', st.event_date)::date AS week_start,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    1::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint
                FROM started_touch st
                WHERE st.event_date IS NOT NULL

                UNION ALL

                SELECT
                    DATE_TRUNC('week', nt.event_date)::date AS week_start,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    0::bigint,
                    1::bigint
                FROM not_started_touch nt
                WHERE nt.event_date IS NOT NULL
            )
            SELECT
                w.week_start,
                SUM(w.starts) AS starts,
                SUM(w.direct_source_cnt) AS direct_source_cnt,
                SUM(w.new_in_system) AS new_in_system,
                SUM(w.old_in_system) AS old_in_system,
                SUM(w.platform) AS platform,
                SUM(w.learning) AS learning,
                SUM(w.started_learning) AS started_learning,
                SUM(w.base) AS base,
                SUM(w.mtt) AS mtt,
                SUM(w.spin) AS spin,
                SUM(w.cash) AS cash,
                SUM(w.not_started) AS not_started
            FROM weekly w
            WHERE
                (CAST(:start AS date) IS NULL OR w.week_start >= DATE_TRUNC('week', CAST(:start AS date))::date)
                AND (CAST(:end AS date) IS NULL OR w.week_start <= DATE_TRUNC('week', CAST(:end AS date))::date)
            GROUP BY week_start
            ORDER BY week_start
            """
        )
        result = await session.execute(query, params)
        rows: List[WeeklyRow] = []
        for row in result.fetchall():
            if not row.week_start:
                continue
            rows.append(
                WeeklyRow(
                    week_start=row.week_start,
                    almanah_starts=int(row.starts or 0),
                    direct_source_cnt=int(row.direct_source_cnt or 0),
                    new_in_system=int(row.new_in_system or 0),
                    old_in_system=int(row.old_in_system or 0),
                    platform=int(row.platform or 0),
                    learning=int(row.learning or 0),
                    started_learning=int(row.started_learning or 0),
                    base=int(row.base or 0),
                    mtt=int(row.mtt or 0),
                    spin=int(row.spin or 0),
                    cash=int(row.cash or 0),
                    not_started=int(row.not_started or 0),
                    channel_subscribed=0,
                    saloon=0,
                    completed_course=0,
                    distance_grinding=0,
                    contract_signed=0,
                    budget=0.0,
                )
            )
        return rows

    async def _load_total_bot_starts(
        self,
        session: AsyncSession,
        event_start: Optional[date],
        event_end: Optional[date],
        cohort_ids: Optional[set[int]],
    ) -> Dict[date, int]:
        conditions = ["created_at IS NOT NULL", "bot_key IS NOT NULL", "trim(bot_key) <> ''"]
        params: Dict[str, Any] = {}
        if event_start:
            conditions.append("created_at::date >= :event_start")
            params["event_start"] = event_start
        if event_end:
            conditions.append("created_at::date <= :event_end")
            params["event_end"] = event_end
        if cohort_ids:
            conditions.append("tg_user_id = ANY(:cohort_ids)")
            params["cohort_ids"] = list(cohort_ids)
        where_clause = " AND ".join(conditions)
        query = text(
            f"""
            SELECT
                DATE_TRUNC('week', created_at)::date AS week_start,
                COUNT(*) AS total_starts
            FROM raw_bot_users
            WHERE {where_clause}
            GROUP BY week_start
            """
        )
        result = await session.execute(query, params)
        return {row.week_start: int(row.total_starts or 0) for row in result.fetchall() if row.week_start}

    async def _load_budgets(self, session: AsyncSession) -> Dict[date, float]:
        query = text(
            """
            WITH budgets AS (
                SELECT
                    DATE_TRUNC('week', week_start)::date AS week_start,
                    SUM(amount) AS budget
                FROM budget_weekly
                GROUP BY DATE_TRUNC('week', week_start)::date
            )
            SELECT
                week_start,
                COALESCE(budget, 0) AS budget
            FROM budgets
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
        # Use CTE to aggregate all flags per user across all their bot rows,
        # then join back to the weekly cohort (keyed by learn_start_date week).
        query = text(
            f"""
            WITH learning_cohort AS (
                SELECT DISTINCT
                    tg_user_id,
                    DATE_TRUNC('week', learn_start_date)::date AS week_start
                FROM raw_bot_users
                WHERE {where_clause}
            ),
            user_flags AS (
                SELECT
                    tg_user_id,
                    BOOL_OR(completed_course IS TRUE AND completed_course_at IS NOT NULL) AS did_complete,
                    BOOL_OR(distance_grinding IS TRUE) AS did_distance,
                    BOOL_OR(contract_signed IS TRUE) AS did_contract,
                    BOOL_OR(interview_reached IS TRUE) AS did_interview,
                    BOOL_OR(offer_received IS TRUE) AS did_offer,
                    BOOL_OR(LOWER(TRIM(COALESCE(start_course, ''))) LIKE 'mtt%') AS is_mtt,
                    BOOL_OR(LOWER(TRIM(COALESCE(start_course, ''))) LIKE 'spin%') AS is_spin,
                    BOOL_OR(LOWER(TRIM(COALESCE(start_course, ''))) LIKE 'cash%') AS is_cash
                FROM raw_bot_users
                WHERE tg_user_id IN (SELECT tg_user_id FROM learning_cohort)
                GROUP BY tg_user_id
            )
            SELECT
                lc.week_start,
                COUNT(DISTINCT CASE WHEN uf.did_complete THEN lc.tg_user_id END) AS completed_course,
                COUNT(DISTINCT CASE WHEN uf.did_distance THEN lc.tg_user_id END) AS distance_grinding,
                COUNT(DISTINCT CASE WHEN uf.did_contract THEN lc.tg_user_id END) AS contract_signed,
                COUNT(DISTINCT CASE WHEN uf.did_interview THEN lc.tg_user_id END) AS interview_reached,
                COUNT(DISTINCT CASE WHEN uf.did_offer THEN lc.tg_user_id END) AS offer_received,
                COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_mtt THEN lc.tg_user_id END) AS completed_mtt,
                COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_spin THEN lc.tg_user_id END) AS completed_spin,
                COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_cash THEN lc.tg_user_id END) AS completed_cash,
                COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_mtt THEN lc.tg_user_id END) AS contract_mtt,
                COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_spin THEN lc.tg_user_id END) AS contract_spin,
                COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_cash THEN lc.tg_user_id END) AS contract_cash
            FROM learning_cohort lc
            JOIN user_flags uf ON uf.tg_user_id = lc.tg_user_id
            GROUP BY lc.week_start
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
                "interview_reached": int(row.interview_reached or 0),
                "offer_received": int(row.offer_received or 0),
                "completed_mtt": int(row.completed_mtt or 0),
                "completed_spin": int(row.completed_spin or 0),
                "completed_cash": int(row.completed_cash or 0),
                "contract_mtt": int(row.contract_mtt or 0),
                "contract_spin": int(row.contract_spin or 0),
                "contract_cash": int(row.contract_cash or 0),
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
