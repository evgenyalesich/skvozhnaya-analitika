from datetime import date as dt_date
from typing import Any, List, Optional

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession


class ReportRepositoryBudgetMixin:
    """Budget and course-mix reporting slice."""

    async def course_mix(
        self,
        session: AsyncSession,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> List[dict]:
        conditions = ["started_learning IS TRUE"]
        params: dict[str, Any] = {}
        if start_date:
            conditions.append("learn_start_date >= :start_date")
            params["start_date"] = start_date
        if end_date:
            conditions.append("learn_start_date <= :end_date")
            params["end_date"] = end_date
        where_clause = " AND ".join(conditions)
        query = f"""
        SELECT
            COALESCE(start_course, 'UNKNOWN') AS course,
            COUNT(*) AS users
        FROM raw_bot_users
        WHERE tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
          AND {where_clause}
        GROUP BY COALESCE(start_course, 'UNKNOWN')
        ORDER BY users DESC
        """
        result = await session.execute(text(query), params)
        rows = result.fetchall()
        return [
            {
                "course": row.course,
                "users": int(row.users or 0),
            }
            for row in rows
        ]

    # ===== Budget weekly report =====
    async def budget_weekly_report(
        self,
        session: AsyncSession,
        start_date: Optional[str],
        end_date: Optional[str],
        interval: str = "week",
        bots: Optional[list[str]] = None,
        advertising_companies: Optional[list[str]] = None,
    ) -> List[dict]:
        if interval not in {"day", "week"}:
            raise ValueError("interval must be day or week")
        def _parse_date(value: Optional[str | dt_date]) -> Optional[dt_date]:
            if not value:
                return None
            if isinstance(value, dt_date):
                return value
            if isinstance(value, str):
                try:
                    return dt_date.fromisoformat(value)
                except ValueError:
                    return None
            return None

        conditions = []
        params: dict[str, Any] = {}
        parsed_start = _parse_date(start_date)
        parsed_end = _parse_date(end_date)
        if parsed_start:
            conditions.append("b.period_start >= :start_date")
            params["start_date"] = parsed_start
        if parsed_end:
            conditions.append("b.period_start <= :end_date")
            params["end_date"] = parsed_end
        if bots:
            conditions.append("COALESCE(b.bot_key, '') = ANY(:bots)")
            params["bots"] = bots
        if advertising_companies:
            conditions.append("b.campaign = ANY(:advertising_companies)")
            params["advertising_companies"] = advertising_companies
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        metrics_filters = []
        if bots:
            metrics_filters.append("bot_key = ANY(:bots)")
        if advertising_companies:
            metrics_filters.append("COALESCE(advertising_company, 'нет метки') = ANY(:advertising_companies)")
        metrics_where = f"AND {' AND '.join(metrics_filters)}" if metrics_filters else ""

        subs_filters = []
        if bots:
            subs_filters.append("ud.bot_key = ANY(:bots)")
        if advertising_companies:
            subs_filters.append("ud.company = ANY(:advertising_companies)")
        subs_where = f"AND {' AND '.join(subs_filters)}" if subs_filters else ""

        course_filters = []
        if bots:
            course_filters.append("bot_key = ANY(:bots)")
        if advertising_companies:
            course_filters.append("COALESCE(advertising_company, 'нет метки') = ANY(:advertising_companies)")
        course_where = f"AND {' AND '.join(course_filters)}" if course_filters else ""

        ad_filters = []
        if bots:
            ad_filters.append("COALESCE(bot_key, '') = ANY(:bots)")
        if advertising_companies:
            ad_filters.append("campaign = ANY(:advertising_companies)")
        ad_where = f"WHERE {' AND '.join(ad_filters)}" if ad_filters else ""
        if interval == "day":
            budget_cte = """
            budget_base AS (
                SELECT
                    b.week_start::date AS period_start,
                    b.campaign AS campaign,
                    b.bot_key AS bot_key,
                    b.amount AS budget,
                    b.currency AS currency
                FROM budget_weekly b
            )
            """
            metrics_date = "DATE_TRUNC('day', created_at)::date"
            subs_date = "DATE_TRUNC('day', e.checked_at)::date"
            course_date = "DATE_TRUNC('day', learn_start_date)::date"
            ad_metrics_cte = """
            ad_metrics AS (
                SELECT
                    (week_start + gs)::date AS period_start,
                    campaign,
                    COALESCE(bot_key, '') AS bot_key,
                    SUM(impressions) / 7.0 AS impressions,
                    SUM(clicks) / 7.0 AS clicks,
                    SUM(spend) / 7.0 AS spend
                FROM ad_metrics_weekly
                CROSS JOIN generate_series(0,6) AS gs
                {ad_where}
                GROUP BY 1, 2, 3
            )
            """
        else:
            budget_cte = """
            budget_base AS (
                SELECT
                    DATE_TRUNC('week', b.week_start)::date AS period_start,
                    b.campaign AS campaign,
                    b.bot_key AS bot_key,
                    SUM(b.amount) AS budget,
                    b.currency AS currency
                FROM budget_weekly b
                GROUP BY DATE_TRUNC('week', b.week_start)::date, b.campaign, b.bot_key, b.currency
            )
            """
            metrics_date = "DATE_TRUNC('week', created_at)::date"
            subs_date = "DATE_TRUNC('week', e.checked_at)::date"
            course_date = "DATE_TRUNC('week', learn_start_date)::date"
            ad_metrics_cte = """
            ad_metrics AS (
                SELECT
                    DATE_TRUNC('week', week_start)::date AS period_start,
                    campaign,
                    COALESCE(bot_key, '') AS bot_key,
                    SUM(impressions) AS impressions,
                    SUM(clicks) AS clicks,
                    SUM(spend) AS spend
                FROM ad_metrics_weekly
                {ad_where}
                GROUP BY 1, 2, 3
            )
            """
        query = f"""
        WITH {budget_cte}
        , user_dim AS (
            SELECT
                tg_user_id,
                COALESCE(MAX(advertising_company), 'нет метки') AS company,
                COALESCE(MAX(bot_key), '') AS bot_key
            FROM raw_bot_users
            WHERE tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
            GROUP BY tg_user_id
        )
        , metrics AS (
            SELECT
                {metrics_date} AS period_start,
                COALESCE(advertising_company, 'нет метки') AS company,
                COALESCE(bot_key, '') AS bot_key,
                COUNT(DISTINCT tg_user_id) AS starts,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE converted_to_lead IS TRUE) AS lead,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE registered_platform IS TRUE) AS platform,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE started_learning IS TRUE) AS learning,
                COUNT(DISTINCT tg_user_id) FILTER (
                    WHERE completed_course IS TRUE
                      AND completed_course_at IS NOT NULL
                      AND completed_course_at >= created_at
                ) AS completed_course,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE interview_reached IS TRUE) AS interview,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE interview_passed IS TRUE) AS passed,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE offer_received IS TRUE) AS offer,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE contract_signed IS TRUE) AS contract
            FROM raw_bot_users
            WHERE tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
            {metrics_where}
            GROUP BY period_start, company, bot_key
        )
        , subs AS (
            SELECT
                {subs_date} AS period_start,
                ud.company AS company,
                ud.bot_key AS bot_key,
                COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.status = 'subscribed') AS subscribed,
                COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.status = 'unsubscribed') AS unsubscribed
            FROM telegram_subscription_events e
            JOIN user_dim ud ON ud.tg_user_id = e.tg_user_id
            WHERE 1=1
            {subs_where}
            GROUP BY period_start, company, bot_key
        )
        , course_mix AS (
            SELECT
                {course_date} AS period_start,
                COALESCE(advertising_company, 'нет метки') AS company,
                COALESCE(bot_key, '') AS bot_key,
                SUM(CASE WHEN start_course = 'MTT' THEN 1 ELSE 0 END) AS mtt,
                SUM(CASE WHEN start_course = 'SPIN' THEN 1 ELSE 0 END) AS spin,
                SUM(CASE WHEN start_course = 'CASH' THEN 1 ELSE 0 END) AS cash
            FROM raw_bot_users
            WHERE learn_start_date IS NOT NULL
              AND tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
              {course_where}
            GROUP BY period_start, company, bot_key
        )
        , {ad_metrics_cte.strip().format(ad_where=ad_where)}
        SELECT
            b.period_start AS period_start,
            b.campaign AS campaign,
            b.bot_key AS bot_key,
            b.budget AS budget,
            b.currency AS currency,
            COALESCE(m.starts, 0) AS starts,
            COALESCE(m.lead, 0) AS lead,
            COALESCE(m.platform, 0) AS platform,
            COALESCE(m.learning, 0) AS learning,
            COALESCE(m.completed_course, 0) AS completed_course,
            COALESCE(m.interview, 0) AS interview,
            COALESCE(m.passed, 0) AS passed,
            COALESCE(m.offer, 0) AS offer,
            COALESCE(m.contract, 0) AS contract,
            COALESCE(a.impressions, 0) AS impressions,
            COALESCE(a.clicks, 0) AS clicks,
            COALESCE(a.spend, 0) AS spend,
            COALESCE(s.subscribed, 0) AS subscribed,
            COALESCE(s.unsubscribed, 0) AS unsubscribed,
            COALESCE(c.mtt, 0) AS course_mtt,
            COALESCE(c.spin, 0) AS course_spin,
            COALESCE(c.cash, 0) AS course_cash
        FROM budget_base b
        LEFT JOIN metrics m
            ON m.period_start = b.period_start
           AND (
                (b.bot_key IS NOT NULL AND b.bot_key <> '' AND lower(trim(m.bot_key)) = lower(trim(b.bot_key)))
                OR ((b.bot_key IS NULL OR b.bot_key = '') AND lower(trim(m.company)) = lower(trim(b.campaign)))
           )
        LEFT JOIN subs s
            ON s.period_start = b.period_start
           AND (
                (b.bot_key IS NOT NULL AND b.bot_key <> '' AND lower(trim(s.bot_key)) = lower(trim(b.bot_key)))
                OR ((b.bot_key IS NULL OR b.bot_key = '') AND lower(trim(s.company)) = lower(trim(b.campaign)))
           )
        LEFT JOIN course_mix c
            ON c.period_start = b.period_start
           AND (
                (b.bot_key IS NOT NULL AND b.bot_key <> '' AND lower(trim(c.bot_key)) = lower(trim(b.bot_key)))
                OR ((b.bot_key IS NULL OR b.bot_key = '') AND lower(trim(c.company)) = lower(trim(b.campaign)))
           )
        LEFT JOIN ad_metrics a
            ON a.period_start = b.period_start
           AND lower(trim(a.campaign)) = lower(trim(b.campaign))
           AND (
                b.bot_key IS NULL
                OR b.bot_key = ''
                OR lower(trim(a.bot_key)) = lower(trim(b.bot_key))
           )
        {where_clause}
        ORDER BY b.period_start DESC, b.campaign ASC
        """
        result = await session.execute(text(query), params)
        rows = result.fetchall()
        payload = []
        for row in rows:
            budget = float(row.budget or 0)
            spend = float(row.spend or 0)
            spend_base = spend if spend > 0 else budget
            starts = int(row.starts or 0)
            learning = int(row.learning or 0)
            contract = int(row.contract or 0)
            lead = int(row.lead or 0)
            impressions = int(row.impressions or 0)
            clicks = int(row.clicks or 0)
            subscribed = int(row.subscribed or 0)
            cpf = (spend_base / subscribed) if subscribed else None       # Cost per Follow (подписчик в канал)
            cpl = (spend_base / lead) if lead else None                   # Cost per Lead (переход в лид-бот)
            cpa = (spend_base / learning) if learning else None           # Cost per Acquisition = cost per learning start (старт обучения)
            cpc = (spend_base / contract) if contract else None           # Cost per Contract (подписание контракта); не путать с cpc_click
            ctr = (clicks / impressions * 100) if impressions else None   # Click-through rate, %
            cpc_click = (spend_base / clicks) if clicks else None         # Cost per Click (клик по рекламе)
            cpm = (spend_base / impressions * 1000) if impressions else None  # Cost per Mille (1000 показов)
            payload.append(
                {
                    "week_start": row.period_start.isoformat() if row.period_start else None,
                    "campaign": row.campaign,
                    "bot_key": row.bot_key,
                    "budget": budget,
                    "currency": row.currency,
                    "starts": starts,
                    "lead": lead,
                    "platform": int(row.platform or 0),
                    "learning": learning,
                    "completed_course": int(row.completed_course or 0),
                    "interview": int(row.interview or 0),
                    "passed": int(row.passed or 0),
                    "offer": int(row.offer or 0),
                    "contract": contract,
                    "impressions": impressions,
                    "clicks": clicks,
                    "spend": spend,
                    "ctr": ctr,
                    "cpc_click": cpc_click,
                    "cpm": cpm,
                    "subscribed": subscribed,
                    "unsubscribed": int(row.unsubscribed or 0),
                    "course_mtt": int(row.course_mtt or 0),
                    "course_spin": int(row.course_spin or 0),
                    "course_cash": int(row.course_cash or 0),
                    "cpf": cpf,
                    "cpl": cpl,
                    "cpa": cpa,
                    "cpc": cpc,
                }
            )
        return payload
