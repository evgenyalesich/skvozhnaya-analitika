from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.report_bot_scope import normalized_excluded_bot_keys


class RoistatWeeklyReportDataFunnelMixin:
    async def _load_weekly_cohort_funnel(
        self,
        session: AsyncSession,
        event_start: Optional[date],
        event_end: Optional[date],
        cohort_ids: Optional[set[int]],
        bots: Optional[List[str]] = None,
    ) -> List[WeeklyRow]:
        lead_conditions = [
            "created_at IS NOT NULL",
            "bot_key IS NOT NULL",
            "trim(bot_key) <> ''",
            "lower(trim(bot_key)) LIKE 'lead%'",
            "LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)",
        ]
        params: Dict[str, Any] = {"excluded_bot_keys": normalized_excluded_bot_keys()}
        if cohort_ids:
            lead_conditions.append("tg_user_id = ANY(:cohort_ids)")
            params["cohort_ids"] = list(cohort_ids)
        if bots:
            lead_conditions.append("bot_key = ANY(:filter_bots)")
            params["filter_bots"] = list(bots)
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
                  AND tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
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
                  AND tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
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
                  AND LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                GROUP BY tg_user_id
            ),
            user_flags AS (
                SELECT
                    ru.tg_user_id,
                    BOOL_OR(learn_start_date IS NOT NULL) AS started_learning
                FROM raw_bot_users ru
                WHERE ru.tg_user_id IN (SELECT tg_user_id FROM almanah_lead_cohort)
                  AND ru.tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                GROUP BY ru.tg_user_id
            ),
            platform_touch AS (
                SELECT
                    ru.tg_user_id,
                    MIN(ru.platform_registered_at)::date AS event_date
                FROM raw_bot_users ru
                WHERE ru.tg_user_id IN (SELECT tg_user_id FROM almanah_lead_cohort)
                  AND LOWER(TRIM(COALESCE(ru.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND ru.tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
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
                  AND LOWER(TRIM(COALESCE(ru.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND ru.tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                GROUP BY ru.tg_user_id
            ),
            started_touch AS (
                SELECT
                    ru.tg_user_id,
                    MIN(ru.learn_start_date)::date AS event_date
                FROM raw_bot_users ru
                WHERE ru.tg_user_id IN (SELECT tg_user_id FROM almanah_lead_cohort)
                  AND LOWER(TRIM(COALESCE(ru.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND ru.tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
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

