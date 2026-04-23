from typing import Any, List, Optional
import datetime as dt

from sqlalchemy import Date, and_, desc, exists, func, not_, select, cast, String, or_, text
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.report_filters import ReportFilters, RawUserFilters
from app.models.analytics import BotRegistry, PhUserMirrorReplica, RawBotUser
from app.services.employee_registry_service import apply_employee_exclusion
from app.services.report_bot_scope import (
    apply_excluded_bot_filter,
    is_excluded_bot_key,
    normalized_excluded_bot_keys,
)


class RawUserRepository:
    @staticmethod
    def _msk_date(column):
        return func.timezone("Europe/Moscow", column).cast(Date)

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
    def _split_search_terms(value: str | None) -> list[str]:
        if not value:
            return []
        normalized = value.replace("\n", ",").replace(";", ",")
        return [item.strip() for item in normalized.split(",") if item.strip()]

    @staticmethod
    def _normalize_key(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _normalized_lower(value: str | None) -> str:
        if not value:
            return ""
        return value.strip().lower()

    def _derive_source_category(self, user: RawBotUser) -> str:
        bot_key = self._normalized_lower(user.bot_key)
        tg_user_id = int(user.tg_user_id or 0)
        ph_user_id = int(user.ph_user_id) if user.ph_user_id is not None else None
        # Business rule:
        # - lead rows where ph_user_id equals the canonical id are PH-only site registrations
        # - lead rows with TG identity and separate PH identity belong to Almanah
        if bot_key == "lead":
            if ph_user_id is not None and abs(tg_user_id) == ph_user_id:
                return "direct_source"
            return "almanah"
        if tg_user_id < 0 and user.ph_user_id is not None:
            return "direct_source"
        return "bot_source"

    @staticmethod
    def _lead_mirror_dedup_condition():
        """
        Keep all non-lead rows and real lead rows (tg_user_id >= 0).
        For synthetic mirror lead rows (tg_user_id < 0), keep only those that
        don't have a corresponding real lead row by the same ph_user_id.
        """
        real_lead = aliased(RawBotUser)
        normalized_bot = func.lower(func.trim(func.coalesce(RawBotUser.bot_key, "")))
        duplicate_real_exists = exists(
            select(1).select_from(real_lead).where(
                func.lower(func.trim(func.coalesce(real_lead.bot_key, ""))) == "lead",
                real_lead.tg_user_id >= 0,
                or_(
                    and_(
                        RawBotUser.ph_user_id.is_not(None),
                        real_lead.ph_user_id.is_not(None),
                        real_lead.ph_user_id == RawBotUser.ph_user_id,
                    ),
                    real_lead.tg_user_id == func.abs(RawBotUser.tg_user_id),
                ),
            )
        )
        return or_(
            normalized_bot != "lead",
            RawBotUser.tg_user_id >= 0,
            RawBotUser.ph_user_id.is_(None),
            not_(duplicate_real_exists),
        )

    async def _load_canonical_base_map(self, session: AsyncSession) -> dict[str, str]:
        result = await session.execute(select(BotRegistry.bot_key, BotRegistry.canonical_base))
        mapping: dict[str, str] = {}
        for bot_key, canonical_base in result.all():
            normalized_key = self._normalize_key(bot_key)
            normalized_base = self._normalize_key(canonical_base)
            if normalized_key and normalized_base:
                mapping[normalized_key] = normalized_base
        return mapping

    def _canonical_base(self, bot_key: str | None, canonical_map: dict[str, str]) -> str | None:
        normalized_key = self._normalize_key(bot_key)
        if not normalized_key:
            return None
        return canonical_map.get(normalized_key, normalized_key)

    async def _load_first_seen_maps(
        self, session: AsyncSession, users: List[RawBotUser]
    ) -> tuple[dict[int, dt.datetime], dict[tuple[int, str], dt.datetime]]:
        tg_user_ids = sorted({int(user.tg_user_id) for user in users if user.tg_user_id is not None})
        bot_pairs = sorted(
            {
                (int(user.tg_user_id), user.bot_key)
                for user in users
                if user.tg_user_id is not None and user.bot_key
            }
        )
        touch_pairs = {
            (int(user.tg_user_id), user.first_touch_bot)
            for user in users
            if user.tg_user_id is not None and user.first_touch_bot
        } | {
            (int(user.tg_user_id), user.last_touch_bot)
            for user in users
            if user.tg_user_id is not None and user.last_touch_bot
        }
        bot_pairs = sorted(set(bot_pairs) | touch_pairs)
        system_map: dict[int, dt.datetime] = {}
        bot_map: dict[tuple[int, str], dt.datetime] = {}
        if tg_user_ids:
            system_stmt = (
                select(
                    RawBotUser.tg_user_id,
                    func.min(RawBotUser.created_at).label("first_seen_at_system"),
                )
                .where(RawBotUser.tg_user_id.in_(tg_user_ids))
                .group_by(RawBotUser.tg_user_id)
            )
            system_rows = await session.execute(system_stmt)
            for row in system_rows:
                if row.tg_user_id is not None and row.first_seen_at_system is not None:
                    system_map[int(row.tg_user_id)] = row.first_seen_at_system
        if bot_pairs:
            tg_ids = sorted({tg_user_id for tg_user_id, _ in bot_pairs})
            bot_keys = sorted({bot_key for _, bot_key in bot_pairs})
            bot_stmt = (
                select(
                    RawBotUser.tg_user_id,
                    RawBotUser.bot_key,
                    func.min(RawBotUser.created_at).label("first_seen_at_bot"),
                )
                .where(
                    RawBotUser.tg_user_id.in_(tg_ids),
                    RawBotUser.bot_key.in_(bot_keys),
                )
                .group_by(RawBotUser.tg_user_id, RawBotUser.bot_key)
            )
            bot_rows = await session.execute(bot_stmt)
            for row in bot_rows:
                if row.tg_user_id is not None and row.bot_key and row.first_seen_at_bot is not None:
                    bot_map[(int(row.tg_user_id), row.bot_key)] = row.first_seen_at_bot
        return system_map, bot_map

    async def _load_mirror_map(self, session: AsyncSession, users: List[RawBotUser]) -> dict[tuple[int | None, int | None], PhUserMirrorReplica]:
        lead_user_ids = sorted({int(user.lead_user_id) for user in users if user.lead_user_id is not None})
        ph_ids = sorted({str(int(user.ph_user_id)) for user in users if user.ph_user_id is not None})
        conditions = []
        if lead_user_ids:
            conditions.append(PhUserMirrorReplica.id.in_(lead_user_ids))
        if ph_ids:
            conditions.append(PhUserMirrorReplica.ph_id.in_(ph_ids))
        if not conditions:
            return {}
        result = await session.execute(select(PhUserMirrorReplica).where(or_(*conditions)))
        rows = result.scalars().all()
        mirror_map: dict[tuple[int | None, int | None], PhUserMirrorReplica] = {}
        for row in rows:
            lead_user_id = int(row.id) if row.id is not None else None
            ph_user_id = int(row.ph_id) if row.ph_id and str(row.ph_id).isdigit() else None
            mirror_map[(lead_user_id, ph_user_id)] = row
            mirror_map[(lead_user_id, None)] = row
            mirror_map[(None, ph_user_id)] = row
        return mirror_map

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
                    b.week_start::date AS day,
                    LOWER(TRIM(b.campaign)) AS campaign,
                    COALESCE(LOWER(TRIM(b.bot_key)), '') AS bot_key,
                    b.amount AS budget
                FROM budget_weekly b
                WHERE b.week_start::date = ANY(:days)
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
                  AND LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
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
            "excluded_bot_keys": normalized_excluded_bot_keys(),
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
    def _apply_filters(self, stmt, filters: ReportFilters, touch_mode: str = "event"):
        stmt = apply_excluded_bot_filter(stmt, RawBotUser.bot_key)
        date_col = RawBotUser.created_at
        date_col_msk = self._msk_date(date_col)
        if filters.start_date:
            stmt = stmt.where(date_col_msk >= filters.start_date)
        if filters.end_date:
            stmt = stmt.where(date_col_msk <= filters.end_date)
        if filters.bots:
            visible_bot_keys = [bot_key for bot_key in filters.bots if not is_excluded_bot_key(bot_key)]
            if not visible_bot_keys:
                stmt = stmt.where(text("1=0"))
            else:
                current_registry = aliased(BotRegistry)
                first_touch_registry = aliased(BotRegistry)
                last_touch_registry = aliased(BotRegistry)
                current_canonical_sq = (
                    select(current_registry.canonical_base)
                    .select_from(current_registry)
                    .where(current_registry.bot_key == RawBotUser.bot_key)
                    .scalar_subquery()
                )
                first_touch_canonical_sq = (
                    select(first_touch_registry.canonical_base)
                    .select_from(first_touch_registry)
                    .where(first_touch_registry.bot_key == RawBotUser.first_touch_bot)
                    .scalar_subquery()
                )
                last_touch_canonical_sq = (
                    select(last_touch_registry.canonical_base)
                    .select_from(last_touch_registry)
                    .where(last_touch_registry.bot_key == RawBotUser.last_touch_bot)
                    .scalar_subquery()
                )
                if touch_mode == "first":
                    stmt = stmt.where(
                        or_(
                            RawBotUser.first_touch_bot.in_(visible_bot_keys),
                            func.coalesce(first_touch_canonical_sq, RawBotUser.first_touch_bot).in_(visible_bot_keys),
                        )
                    )
                elif touch_mode == "last":
                    stmt = stmt.where(
                        or_(
                            RawBotUser.last_touch_bot.in_(visible_bot_keys),
                            func.coalesce(last_touch_canonical_sq, RawBotUser.last_touch_bot).in_(visible_bot_keys),
                        )
                    )
                else:
                    stmt = stmt.where(
                        or_(
                            RawBotUser.bot_key.in_(visible_bot_keys),
                            func.coalesce(current_canonical_sq, RawBotUser.bot_key).in_(visible_bot_keys),
                        )
                    )
                if any((bot or "").strip().lower() == "lead" for bot in visible_bot_keys):
                    stmt = stmt.where(self._lead_mirror_dedup_condition())
        if filters.advertising_companies:
            stmt = stmt.where(RawBotUser.advertising_company.in_(filters.advertising_companies))
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_source, RawBotUser.platform_utm_source, filters.utm_source)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_campaign, RawBotUser.platform_utm_campaign, filters.utm_campaign)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_medium, RawBotUser.platform_utm_medium, filters.utm_medium)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_content, RawBotUser.platform_utm_content, filters.utm_content)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_term, RawBotUser.platform_utm_term, filters.utm_term)
        return apply_employee_exclusion(stmt, RawBotUser.tg_user_id)

    def _apply_raw_filters(self, stmt, raw_filters: RawUserFilters, touch_mode: str = "event"):
        system_user = aliased(RawBotUser)
        current_registry = aliased(BotRegistry)
        first_touch_registry = aliased(BotRegistry)
        last_touch_registry = aliased(BotRegistry)
        first_seen_system_sq = (
            select(func.min(system_user.created_at))
            .select_from(system_user)
            .where(
                system_user.tg_user_id == RawBotUser.tg_user_id,
                func.lower(func.trim(func.coalesce(system_user.bot_key, ""))).notin_(normalized_excluded_bot_keys()),
            )
            .scalar_subquery()
        )
        touch_date_col = RawBotUser.created_at
        if touch_mode == "first":
            touch_date_col = first_seen_system_sq
        elif touch_mode == "last":
            touch_date_col = RawBotUser.learn_start_date
        touch_bot_first_seen_sq = None
        if touch_mode == "first":
            touch_bot_first_seen_sq = first_seen_system_sq
        elif touch_mode == "last":
            touch_bot_user = aliased(RawBotUser)
            touch_bot_first_seen_sq = (
                select(func.min(touch_bot_user.created_at))
                .select_from(touch_bot_user)
                .where(
                    touch_bot_user.tg_user_id == RawBotUser.tg_user_id,
                    touch_bot_user.bot_key == RawBotUser.last_touch_bot,
                )
                .scalar_subquery()
            )
        current_canonical_sq = (
            select(current_registry.canonical_base)
            .select_from(current_registry)
            .where(current_registry.bot_key == RawBotUser.bot_key)
            .scalar_subquery()
        )
        first_touch_canonical_sq = (
            select(first_touch_registry.canonical_base)
            .select_from(first_touch_registry)
            .where(first_touch_registry.bot_key == RawBotUser.first_touch_bot)
            .scalar_subquery()
        )
        last_touch_canonical_sq = (
            select(last_touch_registry.canonical_base)
            .select_from(last_touch_registry)
            .where(last_touch_registry.bot_key == RawBotUser.last_touch_bot)
            .scalar_subquery()
        )
        if raw_filters.bot_keys:
            visible_bot_keys = [bot_key for bot_key in raw_filters.bot_keys if not is_excluded_bot_key(bot_key)]
            if not visible_bot_keys:
                stmt = stmt.where(text("1=0"))
            else:
                # Base filter in RAW must always filter by row bot_key.
                stmt = stmt.where(
                    or_(
                        RawBotUser.bot_key.in_(visible_bot_keys),
                        func.coalesce(current_canonical_sq, RawBotUser.bot_key).in_(visible_bot_keys),
                    )
                )
                # In touch modes additionally require matching touch attribution bot.
                if touch_mode == "first":
                    stmt = stmt.where(
                        or_(
                            RawBotUser.first_touch_bot.in_(visible_bot_keys),
                            func.coalesce(first_touch_canonical_sq, RawBotUser.first_touch_bot).in_(visible_bot_keys),
                        )
                    )
                elif touch_mode == "last":
                    stmt = stmt.where(
                        or_(
                            RawBotUser.last_touch_bot.in_(visible_bot_keys),
                            func.coalesce(last_touch_canonical_sq, RawBotUser.last_touch_bot).in_(visible_bot_keys),
                        )
                    )
                if any((bot or "").strip().lower() == "lead" for bot in visible_bot_keys):
                    stmt = stmt.where(self._lead_mirror_dedup_condition())
        if raw_filters.tg_user_id:
            search_terms = self._split_search_terms(raw_filters.tg_user_id)
            if len(search_terms) > 1:
                numeric_terms = [int(term) for term in search_terms if term.isdigit()]
                username_terms = [term.lstrip("@") for term in search_terms if not term.isdigit()]
                conditions = []
                if numeric_terms:
                    conditions.append(RawBotUser.tg_user_id.in_(numeric_terms))
                if username_terms:
                    conditions.append(func.lower(RawBotUser.username).in_([term.lower() for term in username_terms]))
                if conditions:
                    stmt = stmt.where(or_(*conditions))
            else:
                term = search_terms[0] if search_terms else raw_filters.tg_user_id.strip()
                normalized_term = term.lstrip("@")
                if normalized_term.isdigit():
                    stmt = stmt.where(
                        or_(
                            RawBotUser.tg_user_id == int(normalized_term),
                            cast(RawBotUser.tg_user_id, String).ilike(f"%{normalized_term}%"),
                        )
                    )
                else:
                    stmt = stmt.where(
                        or_(
                            RawBotUser.username.ilike(f"%{normalized_term}%"),
                            cast(RawBotUser.tg_user_id, String).ilike(f"%{normalized_term}%"),
                        )
                    )
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_source, RawBotUser.platform_utm_source, raw_filters.utm_source)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_campaign, RawBotUser.platform_utm_campaign, raw_filters.utm_campaign)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_medium, RawBotUser.platform_utm_medium, raw_filters.utm_medium)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_content, RawBotUser.platform_utm_content, raw_filters.utm_content)
        stmt = self._apply_utm_filter(stmt, RawBotUser.utm_term, RawBotUser.platform_utm_term, raw_filters.utm_term)
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
            completed_condition = and_(
                RawBotUser.completed_course.is_(True),
                RawBotUser.completed_course_at.is_not(None),
                RawBotUser.completed_course_at >= RawBotUser.created_at,
            )
            stmt = stmt.where(completed_condition if raw_filters.completed_course else not_(completed_condition))
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
        if raw_filters.user_status:
            is_touch_mode = touch_mode in {"first", "last"}
            if is_touch_mode:
                scope_col = touch_bot_first_seen_sq if touch_bot_first_seen_sq is not None else touch_date_col
                is_new_scope = self._msk_date(first_seen_system_sq) == self._msk_date(scope_col)
                is_old_scope = self._msk_date(first_seen_system_sq) < self._msk_date(scope_col)
            else:
                is_new_scope = self._msk_date(first_seen_system_sq) == self._msk_date(touch_date_col)
                is_old_scope = self._msk_date(first_seen_system_sq) < self._msk_date(touch_date_col)
            if raw_filters.user_status == "new_in_system":
                stmt = stmt.where(is_new_scope)
            elif raw_filters.user_status == "new_in_bot":
                if touch_mode in {"first", "last"}:
                    stmt = stmt.where(is_new_scope)
                else:
                    stmt = stmt.where(
                        or_(
                            first_seen_system_sq == RawBotUser.created_at,
                            func.coalesce(current_canonical_sq, RawBotUser.bot_key)
                            == func.coalesce(first_touch_canonical_sq, RawBotUser.first_touch_bot),
                        )
                    )
            elif raw_filters.user_status == "old_in_system":
                stmt = stmt.where(is_old_scope)
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
        if raw_filters.source_categories:
            normalized = [v.strip().lower() for v in raw_filters.source_categories if v and v.strip()]
            conditions = []
            if "almanah" in normalized:
                conditions.append(
                    and_(
                        func.lower(func.trim(func.coalesce(RawBotUser.bot_key, ""))) == "lead",
                        or_(
                            RawBotUser.ph_user_id.is_(None),
                            func.abs(RawBotUser.tg_user_id) != RawBotUser.ph_user_id,
                        ),
                    )
                )
            if "direct_source" in normalized or "direct_link" in normalized or "ph_mirror_register" in normalized:
                conditions.append(
                    and_(
                        func.lower(func.trim(func.coalesce(RawBotUser.bot_key, ""))) == "lead",
                        RawBotUser.ph_user_id.is_not(None),
                        func.abs(RawBotUser.tg_user_id) == RawBotUser.ph_user_id,
                    )
                )
            if "bot_source" in normalized:
                conditions.append(
                    func.lower(func.trim(func.coalesce(RawBotUser.bot_key, ""))) != "lead"
                )
            if conditions:
                stmt = stmt.where(or_(*conditions))
        return stmt

    async def fetch_raw(
        self,
        session: AsyncSession,
        filters: ReportFilters,
        raw_filters: RawUserFilters,
        touch_mode: str = "event",
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_direction: str = "desc",
    ) -> tuple[List[dict[str, Any]], int]:
        base = select(RawBotUser)
        base = self._apply_filters(base, filters, touch_mode=touch_mode)
        base = self._apply_raw_filters(base, raw_filters, touch_mode=touch_mode)
        column = getattr(RawBotUser, sort_by)
        base = base.order_by(desc(column) if sort_direction == "desc" else column)
        stmt = base.offset(offset).limit(limit)
        count_stmt = select(func.count()).select_from(RawBotUser)
        count_stmt = self._apply_filters(count_stmt, filters, touch_mode=touch_mode)
        count_stmt = self._apply_raw_filters(count_stmt, raw_filters, touch_mode=touch_mode)
        total_result = await session.execute(count_stmt)
        total = total_result.scalar_one() or 0
        result = await session.execute(stmt)
        users = result.scalars().all()
        budget_cpa_map = await self._load_budget_cpa_learning(session, users)
        canonical_base_map = await self._load_canonical_base_map(session)
        first_seen_at_system_map, first_seen_at_bot_map = await self._load_first_seen_maps(session, users)
        mirror_map = await self._load_mirror_map(session, users)
        return [
            self._serialize(
                user,
                budget_cpa_map,
                canonical_base_map,
                first_seen_at_system_map,
                first_seen_at_bot_map,
                mirror_map,
                touch_mode=touch_mode,
            )
            for user in users
        ], total

    def _serialize(
        self,
        user: RawBotUser,
        budget_cpa_map: dict[tuple[str, str, str], float],
        canonical_base_map: dict[str, str],
        first_seen_at_system_map: dict[int, dt.datetime],
        first_seen_at_bot_map: dict[tuple[int, str], dt.datetime],
        mirror_map: dict[tuple[int | None, int | None], PhUserMirrorReplica],
        touch_mode: str = "event",
    ) -> dict[str, Optional[str]]:
        budget_value = 0.0
        completed_course = bool(
            user.completed_course
            and user.completed_course_at is not None
            and user.created_at is not None
            and user.completed_course_at >= user.created_at
        )
        course_duration_days: int | None = None
        if user.learn_start_date and user.completed_course_at and user.completed_course_at >= user.learn_start_date:
            course_duration_days = (user.completed_course_at.date() - user.learn_start_date.date()).days
        if user.learn_start_date and user.started_learning:
            day = user.learn_start_date.date().isoformat()
            campaign = (user.advertising_company or "нет метки").strip().lower()
            bot_key = (user.bot_key or "").strip().lower()
            budget_value = budget_cpa_map.get((day, campaign, bot_key), 0.0)
            if budget_value == 0.0:
                budget_value = budget_cpa_map.get((day, campaign, ""), 0.0)
        first_seen_at_system = first_seen_at_system_map.get(int(user.tg_user_id))
        first_seen_at_bot = first_seen_at_bot_map.get((int(user.tg_user_id), user.bot_key))
        current_canonical_base = self._canonical_base(user.bot_key, canonical_base_map)
        first_touch_canonical_base = self._canonical_base(user.first_touch_bot, canonical_base_map)
        lead_user_id = int(user.lead_user_id) if user.lead_user_id is not None else None
        ph_user_id = int(user.ph_user_id) if user.ph_user_id is not None else None
        mirror = (
            mirror_map.get((lead_user_id, ph_user_id))
            or mirror_map.get((lead_user_id, None))
            or mirror_map.get((None, ph_user_id))
        )
        reference_ts = user.created_at
        if touch_mode == "first":
            reference_ts = first_seen_at_bot_map.get((int(user.tg_user_id), user.first_touch_bot or ""))
        elif touch_mode == "last":
            reference_ts = first_seen_at_bot_map.get((int(user.tg_user_id), user.last_touch_bot or ""))
        new_in_system = False
        old_in_system = False
        if first_seen_at_system and reference_ts:
            if touch_mode in {"first", "last"}:
                new_in_system = first_seen_at_system.date() == reference_ts.date()
                old_in_system = first_seen_at_system.date() < reference_ts.date()
            else:
                new_in_system = reference_ts == first_seen_at_system
                old_in_system = first_seen_at_system < reference_ts
        if touch_mode in {"first", "last"}:
            new_in_bot = new_in_system
        else:
            new_in_bot = bool(
                current_canonical_base
                and first_touch_canonical_base
                and current_canonical_base == first_touch_canonical_base
            )
        payload = {
            "id": user.id,
            "bot_key": user.bot_key,
            "tg_user_id": user.tg_user_id,
            "ph_user_id": user.ph_user_id or (int(mirror.ph_id) if mirror and mirror.ph_id and str(mirror.ph_id).isdigit() else None),
            "username": user.username,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "first_seen_at_system": first_seen_at_system.isoformat() if first_seen_at_system else None,
            "first_seen_at_bot": first_seen_at_bot.isoformat() if first_seen_at_bot else None,
            "new_in_system": new_in_system,
            "new_in_bot": new_in_bot,
            "old_in_system": old_in_system,
            "user_block": user.user_block,
            "utm_source": user.utm_source or "(none)",
            "utm_campaign": user.utm_campaign or "(none)",
            "utm_medium": user.utm_medium,
            "utm_content": user.utm_content,
            "utm_term": user.utm_term,
            "platform_utm_source": user.platform_utm_source,
            "platform_utm_campaign": user.platform_utm_campaign,
            "platform_utm_medium": user.platform_utm_medium,
            "platform_utm_content": user.platform_utm_content,
            "platform_utm_term": user.platform_utm_term,
            "advertising_company": user.advertising_company,
            "budget": budget_value,
            "ingested_at": user.ingested_at.isoformat() if user.ingested_at else None,
            "converted_to_lead": user.converted_to_lead,
            "registered_platform": user.registered_platform or mirror is not None,
            "started_learning": user.started_learning,
            "completed_course": completed_course,
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
            "platform_registered_at": user.platform_registered_at.isoformat() if user.platform_registered_at else None,
            "completed_course_at": user.completed_course_at.isoformat() if user.completed_course_at else None,
            "course_duration_days": course_duration_days,
            "start_course": user.start_course,
            "referer": mirror.referer if mirror and mirror.referer else user.referer,
            "raw_link": mirror.raw_link if mirror and mirror.raw_link else user.raw_link,
            "bot_raw": mirror.bot_raw if mirror and mirror.bot_raw else user.bot_raw,
            "ph_raw": mirror.ph_raw if mirror and mirror.ph_raw else user.ph_raw,
            "last_activity": mirror.last_activity if mirror and mirror.last_activity else user.last_activity,
            "ph_group": mirror.ph_group if mirror and mirror.ph_group else user.ph_group,
            # Keep first touch visible even when it points to lead/almanah.
            "first_touch_bot": user.first_touch_bot,
            "first_touch_campaign": user.first_touch_campaign,
            "last_touch_bot": None if is_excluded_bot_key(user.last_touch_bot) else user.last_touch_bot,
            "last_touch_campaign": user.last_touch_campaign,
            "canonical_base": current_canonical_base,
            "first_touch_canonical_base": first_touch_canonical_base,
            "source_category": self._derive_source_category(user),
        }
        return payload
