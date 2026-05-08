# ===== Subscriptions: events SQL block =====
from datetime import date as dt_date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ReportRepositorySubscriptionsEventsSqlMixin:
    async def _load_channel_events_sql(
        self,
        session: AsyncSession,
        *,
        interval: str,
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
    ) -> tuple[dict[tuple[str, str, dt_date], dict[str, int]], dict[dt_date, dict[str, int]]]:
        subs_map: dict[tuple[str, str, dt_date], dict[str, int]] = {}
        overall_subs_map: dict[dt_date, dict[str, int]] = {}
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
        return subs_map, overall_subs_map
