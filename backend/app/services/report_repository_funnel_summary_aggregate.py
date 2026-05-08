from typing import List

from sqlalchemy import desc, false, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.report_filters import ReportFilters
from app.models.analytics import RawBotUser, WeeklyFunnelBotAgg
from app.services.report_bot_scope import normalized_excluded_bot_keys


class ReportRepositoryFunnelSummaryAggregateMixin:
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
                func.max(RawBotUser.platform_registered_at).label("last_touch_date"),
            )
            .where(RawBotUser.ph_user_id.is_not(None))
            .where(RawBotUser.platform_registered_at.is_not(None))
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
        if touch_mode == "first_touch":
            # Business rule: first_touch slice represents unique NEW users in bots.
            new_in_system_filter = true()
            old_in_system_filter = false()

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
                if touch_mode == "first_touch":
                    pass
                elif touch_bot_first_seen_col is not None:
                    stmt = stmt.where(
                        self._msk_date(first_seen_system_sq.c.first_seen_at_system) == self._msk_date(touch_bot_first_seen_col)
                    )
                else:
                    stmt = stmt.where(first_seen_system_sq.c.first_seen_at_system == touch_date_col)
            elif filters.user_scope == "old":
                if touch_mode == "first_touch":
                    stmt = stmt.where(false())
                elif touch_bot_first_seen_col is not None:
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
