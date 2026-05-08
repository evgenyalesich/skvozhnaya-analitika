# ===== Subscriptions: weekly/funnel SQL block =====
from datetime import date as dt_date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.report_repository_subscriptions_sql_weekly_budget import (
    build_channel_funnel_rows,
    load_total_and_channel_budget,
    load_weekly_explicit_budget,
)


class ReportRepositorySubscriptionsWeeklySqlMixin:
    async def _load_channel_weekly_sql(
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
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        channel_funnel: list[dict[str, object]] = []
        channel_report_weekly: list[dict[str, object]] = []
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
                    MIN(ru.contract_signed_at) FILTER (
                        WHERE ru.contract_signed IS TRUE
                          AND ru.contract_signed_at IS NOT NULL
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
        
        _, explicit_channel_budget = await load_total_and_channel_budget(
            session,
            start_date_obj=start_date_obj,
            end_date_obj=end_date_obj,
            utm_source=utm_source,
            utm_campaign=utm_campaign,
            utm_medium=utm_medium,
            utm_content=utm_content,
            utm_term=utm_term,
        )
        
        channel_funnel = build_channel_funnel_rows(
            funnel_rows=funnel_rows,
            label_map=label_map,
            channel_key_map=channel_key_map,
            explicit_channel_budget=explicit_channel_budget,
            pct_fn=self._pct,
            safe_cost_fn=self._safe_cost,
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
                    MIN(ru.contract_signed_at) FILTER (
                        WHERE ru.contract_signed IS TRUE
                          AND ru.contract_signed_at IS NOT NULL
                    ) AS contract_stage_at
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
        
        weekly_explicit = await load_weekly_explicit_budget(
            session,
            start_date_obj=start_date_obj,
            end_date_obj=end_date_obj,
            utm_source=utm_source,
            utm_campaign=utm_campaign,
            utm_medium=utm_medium,
            utm_content=utm_content,
            utm_term=utm_term,
        )
        
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
                    "start_in_bot_cost": self._safe_cost(budget, in_bot),
                    "registration_cost": self._safe_cost(budget, registrations),
                    "started_learning_cost": self._safe_cost(budget, started_learning),
                    "completed_course_cost": self._safe_cost(budget, completed_course),
                    "contract_cost": self._safe_cost(budget, contract_signed),
                }
            )
        return channel_funnel, channel_report_weekly
