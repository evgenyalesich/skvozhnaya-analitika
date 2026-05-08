from __future__ import annotations

import datetime as dt
from datetime import date as dt_date
from typing import Any, List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.report_filters import RawUserFilters, ReportFilters
from app.models.analytics import PhUserMirrorReplica, RawBotUser
from app.services.report_bot_scope import is_excluded_bot_key


class RawUserRepositoryFetchMixin:
    """Получение и сериализация сырых пользователей для таблицы RawUsersTable."""

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
        """Пагинированная выборка пользователей с обогащением из зеркальной таблицы.

        Возвращает (список_записей, total_count). Помимо raw-полей добавляет:
        - first_seen_at_system / first_seen_at_bot — из агрегирующего подзапроса
        - new_in_system / old_in_system / new_in_bot — вычисляемые флаги
        - данные из PhUserMirrorReplica (referer, ph_raw, ph_group и др.)
        - course_duration_days — количество дней от старта до завершения курса
        - budget — бюджет из агрегата по дню+компании+боту
        """
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
        user_platform_map = await self._load_user_platform_map(session, users)
        mirror_map = await self._load_mirror_map(session, users)
        return [
            self._serialize(
                user,
                budget_cpa_map,
                canonical_base_map,
                first_seen_at_system_map,
                first_seen_at_bot_map,
                user_platform_map,
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
        user_platform_map: dict[int, dict[str, int | dt.datetime | bool | None]],
        mirror_map: dict[tuple[int | None, int | None], PhUserMirrorReplica],
        touch_mode: str = "event",
    ) -> dict[str, Optional[str]]:
        """Сериализует одну запись RawBotUser в dict для API-ответа.

        Обогащает данными из mirror_map (PhUserMirrorReplica - приоритет над raw).
        new_in_system: пользователь впервые в системе именно этот день.
        old_in_system: уже был в системе до этого события.
        Для touch_mode first/last использует дату первого/последнего касания как reference.
        """
        budget_value = 0.0
        course_duration_days: int | None = None
        first_seen_at_system = first_seen_at_system_map.get(int(user.tg_user_id))
        first_seen_at_bot = first_seen_at_bot_map.get((int(user.tg_user_id), user.bot_key))
        current_canonical_base = self._canonical_base(user.bot_key, canonical_base_map)
        first_touch_canonical_base = self._canonical_base(user.first_touch_bot, canonical_base_map)
        lead_user_id = int(user.lead_user_id) if user.lead_user_id is not None else None
        ph_user_id = int(user.ph_user_id) if user.ph_user_id is not None else None
        mirror = (
            mirror_map.get((lead_user_id, ph_user_id))
            or mirror_map.get((int(user.tg_user_id), ph_user_id))
            or mirror_map.get((int(user.tg_user_id), None))
            or mirror_map.get((lead_user_id, None))
            or mirror_map.get((None, ph_user_id))
        )
        platform_meta = user_platform_map.get(int(user.tg_user_id))
        platform_meta_registered_at = platform_meta.get("platform_registered_at") if platform_meta else None
        platform_meta_ph_user_id = platform_meta.get("ph_user_id") if platform_meta else None
        platform_meta_learn_start = platform_meta.get("learn_start_date") if platform_meta else None
        platform_meta_started_learning = bool(platform_meta.get("started_learning")) if platform_meta else False
        platform_meta_start_course = platform_meta.get("start_course") if platform_meta else None
        platform_meta_completed_course_at = platform_meta.get("completed_course_at") if platform_meta else None
        platform_meta_completed_course = bool(platform_meta.get("completed_course")) if platform_meta else False
        platform_meta_interview_reached = bool(platform_meta.get("interview_reached")) if platform_meta else False
        platform_meta_interview_passed = bool(platform_meta.get("interview_passed")) if platform_meta else False
        platform_meta_offer_received = bool(platform_meta.get("offer_received")) if platform_meta else False
        platform_meta_contract_signed = bool(platform_meta.get("contract_signed")) if platform_meta else False
        platform_meta_distance_grinding = bool(platform_meta.get("distance_grinding")) if platform_meta else False
        platform_meta_interview_reached_at = platform_meta.get("interview_reached_at") if platform_meta else None
        platform_meta_interview_passed_at = platform_meta.get("interview_passed_at") if platform_meta else None
        platform_meta_offer_received_at = platform_meta.get("offer_received_at") if platform_meta else None
        platform_meta_contract_signed_at = platform_meta.get("contract_signed_at") if platform_meta else None
        platform_meta_interview_reached_status = platform_meta.get("interview_reached_status") if platform_meta else None
        platform_meta_interview_passed_status = platform_meta.get("interview_passed_status") if platform_meta else None
        platform_meta_offer_received_status = platform_meta.get("offer_received_status") if platform_meta else None
        platform_meta_contract_signed_status = platform_meta.get("contract_signed_status") if platform_meta else None
        effective_ph_user_id = user.ph_user_id or platform_meta_ph_user_id or (
            int(mirror.ph_id) if mirror and mirror.ph_id and str(mirror.ph_id).isdigit() else None
        )
        if mirror is None and effective_ph_user_id is not None:
            mirror = mirror_map.get((int(user.tg_user_id), effective_ph_user_id)) or mirror_map.get((None, effective_ph_user_id))
        effective_platform_registered_at = (
            user.platform_registered_at
            or platform_meta_registered_at
            or self._extract_platform_registered_at_from_mirror(mirror)
        )
        effective_learn_start_date = user.learn_start_date or platform_meta_learn_start or self._extract_learn_start_from_mirror(mirror)
        effective_start_course = user.start_course or platform_meta_start_course or self._extract_course_from_mirror(mirror)
        effective_started_learning = user.started_learning or platform_meta_started_learning or effective_learn_start_date is not None
        effective_completed_course_at = user.completed_course_at or platform_meta_completed_course_at
        effective_completed_course = user.completed_course or platform_meta_completed_course
        effective_interview_reached = user.interview_reached or platform_meta_interview_reached
        effective_interview_passed = user.interview_passed or platform_meta_interview_passed
        effective_offer_received = user.offer_received or platform_meta_offer_received
        effective_contract_signed = user.contract_signed or platform_meta_contract_signed
        effective_distance_grinding = user.distance_grinding or platform_meta_distance_grinding
        effective_interview_reached_at = user.interview_reached_at or platform_meta_interview_reached_at
        effective_interview_passed_at = user.interview_passed_at or platform_meta_interview_passed_at
        effective_offer_received_at = user.offer_received_at or platform_meta_offer_received_at
        effective_contract_signed_at = user.contract_signed_at or platform_meta_contract_signed_at
        effective_interview_reached_status = user.interview_reached_status or platform_meta_interview_reached_status
        effective_interview_passed_status = user.interview_passed_status or platform_meta_interview_passed_status
        effective_offer_received_status = user.offer_received_status or platform_meta_offer_received_status
        effective_contract_signed_status = user.contract_signed_status or platform_meta_contract_signed_status
        mirror_utm = self._extract_utm_from_mirror(mirror)
        if effective_learn_start_date and effective_completed_course_at and effective_completed_course_at >= effective_learn_start_date:
            course_duration_days = (effective_completed_course_at.date() - effective_learn_start_date.date()).days
            effective_completed_course = True
        if effective_learn_start_date and effective_started_learning:
            day = effective_learn_start_date.date().isoformat()
            campaign = (user.advertising_company or "нет метки").strip().lower()
            bot_key = (user.bot_key or "").strip().lower()
            budget_value = budget_cpa_map.get((day, campaign, bot_key), 0.0)
            if budget_value == 0.0:
                budget_value = budget_cpa_map.get((day, campaign, ""), 0.0)
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
            "ph_user_id": effective_ph_user_id,
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
            "platform_utm_source": user.platform_utm_source or mirror_utm.get("utm_source"),
            "platform_utm_campaign": user.platform_utm_campaign or mirror_utm.get("utm_campaign"),
            "platform_utm_medium": user.platform_utm_medium or mirror_utm.get("utm_medium"),
            "platform_utm_content": user.platform_utm_content or mirror_utm.get("utm_content"),
            "platform_utm_term": user.platform_utm_term or mirror_utm.get("utm_term"),
            "advertising_company": user.advertising_company,
            "budget": budget_value,
            "ingested_at": user.ingested_at.isoformat() if user.ingested_at else None,
            "converted_to_lead": user.converted_to_lead,
            "registered_platform": user.registered_platform or bool(platform_meta and platform_meta.get("registered_platform")) or effective_platform_registered_at is not None or mirror is not None,
            "started_learning": effective_started_learning,
            "completed_course": effective_completed_course,
            "used_simulator": user.used_simulator,
            "interview_reached": effective_interview_reached,
            "interview_passed": effective_interview_passed,
            "offer_received": effective_offer_received,
            "contract_signed": effective_contract_signed,
            "interview_reached_at": effective_interview_reached_at.isoformat() if effective_interview_reached_at else None,
            "interview_passed_at": effective_interview_passed_at.isoformat() if effective_interview_passed_at else None,
            "offer_received_at": effective_offer_received_at.isoformat() if effective_offer_received_at else None,
            "contract_signed_at": effective_contract_signed_at.isoformat() if effective_contract_signed_at else None,
            "distance_grinding": effective_distance_grinding,
            "interview_reached_status": effective_interview_reached_status,
            "interview_passed_status": effective_interview_passed_status,
            "offer_received_status": effective_offer_received_status,
            "contract_signed_status": effective_contract_signed_status,
            "channel_subscribed": user.channel_subscribed,
            "channel_subscribed_at": user.channel_subscribed_at.isoformat() if user.channel_subscribed_at else None,
            "community_member": user.community_member,
            "team_member": user.team_member,
            "community_member_status": user.community_member_status,
            "internal_status": user.internal_status,
            "learn_start_date": effective_learn_start_date.isoformat() if effective_learn_start_date else None,
            "platform_registered_at": effective_platform_registered_at.isoformat() if effective_platform_registered_at else None,
            "completed_course_at": effective_completed_course_at.isoformat() if effective_completed_course_at else None,
            "course_duration_days": course_duration_days,
            "start_course": effective_start_course,
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
