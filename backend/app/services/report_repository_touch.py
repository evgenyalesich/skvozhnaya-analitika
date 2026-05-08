from datetime import date as dt_date
from typing import Any, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.report_filters import ReportFilters
from app.services.report_bot_scope import normalized_excluded_bot_keys


class ReportRepositoryTouchMixin:
    """Touch attribution endpoints for summary tables and weekly diagrams."""

    @staticmethod
    def _touch_value_expr(column_name: str) -> str:
        return f"""
            COALESCE(
                NULLIF(
                    CASE
                        WHEN LOWER(BTRIM(COALESCE({column_name}, ''))) IN ('', '-', '—', 'none', 'null', '(none)', 'undefined', 'n/a', 'na', 'нет метки')
                        THEN ''
                        ELSE BTRIM(COALESCE({column_name}, ''))
                    END,
                ''),
                ''
            )
        """

    def _touch_attributed_cte_sql(self, mode: str) -> str:
        bot_expr = self._touch_value_expr("r.bot_key")
        company_expr = self._touch_value_expr("r.advertising_company")
        campaign_expr = f"""
            COALESCE(
                NULLIF({self._touch_value_expr("r.platform_utm_campaign")}, ''),
                NULLIF({self._touch_value_expr("r.utm_campaign")}, ''),
                'нет метки'
            )
        """
        utm_source_expr = f"""
            COALESCE(
                NULLIF({self._touch_value_expr("r.platform_utm_source")}, ''),
                NULLIF({self._touch_value_expr("r.utm_source")}, ''),
                ''
            )
        """
        utm_campaign_expr = f"""
            COALESCE(
                NULLIF({self._touch_value_expr("r.platform_utm_campaign")}, ''),
                NULLIF({self._touch_value_expr("r.utm_campaign")}, ''),
                ''
            )
        """
        utm_medium_expr = f"""
            COALESCE(
                NULLIF({self._touch_value_expr("r.platform_utm_medium")}, ''),
                NULLIF({self._touch_value_expr("r.utm_medium")}, ''),
                ''
            )
        """
        utm_content_expr = f"""
            COALESCE(
                NULLIF({self._touch_value_expr("r.platform_utm_content")}, ''),
                NULLIF({self._touch_value_expr("r.utm_content")}, ''),
                ''
            )
        """
        utm_term_expr = f"""
            COALESCE(
                NULLIF({self._touch_value_expr("r.platform_utm_term")}, ''),
                NULLIF({self._touch_value_expr("r.utm_term")}, ''),
                ''
            )
        """

        common_non_lead_rows = f"""
            non_lead_rows AS (
                SELECT
                    r.tg_user_id,
                    COALESCE(NULLIF({bot_expr}, ''), 'нет метки') AS bot_key,
                    COALESCE(NULLIF({company_expr}, ''), 'Без категории') AS company,
                    {campaign_expr} AS campaign,
                    {utm_source_expr} AS utm_source,
                    {utm_campaign_expr} AS utm_campaign,
                    {utm_medium_expr} AS utm_medium,
                    {utm_content_expr} AS utm_content,
                    {utm_term_expr} AS utm_term,
                    r.created_at
                FROM raw_bot_users r
                WHERE r.tg_user_id > 0
                  AND r.created_at IS NOT NULL
                  AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND LOWER(TRIM(COALESCE(r.bot_key, ''))) NOT LIKE 'lead%'
            )
        """

        if mode == "first":
            return f"""
                WITH
                {common_non_lead_rows},
                attributed AS (
                    SELECT DISTINCT ON (nr.tg_user_id)
                        nr.tg_user_id,
                        nr.bot_key,
                        nr.company,
                        nr.campaign,
                        nr.utm_source,
                        nr.utm_campaign,
                        nr.utm_medium,
                        nr.utm_content,
                        nr.utm_term,
                        nr.created_at AS touch_at,
                        nr.created_at AS filter_at
                    FROM non_lead_rows nr
                    ORDER BY nr.tg_user_id, nr.created_at ASC, nr.bot_key ASC
                )
            """

        return f"""
            WITH
            {common_non_lead_rows},
            platform_users AS (
                SELECT
                    r.tg_user_id,
                    MIN(r.platform_registered_at) AS conversion_at
                FROM raw_bot_users r
                WHERE r.tg_user_id > 0
                  AND r.ph_user_id IS NOT NULL
                  AND r.platform_registered_at IS NOT NULL
                GROUP BY r.tg_user_id
            ),
            ranked AS (
                SELECT
                    nr.tg_user_id,
                    nr.bot_key,
                    nr.company,
                    nr.campaign,
                    nr.utm_source,
                    nr.utm_campaign,
                    nr.utm_medium,
                    nr.utm_content,
                    nr.utm_term,
                    nr.created_at AS touch_at,
                    pu.conversion_at AS filter_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY nr.tg_user_id
                        ORDER BY nr.created_at DESC, nr.bot_key ASC
                    ) AS rn
                FROM non_lead_rows nr
                JOIN platform_users pu
                  ON pu.tg_user_id = nr.tg_user_id
                WHERE nr.created_at <= pu.conversion_at
            ),
            attributed AS (
                SELECT
                    tg_user_id,
                    bot_key,
                    company,
                    campaign,
                    utm_source,
                    utm_campaign,
                    utm_medium,
                    utm_content,
                    utm_term,
                    touch_at,
                    filter_at
                FROM ranked
                WHERE rn = 1
            )
        """

    async def touch_summary(
        self,
        session: AsyncSession,
        start_date: Optional[str],
        end_date: Optional[str],
        mode: str,
    ) -> List[dict]:
        if mode not in {"first", "last"}:
            raise ValueError("mode must be first or last")

        params: dict[str, Any] = {
            "excluded_bot_keys": normalized_excluded_bot_keys(),
            "start_date": start_date,
            "end_date": end_date,
        }
        query = text(
            f"""
            {self._touch_attributed_cte_sql(mode)}
            SELECT
                a.bot_key AS bot,
                COALESCE(NULLIF(BTRIM(a.campaign), ''), 'нет метки') AS campaign,
                COUNT(DISTINCT a.tg_user_id) AS users
            FROM attributed a
            WHERE a.tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
              AND (CAST(:start_date AS date) IS NULL OR (a.filter_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start_date AS date))
              AND (CAST(:end_date AS date) IS NULL OR (a.filter_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end_date AS date))
            GROUP BY 1, 2
            ORDER BY users DESC, bot, campaign
            """
        )
        result = await session.execute(query, params)
        return [
            {
                "bot": row.bot,
                "campaign": row.campaign,
                "users": int(row.users or 0),
            }
            for row in result.fetchall()
        ]

    async def touch_funnel_summary(
        self,
        session: AsyncSession,
        filters: ReportFilters,
        mode: str = "last",
    ) -> List[dict[str, int]]:
        if mode not in {"first", "last"}:
            raise ValueError("mode must be first or last")

        params: dict[str, Any] = {
            "excluded_bot_keys": normalized_excluded_bot_keys(),
            "start_date": filters.start_date,
            "end_date": filters.end_date,
        }
        attr_filter_sql = self._build_touch_attr_filters_sql("a", filters, params)
        query = text(
            f"""
            {self._touch_attributed_cte_sql(mode)},
            user_flags AS (
                SELECT
                    ru.tg_user_id,
                    BOOL_OR(LOWER(TRIM(COALESCE(ru.bot_key, ''))) LIKE 'lead%') AS did_lead,
                    BOOL_OR(ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL) AS raw_platform,
                    BOOL_OR(ru.started_learning IS TRUE OR ru.learn_start_date IS NOT NULL) AS raw_learning,
                    BOOL_OR(ru.completed_course IS TRUE AND ru.completed_course_at IS NOT NULL) AS raw_course,
                    BOOL_OR(ru.interview_reached IS TRUE) AS raw_interview,
                    BOOL_OR(ru.interview_passed IS TRUE) AS raw_passed,
                    BOOL_OR(ru.offer_received IS TRUE) AS raw_offer,
                    BOOL_OR(ru.distance_grinding IS TRUE) AS raw_distance,
                    BOOL_OR(ru.contract_signed IS TRUE) AS raw_contract
                FROM raw_bot_users ru
                WHERE ru.tg_user_id > 0
                GROUP BY ru.tg_user_id
            ),
            normalized_flags AS (
                SELECT
                    uf.tg_user_id,
                    uf.did_lead,
                    uf.raw_platform AS did_platform,
                    (uf.raw_platform AND uf.raw_learning) AS did_learning,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course) AS did_course,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course AND uf.raw_interview) AS did_interview,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course AND uf.raw_interview AND uf.raw_passed) AS did_passed,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course AND uf.raw_interview AND uf.raw_passed AND uf.raw_offer) AS did_offer,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course AND uf.raw_interview AND uf.raw_passed AND uf.raw_offer AND uf.raw_distance) AS did_distance,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course AND uf.raw_interview AND uf.raw_passed AND uf.raw_offer AND uf.raw_contract) AS did_contract
                FROM user_flags uf
            )
            SELECT
                a.bot_key AS bot,
                COUNT(DISTINCT a.tg_user_id) AS entered,
                COUNT(DISTINCT CASE WHEN uf.did_lead THEN a.tg_user_id END) AS lead,
                COUNT(DISTINCT CASE WHEN uf.did_platform THEN a.tg_user_id END) AS platform,
                COUNT(DISTINCT CASE WHEN uf.did_learning THEN a.tg_user_id END) AS learning,
                COUNT(DISTINCT CASE WHEN uf.did_course THEN a.tg_user_id END) AS course,
                COUNT(DISTINCT CASE WHEN uf.did_interview THEN a.tg_user_id END) AS interview,
                COUNT(DISTINCT CASE WHEN uf.did_passed THEN a.tg_user_id END) AS passed,
                COUNT(DISTINCT CASE WHEN uf.did_offer THEN a.tg_user_id END) AS offer,
                COUNT(DISTINCT CASE WHEN uf.did_distance THEN a.tg_user_id END) AS distance_grinding,
                COUNT(DISTINCT CASE WHEN uf.did_contract THEN a.tg_user_id END) AS contract
            FROM attributed a
            JOIN normalized_flags uf ON uf.tg_user_id = a.tg_user_id
            WHERE a.tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
              AND (CAST(:start_date AS date) IS NULL OR (a.filter_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start_date AS date))
              AND (CAST(:end_date AS date) IS NULL OR (a.filter_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end_date AS date))
              {attr_filter_sql}
            GROUP BY 1
            ORDER BY entered DESC, bot
            """
        )
        result = await session.execute(query, params)
        return [
            {
                "bot": row.bot,
                "entered": int(row.entered or 0),
                "lead": int(row.lead or 0),
                "platform": int(row.platform or 0),
                "learning": int(row.learning or 0),
                "course": int(row.course or 0),
                "interview": int(row.interview or 0),
                "passed": int(row.passed or 0),
                "offer": int(row.offer or 0),
                "distance_grinding": int(row.distance_grinding or 0),
                "contract": int(row.contract or 0),
            }
            for row in result.fetchall()
        ]

    async def touch_weekly(
        self,
        session: AsyncSession,
        group_key: str,
        mode: str = "last",
        start_date: Optional[str | dt_date] = None,
        end_date: Optional[str | dt_date] = None,
    ) -> Tuple[List[str], dict[str, List[dict]]]:
        if mode not in {"first", "last"}:
            raise ValueError("mode must be first or last")
        if group_key.strip().lower() in normalized_excluded_bot_keys():
            return [], {}

        params: dict[str, Any] = {
            "excluded_bot_keys": normalized_excluded_bot_keys(),
            "group_key": group_key,
            "start_date": self._coerce_date(start_date),
            "end_date": self._coerce_date(end_date),
        }
        query = text(
            f"""
            {self._touch_attributed_cte_sql(mode)},
            user_flags AS (
                SELECT
                    ru.tg_user_id,
                    BOOL_OR(LOWER(TRIM(COALESCE(ru.bot_key, ''))) LIKE 'lead%') AS did_lead,
                    BOOL_OR(ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL) AS raw_platform,
                    BOOL_OR(ru.started_learning IS TRUE OR ru.learn_start_date IS NOT NULL) AS raw_learning,
                    BOOL_OR(ru.completed_course IS TRUE AND ru.completed_course_at IS NOT NULL) AS raw_course,
                    BOOL_OR(ru.interview_reached IS TRUE) AS raw_interview,
                    BOOL_OR(ru.interview_passed IS TRUE) AS raw_passed,
                    BOOL_OR(ru.offer_received IS TRUE) AS raw_offer,
                    BOOL_OR(ru.distance_grinding IS TRUE) AS raw_distance,
                    BOOL_OR(ru.contract_signed IS TRUE) AS raw_contract
                FROM raw_bot_users ru
                WHERE ru.tg_user_id > 0
                GROUP BY ru.tg_user_id
            ),
            normalized_flags AS (
                SELECT
                    uf.tg_user_id,
                    uf.did_lead,
                    uf.raw_platform AS did_platform,
                    (uf.raw_platform AND uf.raw_learning) AS did_learning,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course) AS did_course,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course AND uf.raw_interview) AS did_interview,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course AND uf.raw_interview AND uf.raw_passed) AS did_passed,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course AND uf.raw_interview AND uf.raw_passed AND uf.raw_offer) AS did_offer,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course AND uf.raw_interview AND uf.raw_passed AND uf.raw_offer AND uf.raw_distance) AS did_distance,
                    (uf.raw_platform AND uf.raw_learning AND uf.raw_course AND uf.raw_interview AND uf.raw_passed AND uf.raw_offer AND uf.raw_contract) AS did_contract
                FROM user_flags uf
            )
            SELECT
                date_trunc('week', a.filter_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                COUNT(DISTINCT a.tg_user_id) AS entered,
                COUNT(DISTINCT CASE WHEN uf.did_lead THEN a.tg_user_id END) AS lead,
                COUNT(DISTINCT CASE WHEN uf.did_platform THEN a.tg_user_id END) AS platform,
                COUNT(DISTINCT CASE WHEN uf.did_learning THEN a.tg_user_id END) AS learning,
                COUNT(DISTINCT CASE WHEN uf.did_course THEN a.tg_user_id END) AS course,
                COUNT(DISTINCT CASE WHEN uf.did_interview THEN a.tg_user_id END) AS interview,
                COUNT(DISTINCT CASE WHEN uf.did_passed THEN a.tg_user_id END) AS passed,
                COUNT(DISTINCT CASE WHEN uf.did_offer THEN a.tg_user_id END) AS offer,
                COUNT(DISTINCT CASE WHEN uf.did_distance THEN a.tg_user_id END) AS distance_grinding,
                COUNT(DISTINCT CASE WHEN uf.did_contract THEN a.tg_user_id END) AS contract
            FROM attributed a
            JOIN normalized_flags uf ON uf.tg_user_id = a.tg_user_id
            WHERE a.bot_key = :group_key
              AND a.tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
              AND (CAST(:start_date AS date) IS NULL OR (a.filter_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start_date AS date))
              AND (CAST(:end_date AS date) IS NULL OR (a.filter_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end_date AS date))
            GROUP BY 1
            ORDER BY 1
            """
        )
        result = await session.execute(query, params)

        months: List[str] = []
        monthly_rows: dict[str, List[dict]] = {}
        for row in result.fetchall():
            if not row.week_start:
                continue
            week_start = row.week_start
            week_end = week_start + dt_date.resolution * 6
            month_key = week_start.strftime("%Y-%m")
            if month_key not in months:
                months.append(month_key)
            monthly_rows.setdefault(month_key, []).append(
                {
                    "week_start": week_start.isoformat(),
                    "week_end": week_end.isoformat(),
                    "values": {
                        "entered": int(row.entered or 0),
                        "lead": int(row.lead or 0),
                        "platform": int(row.platform or 0),
                        "learning": int(row.learning or 0),
                        "course": int(row.course or 0),
                        "interview": int(row.interview or 0),
                        "passed": int(row.passed or 0),
                        "offer": int(row.offer or 0),
                        "distance_grinding": int(row.distance_grinding or 0),
                        "contract": int(row.contract or 0),
                    },
                }
            )
        return months, monthly_rows
