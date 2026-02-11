from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from datetime import date as dt_date, timedelta

from sqlalchemy import Date, Integer, desc, func, literal, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.report_filters import ReportFilters
from app.models.analytics import AdvertisingCompany, RawBotUser, TgSubsDailyAgg


@dataclass
class BreakdownResult:
    group: Optional[str]
    users: int
    budget: float


class ReportRepository:
    @staticmethod
    def _coerce_date(value: Optional[str | dt_date]) -> Optional[dt_date]:
        if value is None:
            return None
        if isinstance(value, dt_date):
            return value
        return dt_date.fromisoformat(value)

    def _apply_filters_with_date(self, stmt, filters: ReportFilters, date_col):
        if filters.start_date:
            stmt = stmt.where(date_col >= filters.start_date)
        if filters.end_date:
            # inclusive end_date for full day
            stmt = stmt.where(date_col < (filters.end_date + timedelta(days=1)))
        if filters.bots:
            stmt = stmt.where(RawBotUser.bot_key.in_(filters.bots))
        if filters.advertising_companies:
            stmt = stmt.where(RawBotUser.advertising_company.in_(filters.advertising_companies))
        if filters.utm_source:
            stmt = stmt.where(RawBotUser.utm_source.in_(filters.utm_source))
        if filters.utm_campaign:
            stmt = stmt.where(RawBotUser.utm_campaign.in_(filters.utm_campaign))
        if filters.utm_medium:
            stmt = stmt.where(RawBotUser.utm_medium.in_(filters.utm_medium))
        if filters.utm_content:
            stmt = stmt.where(RawBotUser.utm_content.in_(filters.utm_content))
        if filters.utm_term:
            stmt = stmt.where(RawBotUser.utm_term.in_(filters.utm_term))
        return stmt

    def _apply_filters(self, stmt, filters: ReportFilters):
        return self._apply_filters_with_date(stmt, filters, RawBotUser.created_at)

    async def total(self, session: AsyncSession, filters: ReportFilters) -> dict[str, Optional[float]]:
        stmt = select(
            func.count(func.distinct(RawBotUser.tg_user_id)).label("users"),
            func.coalesce(func.sum(RawBotUser.budget), 0).label("budget"),
        )
        stmt = self._apply_filters(stmt, filters)
        result = await session.execute(stmt)
        row = result.one()
        total_users = row.users or 0
        total_budget = row.budget or 0.0
        return {
            "total_users": total_users,
            "total_budget": total_budget,
            "cac": (total_budget / total_users) if total_users else None,
        }

    async def daily(self, session: AsyncSession, filters: ReportFilters, limit: Optional[int] = None) -> List[dict[str, Optional[float]]]:
        date_expr = func.date_trunc("day", RawBotUser.created_at)
        stmt = (
            select(
                date_expr.label("date"),
                func.count(func.distinct(RawBotUser.tg_user_id)).label("users"),
                func.coalesce(func.sum(RawBotUser.budget), 0).label("budget"),
            )
            .group_by(date_expr)
            .order_by(date_expr)
        )
        stmt = self._apply_filters(stmt, filters)
        if limit:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        return [
            {"date": row.date.strftime("%Y-%m-%d"), "users": row.users, "budget": row.budget}
            for row in result.all()
        ]

    async def breakdown(
        self, session: AsyncSession, filters: ReportFilters, group_by: str, limit: int = 20
    ) -> List[BreakdownResult]:
        if group_by == "source_campaign":
            label = func.concat(
                func.coalesce(RawBotUser.utm_source, "—"),
                " / ",
                func.coalesce(RawBotUser.utm_campaign, "—"),
            ).label("group_value")
        else:
            column = getattr(RawBotUser, group_by)
            label = func.coalesce(column, "—").label("group_value")

        stmt = (
            select(
                label,
                func.count(func.distinct(RawBotUser.tg_user_id)).label("users"),
                func.coalesce(func.sum(RawBotUser.budget), 0).label("budget"),
            )
            .group_by(label)
            .order_by(desc("users"))
            .limit(limit)
        )
        stmt = self._apply_filters(stmt, filters)
        result = await session.execute(stmt)
        return [
            BreakdownResult(group=row.group_value, users=row.users, budget=row.budget) for row in result.all()
        ]

    async def conversions(self, session: AsyncSession, filters: ReportFilters) -> List[dict[str, Optional[float]]]:
        entered_count = func.count(func.distinct(RawBotUser.tg_user_id))
        converted_count = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
            RawBotUser.converted_to_lead.is_(True)
        )
        stmt = (
            select(
                RawBotUser.bot_key.label("bot_key"),
                entered_count.label("entered"),
                converted_count.label("converted"),
            )
            .group_by(RawBotUser.bot_key)
            .order_by(desc("entered"))
        )
        stmt = self._apply_filters(stmt, filters)
        result = await session.execute(stmt)
        rows = result.all()
        total_entered = sum(row.entered or 0 for row in rows)
        total_converted = sum(row.converted or 0 for row in rows)
        overall_rate = (total_converted / total_entered) * 100 if total_entered else 0
        return [
            {
                "bot_key": row.bot_key,
                "entered": row.entered or 0,
                "converted": row.converted or 0,
                "conversion_rate": (row.converted or 0) / (row.entered or 1) * 100 if row.entered else 0,
                "overall_entered": total_entered,
                "overall_converted": total_converted,
                "overall_rate": overall_rate,
            }
            for row in rows
        ]

    async def stages(self, session: AsyncSession, filters: ReportFilters) -> dict[str, int]:
        entered_count = func.count(func.distinct(RawBotUser.tg_user_id))
        stmt = select(
            entered_count.label("entered"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.converted_to_lead.is_(True)
            ).label("lead"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.registered_platform.is_(True)
            ).label("platform"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.started_learning.is_(True)
            ).label("learning"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.completed_course.is_(True)
            ).label("course"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.used_simulator.is_(True)
            ).label("simulator"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.interview_reached.is_(True)
            ).label("interview"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.interview_passed.is_(True)
            ).label("passed"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.offer_received.is_(True)
            ).label("offer"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.contract_signed.is_(True)
            ).label("contract"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.distance_grinding.is_(True)
            ).label("distance_grinding"),
        )
        stmt = self._apply_filters(stmt, filters)
        result = await session.execute(stmt)
        row = result.one()
        return {
            "entered": int(row.entered or 0),
            "lead": int(row.lead or 0),
            "platform": int(row.platform or 0),
            "learning": int(row.learning or 0),
            "course": int(row.course or 0),
            "simulator": int(row.simulator or 0),
            "interview": int(row.interview or 0),
            "passed": int(row.passed or 0),
            "offer": int(row.offer or 0),
            "contract": int(row.contract or 0),
            "distance_grinding": int(row.distance_grinding or 0),
        }

    async def summary(
        self, session: AsyncSession, filters: ReportFilters, group_by: str
    ) -> List[dict[str, int]]:
        if group_by == "advertising_company":
            label = func.coalesce(RawBotUser.advertising_company, "—").label("group_value")
        else:
            label = RawBotUser.bot_key.label("group_value")

        stmt = select(
            label,
            func.count(func.distinct(RawBotUser.tg_user_id)).label("entered"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.converted_to_lead.is_(True)
            ).label("lead"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.registered_platform.is_(True)
            ).label("platform"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.started_learning.is_(True)
            ).label("learning"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.completed_course.is_(True)
            ).label("course"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.used_simulator.is_(True)
            ).label("simulator"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.interview_reached.is_(True)
            ).label("interview"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.interview_passed.is_(True)
            ).label("passed"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.offer_received.is_(True)
            ).label("offer"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.contract_signed.is_(True)
            ).label("contract"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.distance_grinding.is_(True)
            ).label("distance_grinding"),
        ).group_by(label)
        stmt = self._apply_filters(stmt, filters)
        stmt = stmt.order_by(desc("entered"))
        result = await session.execute(stmt)
        return [
            {
                "group": row.group_value,
                "entered": int(row.entered or 0),
                "lead": int(row.lead or 0),
                "platform": int(row.platform or 0),
                "learning": int(row.learning or 0),
                "course": int(row.course or 0),
                "simulator": int(row.simulator or 0),
                "interview": int(row.interview or 0),
                "passed": int(row.passed or 0),
                "offer": int(row.offer or 0),
                "contract": int(row.contract or 0),
                "distance_grinding": int(row.distance_grinding or 0),
            }
            for row in result.all()
        ]

    async def subscriptions_vs_starts(
        self,
        session: AsyncSession,
        start_date: Optional[str | dt_date],
        end_date: Optional[str | dt_date],
        group_by_campaign: bool = False,
        interval: str = "day",
        channel_id: str | None = None,
        community_id: str | None = None,
        bots: Optional[list[str]] = None,
        advertising_companies: Optional[list[str]] = None,
        utm_source: Optional[list[str]] = None,
        utm_campaign: Optional[list[str]] = None,
        utm_medium: Optional[list[str]] = None,
        utm_content: Optional[list[str]] = None,
        utm_term: Optional[list[str]] = None,
    ) -> List[dict]:
        if interval not in {"day", "week"}:
            raise ValueError("interval must be day or week")
        start_date_obj = self._coerce_date(start_date)
        end_date_obj = self._coerce_date(end_date)

        active_companies: list[str] = []
        if group_by_campaign:
            active_companies = (
                await session.execute(
                    select(AdvertisingCompany.company_name).where(AdvertisingCompany.is_active.is_(True))
                )
            ).scalars().all()
            active_companies = sorted({name for name in active_companies if name})

        params: dict[str, Any] = {}
        if start_date_obj:
            params["start_date"] = start_date_obj
        if end_date_obj:
            params["end_date"] = end_date_obj
        if bots:
            params["bots"] = list(bots)
        if advertising_companies:
            params["advertising_companies"] = list(advertising_companies)
        if utm_source:
            params["utm_source"] = list(utm_source)
        if utm_campaign:
            params["utm_campaign"] = list(utm_campaign)
        if utm_medium:
            params["utm_medium"] = list(utm_medium)
        if utm_content:
            params["utm_content"] = list(utm_content)
        if utm_term:
            params["utm_term"] = list(utm_term)
        if group_by_campaign and active_companies:
            params["active_companies"] = list(active_companies)

        ud_filters = []
        if bots:
            ud_filters.append("ud.bot_key = ANY(CAST(:bots AS text[]))")
        if advertising_companies:
            ud_filters.append("ud.advertising_company = ANY(CAST(:advertising_companies AS text[]))")
        if utm_source:
            ud_filters.append("ud.utm_source = ANY(CAST(:utm_source AS text[]))")
        if utm_campaign:
            ud_filters.append("ud.utm_campaign = ANY(CAST(:utm_campaign AS text[]))")
        if utm_medium:
            ud_filters.append("ud.utm_medium = ANY(CAST(:utm_medium AS text[]))")
        if utm_content:
            ud_filters.append("ud.utm_content = ANY(CAST(:utm_content AS text[]))")
        if utm_term:
            ud_filters.append("ud.utm_term = ANY(CAST(:utm_term AS text[]))")
        if group_by_campaign and active_companies:
            ud_filters.append("ud.advertising_company = ANY(CAST(:active_companies AS text[]))")

        ud_where = " AND " + " AND ".join(ud_filters) if ud_filters else ""

        channel_filter = "1=0"
        community_filter = "1=0"
        if channel_id:
            channel_filter = "e.channel_id = :channel_id"
            params["channel_id"] = str(channel_id)
        if community_id:
            community_filter = "e.channel_id = :community_id"
            params["community_id"] = str(community_id)

        period_expr = "checked_at::date" if interval == "day" else "DATE_TRUNC('week', checked_at)::date"
        ft_period_expr = "day" if interval == "day" else "DATE_TRUNC('week', day)::date"

        campaign_expr = "ud.advertising_company" if group_by_campaign else "''"
        bot_expr = "ud.bot_key" if group_by_campaign else "''"

        date_filters = []
        if start_date_obj:
            date_filters.append(f"{period_expr} >= :start_date")
        if end_date_obj:
            date_filters.append(f"{period_expr} <= :end_date")
        event_date_where = " AND " + " AND ".join(date_filters) if date_filters else ""

        ft_filters = []
        if start_date_obj:
            ft_filters.append("day >= :start_date")
        if end_date_obj:
            ft_filters.append("day <= :end_date")
        ft_where = " AND " + " AND ".join(ft_filters) if ft_filters else ""

        query = text(
            f"""
            WITH user_dim AS (
                SELECT
                    tg_user_id,
                    COALESCE(MAX(first_touch_campaign), 'нет метки') AS campaign,
                    COALESCE(MAX(bot_key), '') AS bot_key,
                    COALESCE(MAX(advertising_company), '') AS advertising_company,
                    COALESCE(MAX(utm_source), '') AS utm_source,
                    COALESCE(MAX(utm_campaign), '') AS utm_campaign,
                    COALESCE(MAX(utm_medium), '') AS utm_medium,
                    COALESCE(MAX(utm_content), '') AS utm_content,
                    COALESCE(MAX(utm_term), '') AS utm_term
                FROM raw_bot_users
                GROUP BY tg_user_id
            ),
            first_touch AS (
                SELECT
                    ru.tg_user_id,
                    MIN(ru.created_at)::date AS day
                FROM raw_bot_users ru
                WHERE ru.created_at IS NOT NULL
                  AND lower(COALESCE(ru.bot_key, '')) NOT LIKE 'lead%%'
                GROUP BY ru.tg_user_id
            ),
            almanah_touch AS (
                SELECT
                    ru.tg_user_id,
                    MIN(ru.created_at)::date AS day
                FROM raw_bot_users ru
                WHERE ru.created_at IS NOT NULL
                  AND lower(COALESCE(ru.bot_key, '')) LIKE 'lead%%'
                GROUP BY ru.tg_user_id
            ),
            bot_starts AS (
                SELECT
                    {ft_period_expr} AS day,
                    {campaign_expr} AS campaign,
                    {bot_expr} AS bot_key,
                    ud.advertising_company,
                    ud.utm_source,
                    ud.utm_campaign,
                    ud.utm_medium,
                    ud.utm_content,
                    ud.utm_term,
                    COUNT(DISTINCT ft.tg_user_id) AS bot_starts
                FROM first_touch ft
                JOIN user_dim ud ON ud.tg_user_id = ft.tg_user_id
                WHERE 1=1
                  {ft_where}
                  {ud_where}
                GROUP BY
                    day, campaign, bot_key, ud.advertising_company,
                    ud.utm_source, ud.utm_campaign, ud.utm_medium, ud.utm_content, ud.utm_term
            ),
            almanah_starts AS (
                SELECT
                    {ft_period_expr} AS day,
                    {campaign_expr} AS campaign,
                    {bot_expr} AS bot_key,
                    ud.advertising_company,
                    ud.utm_source,
                    ud.utm_campaign,
                    ud.utm_medium,
                    ud.utm_content,
                    ud.utm_term,
                    COUNT(DISTINCT at.tg_user_id) AS almanah_starts
                FROM almanah_touch at
                JOIN user_dim ud ON ud.tg_user_id = at.tg_user_id
                WHERE 1=1
                  {ft_where}
                  {ud_where}
                GROUP BY
                    day, campaign, bot_key, ud.advertising_company,
                    ud.utm_source, ud.utm_campaign, ud.utm_medium, ud.utm_content, ud.utm_term
            ),
            channel_events AS (
                SELECT
                    {period_expr} AS day,
                    {campaign_expr} AS campaign,
                    {bot_expr} AS bot_key,
                    ud.advertising_company,
                    ud.utm_source,
                    ud.utm_campaign,
                    ud.utm_medium,
                    ud.utm_content,
                    ud.utm_term,
                    COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.status = 'subscribed') AS channel_subscribed,
                    COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.status = 'unsubscribed') AS channel_unsubscribed
                FROM telegram_subscription_events e
                JOIN user_dim ud ON ud.tg_user_id = e.tg_user_id
                WHERE {channel_filter}
                  {event_date_where}
                  {ud_where}
                GROUP BY
                    day, campaign, bot_key, ud.advertising_company,
                    ud.utm_source, ud.utm_campaign, ud.utm_medium, ud.utm_content, ud.utm_term
            ),
            community_events AS (
                SELECT
                    {period_expr} AS day,
                    {campaign_expr} AS campaign,
                    {bot_expr} AS bot_key,
                    ud.advertising_company,
                    ud.utm_source,
                    ud.utm_campaign,
                    ud.utm_medium,
                    ud.utm_content,
                    ud.utm_term,
                    COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.status = 'subscribed') AS saloon_subscribed,
                    COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.status = 'unsubscribed') AS saloon_unsubscribed
                FROM telegram_subscription_events e
                JOIN user_dim ud ON ud.tg_user_id = e.tg_user_id
                WHERE {community_filter}
                  {event_date_where}
                  {ud_where}
                GROUP BY
                    day, campaign, bot_key, ud.advertising_company,
                    ud.utm_source, ud.utm_campaign, ud.utm_medium, ud.utm_content, ud.utm_term
            ),
            merged AS (
                SELECT
                    COALESCE(bs.day, als.day, ce.day, cme.day) AS day,
                    COALESCE(bs.campaign, als.campaign, ce.campaign, cme.campaign) AS campaign,
                    COALESCE(bs.bot_key, als.bot_key, ce.bot_key, cme.bot_key) AS bot_key,
                    COALESCE(bs.advertising_company, als.advertising_company, ce.advertising_company, cme.advertising_company) AS advertising_company,
                    COALESCE(bs.utm_source, als.utm_source, ce.utm_source, cme.utm_source) AS utm_source,
                    COALESCE(bs.utm_campaign, als.utm_campaign, ce.utm_campaign, cme.utm_campaign) AS utm_campaign,
                    COALESCE(bs.utm_medium, als.utm_medium, ce.utm_medium, cme.utm_medium) AS utm_medium,
                    COALESCE(bs.utm_content, als.utm_content, ce.utm_content, cme.utm_content) AS utm_content,
                    COALESCE(bs.utm_term, als.utm_term, ce.utm_term, cme.utm_term) AS utm_term,
                    COALESCE(bs.bot_starts, 0) AS bot_starts,
                    COALESCE(als.almanah_starts, 0) AS almanah_starts,
                    COALESCE(ce.channel_subscribed, 0) AS channel_subscribed,
                    COALESCE(ce.channel_unsubscribed, 0) AS channel_unsubscribed,
                    COALESCE(cme.saloon_subscribed, 0) AS saloon_subscribed,
                    COALESCE(cme.saloon_unsubscribed, 0) AS saloon_unsubscribed
                FROM bot_starts bs
                FULL OUTER JOIN almanah_starts als ON
                    bs.day = als.day AND bs.campaign = als.campaign AND bs.bot_key = als.bot_key
                    AND bs.advertising_company = als.advertising_company
                    AND bs.utm_source = als.utm_source AND bs.utm_campaign = als.utm_campaign
                    AND bs.utm_medium = als.utm_medium AND bs.utm_content = als.utm_content
                    AND bs.utm_term = als.utm_term
                FULL OUTER JOIN channel_events ce ON
                    COALESCE(bs.day, als.day) = ce.day
                    AND COALESCE(bs.campaign, als.campaign) = ce.campaign
                    AND COALESCE(bs.bot_key, als.bot_key) = ce.bot_key
                    AND COALESCE(bs.advertising_company, als.advertising_company) = ce.advertising_company
                    AND COALESCE(bs.utm_source, als.utm_source) = ce.utm_source
                    AND COALESCE(bs.utm_campaign, als.utm_campaign) = ce.utm_campaign
                    AND COALESCE(bs.utm_medium, als.utm_medium) = ce.utm_medium
                    AND COALESCE(bs.utm_content, als.utm_content) = ce.utm_content
                    AND COALESCE(bs.utm_term, als.utm_term) = ce.utm_term
                FULL OUTER JOIN community_events cme ON
                    COALESCE(bs.day, als.day, ce.day) = cme.day
                    AND COALESCE(bs.campaign, als.campaign, ce.campaign) = cme.campaign
                    AND COALESCE(bs.bot_key, als.bot_key, ce.bot_key) = cme.bot_key
                    AND COALESCE(bs.advertising_company, als.advertising_company, ce.advertising_company) = cme.advertising_company
                    AND COALESCE(bs.utm_source, als.utm_source, ce.utm_source) = cme.utm_source
                    AND COALESCE(bs.utm_campaign, als.utm_campaign, ce.utm_campaign) = cme.utm_campaign
                    AND COALESCE(bs.utm_medium, als.utm_medium, ce.utm_medium) = cme.utm_medium
                    AND COALESCE(bs.utm_content, als.utm_content, ce.utm_content) = cme.utm_content
                    AND COALESCE(bs.utm_term, als.utm_term) = cme.utm_term
            )
            SELECT
                day,
                campaign,
                bot_key,
                bot_starts,
                almanah_starts,
                channel_subscribed,
                channel_unsubscribed,
                saloon_subscribed,
                saloon_unsubscribed
            FROM merged
            WHERE day IS NOT NULL
            ORDER BY campaign ASC, bot_key ASC, day ASC
            """
        )
        rows = (await session.execute(query, params)).all()
        payload = []
        for row in rows:
            channel_total = int(row.channel_subscribed or 0) - int(row.channel_unsubscribed or 0)
            saloon_total = int(row.saloon_subscribed or 0) - int(row.saloon_unsubscribed or 0)
            payload.append(
                {
                    "date": row.day.isoformat() if row.day else None,
                    "campaign": row.campaign,
                    "bot_key": row.bot_key or "",
                    "bot_starts": int(row.bot_starts or 0),
                    "almanah_starts": int(row.almanah_starts or 0),
                    "channel_subscribed": int(row.channel_subscribed or 0),
                    "channel_unsubscribed": int(row.channel_unsubscribed or 0),
                    "channel_total": int(max(channel_total, 0)),
                    "saloon_subscribed": int(row.saloon_subscribed or 0),
                    "saloon_unsubscribed": int(row.saloon_unsubscribed or 0),
                    "saloon_total": int(max(saloon_total, 0)),
                }
            )
        return payload

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
        WHERE {where_clause}
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

    async def touch_summary(
        self,
        session: AsyncSession,
        start_date: Optional[str],
        end_date: Optional[str],
        mode: str,
    ) -> List[dict]:
        if mode not in {"first", "last"}:
            raise ValueError("mode must be first or last")
        if mode == "first":
            bot_col = "first_touch_bot"
            campaign_col = "first_touch_campaign"
        else:
            bot_col = "last_touch_bot"
            campaign_col = "last_touch_campaign"

        conditions = []
        params: dict[str, Any] = {}
        date_col = "created_at" if mode == "first" else "learn_start_date"
        if start_date:
            conditions.append(f"{date_col} >= :start_date")
            params["start_date"] = start_date
        if end_date:
            conditions.append(f"{date_col} <= :end_date")
            params["end_date"] = end_date
        if mode == "last":
            conditions.append("learn_start_date IS NOT NULL")
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
        SELECT
            COALESCE({bot_col}, 'нет метки') AS bot,
            COALESCE({campaign_col}, 'нет метки') AS campaign,
            COUNT(DISTINCT tg_user_id) AS users
        FROM raw_bot_users
        {where_clause}
        GROUP BY bot, campaign
        ORDER BY users DESC
        """
        result = await session.execute(text(query), params)
        rows = result.fetchall()
        return [
            {
                "bot": row.bot,
                "campaign": row.campaign,
                "users": int(row.users or 0),
            }
            for row in rows
        ]

    async def touch_funnel_summary(
        self,
        session: AsyncSession,
        filters: ReportFilters,
        mode: str = "last",
    ) -> List[dict[str, int]]:
        if mode not in {"first", "last"}:
            raise ValueError("mode must be first or last")
        bot_col = RawBotUser.first_touch_bot if mode == "first" else RawBotUser.last_touch_bot
        date_col = RawBotUser.created_at if mode == "first" else RawBotUser.learn_start_date
        bot_label = func.coalesce(bot_col, "нет метки").label("bot")

        stmt = select(
            bot_label,
            func.count(func.distinct(RawBotUser.tg_user_id)).label("entered"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.interview_reached.is_(True)
            ).label("interview"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.interview_passed.is_(True)
            ).label("passed"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.offer_received.is_(True)
            ).label("offer"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.distance_grinding.is_(True)
            ).label("distance_grinding"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.contract_signed.is_(True)
            ).label("contract"),
        ).where(
            bot_col.isnot(None),
            func.trim(bot_col) != "",
            func.lower(func.trim(bot_col)) != "нет метки",
            date_col.isnot(None),
        ).group_by(bot_label)

        stmt = self._apply_filters_with_date(stmt, filters, date_col)
        stmt = stmt.order_by(desc("entered"))
        result = await session.execute(stmt)
        return [
            {
                "bot": row.bot,
                "entered": int(row.entered or 0),
                "interview": int(row.interview or 0),
                "passed": int(row.passed or 0),
                "offer": int(row.offer or 0),
                "distance_grinding": int(row.distance_grinding or 0),
                "contract": int(row.contract or 0),
            }
            for row in result.all()
        ]

    async def touch_weekly(
        self,
        session: AsyncSession,
        group_key: str,
        mode: str = "last",
    ) -> Tuple[List[str], dict[str, List[dict]]]:
        bot_value = group_key
        if mode not in {"first", "last"}:
            raise ValueError("mode must be first or last")
        bot_col = RawBotUser.first_touch_bot if mode == "first" else RawBotUser.last_touch_bot
        date_col = RawBotUser.created_at if mode == "first" else RawBotUser.learn_start_date
        bot_label = func.coalesce(bot_col, "нет метки")
        week_start = func.date_trunc("week", date_col).label("week_start")

        stmt = (
            select(
                week_start,
                func.count(func.distinct(RawBotUser.tg_user_id)).label("entered"),
                func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                    RawBotUser.interview_reached.is_(True)
                ).label("interview"),
                func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                    RawBotUser.interview_passed.is_(True)
                ).label("passed"),
                func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                    RawBotUser.offer_received.is_(True)
                ).label("offer"),
                func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                    RawBotUser.distance_grinding.is_(True)
                ).label("distance_grinding"),
                func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                    RawBotUser.contract_signed.is_(True)
                ).label("contract"),
            )
            .where(
                bot_label == bot_value,
                bot_col.isnot(None),
                func.trim(bot_col) != "",
                func.lower(func.trim(bot_col)) != "нет метки",
                date_col.isnot(None),
            )
            .group_by(week_start)
            .order_by(week_start)
        )
        result = await session.execute(stmt)

        months: List[str] = []
        monthly_rows: dict[str, List[dict]] = {}
        for row in result.fetchall():
            if not row.week_start:
                continue
            month_key = row.week_start.strftime("%Y-%m")
            week_end = (row.week_start + timedelta(days=6)).date().isoformat()
            weekly_row = {
                "week_start": row.week_start.date().isoformat(),
                "week_end": week_end,
                "values": {
                    "entered": int(row.entered or 0),
                    "interview": int(row.interview or 0),
                    "passed": int(row.passed or 0),
                    "offer": int(row.offer or 0),
                    "distance_grinding": int(row.distance_grinding or 0),
                    "contract": int(row.contract or 0),
                },
            }
            monthly_rows.setdefault(month_key, []).append(weekly_row)
            months.append(month_key)

        months_sorted = sorted(set(months))
        return months_sorted, monthly_rows

    async def budget_weekly_report(
        self,
        session: AsyncSession,
        start_date: Optional[str],
        end_date: Optional[str],
        interval: str = "week",
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
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        if interval == "day":
            budget_cte = """
            budget_base AS (
                SELECT
                    (b.week_start + gs)::date AS period_start,
                    b.campaign AS campaign,
                    b.bot_key AS bot_key,
                    (b.amount / 7.0) AS budget,
                    b.currency AS currency
                FROM budget_weekly b
                CROSS JOIN generate_series(0,6) AS gs
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
                GROUP BY 1, 2, 3
            )
            """
        else:
            budget_cte = """
            budget_base AS (
                SELECT
                    b.week_start AS period_start,
                    b.campaign AS campaign,
                    b.bot_key AS bot_key,
                    b.amount AS budget,
                    b.currency AS currency
                FROM budget_weekly b
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
                GROUP BY 1, 2, 3
            )
            """
        query = f"""
        WITH {budget_cte}
        , metrics AS (
            SELECT
                {metrics_date} AS period_start,
                COALESCE(advertising_company, 'нет метки') AS company,
                COALESCE(bot_key, '') AS bot_key,
                COUNT(DISTINCT tg_user_id) AS starts,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE converted_to_lead IS TRUE) AS lead,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE registered_platform IS TRUE) AS platform,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE started_learning IS TRUE) AS learning,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE completed_course IS TRUE) AS completed_course,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE interview_reached IS TRUE) AS interview,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE interview_passed IS TRUE) AS passed,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE offer_received IS TRUE) AS offer,
                COUNT(DISTINCT tg_user_id) FILTER (WHERE contract_signed IS TRUE) AS contract
            FROM raw_bot_users
            GROUP BY period_start, company, bot_key
        )
        , subs AS (
            SELECT
                {subs_date} AS period_start,
                COALESCE(r.advertising_company, 'нет метки') AS company,
                COALESCE(r.bot_key, '') AS bot_key,
                SUM(CASE WHEN e.status = 'subscribed' THEN 1 ELSE 0 END) AS subscribed,
                SUM(CASE WHEN e.status = 'unsubscribed' THEN 1 ELSE 0 END) AS unsubscribed
            FROM telegram_subscription_events e
            JOIN raw_bot_users r ON r.tg_user_id = e.tg_user_id
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
            GROUP BY period_start, company, bot_key
        )
        , {ad_metrics_cte.strip()}
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
            cpf = (spend_base / subscribed) if subscribed else None
            cpl = (spend_base / lead) if lead else None
            cpa = (spend_base / learning) if learning else None
            cpc = (spend_base / contract) if contract else None
            ctr = (clicks / impressions * 100) if impressions else None
            cpc_click = (spend_base / clicks) if clicks else None
            cpm = (spend_base / impressions * 1000) if impressions else None
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
