from typing import Any, List, Optional
import datetime as dt

from sqlalchemy import desc, func, select, cast, String, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.report_filters import ReportFilters, RawUserFilters
from app.models.analytics import RawBotUser


class RawUserRepository:
    async def _load_budget_cpa_learning(self, session: AsyncSession, users: List[RawBotUser]) -> dict[tuple[str, str, str], float]:
        keys = set()
        days = set()
        campaigns = set()
        bot_keys = set()
        for user in users:
            if not user.learn_start_date:
                continue
            day = user.learn_start_date.date()
            campaign = (user.advertising_company or "нет метки").strip().lower()
            bot_key = (user.bot_key or "").strip().lower()
            days.add(day)
            campaigns.add(campaign)
            if bot_key:
                bot_keys.add(bot_key)
            keys.add((day.isoformat(), campaign, bot_key))
        if not days or not campaigns:
            return {}

        query = text(
            """
            WITH budget_base AS (
                SELECT
                    (b.week_start + gs)::date AS day,
                    LOWER(TRIM(b.campaign)) AS campaign,
                    COALESCE(LOWER(TRIM(b.bot_key)), '') AS bot_key,
                    (b.amount / 7.0) AS budget
                FROM budget_weekly b
                CROSS JOIN generate_series(0, 6) AS gs
                WHERE (b.week_start + gs)::date = ANY(:days)
                  AND LOWER(TRIM(b.campaign)) = ANY(:campaigns)
                  AND (
                        b.bot_key IS NULL
                        OR b.bot_key = ''
                        OR LOWER(TRIM(b.bot_key)) = ANY(:bot_keys)
                  )
            ),
            learning AS (
                SELECT
                    DATE(learn_start_date)::date AS day,
                    LOWER(TRIM(COALESCE(advertising_company, 'нет метки'))) AS campaign,
                    LOWER(TRIM(COALESCE(bot_key, ''))) AS bot_key,
                    COUNT(DISTINCT tg_user_id) FILTER (WHERE started_learning IS TRUE) AS learning
                FROM raw_bot_users
                WHERE learn_start_date IS NOT NULL
                  AND DATE(learn_start_date)::date = ANY(:days)
                  AND LOWER(TRIM(COALESCE(advertising_company, 'нет метки'))) = ANY(:campaigns)
                  AND (
                        bot_key IS NULL
                        OR bot_key = ''
                        OR LOWER(TRIM(bot_key)) = ANY(:bot_keys)
                  )
                GROUP BY day, campaign, bot_key
            )
            SELECT
                b.day,
                b.campaign,
                b.bot_key,
                SUM(b.budget) AS budget,
                COALESCE(l.learning, 0) AS learning
            FROM budget_base b
            LEFT JOIN learning l
              ON l.day = b.day
             AND (
                    (b.bot_key <> '' AND l.bot_key = b.bot_key)
                    OR (b.bot_key = '' AND l.campaign = b.campaign)
                 )
            GROUP BY b.day, b.campaign, b.bot_key, l.learning
            """
        )
        normalized_days: list[dt.date] = []
        for day in days:
            if isinstance(day, dt.date):
                normalized_days.append(day)
            else:
                try:
                    normalized_days.append(dt.date.fromisoformat(str(day)))
                except ValueError:
                    continue
        if not normalized_days:
            return {}

        params = {
            "days": normalized_days,
            "campaigns": list(campaigns),
            "bot_keys": list(bot_keys) if bot_keys else [""],
        }
        result = await session.execute(query, params)
        rows = result.fetchall()
        cpa_map: dict[tuple[str, str, str], float] = {}
        for row in rows:
            learning = int(row.learning or 0)
            if learning <= 0:
                continue
            budget = float(row.budget or 0.0)
            if budget <= 0:
                continue
            cpa = budget / learning
            key = (row.day.isoformat(), str(row.campaign), str(row.bot_key))
            cpa_map[key] = cpa
        return cpa_map
    def _apply_filters(self, stmt, filters: ReportFilters):
        if filters.start_date:
            stmt = stmt.where(RawBotUser.created_at >= filters.start_date)
        if filters.end_date:
            stmt = stmt.where(RawBotUser.created_at <= filters.end_date)
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

    def _apply_raw_filters(self, stmt, raw_filters: RawUserFilters):
        if raw_filters.bot_keys:
            stmt = stmt.where(RawBotUser.bot_key.in_(raw_filters.bot_keys))
        if raw_filters.tg_user_id:
            stmt = stmt.where(cast(RawBotUser.tg_user_id, String).ilike(f"%{raw_filters.tg_user_id}%"))
        if raw_filters.utm_source:
            stmt = stmt.where(RawBotUser.utm_source.in_(raw_filters.utm_source))
        if raw_filters.utm_campaign:
            stmt = stmt.where(RawBotUser.utm_campaign.in_(raw_filters.utm_campaign))
        if raw_filters.utm_medium:
            stmt = stmt.where(RawBotUser.utm_medium.in_(raw_filters.utm_medium))
        if raw_filters.utm_content:
            stmt = stmt.where(RawBotUser.utm_content.in_(raw_filters.utm_content))
        if raw_filters.utm_term:
            stmt = stmt.where(RawBotUser.utm_term.in_(raw_filters.utm_term))
        if raw_filters.advertising_companies:
            stmt = stmt.where(RawBotUser.advertising_company.in_(raw_filters.advertising_companies))
        if raw_filters.budget_min is not None:
            stmt = stmt.where(RawBotUser.budget >= raw_filters.budget_min)
        if raw_filters.budget_max is not None:
            stmt = stmt.where(RawBotUser.budget <= raw_filters.budget_max)
        if raw_filters.converted_to_lead is not None:
            stmt = stmt.where(RawBotUser.converted_to_lead.is_(raw_filters.converted_to_lead))
        if raw_filters.registered_platform is not None:
            stmt = stmt.where(RawBotUser.registered_platform.is_(raw_filters.registered_platform))
        if raw_filters.started_learning is not None:
            stmt = stmt.where(RawBotUser.started_learning.is_(raw_filters.started_learning))
        if raw_filters.completed_course is not None:
            stmt = stmt.where(RawBotUser.completed_course.is_(raw_filters.completed_course))
        if raw_filters.used_simulator is not None:
            stmt = stmt.where(RawBotUser.used_simulator.is_(raw_filters.used_simulator))
        if raw_filters.interview_reached is not None:
            stmt = stmt.where(RawBotUser.interview_reached.is_(raw_filters.interview_reached))
        if raw_filters.interview_passed is not None:
            stmt = stmt.where(RawBotUser.interview_passed.is_(raw_filters.interview_passed))
        if raw_filters.offer_received is not None:
            stmt = stmt.where(RawBotUser.offer_received.is_(raw_filters.offer_received))
        if raw_filters.contract_signed is not None:
            stmt = stmt.where(RawBotUser.contract_signed.is_(raw_filters.contract_signed))
        if raw_filters.distance_grinding is not None:
            stmt = stmt.where(RawBotUser.distance_grinding.is_(raw_filters.distance_grinding))
        if raw_filters.interview_reached_status:
            stmt = stmt.where(RawBotUser.interview_reached_status.ilike(f"%{raw_filters.interview_reached_status}%"))
        if raw_filters.interview_passed_status:
            stmt = stmt.where(RawBotUser.interview_passed_status.ilike(f"%{raw_filters.interview_passed_status}%"))
        if raw_filters.offer_received_status:
            stmt = stmt.where(RawBotUser.offer_received_status.ilike(f"%{raw_filters.offer_received_status}%"))
        if raw_filters.contract_signed_status:
            stmt = stmt.where(RawBotUser.contract_signed_status.ilike(f"%{raw_filters.contract_signed_status}%"))
        if raw_filters.channel_subscribed is not None:
            stmt = stmt.where(RawBotUser.channel_subscribed.is_(raw_filters.channel_subscribed))
        if raw_filters.community_member is not None:
            stmt = stmt.where(RawBotUser.community_member.is_(raw_filters.community_member))
        if raw_filters.team_member is not None:
            stmt = stmt.where(RawBotUser.team_member.is_(raw_filters.team_member))
        if raw_filters.community_member_status:
            stmt = stmt.where(RawBotUser.community_member_status.ilike(f"%{raw_filters.community_member_status}%"))
        if raw_filters.internal_status:
            stmt = stmt.where(RawBotUser.internal_status.ilike(f"%{raw_filters.internal_status}%"))
        if raw_filters.user_block is not None:
            stmt = stmt.where(RawBotUser.user_block.is_(raw_filters.user_block))
        if raw_filters.first_touch_present is not None:
            if raw_filters.first_touch_present:
                stmt = stmt.where(
                    RawBotUser.first_touch_bot.isnot(None),
                    RawBotUser.first_touch_bot != "",
                    RawBotUser.first_touch_bot != "нет метки",
                )
            else:
                stmt = stmt.where(
                    or_(
                        RawBotUser.first_touch_bot.is_(None),
                        RawBotUser.first_touch_bot == "",
                        RawBotUser.first_touch_bot == "нет метки",
                    )
                )
        if raw_filters.last_touch_present is not None:
            if raw_filters.last_touch_present:
                stmt = stmt.where(
                    RawBotUser.last_touch_bot.isnot(None),
                    RawBotUser.last_touch_bot != "",
                    RawBotUser.last_touch_bot != "нет метки",
                )
            else:
                stmt = stmt.where(
                    or_(
                        RawBotUser.last_touch_bot.is_(None),
                        RawBotUser.last_touch_bot == "",
                        RawBotUser.last_touch_bot == "нет метки",
                    )
                )
        return stmt

    async def fetch_raw(
        self,
        session: AsyncSession,
        filters: ReportFilters,
        raw_filters: RawUserFilters,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_direction: str = "desc",
    ) -> tuple[List[dict[str, Any]], int]:
        base = select(RawBotUser)
        base = self._apply_filters(base, filters)
        base = self._apply_raw_filters(base, raw_filters)
        column = getattr(RawBotUser, sort_by)
        base = base.order_by(desc(column) if sort_direction == "desc" else column)
        stmt = base.offset(offset).limit(limit)
        count_stmt = select(func.count()).select_from(RawBotUser)
        count_stmt = self._apply_filters(count_stmt, filters)
        count_stmt = self._apply_raw_filters(count_stmt, raw_filters)
        total_result = await session.execute(count_stmt)
        total = total_result.scalar_one() or 0
        result = await session.execute(stmt)
        users = result.scalars().all()
        budget_cpa_map = await self._load_budget_cpa_learning(session, users)
        return [self._serialize(user, budget_cpa_map) for user in users], total

    def _serialize(self, user: RawBotUser, budget_cpa_map: dict[tuple[str, str, str], float]) -> dict[str, Optional[str]]:
        budget_value = 0.0
        if user.learn_start_date and user.started_learning:
            day = user.learn_start_date.date().isoformat()
            campaign = (user.advertising_company or "нет метки").strip().lower()
            bot_key = (user.bot_key or "").strip().lower()
            budget_value = budget_cpa_map.get((day, campaign, bot_key), 0.0)
            if budget_value == 0.0:
                budget_value = budget_cpa_map.get((day, campaign, ""), 0.0)
        payload = {
            "id": user.id,
            "bot_key": user.bot_key,
            "tg_user_id": user.tg_user_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "user_block": user.user_block,
            "utm_source": user.utm_source or "(none)",
            "utm_campaign": user.utm_campaign or "(none)",
            "utm_medium": user.utm_medium,
            "utm_content": user.utm_content,
            "utm_term": user.utm_term,
            "advertising_company": user.advertising_company,
            "budget": budget_value,
            "ingested_at": user.ingested_at.isoformat() if user.ingested_at else None,
            "converted_to_lead": user.converted_to_lead,
            "registered_platform": user.registered_platform,
            "started_learning": user.started_learning,
            "completed_course": user.completed_course,
            "used_simulator": user.used_simulator,
            "interview_reached": user.interview_reached,
            "interview_passed": user.interview_passed,
            "offer_received": user.offer_received,
            "contract_signed": user.contract_signed,
            "distance_grinding": user.distance_grinding,
            "interview_reached_status": user.interview_reached_status,
            "interview_passed_status": user.interview_passed_status,
            "offer_received_status": user.offer_received_status,
            "contract_signed_status": user.contract_signed_status,
            "channel_subscribed": user.channel_subscribed,
            "community_member": user.community_member,
            "team_member": user.team_member,
            "community_member_status": user.community_member_status,
            "internal_status": user.internal_status,
            "learn_start_date": user.learn_start_date.isoformat() if user.learn_start_date else None,
            "start_course": user.start_course,
            "first_touch_bot": user.first_touch_bot,
            "first_touch_campaign": user.first_touch_campaign,
            "last_touch_bot": user.last_touch_bot,
            "last_touch_campaign": user.last_touch_campaign,
        }
        return payload
