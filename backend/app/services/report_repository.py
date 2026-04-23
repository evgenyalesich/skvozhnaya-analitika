from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from datetime import date as dt_date, timedelta

from sqlalchemy import Date, Integer, desc, exists, func, literal, literal_column, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.report_filters import ReportFilters
from app.core.config import settings
from app.models.analytics import (
    AdvertisingCompany,
    BudgetWeekly,
    RawBotUser,
    TgSubsDailyAgg,
    WeeklyFunnelBotAgg,
)
from app.services.employee_registry_service import apply_employee_exclusion
from app.services.report_bot_scope import apply_excluded_bot_filter, normalized_excluded_bot_keys


@dataclass
class BreakdownResult:
    group: Optional[str]
    users: int
    budget: float


class ReportRepository:
    @staticmethod
    def _can_use_weekly_bot_agg(filters: ReportFilters, touch_mode: str = "event") -> bool:
        # The historical weekly aggregate uses the old funnel semantics
        # (UTC dates, converted_to_lead, TG ids for PH stages). Keep live reports
        # on raw data until the aggregate builder is migrated to the same rules.
        return False

    @staticmethod
    def _pct(num: int, den: int) -> float:
        if not den:
            return 0.0
        return round((num / den) * 100, 2)

    @staticmethod
    def _apply_utm_filter(stmt, primary_col, platform_col, values: list[str]):
        if values:
            normalized = [v.strip().lower() for v in values if isinstance(v, str) and v.strip()]
            if normalized:
                stmt = stmt.where(
                    or_(
                        func.lower(func.trim(func.coalesce(primary_col, ""))).in_(normalized),
                        func.lower(func.trim(func.coalesce(platform_col, ""))).in_(normalized),
                    )
                )
        return stmt

    @staticmethod
    def _completed_course_condition():
        return (
            RawBotUser.completed_course.is_(True)
            & RawBotUser.completed_course_at.is_not(None)
            & (RawBotUser.completed_course_at >= RawBotUser.created_at)
        )

    @staticmethod
    def _coerce_date(value: Optional[str | dt_date]) -> Optional[dt_date]:
        if value is None:
            return None
        if isinstance(value, dt_date):
            return value
        return dt_date.fromisoformat(value)

    @staticmethod
    def _msk_date(column):
        return func.timezone("Europe/Moscow", column).cast(Date)

    @staticmethod
    def _real_lead_condition():
        return (
            (RawBotUser.tg_user_id > 0)
            & func.lower(func.trim(func.coalesce(RawBotUser.bot_key, ""))).like("lead%")
        )

    def _lead_transition_condition(self, filters: ReportFilters | None = None, reference_col=None):
        lead_user = aliased(RawBotUser)
        reference_col = reference_col if reference_col is not None else RawBotUser.created_at
        conditions = [
            lead_user.tg_user_id == RawBotUser.tg_user_id,
            lead_user.tg_user_id > 0,
            lead_user.created_at.is_not(None),
            func.lower(func.trim(func.coalesce(lead_user.bot_key, ""))).like("lead%"),
            self._msk_date(lead_user.created_at) >= self._msk_date(reference_col),
        ]
        if filters and filters.start_date:
            conditions.append(self._msk_date(lead_user.created_at) >= filters.start_date)
        if filters and filters.end_date:
            conditions.append(self._msk_date(lead_user.created_at) <= filters.end_date)
        return exists(select(1).where(*conditions))

    @staticmethod
    def _converted_to_lead_condition():
        lead_user = aliased(RawBotUser)
        has_lead_row = exists(
            select(1).where(
                lead_user.tg_user_id == RawBotUser.tg_user_id,
                func.lower(func.trim(func.coalesce(lead_user.bot_key, ""))).like("lead%"),
            )
        )
        return or_(RawBotUser.converted_to_lead.is_(True), has_lead_row)

    def _strict_stage_conditions(self, filters: ReportFilters | None = None):
        # Strict sequential funnel:
        # entered -> lead -> platform -> learning -> course -> interview -> passed -> offer
        # simulator is a side metric from course (must not block interview/offer/contract),
        # distance/contract are post-offer branches and should not block each other.
        lead = self._lead_transition_condition(filters)
        platform = (
            RawBotUser.ph_user_id.is_not(None)
            & RawBotUser.registered_platform.is_(True)
            & RawBotUser.platform_registered_at.is_not(None)
        )
        learning = platform & RawBotUser.started_learning.is_(True)
        course = learning & self._completed_course_condition()
        simulator = course & RawBotUser.used_simulator.is_(True)
        interview = course & RawBotUser.interview_reached.is_(True)
        passed = interview & RawBotUser.interview_passed.is_(True)
        offer = passed & RawBotUser.offer_received.is_(True)
        distance = offer & RawBotUser.distance_grinding.is_(True)
        contract = offer & RawBotUser.contract_signed.is_(True)
        return {
            "lead": lead,
            "platform": platform,
            "learning": learning,
            "course": course,
            "simulator": simulator,
            "interview": interview,
            "passed": passed,
            "offer": offer,
            "distance_grinding": distance,
            "contract": contract,
        }

    def _apply_filters_with_date(self, stmt, filters: ReportFilters, date_col):
        stmt = apply_excluded_bot_filter(stmt, RawBotUser.bot_key)
        msk_date_col = self._msk_date(date_col)
        if filters.start_date:
            stmt = stmt.where(msk_date_col >= filters.start_date)
        if filters.end_date:
            stmt = stmt.where(msk_date_col <= filters.end_date)
        if filters.bots:
            normalized_bots = [b.strip().lower() for b in filters.bots if isinstance(b, str) and b.strip()]
            if normalized_bots:
                stmt = stmt.where(
                    func.lower(func.trim(func.coalesce(RawBotUser.bot_key, ""))).in_(normalized_bots)
                )
        if filters.advertising_companies:
            stmt = stmt.where(RawBotUser.advertising_company.in_(filters.advertising_companies))
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_source, RawBotUser.platform_utm_source, filters.utm_source)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_campaign, RawBotUser.platform_utm_campaign, filters.utm_campaign)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_medium, RawBotUser.platform_utm_medium, filters.utm_medium)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_content, RawBotUser.platform_utm_content, filters.utm_content)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_term, RawBotUser.platform_utm_term, filters.utm_term)
        if filters.user_scope in {"new", "old"}:
            system_user = aliased(RawBotUser)
            first_seen_system_sq = (
                select(func.min(system_user.created_at))
                .where(system_user.tg_user_id == RawBotUser.tg_user_id)
                .scalar_subquery()
            )
            if filters.user_scope == "new":
                stmt = stmt.where(self._msk_date(first_seen_system_sq) == self._msk_date(RawBotUser.created_at))
            elif filters.user_scope == "old":
                stmt = stmt.where(self._msk_date(first_seen_system_sq) < self._msk_date(RawBotUser.created_at))
        return stmt

    def _apply_filters(self, stmt, filters: ReportFilters):
        stmt = self._apply_filters_with_date(stmt, filters, RawBotUser.created_at)
        return apply_employee_exclusion(stmt, RawBotUser.tg_user_id)

    @staticmethod
    def _normalized_company_sql(alias: str) -> str:
        return f"""
            CASE
                WHEN {alias}.advertising_company IS NULL
                  OR BTRIM({alias}.advertising_company) = ''
                  OR LOWER(BTRIM({alias}.advertising_company)) IN ('-', '—', '(none)', 'none', 'null', 'нет метки')
                THEN 'Без категории'
                ELSE BTRIM({alias}.advertising_company)
            END
        """

    @staticmethod
    def _bot_label_sql(alias: str) -> str:
        return f"COALESCE(NULLIF(BTRIM({alias}.bot_key), ''), 'Без бота')"

    @staticmethod
    def _build_touch_attr_filters_sql(
        alias: str,
        filters: ReportFilters,
        params: dict[str, Any],
    ) -> str:
        conditions: list[str] = []
        if filters.bots:
            normalized_bots = [b.strip() for b in filters.bots if isinstance(b, str) and b.strip()]
            if normalized_bots:
                params["filter_bots"] = normalized_bots
                conditions.append(f"{alias}.bot_key = ANY(:filter_bots)")
        if filters.advertising_companies:
            normalized_companies = [c.strip() for c in filters.advertising_companies if isinstance(c, str) and c.strip()]
            if normalized_companies:
                params["filter_advertising_companies"] = normalized_companies
                conditions.append(f"{alias}.company = ANY(:filter_advertising_companies)")

        utm_fields = (
            ("utm_source", filters.utm_source),
            ("utm_campaign", filters.utm_campaign),
            ("utm_medium", filters.utm_medium),
            ("utm_content", filters.utm_content),
            ("utm_term", filters.utm_term),
        )
        for field_name, values in utm_fields:
            normalized_values = [v.strip().lower() for v in (values or []) if isinstance(v, str) and v.strip()]
            if normalized_values:
                params[f"filter_{field_name}"] = normalized_values
                conditions.append(f"LOWER(TRIM(COALESCE({alias}.{field_name}, ''))) = ANY(:filter_{field_name})")
        return "".join(f"\n              AND {condition}" for condition in conditions)

    async def _touch_summary_rows(
        self,
        session: AsyncSession,
        filters: ReportFilters,
        group_by: str,
        touch_mode: str,
    ) -> List[dict[str, int]]:
        if group_by not in {"bot_key", "advertising_company"}:
            return []

        params: dict[str, Any] = {
            "excluded_bot_keys": normalized_excluded_bot_keys(),
            "start": filters.start_date,
            "end": filters.end_date,
            "user_scope": filters.user_scope or "all",
        }
        attr_filter_sql = self._build_touch_attr_filters_sql("a", filters, params)
        group_expr = "a.bot_key" if group_by == "bot_key" else "a.company"

        if touch_mode == "first_touch":
            attributed_cte = f"""
            attributed AS (
                SELECT DISTINCT ON (be.tg_user_id)
                    be.tg_user_id,
                    be.company,
                    be.bot_key,
                    be.utm_source,
                    be.utm_campaign,
                    be.utm_medium,
                    be.utm_content,
                    be.utm_term,
                    be.first_bot_at AS touch_at,
                    be.first_bot_at
                FROM bot_entries be
                ORDER BY be.tg_user_id, be.first_bot_at ASC, be.bot_key ASC
            )
            """
        elif touch_mode == "last_touch":
            attributed_cte = f"""
            last_touch_candidates AS (
                SELECT
                    nr.tg_user_id,
                    nr.company,
                    nr.bot_key,
                    nr.utm_source,
                    nr.utm_campaign,
                    nr.utm_medium,
                    nr.utm_content,
                    nr.utm_term,
                    nr.created_at AS touch_at,
                    be.first_bot_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY nr.tg_user_id
                        ORDER BY nr.created_at DESC, nr.bot_key ASC
                    ) AS rn
                FROM non_lead_rows nr
                JOIN user_flags uf ON uf.tg_user_id = nr.tg_user_id
                JOIN bot_entries be
                  ON be.tg_user_id = nr.tg_user_id
                 AND be.company = nr.company
                 AND be.bot_key = nr.bot_key
                WHERE uf.first_platform_at IS NOT NULL
                  AND uf.first_lesson_at IS NOT NULL
                  AND nr.created_at <= uf.first_lesson_at
            ),
            attributed AS (
                SELECT
                    ltc.tg_user_id,
                    ltc.company,
                    ltc.bot_key,
                    ltc.utm_source,
                    ltc.utm_campaign,
                    ltc.utm_medium,
                    ltc.utm_content,
                    ltc.utm_term,
                    ltc.touch_at,
                    ltc.first_bot_at
                FROM last_touch_candidates ltc
                WHERE ltc.rn = 1
            )
            """
        else:
            attributed_cte = f"""
            attributed AS (
                SELECT
                    be.tg_user_id,
                    be.company,
                    be.bot_key,
                    be.utm_source,
                    be.utm_campaign,
                    be.utm_medium,
                    be.utm_content,
                    be.utm_term,
                    be.first_bot_at AS touch_at,
                    be.first_bot_at
                FROM bot_entries be
            )
            """

        query = text(
            f"""
            WITH first_seen AS (
                SELECT
                    tg_user_id,
                    MIN(created_at) AS first_seen_at_system
                FROM raw_bot_users
                WHERE tg_user_id > 0
                  AND created_at IS NOT NULL
                  AND LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
                GROUP BY tg_user_id
            ),
            user_flags AS (
                SELECT
                    ru.tg_user_id,
                    BOOL_OR(ru.converted_to_lead IS TRUE OR LOWER(TRIM(COALESCE(ru.bot_key, ''))) LIKE 'lead%') AS did_lead,
                    BOOL_OR(ru.channel_subscribed IS TRUE) AS did_channel,
                    BOOL_OR(ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL) AS did_platform,
                    MIN(ru.ph_user_id) FILTER (
                        WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
                    ) AS ph_user_id,
                    BOOL_OR(ru.started_learning IS TRUE OR ru.learn_start_date IS NOT NULL) AS did_learning,
                    BOOL_OR(ru.completed_course IS TRUE AND ru.completed_course_at IS NOT NULL) AS did_course,
                    BOOL_OR(ru.used_simulator IS TRUE) AS did_simulator,
                    BOOL_OR(ru.interview_reached IS TRUE) AS did_interview,
                    BOOL_OR(ru.interview_passed IS TRUE) AS did_passed,
                    BOOL_OR(ru.offer_received IS TRUE) AS did_offer,
                    BOOL_OR(ru.contract_signed IS TRUE) AS did_contract,
                    BOOL_OR(ru.distance_grinding IS TRUE) AS did_distance,
                    MIN(ru.platform_registered_at) FILTER (
                        WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
                    ) AS first_platform_at,
                    MIN(ru.learn_start_date) FILTER (
                        WHERE ru.ph_user_id IS NOT NULL
                          AND ru.platform_registered_at IS NOT NULL
                          AND ru.learn_start_date IS NOT NULL
                    ) AS first_lesson_at
                FROM raw_bot_users ru
                WHERE ru.tg_user_id > 0
                GROUP BY ru.tg_user_id
            ),
            non_lead_rows AS (
                SELECT
                    r.tg_user_id,
                    {self._normalized_company_sql("r")} AS company,
                    {self._bot_label_sql("r")} AS bot_key,
                    COALESCE(r.platform_utm_source, r.utm_source, '') AS utm_source,
                    COALESCE(r.platform_utm_campaign, r.utm_campaign, '') AS utm_campaign,
                    COALESCE(r.platform_utm_medium, r.utm_medium, '') AS utm_medium,
                    COALESCE(r.platform_utm_content, r.utm_content, '') AS utm_content,
                    COALESCE(r.platform_utm_term, r.utm_term, '') AS utm_term,
                    r.created_at
                FROM raw_bot_users r
                WHERE r.tg_user_id > 0
                  AND r.created_at IS NOT NULL
                  AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND LOWER(TRIM(COALESCE(r.bot_key, ''))) NOT LIKE 'lead%'
            ),
            bot_entries AS (
                SELECT DISTINCT ON (nr.tg_user_id, nr.company, nr.bot_key)
                    nr.tg_user_id,
                    nr.company,
                    nr.bot_key,
                    nr.utm_source,
                    nr.utm_campaign,
                    nr.utm_medium,
                    nr.utm_content,
                    nr.utm_term,
                    nr.created_at AS first_bot_at
                FROM non_lead_rows nr
                ORDER BY nr.tg_user_id, nr.company, nr.bot_key, nr.created_at ASC
            ),
            {attributed_cte}
            SELECT
                {group_expr} AS group_value,
                COUNT(DISTINCT a.tg_user_id) AS entered,
                COUNT(
                    DISTINCT CASE
                        WHEN (fs.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date
                             = (a.first_bot_at AT TIME ZONE 'Europe/Moscow')::date
                        THEN a.tg_user_id
                    END
                ) AS new_in_system,
                COUNT(
                    DISTINCT CASE
                        WHEN (fs.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date
                             < (a.first_bot_at AT TIME ZONE 'Europe/Moscow')::date
                        THEN a.tg_user_id
                    END
                ) AS old_in_system,
                COUNT(DISTINCT CASE WHEN uf.did_lead THEN a.tg_user_id END) AS lead,
                COUNT(DISTINCT CASE WHEN uf.did_channel THEN a.tg_user_id END) AS subscribed,
                COUNT(DISTINCT CASE WHEN uf.did_platform THEN uf.ph_user_id END) AS platform,
                COUNT(DISTINCT CASE WHEN uf.did_learning THEN uf.ph_user_id END) AS learning,
                COUNT(DISTINCT CASE WHEN uf.did_course THEN uf.ph_user_id END) AS course,
                COUNT(DISTINCT CASE WHEN uf.did_simulator THEN uf.ph_user_id END) AS simulator,
                COUNT(DISTINCT CASE WHEN uf.did_interview THEN uf.ph_user_id END) AS interview,
                COUNT(DISTINCT CASE WHEN uf.did_passed THEN uf.ph_user_id END) AS passed,
                COUNT(DISTINCT CASE WHEN uf.did_offer THEN uf.ph_user_id END) AS offer,
                COUNT(DISTINCT CASE WHEN uf.did_contract THEN uf.ph_user_id END) AS contract,
                COUNT(DISTINCT CASE WHEN uf.did_distance THEN uf.ph_user_id END) AS distance_grinding
            FROM attributed a
            JOIN first_seen fs ON fs.tg_user_id = a.tg_user_id
            JOIN user_flags uf ON uf.tg_user_id = a.tg_user_id
            WHERE (CAST(:start AS date) IS NULL OR (a.touch_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR (a.touch_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date))
              AND (
                    :user_scope = 'all'
                    OR (
                        :user_scope = 'new'
                        AND (fs.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date
                            = (a.first_bot_at AT TIME ZONE 'Europe/Moscow')::date
                    )
                    OR (
                        :user_scope = 'old'
                        AND (fs.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date
                            < (a.first_bot_at AT TIME ZONE 'Europe/Moscow')::date
                    )
                ){attr_filter_sql}
            GROUP BY 1
            ORDER BY entered DESC, group_value
            """
        )
        result = await session.execute(query, params)
        return [
            {
                "group": row.group_value,
                "entered": int(row.entered or 0),
                "new_in_system": int(row.new_in_system or 0),
                "old_in_system": int(row.old_in_system or 0),
                "lead": int(row.lead or 0),
                "subscribed": int(row.subscribed or 0),
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
            if row.group_value
        ]

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
        effective_source = func.coalesce(RawBotUser.platform_utm_source, RawBotUser.utm_source, "—")
        effective_campaign = func.coalesce(RawBotUser.platform_utm_campaign, RawBotUser.utm_campaign, "—")
        if group_by == "source_campaign":
            label = func.concat(
                effective_source,
                " / ",
                effective_campaign,
            ).label("group_value")
        elif group_by == "utm_source":
            label = effective_source.label("group_value")
        elif group_by == "utm_campaign":
            label = effective_campaign.label("group_value")
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
        if self._can_use_weekly_bot_agg(filters):
            result = await session.execute(
                select(
                    WeeklyFunnelBotAgg.bot_key.label("bot_key"),
                    func.sum(WeeklyFunnelBotAgg.entered).label("entered"),
                    func.sum(WeeklyFunnelBotAgg.lead).label("converted"),
                )
                .group_by(WeeklyFunnelBotAgg.bot_key)
                .order_by(desc("entered"))
            )
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
        entered_count = func.count(func.distinct(RawBotUser.tg_user_id))
        converted_to_lead_condition = self._lead_transition_condition(filters)
        converted_count = func.count(func.distinct(RawBotUser.tg_user_id)).filter(
            converted_to_lead_condition
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
        stage_conditions = self._strict_stage_conditions(filters)
        platform_count = func.count(func.distinct(RawBotUser.ph_user_id)).filter(
            RawBotUser.ph_user_id.is_not(None),
            RawBotUser.platform_registered_at.is_not(None),
        )
        stmt = select(
            entered_count.label("entered"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                stage_conditions["lead"]
            ).label("lead"),
            platform_count.label("platform"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["learning"]
            ).label("learning"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["course"]
            ).label("course"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["simulator"]
            ).label("simulator"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["interview"]
            ).label("interview"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["passed"]
            ).label("passed"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["offer"]
            ).label("offer"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["contract"]
            ).label("contract"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["distance_grinding"]
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
        self, session: AsyncSession, filters: ReportFilters, group_by: str,
        touch_mode: str = "event",
    ) -> List[dict[str, int]]:
        if touch_mode in {"event", "first_touch", "last_touch"} and group_by in {"bot_key", "advertising_company"}:
            touch_rows = await self._touch_summary_rows(session, filters, group_by, touch_mode)
            if touch_rows:
                return touch_rows
        if group_by == "bot_key" and self._can_use_weekly_bot_agg(filters, touch_mode=touch_mode):
            result = await session.execute(
                select(
                    WeeklyFunnelBotAgg.bot_key.label("group_value"),
                    func.sum(WeeklyFunnelBotAgg.entered).label("entered"),
                    func.sum(WeeklyFunnelBotAgg.new_in_system).label("new_in_system"),
                    func.sum(WeeklyFunnelBotAgg.old_in_system).label("old_in_system"),
                    func.sum(WeeklyFunnelBotAgg.lead).label("lead"),
                    func.sum(WeeklyFunnelBotAgg.subscribed).label("subscribed"),
                    func.sum(WeeklyFunnelBotAgg.platform).label("platform"),
                    func.sum(WeeklyFunnelBotAgg.learning).label("learning"),
                    func.sum(WeeklyFunnelBotAgg.course).label("course"),
                    func.sum(WeeklyFunnelBotAgg.simulator).label("simulator"),
                    func.sum(WeeklyFunnelBotAgg.interview).label("interview"),
                    func.sum(WeeklyFunnelBotAgg.passed).label("passed"),
                    func.sum(WeeklyFunnelBotAgg.offer).label("offer"),
                    func.sum(WeeklyFunnelBotAgg.contract).label("contract"),
                    func.sum(WeeklyFunnelBotAgg.distance_grinding).label("distance_grinding"),
                )
                .group_by(WeeklyFunnelBotAgg.bot_key)
                .order_by(desc("entered"))
            )
            return [
                {
                    "group": row.group_value,
                    "entered": int(row.entered or 0),
                    "new_in_system": int(row.new_in_system or 0),
                    "old_in_system": int(row.old_in_system or 0),
                    "lead": int(row.lead or 0),
                    "subscribed": int(row.subscribed or 0),
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
        stage_conditions = self._strict_stage_conditions(filters)
        first_seen_system_sq = (
            select(
                RawBotUser.tg_user_id.label("tg_user_id"),
                func.min(RawBotUser.created_at).label("first_seen_at_system"),
            )
            .group_by(RawBotUser.tg_user_id)
            .subquery()
        )
        last_seen_system_sq = (
            select(
                RawBotUser.tg_user_id.label("tg_user_id"),
                func.max(RawBotUser.created_at).label("last_seen_at_system"),
            )
            .group_by(RawBotUser.tg_user_id)
            .subquery()
        )
        last_touch_date_sq = (
            select(
                RawBotUser.tg_user_id.label("tg_user_id"),
                func.max(RawBotUser.learn_start_date).label("last_touch_date"),
            )
            .where(RawBotUser.learn_start_date.is_not(None))
            .where(func.lower(func.trim(func.coalesce(RawBotUser.bot_key, ""))).notin_(normalized_excluded_bot_keys()))
            .group_by(RawBotUser.tg_user_id)
            .subquery()
        )

        # Subqueries: for each user find advertising_company of their first/last touch bot
        # by self-joining raw_bot_users on (tg_user_id, bot_key=first_touch_bot)
        FtBotUser = aliased(RawBotUser)
        LtBotUser = aliased(RawBotUser)
        ft_company_sq = (
            select(
                RawBotUser.tg_user_id.label("tg_user_id"),
                func.max(FtBotUser.advertising_company).label("ft_company"),
            )
            .join(FtBotUser, (FtBotUser.tg_user_id == RawBotUser.tg_user_id) & (FtBotUser.bot_key == RawBotUser.first_touch_bot))
            .where(
                RawBotUser.first_touch_bot.is_not(None),
                func.trim(func.coalesce(RawBotUser.first_touch_bot, "")) != "",
                func.lower(func.trim(func.coalesce(RawBotUser.first_touch_bot, ""))) != "нет метки",
            )
            .group_by(RawBotUser.tg_user_id)
            .subquery()
        )
        lt_company_sq = (
            select(
                RawBotUser.tg_user_id.label("tg_user_id"),
                func.max(LtBotUser.advertising_company).label("lt_company"),
            )
            .join(LtBotUser, (LtBotUser.tg_user_id == RawBotUser.tg_user_id) & (LtBotUser.bot_key == RawBotUser.last_touch_bot))
            .where(
                RawBotUser.last_touch_bot.is_not(None),
                func.lower(func.trim(func.coalesce(RawBotUser.last_touch_bot, ""))).notin_(normalized_excluded_bot_keys()),
                func.lower(func.trim(func.coalesce(LtBotUser.bot_key, ""))).notin_(normalized_excluded_bot_keys()),
            )
            .group_by(RawBotUser.tg_user_id)
            .subquery()
        )

        touch_filter = None
        use_ft_company_join = False
        use_lt_company_join = False
        use_last_touch_date_join = False
        if group_by == "advertising_company":
            if touch_mode == "first_touch":
                label = func.coalesce(ft_company_sq.c.ft_company, "нет метки").label("group_value")
                touch_filter = (
                    RawBotUser.first_touch_bot.is_not(None)
                    & (func.trim(func.coalesce(RawBotUser.first_touch_bot, "")) != "")
                    & (func.lower(func.trim(func.coalesce(RawBotUser.first_touch_bot, ""))) != "нет метки")
                )
                use_ft_company_join = True
            elif touch_mode == "last_touch":
                label = func.coalesce(lt_company_sq.c.lt_company, "нет метки").label("group_value")
                touch_filter = (
                    RawBotUser.last_touch_bot.is_not(None)
                    & func.lower(func.trim(func.coalesce(RawBotUser.last_touch_bot, ""))).notin_(normalized_excluded_bot_keys())
                    & last_touch_date_sq.c.last_touch_date.is_not(None)
                )
                use_lt_company_join = True
                use_last_touch_date_join = True
            else:
                label = func.coalesce(RawBotUser.advertising_company, "—").label("group_value")
        elif touch_mode == "first_touch":
            label = func.coalesce(RawBotUser.first_touch_bot, "—").label("group_value")
            touch_filter = (
                RawBotUser.first_touch_bot.is_not(None)
                & (func.trim(func.coalesce(RawBotUser.first_touch_bot, "")) != "")
                & (func.lower(func.trim(func.coalesce(RawBotUser.first_touch_bot, ""))) != "нет метки")
            )
        elif touch_mode == "last_touch":
            label = func.coalesce(RawBotUser.last_touch_bot, "—").label("group_value")
            touch_filter = (
                RawBotUser.last_touch_bot.is_not(None)
                & func.lower(func.trim(func.coalesce(RawBotUser.last_touch_bot, ""))).notin_(normalized_excluded_bot_keys())
                & last_touch_date_sq.c.last_touch_date.is_not(None)
            )
            use_last_touch_date_join = True
        else:
            label = RawBotUser.bot_key.label("group_value")

        # For first/last_touch modes, date filtering should use registration date
        # in the attributed touch bot (created_at for that bot).
        touch_bot_first_seen_col = None
        if touch_mode == "first_touch":
            FtFirstBotUser = aliased(RawBotUser)
            touch_bot_first_seen_col = (
                select(func.min(FtFirstBotUser.created_at))
                .where(
                    FtFirstBotUser.tg_user_id == RawBotUser.tg_user_id,
                    FtFirstBotUser.bot_key == RawBotUser.first_touch_bot,
                )
                .scalar_subquery()
            )
            touch_date_col = touch_bot_first_seen_col
        elif touch_mode == "last_touch":
            LtFirstBotUser = aliased(RawBotUser)
            touch_bot_first_seen_col = (
                select(func.min(LtFirstBotUser.created_at))
                .where(
                    LtFirstBotUser.tg_user_id == RawBotUser.tg_user_id,
                    LtFirstBotUser.bot_key == RawBotUser.last_touch_bot,
                )
                .scalar_subquery()
            )
            touch_date_col = touch_bot_first_seen_col
        else:
            touch_date_col = None

        new_in_system_filter = self._msk_date(first_seen_system_sq.c.first_seen_at_system) == self._msk_date(RawBotUser.created_at)
        old_in_system_filter = self._msk_date(first_seen_system_sq.c.first_seen_at_system) < self._msk_date(RawBotUser.created_at)
        if touch_bot_first_seen_col is not None:
            # In touch modes, split new/old by first entry into the touch-attributed bot.
            new_in_system_filter = (
                self._msk_date(first_seen_system_sq.c.first_seen_at_system) == self._msk_date(touch_bot_first_seen_col)
            )
            old_in_system_filter = (
                self._msk_date(first_seen_system_sq.c.first_seen_at_system) < self._msk_date(touch_bot_first_seen_col)
            )

        stmt = select(
            label,
            func.count(func.distinct(RawBotUser.tg_user_id)).label("entered"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                new_in_system_filter
            ).label("new_in_system"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                old_in_system_filter
            ).label("old_in_system"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                stage_conditions["lead"]
            ).label("lead"),
            func.count(func.distinct(RawBotUser.tg_user_id)).filter(
                RawBotUser.channel_subscribed.is_(True)
            ).label("subscribed"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                RawBotUser.ph_user_id.is_not(None),
                RawBotUser.platform_registered_at.is_not(None),
            ).label("platform"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["learning"]
            ).label("learning"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["course"]
            ).label("course"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["simulator"]
            ).label("simulator"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["interview"]
            ).label("interview"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["passed"]
            ).label("passed"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["offer"]
            ).label("offer"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["contract"]
            ).label("contract"),
            func.count(func.distinct(RawBotUser.ph_user_id)).filter(
                stage_conditions["distance_grinding"]
            ).label("distance_grinding"),
        ).join(
            first_seen_system_sq,
            first_seen_system_sq.c.tg_user_id == RawBotUser.tg_user_id,
        ).join(
            last_seen_system_sq,
            last_seen_system_sq.c.tg_user_id == RawBotUser.tg_user_id,
        )
        if use_ft_company_join:
            stmt = stmt.outerjoin(
                ft_company_sq,
                ft_company_sq.c.tg_user_id == RawBotUser.tg_user_id,
            )
        if use_lt_company_join:
            stmt = stmt.outerjoin(
                lt_company_sq,
                lt_company_sq.c.tg_user_id == RawBotUser.tg_user_id,
            )
        if use_last_touch_date_join:
            stmt = stmt.outerjoin(
                last_touch_date_sq,
                last_touch_date_sq.c.tg_user_id == RawBotUser.tg_user_id,
            )
        stmt = stmt.group_by(label)
        if touch_filter is not None:
            stmt = stmt.where(touch_filter)
        if touch_date_col is not None:
            # Date filter by first/last touch date, rest of filters applied normally
            touch_date_msk = self._msk_date(touch_date_col)
            if filters.start_date:
                stmt = stmt.where(touch_date_msk >= filters.start_date)
            if filters.end_date:
                stmt = stmt.where(touch_date_msk <= filters.end_date)
            # Apply non-date filters via helper (pass no dates so it skips them).
            # user_scope for touch modes must be evaluated against touch_date_col
            # (not raw created_at), so apply it separately below.
            filters_no_date = ReportFilters(
                start_date=None, end_date=None,
                bots=filters.bots, advertising_companies=filters.advertising_companies,
                utm_source=filters.utm_source, utm_campaign=filters.utm_campaign,
                utm_medium=filters.utm_medium, utm_content=filters.utm_content,
                utm_term=filters.utm_term, user_scope=None,
            )
            stmt = self._apply_filters(stmt, filters_no_date)
            if filters.user_scope == "new":
                if touch_bot_first_seen_col is not None:
                    stmt = stmt.where(
                        self._msk_date(first_seen_system_sq.c.first_seen_at_system) == self._msk_date(touch_bot_first_seen_col)
                    )
                else:
                    stmt = stmt.where(first_seen_system_sq.c.first_seen_at_system == touch_date_col)
            elif filters.user_scope == "old":
                if touch_bot_first_seen_col is not None:
                    stmt = stmt.where(
                        self._msk_date(first_seen_system_sq.c.first_seen_at_system) < self._msk_date(touch_bot_first_seen_col)
                    )
                else:
                    stmt = stmt.where(first_seen_system_sq.c.first_seen_at_system < touch_date_col)
        else:
            stmt = self._apply_filters(stmt, filters)
        stmt = stmt.order_by(desc("entered"))
        result = await session.execute(stmt)
        return [
            {
                "group": row.group_value,
                "entered": int(row.entered or 0),
                "new_in_system": int(row.new_in_system or 0),
                "old_in_system": int(row.old_in_system or 0),
                "lead": int(row.lead or 0),
                "subscribed": int(row.subscribed or 0),
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
        group_by_bot: bool = False,
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
        channel_id = channel_id or settings.telegram_channel_id
        community_id = community_id or settings.telegram_community_id
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

        conditions = []
        conditions.append(func.lower(func.trim(func.coalesce(TgSubsDailyAgg.bot_key, ""))).notin_(normalized_excluded_bot_keys()))
        if start_date_obj:
            conditions.append(TgSubsDailyAgg.day >= start_date_obj)
        if end_date_obj:
            conditions.append(TgSubsDailyAgg.day <= end_date_obj)
        if bots:
            conditions.append(TgSubsDailyAgg.bot_key.in_(bots))
        if advertising_companies:
            conditions.append(TgSubsDailyAgg.advertising_company.in_(advertising_companies))
        if utm_source:
            conditions.append(TgSubsDailyAgg.utm_source.in_(utm_source))
        if utm_campaign:
            conditions.append(TgSubsDailyAgg.utm_campaign.in_(utm_campaign))
        if utm_medium:
            conditions.append(TgSubsDailyAgg.utm_medium.in_(utm_medium))
        if utm_content:
            conditions.append(TgSubsDailyAgg.utm_content.in_(utm_content))
        if utm_term:
            conditions.append(TgSubsDailyAgg.utm_term.in_(utm_term))
        if group_by_campaign and active_companies:
            conditions.append(TgSubsDailyAgg.advertising_company.in_(active_companies))
        # group_by_bot: no company filter — show all registry bots

        period_expr = TgSubsDailyAgg.day if interval == "day" else func.date_trunc("week", TgSubsDailyAgg.day).cast(Date)
        if group_by_campaign:
            campaign_expr = TgSubsDailyAgg.advertising_company
            bot_expr = TgSubsDailyAgg.bot_key
        elif group_by_bot:
            campaign_expr = literal("")
            bot_expr = TgSubsDailyAgg.bot_key
        else:
            campaign_expr = literal("")
            bot_expr = literal("")

        snapshot_map: dict[tuple[str, str], dict[str, int]] = {}
        events_map: dict[tuple[str, str, dt_date], dict[str, int]] = {}
        subs_map: dict[tuple[str, str, dt_date], dict[str, int]] = {}
        overall_events_map: dict[dt_date, dict[str, int]] = {}
        overall_subs_map: dict[dt_date, dict[str, int]] = {}
        summary: dict[str, dict[str, int]] = {
            "channel": {"active": 0, "subscribed": 0, "unsubscribed": 0},
            "saloon": {"active": 0, "subscribed": 0, "unsubscribed": 0},
        }
        channel_funnel: list[dict[str, object]] = []
        channel_report_weekly: list[dict[str, object]] = []
        if channel_id or community_id:
            snapshot_params: dict[str, object] = {}
            date_filter = ""
            channel_filter_sql = "1=0"
            community_filter_sql = "1=0"
            if channel_id:
                channel_filter_sql = "e.channel_id = :channel_id"
                snapshot_params["channel_id"] = str(channel_id)
            if community_id:
                community_filter_sql = "e.channel_id = :community_id"
                snapshot_params["community_id"] = str(community_id)

            snapshot_sql = text(
                f"""
                WITH user_dim AS (
                    SELECT
                        tg_user_id,
                    COALESCE(MAX(advertising_company), '') AS advertising_company,
                    COALESCE(MAX(bot_key), '') AS bot_key
                    FROM raw_bot_users
                    WHERE tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                    GROUP BY tg_user_id
                ),
                last_status AS (
                    SELECT DISTINCT ON (tg_user_id, channel_id)
                        tg_user_id,
                        channel_id,
                        status
                    FROM telegram_subscription_events e
                    WHERE ({channel_filter_sql} OR {community_filter_sql})
                    {date_filter}
                    ORDER BY tg_user_id, channel_id, checked_at DESC
                )
                SELECT
                    ud.advertising_company AS campaign,
                    ud.bot_key AS bot_key,
                    COUNT(*) FILTER (WHERE ls.channel_id = :channel_id AND ls.status = 'subscribed') AS channel_total,
                    COUNT(*) FILTER (WHERE ls.channel_id = :community_id AND ls.status = 'subscribed') AS saloon_total
                FROM last_status ls
                JOIN user_dim ud ON ud.tg_user_id = ls.tg_user_id
                GROUP BY ud.advertising_company, ud.bot_key
                """
            )
            snapshot_rows = (await session.execute(snapshot_sql, snapshot_params)).all()
            for row in snapshot_rows:
                key = (row.campaign or "", row.bot_key or "")
                snapshot_map[key] = {
                    "channel_total": int(row.channel_total or 0),
                    "saloon_total": int(row.saloon_total or 0),
                }

            summary_params: dict[str, object] = {"channel_id": str(channel_id), "community_id": str(community_id)}
            dim_filters = []
            if bots:
                dim_filters.append("ud.bot_key = ANY(:bots)")
                summary_params["bots"] = bots
            if advertising_companies:
                dim_filters.append("ud.advertising_company = ANY(:advertising_companies)")
                summary_params["advertising_companies"] = advertising_companies
            if utm_source:
                dim_filters.append("ud.utm_source = ANY(:utm_source)")
                summary_params["utm_source"] = utm_source
            if utm_campaign:
                dim_filters.append("ud.utm_campaign = ANY(:utm_campaign)")
                summary_params["utm_campaign"] = utm_campaign
            if utm_medium:
                dim_filters.append("ud.utm_medium = ANY(:utm_medium)")
                summary_params["utm_medium"] = utm_medium
            if utm_content:
                dim_filters.append("ud.utm_content = ANY(:utm_content)")
                summary_params["utm_content"] = utm_content
            if utm_term:
                dim_filters.append("ud.utm_term = ANY(:utm_term)")
                summary_params["utm_term"] = utm_term
            dim_where = " AND ".join(dim_filters)
            if dim_where:
                dim_where = "AND " + dim_where

            period_filters = []
            if start_date_obj:
                period_filters.append("e.checked_at::date >= :start_date")
                summary_params["start_date"] = start_date_obj
            if end_date_obj:
                period_filters.append("e.checked_at::date <= :end_date")
                summary_params["end_date"] = end_date_obj
            if dim_filters:
                period_filters.extend(dim_filters)
            period_where = " AND ".join(period_filters)
            if period_where:
                period_where = "AND " + period_where

            membership_period_filters = ["m.joined_at IS NOT NULL"]
            if start_date_obj:
                membership_period_filters.append("m.joined_at::date >= :start_date")
            if end_date_obj:
                membership_period_filters.append("m.joined_at::date <= :end_date")
            if dim_filters:
                membership_period_filters.extend(dim_filters)
            membership_period_where = " AND ".join(membership_period_filters)
            if membership_period_where:
                membership_period_where = "AND " + membership_period_where

            active_sql = text(
                f"""
                WITH user_dim AS (
                    SELECT
                        tg_user_id,
                        COALESCE(MAX(advertising_company), '') AS advertising_company,
                        COALESCE(MAX(bot_key), '') AS bot_key,
                        COALESCE(MAX(utm_source), '') AS utm_source,
                        COALESCE(MAX(utm_campaign), '') AS utm_campaign,
                        COALESCE(MAX(utm_medium), '') AS utm_medium,
                        COALESCE(MAX(utm_content), '') AS utm_content,
                        COALESCE(MAX(utm_term), '') AS utm_term
                    FROM raw_bot_users
                    WHERE tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                    GROUP BY tg_user_id
                )
                SELECT
                    COUNT(DISTINCT r.tg_user_id) FILTER (WHERE r.channel_subscribed IS TRUE) AS channel_active,
                    COUNT(DISTINCT r.tg_user_id) FILTER (WHERE r.community_member IS TRUE) AS saloon_active
                FROM raw_bot_users r
                JOIN user_dim ud ON ud.tg_user_id = r.tg_user_id
                WHERE 1=1
                  AND r.tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                {dim_where}
                """
            )
            active_row = (await session.execute(active_sql, summary_params)).one()

            summary_subs_sql = text(
                f"""
                WITH user_dim AS (
                    SELECT
                        tg_user_id,
                        COALESCE(MAX(advertising_company), '') AS advertising_company,
                        COALESCE(MAX(bot_key), '') AS bot_key,
                        COALESCE(MAX(utm_source), '') AS utm_source,
                        COALESCE(MAX(utm_campaign), '') AS utm_campaign,
                        COALESCE(MAX(utm_medium), '') AS utm_medium,
                        COALESCE(MAX(utm_content), '') AS utm_content,
                        COALESCE(MAX(utm_term), '') AS utm_term
                    FROM raw_bot_users
                    WHERE tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                    GROUP BY tg_user_id
                )
                SELECT
                    COUNT(DISTINCT m.tg_user_id) FILTER (WHERE m.chat_id = :channel_id) AS channel_subscribed,
                    COUNT(DISTINCT m.tg_user_id) FILTER (WHERE m.chat_id = :community_id) AS saloon_subscribed
                FROM telegram_chat_memberships m
                JOIN user_dim ud ON ud.tg_user_id = m.tg_user_id
                WHERE (m.chat_id = :channel_id OR m.chat_id = :community_id)
                {membership_period_where}
                """
            )
            summary_subs_row = (await session.execute(summary_subs_sql, summary_params)).one()
            summary_unsub_sql = text(
                f"""
                WITH user_dim AS (
                    SELECT
                        tg_user_id,
                        COALESCE(MAX(advertising_company), '') AS advertising_company,
                        COALESCE(MAX(bot_key), '') AS bot_key,
                        COALESCE(MAX(utm_source), '') AS utm_source,
                        COALESCE(MAX(utm_campaign), '') AS utm_campaign,
                        COALESCE(MAX(utm_medium), '') AS utm_medium,
                        COALESCE(MAX(utm_content), '') AS utm_content,
                        COALESCE(MAX(utm_term), '') AS utm_term
                    FROM raw_bot_users
                    WHERE tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                    GROUP BY tg_user_id
                )
                SELECT
                    COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.channel_id = :channel_id AND e.status = 'unsubscribed') AS channel_unsubscribed,
                    COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.channel_id = :community_id AND e.status = 'unsubscribed') AS saloon_unsubscribed
                FROM telegram_subscription_events e
                JOIN user_dim ud ON ud.tg_user_id = e.tg_user_id
                WHERE (e.channel_id = :channel_id OR e.channel_id = :community_id)
                  AND e.source <> 'bot_poll'
                {period_where}
                """
            )
            summary_unsub_row = (await session.execute(summary_unsub_sql, summary_params)).one()

            # Runtime totals from telegram_chat_totals + "not in bot" from memberships.
            membership_params: dict[str, object] = {
                "channel_id": str(channel_id) if channel_id else "",
                "community_id": str(community_id) if community_id else "",
            }
            membership_sql = text("""
                WITH totals AS (
                    SELECT
                        MAX(participants_count) FILTER (WHERE chat_id = :channel_id) AS channel_total_all,
                        MAX(participants_count) FILTER (WHERE chat_id = :community_id) AS saloon_total_all
                    FROM telegram_chat_totals
                ),
                membership AS (
                    SELECT
                        COUNT(*) FILTER (WHERE chat_id = :channel_id   AND is_member = true
                            AND tg_user_id NOT IN (SELECT tg_user_id FROM raw_bot_users)) AS channel_not_in_bot,
                        COUNT(*) FILTER (WHERE chat_id = :community_id AND is_member = true
                            AND tg_user_id NOT IN (SELECT tg_user_id FROM raw_bot_users)) AS saloon_not_in_bot
                    FROM telegram_chat_memberships
                )
                SELECT
                    COALESCE(t.channel_total_all, 0) AS channel_total_all,
                    COALESCE(t.saloon_total_all, 0) AS saloon_total_all,
                    COALESCE(m.channel_not_in_bot, 0) AS channel_not_in_bot,
                    COALESCE(m.saloon_not_in_bot, 0) AS saloon_not_in_bot
                FROM totals t
                CROSS JOIN membership m
            """)
            membership_row = (await session.execute(membership_sql, membership_params)).one()

            summary = {
                "channel": {
                    "active": int(active_row.channel_active or 0),
                    "subscribed": int(summary_subs_row.channel_subscribed or 0),
                    "unsubscribed": int(summary_unsub_row.channel_unsubscribed or 0),
                    "total_in_channel": int(membership_row.channel_total_all or 0),
                    "not_in_bot": int(membership_row.channel_not_in_bot or 0),
                },
                "saloon": {
                    "active": int(active_row.saloon_active or 0),
                    "subscribed": int(summary_subs_row.saloon_subscribed or 0),
                    "unsubscribed": int(summary_unsub_row.saloon_unsubscribed or 0),
                    "total_in_channel": int(membership_row.saloon_total_all or 0),
                    "not_in_bot": int(membership_row.saloon_not_in_bot or 0),
                },
            }

            funnel_params: dict[str, object] = {
                "channel_id": str(channel_id) if channel_id else "",
                "community_id": str(community_id) if community_id else "",
                "start_date": start_date_obj,
                "end_date": end_date_obj,
            }
            funnel_sql = text("""
                WITH membership_dim AS (
                    SELECT
                        chat_id,
                        tg_user_id,
                        MIN(joined_at) AS joined_at
                    FROM telegram_chat_memberships
                    WHERE joined_at IS NOT NULL
                      AND (chat_id = :channel_id OR chat_id = :community_id)
                    GROUP BY chat_id, tg_user_id
                ),
                raw_users AS (
                    SELECT DISTINCT tg_user_id
                    FROM raw_bot_users
                    WHERE tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                ),
                milestones AS (
                    SELECT
                        ru.tg_user_id,
                        MIN(ru.platform_registered_at) FILTER (
                            WHERE ru.registered_platform IS TRUE
                              AND ru.platform_registered_at IS NOT NULL
                        ) AS platform_registered_at,
                        MIN(ru.learn_start_date) FILTER (
                            WHERE ru.learn_start_date IS NOT NULL
                        ) AS learn_start_date,
                        MIN(ru.completed_course_at) FILTER (
                            WHERE ru.completed_course IS TRUE
                              AND ru.completed_course_at IS NOT NULL
                              AND ru.created_at IS NOT NULL
                              AND ru.completed_course_at >= ru.created_at
                        ) AS completed_course_at,
                        MIN(
                            COALESCE(
                                ru.completed_course_at,
                                ru.learn_start_date,
                                ru.platform_registered_at,
                                ru.created_at
                            )
                        ) FILTER (
                            WHERE ru.contract_signed IS TRUE
                        ) AS contract_stage_at
                    FROM raw_bot_users ru
                    WHERE ru.tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                    GROUP BY ru.tg_user_id
                ),
                totals AS (
                    SELECT
                        chat_id,
                        MAX(participants_count) AS participants_count
                    FROM telegram_chat_totals
                    WHERE chat_id IN (:channel_id, :community_id)
                    GROUP BY chat_id
                )
                SELECT
                    md.chat_id,
                    COALESCE(t.participants_count, 0) AS total_in_channel,
                    COUNT(DISTINCT CASE WHEN ru.tg_user_id IS NOT NULL THEN md.tg_user_id END) AS in_bot,
                    COUNT(DISTINCT CASE
                        WHEN m.platform_registered_at IS NOT NULL
                         AND (CAST(:start_date AS DATE) IS NULL OR m.platform_registered_at::date >= CAST(:start_date AS DATE))
                         AND (CAST(:end_date AS DATE) IS NULL OR m.platform_registered_at::date <= CAST(:end_date AS DATE))
                         AND md.joined_at <= m.platform_registered_at
                        THEN md.tg_user_id END) AS registrations,
                    COUNT(DISTINCT CASE
                        WHEN m.learn_start_date IS NOT NULL
                         AND (CAST(:start_date AS DATE) IS NULL OR m.learn_start_date::date >= CAST(:start_date AS DATE))
                         AND (CAST(:end_date AS DATE) IS NULL OR m.learn_start_date::date <= CAST(:end_date AS DATE))
                         AND md.joined_at <= m.learn_start_date
                        THEN md.tg_user_id END) AS started_learning,
                    COUNT(DISTINCT CASE
                        WHEN m.completed_course_at IS NOT NULL
                         AND (CAST(:start_date AS DATE) IS NULL OR m.completed_course_at::date >= CAST(:start_date AS DATE))
                         AND (CAST(:end_date AS DATE) IS NULL OR m.completed_course_at::date <= CAST(:end_date AS DATE))
                         AND md.joined_at <= m.completed_course_at
                        THEN md.tg_user_id END) AS completed_course,
                    COUNT(DISTINCT CASE
                        WHEN m.contract_stage_at IS NOT NULL
                         AND (CAST(:start_date AS DATE) IS NULL OR m.contract_stage_at::date >= CAST(:start_date AS DATE))
                         AND (CAST(:end_date AS DATE) IS NULL OR m.contract_stage_at::date <= CAST(:end_date AS DATE))
                         AND md.joined_at <= m.contract_stage_at
                        THEN md.tg_user_id END) AS contract_signed
                FROM membership_dim md
                LEFT JOIN raw_users ru ON ru.tg_user_id = md.tg_user_id
                LEFT JOIN milestones m ON m.tg_user_id = md.tg_user_id
                LEFT JOIN totals t ON t.chat_id = md.chat_id
                GROUP BY md.chat_id, t.participants_count
                ORDER BY md.chat_id
            """)
            funnel_rows = (await session.execute(funnel_sql, funnel_params)).all()
            label_map = {
                str(channel_id): "Карточный домик",
                str(community_id): "Салун",
            }
            channel_key_map = {
                str(channel_id): "card_house",
                str(community_id): "saloon",
            }

            budget_stmt = select(func.coalesce(func.sum(BudgetWeekly.amount), 0.0))
            budget_stmt = budget_stmt.where(
                func.lower(func.coalesce(BudgetWeekly.channel_key, "")).in_(["card_house", "saloon"])
            )
            if start_date_obj:
                budget_stmt = budget_stmt.where(func.coalesce(BudgetWeekly.period_end, BudgetWeekly.week_start) >= start_date_obj)
            if end_date_obj:
                budget_stmt = budget_stmt.where(BudgetWeekly.week_start <= end_date_obj)
            if utm_source:
                budget_stmt = budget_stmt.where(func.coalesce(BudgetWeekly.utm_source, "").in_(utm_source))
            if utm_campaign:
                budget_stmt = budget_stmt.where(func.coalesce(BudgetWeekly.utm_campaign, "").in_(utm_campaign))
            if utm_medium:
                budget_stmt = budget_stmt.where(func.coalesce(BudgetWeekly.utm_medium, "").in_(utm_medium))
            if utm_content:
                budget_stmt = budget_stmt.where(func.coalesce(BudgetWeekly.utm_content, "").in_(utm_content))
            if utm_term:
                budget_stmt = budget_stmt.where(func.coalesce(BudgetWeekly.utm_term, "").in_(utm_term))
            budget_total = float((await session.execute(budget_stmt)).scalar() or 0.0)

            channel_budget_stmt = (
                select(
                    BudgetWeekly.channel_key.label("channel_key"),
                    func.coalesce(func.sum(BudgetWeekly.amount), 0.0).label("amount"),
                )
                .where(func.lower(func.coalesce(BudgetWeekly.channel_key, "")).in_(["card_house", "saloon"]))
                .group_by(BudgetWeekly.channel_key)
            )
            if start_date_obj:
                channel_budget_stmt = channel_budget_stmt.where(
                    func.coalesce(BudgetWeekly.period_end, BudgetWeekly.week_start) >= start_date_obj
                )
            if end_date_obj:
                channel_budget_stmt = channel_budget_stmt.where(BudgetWeekly.week_start <= end_date_obj)
            if utm_source:
                channel_budget_stmt = channel_budget_stmt.where(func.coalesce(BudgetWeekly.utm_source, "").in_(utm_source))
            if utm_campaign:
                channel_budget_stmt = channel_budget_stmt.where(func.coalesce(BudgetWeekly.utm_campaign, "").in_(utm_campaign))
            if utm_medium:
                channel_budget_stmt = channel_budget_stmt.where(func.coalesce(BudgetWeekly.utm_medium, "").in_(utm_medium))
            if utm_content:
                channel_budget_stmt = channel_budget_stmt.where(func.coalesce(BudgetWeekly.utm_content, "").in_(utm_content))
            if utm_term:
                channel_budget_stmt = channel_budget_stmt.where(func.coalesce(BudgetWeekly.utm_term, "").in_(utm_term))
            channel_budget_rows = (await session.execute(channel_budget_stmt)).all()
            explicit_channel_budget: dict[str, float] = {}
            for b_row in channel_budget_rows:
                key = (b_row.channel_key or "").strip().lower()
                amount = float(b_row.amount or 0.0)
                if key:
                    explicit_channel_budget[key] = explicit_channel_budget.get(key, 0.0) + amount

            funnel_stats: list[dict[str, Any]] = []
            for row in funnel_rows:
                funnel_stats.append(
                    {
                        "row": row,
                    }
                )

            def _safe_cost(spend_value: float, cnt: int) -> float | None:
                if cnt <= 0:
                    return None
                return round(spend_value / cnt, 2)

            for item in funnel_stats:
                row = item["row"]
                total_in_channel = int(row.total_in_channel or 0)
                in_bot = int(row.in_bot or 0)
                registrations = int(row.registrations or 0)
                started_learning = int(row.started_learning or 0)
                completed_course = int(row.completed_course or 0)
                contract_signed = int(row.contract_signed or 0)
                channel_key = channel_key_map.get(str(row.chat_id), "")
                explicit_budget = explicit_channel_budget.get(channel_key, 0.0)
                allocated_budget = explicit_budget
                channel_funnel.append(
                    {
                        "chat_id": str(row.chat_id),
                        "label": label_map.get(str(row.chat_id), str(row.chat_id)),
                        "channel_key": channel_key,
                        "total_in_channel": total_in_channel,
                        "in_bot": in_bot,
                        "registrations": registrations,
                        "started_learning": started_learning,
                        "completed_course": completed_course,
                        "contract_signed": contract_signed,
                        "pct_in_bot": self._pct(in_bot, total_in_channel),
                        "pct_registration": self._pct(registrations, in_bot),
                        "pct_learning": self._pct(started_learning, registrations),
                        "pct_completed": self._pct(completed_course, started_learning),
                        "pct_contract": self._pct(contract_signed, completed_course),
                        "budget": round(allocated_budget, 2),
                        "start_in_bot_cost": _safe_cost(allocated_budget, in_bot),
                        "registration_cost": _safe_cost(allocated_budget, registrations),
                        "started_learning_cost": _safe_cost(allocated_budget, started_learning),
                        "completed_course_cost": _safe_cost(allocated_budget, completed_course),
                        "contract_cost": _safe_cost(allocated_budget, contract_signed),
                    }
                )

            weekly_report_sql = text("""
                WITH user_dim AS (
                    SELECT
                        tg_user_id,
                        COALESCE(MAX(advertising_company), '') AS advertising_company,
                        COALESCE(MAX(bot_key), '') AS bot_key,
                        COALESCE(MAX(utm_source), '') AS utm_source,
                        COALESCE(MAX(utm_campaign), '') AS utm_campaign,
                        COALESCE(MAX(utm_medium), '') AS utm_medium,
                        COALESCE(MAX(utm_content), '') AS utm_content,
                        COALESCE(MAX(utm_term), '') AS utm_term
                    FROM raw_bot_users
                    WHERE tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                    GROUP BY tg_user_id
                ),
                membership_dim AS (
                    SELECT
                        m.chat_id,
                        m.tg_user_id,
                        MIN(m.joined_at) AS joined_at
                    FROM telegram_chat_memberships m
                    JOIN user_dim ud ON ud.tg_user_id = m.tg_user_id
                    WHERE m.joined_at IS NOT NULL
                      AND (m.chat_id = :channel_id OR m.chat_id = :community_id)
                      AND (CAST(:start_date AS DATE) IS NULL OR m.joined_at::date >= CAST(:start_date AS DATE))
                      AND (CAST(:end_date AS DATE) IS NULL OR m.joined_at::date <= CAST(:end_date AS DATE))
                      AND (CAST(:bots AS TEXT[]) IS NULL OR ud.bot_key = ANY(:bots))
                      AND (CAST(:advertising_companies AS TEXT[]) IS NULL OR ud.advertising_company = ANY(:advertising_companies))
                      AND (CAST(:utm_source AS TEXT[]) IS NULL OR ud.utm_source = ANY(:utm_source))
                      AND (CAST(:utm_campaign AS TEXT[]) IS NULL OR ud.utm_campaign = ANY(:utm_campaign))
                      AND (CAST(:utm_medium AS TEXT[]) IS NULL OR ud.utm_medium = ANY(:utm_medium))
                      AND (CAST(:utm_content AS TEXT[]) IS NULL OR ud.utm_content = ANY(:utm_content))
                      AND (CAST(:utm_term AS TEXT[]) IS NULL OR ud.utm_term = ANY(:utm_term))
                    GROUP BY m.chat_id, m.tg_user_id
                ),
                milestones AS (
                    SELECT
                        ru.tg_user_id,
                        MIN(ru.platform_registered_at) FILTER (
                            WHERE ru.registered_platform IS TRUE
                              AND ru.platform_registered_at IS NOT NULL
                        ) AS platform_registered_at,
                        MIN(ru.learn_start_date) FILTER (
                            WHERE ru.learn_start_date IS NOT NULL
                        ) AS learn_start_date,
                        MIN(ru.completed_course_at) FILTER (
                            WHERE ru.completed_course IS TRUE
                              AND ru.completed_course_at IS NOT NULL
                              AND ru.created_at IS NOT NULL
                              AND ru.completed_course_at >= ru.created_at
                        ) AS completed_course_at,
                        MIN(
                            COALESCE(
                                ru.completed_course_at,
                                ru.learn_start_date,
                                ru.platform_registered_at,
                                ru.created_at
                            )
                        ) FILTER (WHERE ru.contract_signed IS TRUE) AS contract_stage_at
                    FROM raw_bot_users ru
                    WHERE ru.tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                    GROUP BY ru.tg_user_id
                ),
                staged AS (
                    SELECT
                        DATE_TRUNC('week', md.joined_at)::date AS week_start,
                        md.chat_id,
                        COUNT(DISTINCT md.tg_user_id) AS in_bot,
                        0::bigint AS registrations,
                        0::bigint AS started_learning,
                        0::bigint AS completed_course,
                        0::bigint AS contract_signed
                    FROM membership_dim md
                    GROUP BY DATE_TRUNC('week', md.joined_at)::date, md.chat_id

                    UNION ALL

                    SELECT
                        DATE_TRUNC('week', m.platform_registered_at)::date AS week_start,
                        md.chat_id,
                        0::bigint,
                        COUNT(DISTINCT md.tg_user_id) AS registrations,
                        0::bigint,
                        0::bigint,
                        0::bigint
                    FROM membership_dim md
                    JOIN milestones m ON m.tg_user_id = md.tg_user_id
                    WHERE m.platform_registered_at IS NOT NULL
                      AND md.joined_at <= m.platform_registered_at
                      AND (CAST(:start_date AS DATE) IS NULL OR m.platform_registered_at::date >= CAST(:start_date AS DATE))
                      AND (CAST(:end_date AS DATE) IS NULL OR m.platform_registered_at::date <= CAST(:end_date AS DATE))
                    GROUP BY DATE_TRUNC('week', m.platform_registered_at)::date, md.chat_id

                    UNION ALL

                    SELECT
                        DATE_TRUNC('week', m.learn_start_date)::date AS week_start,
                        md.chat_id,
                        0::bigint,
                        0::bigint,
                        COUNT(DISTINCT md.tg_user_id) AS started_learning,
                        0::bigint,
                        0::bigint
                    FROM membership_dim md
                    JOIN milestones m ON m.tg_user_id = md.tg_user_id
                    WHERE m.learn_start_date IS NOT NULL
                      AND md.joined_at <= m.learn_start_date
                      AND (CAST(:start_date AS DATE) IS NULL OR m.learn_start_date::date >= CAST(:start_date AS DATE))
                      AND (CAST(:end_date AS DATE) IS NULL OR m.learn_start_date::date <= CAST(:end_date AS DATE))
                    GROUP BY DATE_TRUNC('week', m.learn_start_date)::date, md.chat_id

                    UNION ALL

                    SELECT
                        DATE_TRUNC('week', m.completed_course_at)::date AS week_start,
                        md.chat_id,
                        0::bigint,
                        0::bigint,
                        0::bigint,
                        COUNT(DISTINCT md.tg_user_id) AS completed_course,
                        0::bigint
                    FROM membership_dim md
                    JOIN milestones m ON m.tg_user_id = md.tg_user_id
                    WHERE m.completed_course_at IS NOT NULL
                      AND md.joined_at <= m.completed_course_at
                      AND (CAST(:start_date AS DATE) IS NULL OR m.completed_course_at::date >= CAST(:start_date AS DATE))
                      AND (CAST(:end_date AS DATE) IS NULL OR m.completed_course_at::date <= CAST(:end_date AS DATE))
                    GROUP BY DATE_TRUNC('week', m.completed_course_at)::date, md.chat_id

                    UNION ALL

                    SELECT
                        DATE_TRUNC('week', m.contract_stage_at)::date AS week_start,
                        md.chat_id,
                        0::bigint,
                        0::bigint,
                        0::bigint,
                        0::bigint,
                        COUNT(DISTINCT md.tg_user_id) AS contract_signed
                    FROM membership_dim md
                    JOIN milestones m ON m.tg_user_id = md.tg_user_id
                    WHERE m.contract_stage_at IS NOT NULL
                      AND md.joined_at <= m.contract_stage_at
                      AND (CAST(:start_date AS DATE) IS NULL OR m.contract_stage_at::date >= CAST(:start_date AS DATE))
                      AND (CAST(:end_date AS DATE) IS NULL OR m.contract_stage_at::date <= CAST(:end_date AS DATE))
                    GROUP BY DATE_TRUNC('week', m.contract_stage_at)::date, md.chat_id
                )
                SELECT
                    s.week_start,
                    s.chat_id,
                    SUM(s.in_bot) AS in_bot,
                    SUM(s.registrations) AS registrations,
                    SUM(s.started_learning) AS started_learning,
                    SUM(s.completed_course) AS completed_course,
                    SUM(s.contract_signed) AS contract_signed
                FROM staged s
                WHERE s.week_start IS NOT NULL
                GROUP BY s.week_start, s.chat_id
                ORDER BY s.week_start DESC, s.chat_id
            """)
            weekly_rows = (
                await session.execute(
                    weekly_report_sql,
                    {
                        "channel_id": str(channel_id) if channel_id else "",
                        "community_id": str(community_id) if community_id else "",
                        "start_date": start_date_obj,
                        "end_date": end_date_obj,
                        "bots": bots or None,
                        "advertising_companies": advertising_companies or None,
                        "utm_source": utm_source or None,
                        "utm_campaign": utm_campaign or None,
                        "utm_medium": utm_medium or None,
                        "utm_content": utm_content or None,
                        "utm_term": utm_term or None,
                    },
                )
            ).all()

            budget_weekly_stmt = (
                select(
                    BudgetWeekly.week_start.label("week_start"),
                    BudgetWeekly.channel_key.label("channel_key"),
                    func.coalesce(func.sum(BudgetWeekly.amount), 0.0).label("amount"),
                )
                .where(func.lower(func.coalesce(BudgetWeekly.channel_key, "")).in_(["card_house", "saloon"]))
                .group_by(BudgetWeekly.week_start, BudgetWeekly.channel_key)
            )
            if start_date_obj:
                budget_weekly_stmt = budget_weekly_stmt.where(
                    func.coalesce(BudgetWeekly.period_end, BudgetWeekly.week_start) >= start_date_obj
                )
            if end_date_obj:
                budget_weekly_stmt = budget_weekly_stmt.where(BudgetWeekly.week_start <= end_date_obj)
            if utm_source:
                budget_weekly_stmt = budget_weekly_stmt.where(func.coalesce(BudgetWeekly.utm_source, "").in_(utm_source))
            if utm_campaign:
                budget_weekly_stmt = budget_weekly_stmt.where(func.coalesce(BudgetWeekly.utm_campaign, "").in_(utm_campaign))
            if utm_medium:
                budget_weekly_stmt = budget_weekly_stmt.where(func.coalesce(BudgetWeekly.utm_medium, "").in_(utm_medium))
            if utm_content:
                budget_weekly_stmt = budget_weekly_stmt.where(func.coalesce(BudgetWeekly.utm_content, "").in_(utm_content))
            if utm_term:
                budget_weekly_stmt = budget_weekly_stmt.where(func.coalesce(BudgetWeekly.utm_term, "").in_(utm_term))
            weekly_budget_rows = (await session.execute(budget_weekly_stmt)).all()
            weekly_explicit: dict[tuple[str, dt_date], float] = {}
            def _week_start(value: dt_date) -> dt_date:
                return value - timedelta(days=value.weekday())
            for wb in weekly_budget_rows:
                wk_raw = wb.week_start
                key = (wb.channel_key or "").strip().lower()
                amount = float(wb.amount or 0.0)
                if not wk_raw:
                    continue
                wk = _week_start(wk_raw)
                if key:
                    weekly_explicit[(key, wk)] = weekly_explicit.get((key, wk), 0.0) + amount

            for wr in weekly_rows:
                wk = wr.week_start
                in_bot = int(wr.in_bot or 0)
                registrations = int(wr.registrations or 0)
                started_learning = int(wr.started_learning or 0)
                completed_course = int(wr.completed_course or 0)
                contract_signed = int(wr.contract_signed or 0)
                c_key = channel_key_map.get(str(wr.chat_id), "")
                exp = weekly_explicit.get((c_key, wk), 0.0)
                budget = exp
                channel_report_weekly.append(
                    {
                        "week_start": wk.isoformat() if wk else None,
                        "chat_id": str(wr.chat_id),
                        "channel_key": c_key,
                        "label": label_map.get(str(wr.chat_id), str(wr.chat_id)),
                        "in_bot": in_bot,
                        "registrations": registrations,
                        "started_learning": started_learning,
                        "completed_course": completed_course,
                        "contract_signed": contract_signed,
                        "budget": round(budget, 2),
                        "start_in_bot_cost": _safe_cost(budget, in_bot),
                        "registration_cost": _safe_cost(budget, registrations),
                        "started_learning_cost": _safe_cost(budget, started_learning),
                        "completed_course_cost": _safe_cost(budget, completed_course),
                        "contract_cost": _safe_cost(budget, contract_signed),
                    }
                )

            events_params: dict[str, object] = {}
            events_filters = []
            if start_date_obj:
                events_filters.append("e.checked_at::date >= :start_date")
                events_params["start_date"] = start_date_obj
            if end_date_obj:
                events_filters.append("e.checked_at::date <= :end_date")
                events_params["end_date"] = end_date_obj
            if bots:
                events_filters.append("ud.bot_key = ANY(:bots)")
                events_params["bots"] = bots
            if advertising_companies:
                events_filters.append("ud.advertising_company = ANY(:advertising_companies)")
                events_params["advertising_companies"] = advertising_companies
            if utm_source:
                events_filters.append("ud.utm_source = ANY(:utm_source)")
                events_params["utm_source"] = utm_source
            if utm_campaign:
                events_filters.append("ud.utm_campaign = ANY(:utm_campaign)")
                events_params["utm_campaign"] = utm_campaign
            if utm_medium:
                events_filters.append("ud.utm_medium = ANY(:utm_medium)")
                events_params["utm_medium"] = utm_medium
            if utm_content:
                events_filters.append("ud.utm_content = ANY(:utm_content)")
                events_params["utm_content"] = utm_content
            if utm_term:
                events_filters.append("ud.utm_term = ANY(:utm_term)")
                events_params["utm_term"] = utm_term
            events_where = " AND ".join(events_filters)
            if events_where:
                events_where = "AND " + events_where

            membership_events_params = dict(events_params)
            membership_filters = ["m.joined_at IS NOT NULL"]
            if start_date_obj:
                membership_filters.append("m.joined_at::date >= :start_date")
            if end_date_obj:
                membership_filters.append("m.joined_at::date <= :end_date")
            if bots:
                membership_filters.append("ud.bot_key = ANY(:bots)")
            if advertising_companies:
                membership_filters.append("ud.advertising_company = ANY(:advertising_companies)")
            if utm_source:
                membership_filters.append("ud.utm_source = ANY(:utm_source)")
            if utm_campaign:
                membership_filters.append("ud.utm_campaign = ANY(:utm_campaign)")
            if utm_medium:
                membership_filters.append("ud.utm_medium = ANY(:utm_medium)")
            if utm_content:
                membership_filters.append("ud.utm_content = ANY(:utm_content)")
            if utm_term:
                membership_filters.append("ud.utm_term = ANY(:utm_term)")
            membership_events_where = " AND ".join(membership_filters)
            if membership_events_where:
                membership_events_where = "AND " + membership_events_where

            subscribed_events_sql = text(
                f"""
                WITH user_dim AS (
                    SELECT
                        tg_user_id,
                        COALESCE(MAX(advertising_company), '') AS advertising_company,
                        COALESCE(MAX(bot_key), '') AS bot_key,
                        COALESCE(MAX(utm_source), '') AS utm_source,
                        COALESCE(MAX(utm_campaign), '') AS utm_campaign,
                        COALESCE(MAX(utm_medium), '') AS utm_medium,
                        COALESCE(MAX(utm_content), '') AS utm_content,
                        COALESCE(MAX(utm_term), '') AS utm_term
                    FROM raw_bot_users
                    WHERE tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                    GROUP BY tg_user_id
                )
                SELECT
                    date_trunc(:interval, m.joined_at)::date AS day,
                    ud.advertising_company AS campaign,
                    ud.bot_key AS bot_key,
                    COUNT(DISTINCT m.tg_user_id) FILTER (WHERE m.chat_id = :channel_id) AS channel_subscribed,
                    COUNT(DISTINCT m.tg_user_id) FILTER (WHERE m.chat_id = :community_id) AS saloon_subscribed
                FROM telegram_chat_memberships m
                JOIN user_dim ud ON ud.tg_user_id = m.tg_user_id
                WHERE (m.chat_id = :channel_id OR m.chat_id = :community_id)
                {membership_events_where}
                GROUP BY day, ud.advertising_company, ud.bot_key
                """
            )
            membership_events_params["channel_id"] = str(channel_id)
            membership_events_params["community_id"] = str(community_id)
            membership_events_params["interval"] = "week" if interval == "week" else "day"
            subscribed_rows = (await session.execute(subscribed_events_sql, membership_events_params)).all()
            for row in subscribed_rows:
                key = (row.campaign or "", row.bot_key or "", row.day)
                current = subs_map.get(key, {})
                current["channel_subscribed"] = int(row.channel_subscribed or 0)
                current["saloon_subscribed"] = int(row.saloon_subscribed or 0)
                subs_map[key] = current

            unsubscribed_events_sql = text(
                f"""
                WITH user_dim AS (
                    SELECT
                        tg_user_id,
                        COALESCE(MAX(advertising_company), '') AS advertising_company,
                        COALESCE(MAX(bot_key), '') AS bot_key,
                        COALESCE(MAX(utm_source), '') AS utm_source,
                        COALESCE(MAX(utm_campaign), '') AS utm_campaign,
                        COALESCE(MAX(utm_medium), '') AS utm_medium,
                        COALESCE(MAX(utm_content), '') AS utm_content,
                        COALESCE(MAX(utm_term), '') AS utm_term
                    FROM raw_bot_users
                    WHERE tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                    GROUP BY tg_user_id
                )
                SELECT
                    date_trunc(:interval, e.checked_at)::date AS day,
                    ud.advertising_company AS campaign,
                    ud.bot_key AS bot_key,
                    COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.channel_id = :channel_id AND e.status = 'unsubscribed') AS channel_unsubscribed,
                    COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.channel_id = :community_id AND e.status = 'unsubscribed') AS saloon_unsubscribed
                FROM telegram_subscription_events e
                JOIN user_dim ud ON ud.tg_user_id = e.tg_user_id
                WHERE (e.channel_id = :channel_id OR e.channel_id = :community_id)
                  AND e.source <> 'bot_poll'
                {events_where}
                GROUP BY day, ud.advertising_company, ud.bot_key
                """
            )
            events_params["channel_id"] = str(channel_id)
            events_params["community_id"] = str(community_id)
            events_params["interval"] = "week" if interval == "week" else "day"
            event_rows = (await session.execute(unsubscribed_events_sql, events_params)).all()
            for row in event_rows:
                key = (row.campaign or "", row.bot_key or "", row.day)
                current = subs_map.get(key, {})
                current["channel_unsubscribed"] = int(row.channel_unsubscribed or 0)
                current["saloon_unsubscribed"] = int(row.saloon_unsubscribed or 0)
                subs_map[key] = current

            overall_params: dict[str, object] = {}
            overall_filters = []
            if start_date_obj:
                overall_filters.append("e.checked_at::date >= :start_date")
                overall_params["start_date"] = start_date_obj
            if end_date_obj:
                overall_filters.append("e.checked_at::date <= :end_date")
                overall_params["end_date"] = end_date_obj
            if bots:
                overall_filters.append("ud.bot_key = ANY(:bots)")
                overall_params["bots"] = bots
            if advertising_companies:
                overall_filters.append("ud.advertising_company = ANY(:advertising_companies)")
                overall_params["advertising_companies"] = advertising_companies
            if utm_source:
                overall_filters.append("ud.utm_source = ANY(:utm_source)")
                overall_params["utm_source"] = utm_source
            if utm_campaign:
                overall_filters.append("ud.utm_campaign = ANY(:utm_campaign)")
                overall_params["utm_campaign"] = utm_campaign
            if utm_medium:
                overall_filters.append("ud.utm_medium = ANY(:utm_medium)")
                overall_params["utm_medium"] = utm_medium
            if utm_content:
                overall_filters.append("ud.utm_content = ANY(:utm_content)")
                overall_params["utm_content"] = utm_content
            if utm_term:
                overall_filters.append("ud.utm_term = ANY(:utm_term)")
                overall_params["utm_term"] = utm_term
            overall_where = " AND ".join(overall_filters)
            if overall_where:
                overall_where = "AND " + overall_where

            overall_membership_params = dict(overall_params)
            overall_membership_filters = ["m.joined_at IS NOT NULL"]
            if start_date_obj:
                overall_membership_filters.append("m.joined_at::date >= :start_date")
            if end_date_obj:
                overall_membership_filters.append("m.joined_at::date <= :end_date")
            if bots:
                overall_membership_filters.append("ud.bot_key = ANY(:bots)")
            if advertising_companies:
                overall_membership_filters.append("ud.advertising_company = ANY(:advertising_companies)")
            if utm_source:
                overall_membership_filters.append("ud.utm_source = ANY(:utm_source)")
            if utm_campaign:
                overall_membership_filters.append("ud.utm_campaign = ANY(:utm_campaign)")
            if utm_medium:
                overall_membership_filters.append("ud.utm_medium = ANY(:utm_medium)")
            if utm_content:
                overall_membership_filters.append("ud.utm_content = ANY(:utm_content)")
            if utm_term:
                overall_membership_filters.append("ud.utm_term = ANY(:utm_term)")
            overall_membership_where = " AND ".join(overall_membership_filters)
            if overall_membership_where:
                overall_membership_where = "AND " + overall_membership_where

            overall_membership_params["interval"] = "week" if interval == "week" else "day"
            overall_membership_sql = text(
                f"""
                WITH user_dim AS (
                    SELECT
                        tg_user_id,
                        COALESCE(MAX(advertising_company), '') AS advertising_company,
                        COALESCE(MAX(bot_key), '') AS bot_key,
                        COALESCE(MAX(utm_source), '') AS utm_source,
                        COALESCE(MAX(utm_campaign), '') AS utm_campaign,
                        COALESCE(MAX(utm_medium), '') AS utm_medium,
                        COALESCE(MAX(utm_content), '') AS utm_content,
                        COALESCE(MAX(utm_term), '') AS utm_term
                    FROM raw_bot_users
                    WHERE tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                    GROUP BY tg_user_id
                )
                SELECT
                    date_trunc(:interval, m.joined_at)::date AS day,
                    COUNT(DISTINCT m.tg_user_id) FILTER (WHERE m.chat_id = :channel_id) AS channel_subscribed,
                    COUNT(DISTINCT m.tg_user_id) FILTER (WHERE m.chat_id = :community_id) AS saloon_subscribed
                FROM telegram_chat_memberships m
                JOIN user_dim ud ON ud.tg_user_id = m.tg_user_id
                WHERE (m.chat_id = :channel_id OR m.chat_id = :community_id)
                {overall_membership_where}
                GROUP BY day
                """
            )
            overall_membership_params["channel_id"] = str(channel_id)
            overall_membership_params["community_id"] = str(community_id)
            overall_membership_rows = (await session.execute(overall_membership_sql, overall_membership_params)).all()
            for row in overall_membership_rows:
                overall_subs_map[row.day] = {
                    "channel_subscribed": int(row.channel_subscribed or 0),
                    "saloon_subscribed": int(row.saloon_subscribed or 0),
                }

            overall_params["interval"] = "week" if interval == "week" else "day"
            overall_sql = text(
                f"""
                WITH user_dim AS (
                    SELECT
                        tg_user_id,
                        COALESCE(MAX(advertising_company), '') AS advertising_company,
                        COALESCE(MAX(bot_key), '') AS bot_key,
                        COALESCE(MAX(utm_source), '') AS utm_source,
                        COALESCE(MAX(utm_campaign), '') AS utm_campaign,
                        COALESCE(MAX(utm_medium), '') AS utm_medium,
                        COALESCE(MAX(utm_content), '') AS utm_content,
                        COALESCE(MAX(utm_term), '') AS utm_term
                    FROM raw_bot_users
                    WHERE tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
                    GROUP BY tg_user_id
                )
                SELECT
                    date_trunc(:interval, e.checked_at)::date AS day,
                    COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.channel_id = :channel_id AND e.status = 'unsubscribed') AS channel_unsubscribed,
                    COUNT(DISTINCT e.tg_user_id) FILTER (WHERE e.channel_id = :community_id AND e.status = 'unsubscribed') AS saloon_unsubscribed
                FROM telegram_subscription_events e
                JOIN user_dim ud ON ud.tg_user_id = e.tg_user_id
                WHERE (e.channel_id = :channel_id OR e.channel_id = :community_id)
                  AND e.source <> 'bot_poll'
                {overall_where}
                GROUP BY day
                """
            )
            overall_params["channel_id"] = str(channel_id)
            overall_params["community_id"] = str(community_id)
            overall_rows = (await session.execute(overall_sql, overall_params)).all()
            for row in overall_rows:
                current = overall_subs_map.get(row.day, {})
                current["channel_unsubscribed"] = int(row.channel_unsubscribed or 0)
                current["saloon_unsubscribed"] = int(row.saloon_unsubscribed or 0)
                overall_subs_map[row.day] = current

        stmt = select(
            period_expr.label("day"),
            campaign_expr.label("campaign"),
            bot_expr.label("bot_key"),
            func.sum(TgSubsDailyAgg.bot_starts).label("bot_starts"),
            func.sum(TgSubsDailyAgg.almanah_starts).label("almanah_starts"),
            func.sum(TgSubsDailyAgg.channel_subscribed).label("channel_subscribed"),
            func.sum(TgSubsDailyAgg.channel_unsubscribed).label("channel_unsubscribed"),
            func.sum(TgSubsDailyAgg.saloon_subscribed).label("saloon_subscribed"),
            func.sum(TgSubsDailyAgg.saloon_unsubscribed).label("saloon_unsubscribed"),
        ).select_from(TgSubsDailyAgg)

        if conditions:
            stmt = stmt.where(*conditions)

        stmt = stmt.group_by(period_expr, campaign_expr, bot_expr).order_by(campaign_expr, bot_expr, period_expr)
        rows = (await session.execute(stmt)).all()

        payload = []
        for row in rows:
            snapshot_key = (row.campaign or "", row.bot_key or "")
            snapshot_totals = snapshot_map.get(snapshot_key, {"channel_total": 0, "saloon_total": 0})
            day_key = (row.campaign or "", row.bot_key or "", row.day)
            event_override = subs_map.get(day_key, {})
            channel_subscribed = int(event_override.get("channel_subscribed", 0))
            saloon_subscribed = int(event_override.get("saloon_subscribed", 0))
            channel_unsubscribed = int(event_override.get("channel_unsubscribed", 0))
            saloon_unsubscribed = int(event_override.get("saloon_unsubscribed", 0))
            payload.append(
                {
                    "date": row.day.isoformat() if row.day else None,
                    "campaign": row.campaign,
                    "bot_key": row.bot_key or "",
                    "bot_starts": int(row.bot_starts or 0),
                    "almanah_starts": int(row.almanah_starts or 0),
                    "channel_subscribed": channel_subscribed,
                    "channel_unsubscribed": channel_unsubscribed,
                    "channel_total": int(snapshot_totals["channel_total"]),
                    "saloon_subscribed": saloon_subscribed,
                    "saloon_unsubscribed": saloon_unsubscribed,
                    "saloon_total": int(snapshot_totals["saloon_total"]),
                }
            )
        overall_payload = []
        overall_stmt = select(
            period_expr.label("day"),
            func.sum(TgSubsDailyAgg.bot_starts).label("bot_starts"),
            func.sum(TgSubsDailyAgg.almanah_starts).label("almanah_starts"),
        ).select_from(TgSubsDailyAgg)
        if conditions:
            overall_stmt = overall_stmt.where(*conditions)
        overall_stmt = overall_stmt.group_by(period_expr).order_by(period_expr)
        overall_rows = (await session.execute(overall_stmt)).all()
        for row in overall_rows:
            event_totals = overall_subs_map.get(row.day, {}) if row.day else {}
            overall_payload.append(
                {
                    "date": row.day.isoformat() if row.day else None,
                    "bot_starts": int(row.bot_starts or 0),
                    "almanah_starts": int(row.almanah_starts or 0),
                    "channel_subscribed": int(event_totals.get("channel_subscribed", 0)),
                    "channel_unsubscribed": int(event_totals.get("channel_unsubscribed", 0)),
                    "saloon_subscribed": int(event_totals.get("saloon_subscribed", 0)),
                    "saloon_unsubscribed": int(event_totals.get("saloon_unsubscribed", 0)),
                }
            )
        return {
            "rows": payload,
            "summary": summary,
            "overall_rows": overall_payload,
            "channel_funnel": channel_funnel,
            "channel_report_weekly": channel_report_weekly,
        }

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

        conditions = [
            f"{bot_col} IS NOT NULL",
            f"TRIM({bot_col}) <> ''",
            f"LOWER(TRIM({bot_col})) <> 'нет метки'",
            f"LOWER(TRIM({bot_col})) <> ALL(:excluded_bot_keys)",
            "tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)",
            "LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)",
        ]
        params: dict[str, Any] = {"excluded_bot_keys": normalized_excluded_bot_keys()}
        date_col = "created_at" if mode == "first" else "learn_start_date"
        if start_date:
            conditions.append(f"{date_col} >= :start_date")
            params["start_date"] = start_date
        if end_date:
            conditions.append(f"{date_col} <= :end_date")
            params["end_date"] = end_date
        if mode == "last":
            conditions.append("learn_start_date IS NOT NULL")
        where_clause = f"WHERE {' AND '.join(conditions)}"

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
            func.lower(func.trim(bot_col)).notin_(normalized_excluded_bot_keys()),
            date_col.isnot(None),
        ).group_by(bot_label)

        stmt = self._apply_filters_with_date(stmt, filters, date_col)
        stmt = apply_employee_exclusion(stmt, RawBotUser.tg_user_id)
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
        start_date: Optional[str | dt_date] = None,
        end_date: Optional[str | dt_date] = None,
    ) -> Tuple[List[str], dict[str, List[dict]]]:
        bot_value = group_key
        if mode not in {"first", "last"}:
            raise ValueError("mode must be first or last")
        if group_key.strip().lower() in normalized_excluded_bot_keys():
            return [], {}
        bot_col = RawBotUser.first_touch_bot if mode == "first" else RawBotUser.last_touch_bot
        date_col = RawBotUser.created_at if mode == "first" else RawBotUser.learn_start_date
        start_date_obj = self._coerce_date(start_date)
        end_date_obj = self._coerce_date(end_date)
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
                func.lower(func.trim(bot_col)).notin_(normalized_excluded_bot_keys()),
                date_col.isnot(None),
            )
            .where(
                date_col >= start_date_obj if start_date_obj else True,
                date_col <= end_date_obj if end_date_obj else True,
            )
            .group_by(week_start)
            .order_by(week_start)
        )
        stmt = apply_employee_exclusion(stmt, RawBotUser.tg_user_id)
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
