from __future__ import annotations

from datetime import date as dt_date
from typing import Optional

from sqlalchemy import String, and_, cast, exists, func, literal, literal_column, not_, or_, select, text
from sqlalchemy.orm import aliased

from app.api.report_filters import RawUserFilters, ReportFilters
from app.models.analytics import BotRegistry, RawBotUser
from app.services.employee_registry_service import apply_employee_exclusion
from app.services.report_bot_scope import apply_excluded_bot_filter, normalized_excluded_bot_keys
from app.services.report_bot_scope import is_excluded_bot_key


class RawUserRepositoryFiltersMixin:
    def _apply_filters(self, stmt, filters: ReportFilters, touch_mode: str = "event"):
        stmt = apply_excluded_bot_filter(stmt, RawBotUser.bot_key)
        first_touch_user = aliased(RawBotUser)
        first_touch_pick_user = aliased(RawBotUser)
        platform_user = aliased(RawBotUser)
        last_touch_user = aliased(RawBotUser)
        last_touch_pick_user = aliased(RawBotUser)
        excluded_keys = normalized_excluded_bot_keys()
        first_touch_base_condition = and_(
            first_touch_user.tg_user_id == RawBotUser.tg_user_id,
            first_touch_user.created_at.is_not(None),
            func.lower(func.trim(func.coalesce(first_touch_user.bot_key, ""))).notin_(excluded_keys),
            func.lower(func.trim(func.coalesce(first_touch_user.bot_key, ""))).notlike("lead%"),
        )
        first_touch_pick_condition = and_(
            first_touch_pick_user.tg_user_id == RawBotUser.tg_user_id,
            first_touch_pick_user.created_at.is_not(None),
            func.lower(func.trim(func.coalesce(first_touch_pick_user.bot_key, ""))).notin_(excluded_keys),
            func.lower(func.trim(func.coalesce(first_touch_pick_user.bot_key, ""))).notlike("lead%"),
        )
        last_touch_base_condition = and_(
            last_touch_user.tg_user_id == RawBotUser.tg_user_id,
            last_touch_user.created_at.is_not(None),
            func.lower(func.trim(func.coalesce(last_touch_user.bot_key, ""))).notin_(excluded_keys),
            func.lower(func.trim(func.coalesce(last_touch_user.bot_key, ""))).notlike("lead%"),
        )
        last_touch_pick_condition = and_(
            last_touch_pick_user.tg_user_id == RawBotUser.tg_user_id,
            last_touch_pick_user.created_at.is_not(None),
            func.lower(func.trim(func.coalesce(last_touch_pick_user.bot_key, ""))).notin_(excluded_keys),
            func.lower(func.trim(func.coalesce(last_touch_pick_user.bot_key, ""))).notlike("lead%"),
        )
        first_touch_at_sq = (
            select(func.min(first_touch_user.created_at))
            .select_from(first_touch_user)
            .where(first_touch_base_condition)
            .scalar_subquery()
        )
        first_touch_bot_sq = (
            select(first_touch_pick_user.bot_key)
            .select_from(first_touch_pick_user)
            .where(first_touch_pick_condition)
            .order_by(first_touch_pick_user.created_at.asc(), first_touch_pick_user.bot_key.asc())
            .limit(1)
            .scalar_subquery()
        )
        first_platform_at_sq = (
            select(func.min(platform_user.platform_registered_at))
            .select_from(platform_user)
            .where(
                platform_user.tg_user_id == RawBotUser.tg_user_id,
                platform_user.ph_user_id.is_not(None),
                platform_user.platform_registered_at.is_not(None),
            )
            .scalar_subquery()
        )
        last_touch_at_sq = (
            select(last_touch_user.created_at)
            .select_from(last_touch_user)
            .where(
                last_touch_base_condition,
                or_(
                    first_platform_at_sq.is_(None),
                    last_touch_user.created_at <= first_platform_at_sq,
                ),
            )
            .order_by(last_touch_user.created_at.desc(), last_touch_user.bot_key.asc())
            .limit(1)
            .scalar_subquery()
        )
        last_touch_bot_sq = (
            select(last_touch_pick_user.bot_key)
            .select_from(last_touch_pick_user)
            .where(
                last_touch_pick_condition,
                or_(
                    first_platform_at_sq.is_(None),
                    last_touch_pick_user.created_at <= first_platform_at_sq,
                ),
            )
            .order_by(last_touch_pick_user.created_at.desc(), last_touch_pick_user.bot_key.asc())
            .limit(1)
            .scalar_subquery()
        )
        date_col = RawBotUser.created_at
        touch_bot_expr = RawBotUser.bot_key
        if touch_mode == "first":
            date_col = first_touch_at_sq
            touch_bot_expr = first_touch_bot_sq
            stmt = stmt.where(
                RawBotUser.created_at == first_touch_at_sq,
                RawBotUser.bot_key == first_touch_bot_sq,
            )
        elif touch_mode == "last":
            date_col = last_touch_at_sq
            touch_bot_expr = last_touch_bot_sq
            stmt = stmt.where(
                RawBotUser.created_at == last_touch_at_sq,
                RawBotUser.bot_key == last_touch_bot_sq,
            )
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
                touch_registry = aliased(BotRegistry)
                current_canonical_sq = (
                    select(current_registry.canonical_base)
                    .select_from(current_registry)
                    .where(current_registry.bot_key == RawBotUser.bot_key)
                    .scalar_subquery()
                )
                touch_canonical_sq = (
                    select(touch_registry.canonical_base)
                    .select_from(touch_registry)
                    .where(touch_registry.bot_key == touch_bot_expr)
                    .scalar_subquery()
                )
                if touch_mode == "first":
                    stmt = stmt.where(
                        or_(
                            touch_bot_expr.in_(visible_bot_keys),
                            func.coalesce(touch_canonical_sq, touch_bot_expr).in_(visible_bot_keys),
                        )
                    )
                elif touch_mode == "last":
                    stmt = stmt.where(
                        or_(
                            touch_bot_expr.in_(visible_bot_keys),
                            func.coalesce(touch_canonical_sq, touch_bot_expr).in_(visible_bot_keys),
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
        if touch_mode == "first_touch":
            touch_mode = "first"
        elif touch_mode == "last_touch":
            touch_mode = "last"
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
            platform_user = aliased(RawBotUser)
            did_platform = exists(
                select(1)
                .select_from(platform_user)
                .where(
                    platform_user.tg_user_id == RawBotUser.tg_user_id,
                    platform_user.ph_user_id.is_not(None),
                    platform_user.platform_registered_at.is_not(None),
                )
            )
            stmt = stmt.where(did_platform if raw_filters.registered_platform else not_(did_platform))
        if raw_filters.started_learning is not None:
            learning_user = aliased(RawBotUser)
            did_learning = exists(
                select(1)
                .select_from(learning_user)
                .where(
                    learning_user.tg_user_id == RawBotUser.tg_user_id,
                    or_(
                        learning_user.started_learning.is_(True),
                        learning_user.learn_start_date.is_not(None),
                    ),
                )
            )
            stmt = stmt.where(did_learning if raw_filters.started_learning else not_(did_learning))
        if raw_filters.completed_course is not None:
            completed_user = aliased(RawBotUser)
            completed_condition = exists(
                select(1)
                .select_from(completed_user)
                .where(
                    completed_user.tg_user_id == RawBotUser.tg_user_id,
                    or_(
                        completed_user.completed_course.is_(True),
                        completed_user.completed_course_at.is_not(None),
                    ),
                )
            )
            stmt = stmt.where(completed_condition if raw_filters.completed_course else not_(completed_condition))
        if raw_filters.used_simulator is not None:
            stmt = stmt.where(RawBotUser.used_simulator.is_(raw_filters.used_simulator))
        if raw_filters.interview_reached is not None:
            interview_user = aliased(RawBotUser)
            did_interview = exists(
                select(1)
                .select_from(interview_user)
                .where(
                    interview_user.tg_user_id == RawBotUser.tg_user_id,
                    interview_user.interview_reached.is_(True),
                )
            )
            stmt = stmt.where(did_interview if raw_filters.interview_reached else not_(did_interview))
        if raw_filters.interview_passed is not None:
            passed_user = aliased(RawBotUser)
            did_passed = exists(
                select(1)
                .select_from(passed_user)
                .where(
                    passed_user.tg_user_id == RawBotUser.tg_user_id,
                    passed_user.interview_passed.is_(True),
                )
            )
            stmt = stmt.where(did_passed if raw_filters.interview_passed else not_(did_passed))
        if raw_filters.offer_received is not None:
            offer_user = aliased(RawBotUser)
            did_offer = exists(
                select(1)
                .select_from(offer_user)
                .where(
                    offer_user.tg_user_id == RawBotUser.tg_user_id,
                    offer_user.offer_received.is_(True),
                )
            )
            stmt = stmt.where(did_offer if raw_filters.offer_received else not_(did_offer))
        if raw_filters.contract_signed is not None:
            contract_user = aliased(RawBotUser)
            did_contract = exists(
                select(1)
                .select_from(contract_user)
                .where(
                    contract_user.tg_user_id == RawBotUser.tg_user_id,
                    contract_user.contract_signed.is_(True),
                )
            )
            stmt = stmt.where(did_contract if raw_filters.contract_signed else not_(did_contract))
        if raw_filters.distance_grinding is not None:
            distance_user = aliased(RawBotUser)
            did_distance = exists(
                select(1)
                .select_from(distance_user)
                .where(
                    distance_user.tg_user_id == RawBotUser.tg_user_id,
                    distance_user.distance_grinding.is_(True),
                )
            )
            stmt = stmt.where(did_distance if raw_filters.distance_grinding else not_(did_distance))
        if raw_filters.interview_reached_status:
            interview_status_user = aliased(RawBotUser)
            stmt = stmt.where(
                exists(
                    select(1)
                    .select_from(interview_status_user)
                    .where(
                        interview_status_user.tg_user_id == RawBotUser.tg_user_id,
                        interview_status_user.interview_reached_status.ilike(f"%{raw_filters.interview_reached_status}%"),
                    )
                )
            )
        if raw_filters.interview_passed_status:
            passed_status_user = aliased(RawBotUser)
            stmt = stmt.where(
                exists(
                    select(1)
                    .select_from(passed_status_user)
                    .where(
                        passed_status_user.tg_user_id == RawBotUser.tg_user_id,
                        passed_status_user.interview_passed_status.ilike(f"%{raw_filters.interview_passed_status}%"),
                    )
                )
            )
        if raw_filters.offer_received_status:
            offer_status_user = aliased(RawBotUser)
            stmt = stmt.where(
                exists(
                    select(1)
                    .select_from(offer_status_user)
                    .where(
                        offer_status_user.tg_user_id == RawBotUser.tg_user_id,
                        offer_status_user.offer_received_status.ilike(f"%{raw_filters.offer_received_status}%"),
                    )
                )
            )
        if raw_filters.contract_signed_status:
            contract_status_user = aliased(RawBotUser)
            stmt = stmt.where(
                exists(
                    select(1)
                    .select_from(contract_status_user)
                    .where(
                        contract_status_user.tg_user_id == RawBotUser.tg_user_id,
                        contract_status_user.contract_signed_status.ilike(f"%{raw_filters.contract_signed_status}%"),
                    )
                )
            )
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
