from __future__ import annotations

from datetime import date
from typing import Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.report_bot_scope import normalized_excluded_bot_keys


class RoistatWeeklyReportDataMetricsMixin:
    async def _load_total_bot_starts(
        self,
        session: AsyncSession,
        event_start: Optional[date],
        event_end: Optional[date],
        cohort_ids: Optional[set[int]],
    ) -> Dict[date, int]:
        conditions = ["created_at IS NOT NULL", "bot_key IS NOT NULL", "trim(bot_key) <> ''"]
        conditions.append("LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)")
        conditions.append("tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)")
        params: Dict[str, Any] = {"excluded_bot_keys": normalized_excluded_bot_keys()}
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
            "chat_id = :channel_id",
            "joined_at IS NOT NULL",
        ]
        params: Dict[str, Any] = {"channel_id": str(channel_id)}
        if event_start:
            conditions.append("joined_at::date >= :event_start")
            params["event_start"] = event_start
        if event_end:
            conditions.append("joined_at::date <= :event_end")
            params["event_end"] = event_end
        if cohort_ids:
            conditions.append("tg_user_id = ANY(:cohort_ids)")
            params["cohort_ids"] = list(cohort_ids)
        where_clause = " AND ".join(conditions)
        query = text(
            f"""
            SELECT
                DATE_TRUNC('week', joined_at)::date AS week_start,
                COUNT(DISTINCT tg_user_id) AS subscribed
            FROM telegram_chat_memberships
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
        conditions.append("LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)")
        conditions.append("tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)")
        params: Dict[str, Any] = {
            "excluded_bot_keys": normalized_excluded_bot_keys(),
            "event_start": None,
            "event_end": None,
            "cohort_ids": None,
        }
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
            distance_cohort AS (
                SELECT DISTINCT
                    tg_user_id,
                    DATE_TRUNC(
                        'week',
                        COALESCE(learn_start_date, platform_registered_at, created_at)
                    )::date AS week_start
                FROM raw_bot_users
                WHERE distance_grinding IS TRUE
                  AND COALESCE(learn_start_date, platform_registered_at, created_at) IS NOT NULL
                  AND LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                  AND (
                    CAST(:event_start AS date) IS NULL
                    OR COALESCE(learn_start_date, platform_registered_at, created_at)::date >= :event_start
                  )
                  AND (
                    CAST(:event_end AS date) IS NULL
                    OR COALESCE(learn_start_date, platform_registered_at, created_at)::date <= :event_end
                  )
                  AND (
                    CAST(:cohort_ids AS bigint[]) IS NULL
                    OR tg_user_id = ANY(:cohort_ids)
                  )
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
                  AND LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                GROUP BY tg_user_id
            )
            SELECT
                lc.week_start,
                COUNT(DISTINCT CASE WHEN uf.did_complete THEN lc.tg_user_id END) AS completed_course,
                0::bigint AS distance_grinding,
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

            UNION ALL

            SELECT
                dc.week_start,
                0::bigint AS completed_course,
                COUNT(DISTINCT dc.tg_user_id) AS distance_grinding,
                0::bigint AS contract_signed,
                0::bigint AS interview_reached,
                0::bigint AS offer_received,
                0::bigint AS completed_mtt,
                0::bigint AS completed_spin,
                0::bigint AS completed_cash,
                0::bigint AS contract_mtt,
                0::bigint AS contract_spin,
                0::bigint AS contract_cash
            FROM distance_cohort dc
            GROUP BY dc.week_start
            """
        )
        result = await session.execute(query, params)
        out: Dict[date, Dict[str, int]] = {}
        for row in result.fetchall():
            if not row.week_start:
                continue
            current = out.setdefault(
                row.week_start,
                {
                    "completed_course": 0,
                    "distance_grinding": 0,
                    "contract_signed": 0,
                    "interview_reached": 0,
                    "offer_received": 0,
                    "completed_mtt": 0,
                    "completed_spin": 0,
                    "completed_cash": 0,
                    "contract_mtt": 0,
                    "contract_spin": 0,
                    "contract_cash": 0,
                },
            )
            current["completed_course"] += int(row.completed_course or 0)
            current["distance_grinding"] += int(row.distance_grinding or 0)
            current["contract_signed"] += int(row.contract_signed or 0)
            current["interview_reached"] += int(row.interview_reached or 0)
            current["offer_received"] += int(row.offer_received or 0)
            current["completed_mtt"] += int(row.completed_mtt or 0)
            current["completed_spin"] += int(row.completed_spin or 0)
            current["completed_cash"] += int(row.completed_cash or 0)
            current["contract_mtt"] += int(row.contract_mtt or 0)
            current["contract_spin"] += int(row.contract_spin or 0)
            current["contract_cash"] += int(row.contract_cash or 0)
        return out

