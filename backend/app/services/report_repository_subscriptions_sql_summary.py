# ===== Subscriptions: summary SQL block =====
from datetime import date as dt_date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ReportRepositorySubscriptionsSummarySqlMixin:
    async def _load_channel_summary_sql(
        self,
        session: AsyncSession,
        *,
        channel_id: str | None,
        community_id: str | None,
        start_date_obj: Optional[dt_date],
        end_date_obj: Optional[dt_date],
        bots: Optional[list[str]],
        advertising_companies: Optional[list[str]],
        utm_source: Optional[list[str]],
        utm_campaign: Optional[list[str]],
        utm_medium: Optional[list[str]],
        utm_content: Optional[list[str]],
        utm_term: Optional[list[str]],
    ) -> tuple[dict[tuple[str, str], dict[str, int]], dict[str, dict[str, int]]]:
        snapshot_map: dict[tuple[str, str], dict[str, int]] = {}
        summary: dict[str, dict[str, int]] = {
            "channel": {"active": 0, "subscribed": 0, "unsubscribed": 0},
            "saloon": {"active": 0, "subscribed": 0, "unsubscribed": 0},
        }
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
        return snapshot_map, summary
