# ===== Subscriptions: events/orchestration =====
from datetime import date as dt_date
from typing import List, Optional

from sqlalchemy import Date, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.analytics import AdvertisingCompany, TgSubsDailyAgg
from app.services.report_bot_scope import normalized_excluded_bot_keys
from app.services.report_repository_subscriptions_sql_events import ReportRepositorySubscriptionsEventsSqlMixin
from app.services.report_repository_subscriptions_sql_summary import ReportRepositorySubscriptionsSummarySqlMixin
from app.services.report_repository_subscriptions_sql_weekly import ReportRepositorySubscriptionsWeeklySqlMixin
from app.services.report_repository_subscriptions_funnel import ReportRepositorySubscriptionsFunnelMixin
from app.services.report_repository_subscriptions_summary import ReportRepositorySubscriptionsSummaryMixin


class ReportRepositorySubscriptionsEventsMixin(
    ReportRepositorySubscriptionsSummaryMixin,
    ReportRepositorySubscriptionsFunnelMixin,
    ReportRepositorySubscriptionsSummarySqlMixin,
    ReportRepositorySubscriptionsWeeklySqlMixin,
    ReportRepositorySubscriptionsEventsSqlMixin,
):
    """Subscriptions/events orchestration slice."""

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
        subs_map: dict[tuple[str, str, dt_date], dict[str, int]] = {}
        overall_subs_map: dict[dt_date, dict[str, int]] = {}
        summary: dict[str, dict[str, int]] = {
            "channel": {"active": 0, "subscribed": 0, "unsubscribed": 0},
            "saloon": {"active": 0, "subscribed": 0, "unsubscribed": 0},
        }
        channel_funnel: list[dict[str, object]] = []
        channel_report_weekly: list[dict[str, object]] = []
        if channel_id or community_id:
            snapshot_map, summary = await self._load_channel_summary_sql(
                session,
                channel_id=channel_id,
                community_id=community_id,
                start_date_obj=start_date_obj,
                end_date_obj=end_date_obj,
                bots=bots,
                advertising_companies=advertising_companies,
                utm_source=utm_source,
                utm_campaign=utm_campaign,
                utm_medium=utm_medium,
                utm_content=utm_content,
                utm_term=utm_term,
            )
            channel_funnel, channel_report_weekly = await self._load_channel_weekly_sql(
                session,
                channel_id=channel_id,
                community_id=community_id,
                start_date_obj=start_date_obj,
                end_date_obj=end_date_obj,
                bots=bots,
                advertising_companies=advertising_companies,
                utm_source=utm_source,
                utm_campaign=utm_campaign,
                utm_medium=utm_medium,
                utm_content=utm_content,
                utm_term=utm_term,
            )
            subs_map, overall_subs_map = await self._load_channel_events_sql(
                session,
                interval=interval,
                channel_id=channel_id,
                community_id=community_id,
                start_date_obj=start_date_obj,
                end_date_obj=end_date_obj,
                bots=bots,
                advertising_companies=advertising_companies,
                utm_source=utm_source,
                utm_campaign=utm_campaign,
                utm_medium=utm_medium,
                utm_content=utm_content,
                utm_term=utm_term,
            )

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

        payload = self._build_subscription_rows_payload(rows, snapshot_map, subs_map)
        overall_stmt = select(
            period_expr.label("day"),
            func.sum(TgSubsDailyAgg.bot_starts).label("bot_starts"),
            func.sum(TgSubsDailyAgg.almanah_starts).label("almanah_starts"),
        ).select_from(TgSubsDailyAgg)
        if conditions:
            overall_stmt = overall_stmt.where(*conditions)
        overall_stmt = overall_stmt.group_by(period_expr).order_by(period_expr)
        overall_rows = (await session.execute(overall_stmt)).all()
        overall_payload = self._build_overall_rows_payload(overall_rows, overall_subs_map)
        return {
            "rows": payload,
            "summary": summary,
            "overall_rows": overall_payload,
            "channel_funnel": channel_funnel,
            "channel_report_weekly": channel_report_weekly,
        }
