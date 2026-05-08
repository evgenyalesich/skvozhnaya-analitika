from __future__ import annotations

import json
import re
import datetime as dt
from datetime import date as dt_date
from typing import List, Optional

from sqlalchemy import Date, and_, case, exists, func, not_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.analytics import BotRegistry, PhUserMirrorReplica, RawBotUser
from app.services.report_bot_scope import normalized_excluded_bot_keys
from app.services.utm_normalization import normalize_utm_filter_values


class RawUserRepositoryHelpersMixin:
    _LESSON_TS_RE = re.compile(r"\((\d{4}-\d{2}-\d{2}T[^\)]+)\)")

    @staticmethod
    def _msk_date(column):
        return func.timezone("Europe/Moscow", column).cast(Date)

    @staticmethod
    def _apply_utm_filter(stmt, primary_col, platform_col, values: list[str]):
        normalized = normalize_utm_filter_values(values)
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
    def _parse_json_value(value):
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped or stripped[0] not in "[{":
            return value
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value

    @staticmethod
    def _parse_mirror_datetime(value) -> dt.datetime | None:
        if not value or not isinstance(value, str):
            return None
        normalized = value.strip().replace("Z", "+00:00")
        if not normalized:
            return None
        try:
            return dt.datetime.fromisoformat(normalized.replace("T", " "))
        except ValueError:
            return None

    def _extract_platform_registered_at_from_mirror(self, mirror: PhUserMirrorReplica | None) -> dt.datetime | None:
        if mirror is None:
            return None
        for candidate in (mirror.authorization_date, mirror.ph_registration_at):
            parsed = self._parse_mirror_datetime(candidate)
            if parsed is not None:
                return parsed
        return None

    def _extract_learn_start_from_mirror(self, mirror: PhUserMirrorReplica | None) -> dt.datetime | None:
        if mirror is None:
            return None
        lessons = self._parse_json_value(mirror.lessons)
        if isinstance(lessons, str):
            lessons = [lessons]
        if not isinstance(lessons, list):
            return None
        earliest: dt.datetime | None = None
        for lesson in lessons:
            if not isinstance(lesson, str):
                continue
            for match in self._LESSON_TS_RE.findall(lesson):
                parsed = self._parse_mirror_datetime(match)
                if parsed is None:
                    continue
                if earliest is None or parsed < earliest:
                    earliest = parsed
        return earliest

    def _extract_course_from_mirror(self, mirror: PhUserMirrorReplica | None) -> str | None:
        if mirror is None:
            return None
        for source in (self._parse_json_value(mirror.courses), self._parse_json_value(mirror.lessons)):
            course = self._detect_course(source)
            if course:
                return course
        return None

    def _extract_utm_from_mirror(self, mirror: PhUserMirrorReplica | None) -> dict[str, str | None]:
        empty = {
            "utm_source": None,
            "utm_campaign": None,
            "utm_medium": None,
            "utm_content": None,
            "utm_term": None,
        }
        if mirror is None:
            return empty
        for source in (mirror.ph_utm, mirror.utm):
            parsed = self._parse_json_value(source)
            if not isinstance(parsed, dict):
                continue
            extracted = {
                "utm_source": self._normalize_mirror_utm_value(parsed.get("utm_source")),
                "utm_campaign": self._normalize_mirror_utm_value(parsed.get("utm_campaign")),
                "utm_medium": self._normalize_mirror_utm_value(parsed.get("utm_medium")),
                "utm_content": self._normalize_mirror_utm_value(parsed.get("utm_content")),
                "utm_term": self._normalize_mirror_utm_value(parsed.get("utm_term")),
            }
            if any(extracted.values()):
                return extracted
        return empty

    @staticmethod
    def _normalize_mirror_utm_value(value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return text

    def _detect_course(self, source) -> str | None:
        fallback_base = False
        for item in self._flatten_course_source(source):
            course = self._normalize_course(item)
            if course in {"MTT", "SPIN", "CASH"}:
                return course
            if course == "BASE":
                fallback_base = True
        if fallback_base:
            return "BASE"
        return None

    def _flatten_course_source(self, source):
        if isinstance(source, str):
            parsed = self._parse_json_value(source)
            if parsed is not source:
                yield from self._flatten_course_source(parsed)
                return
        if source is None:
            return
        if isinstance(source, dict):
            for value in source.values():
                yield from self._flatten_course_source(value)
            return
        if isinstance(source, list):
            for value in source:
                yield from self._flatten_course_source(value)
            return
        yield source

    @staticmethod
    def _normalize_course(value) -> str | None:
        if not value or not isinstance(value, str):
            return None
        upper = value.upper()
        if "MTT" in upper or "МТТ" in upper:
            return "MTT"
        if "SPIN" in upper or "СПИН" in upper:
            return "SPIN"
        if "CASH" in upper or "КЭШ" in upper or "КЕШ" in upper:
            return "CASH"
        if "БАЗОВ" in upper or "BASE" in upper:
            return "BASE"
        return None

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

    async def _load_user_platform_map(
        self, session: AsyncSession, users: List[RawBotUser]
    ) -> dict[int, dict[str, int | dt.datetime | bool | None]]:
        tg_user_ids = sorted({int(user.tg_user_id) for user in users if user.tg_user_id is not None})
        if not tg_user_ids:
            return {}
        stmt = (
            select(
                RawBotUser.tg_user_id,
                func.min(RawBotUser.platform_registered_at)
                .filter(
                    RawBotUser.ph_user_id.is_not(None),
                    RawBotUser.platform_registered_at.is_not(None),
                )
                .label("platform_registered_at"),
                func.max(RawBotUser.ph_user_id)
                .filter(RawBotUser.ph_user_id.is_not(None))
                .label("ph_user_id"),
                func.min(RawBotUser.learn_start_date)
                .filter(RawBotUser.learn_start_date.is_not(None))
                .label("learn_start_date"),
                func.bool_or(
                    or_(
                        RawBotUser.started_learning.is_(True),
                        RawBotUser.learn_start_date.is_not(None),
                    )
                ).label("started_learning"),
                func.max(RawBotUser.start_course)
                .filter(RawBotUser.start_course.is_not(None))
                .label("start_course"),
                func.min(RawBotUser.completed_course_at)
                .filter(RawBotUser.completed_course_at.is_not(None))
                .label("completed_course_at"),
                func.bool_or(
                    or_(
                        RawBotUser.completed_course.is_(True),
                        RawBotUser.completed_course_at.is_not(None),
                    )
                ).label("completed_course"),
                func.bool_or(RawBotUser.interview_reached.is_(True)).label("interview_reached"),
                func.bool_or(RawBotUser.interview_passed.is_(True)).label("interview_passed"),
                func.bool_or(RawBotUser.offer_received.is_(True)).label("offer_received"),
                func.bool_or(RawBotUser.contract_signed.is_(True)).label("contract_signed"),
                func.bool_or(RawBotUser.distance_grinding.is_(True)).label("distance_grinding"),
                func.min(RawBotUser.interview_reached_at)
                .filter(RawBotUser.interview_reached_at.is_not(None))
                .label("interview_reached_at"),
                func.min(RawBotUser.interview_passed_at)
                .filter(RawBotUser.interview_passed_at.is_not(None))
                .label("interview_passed_at"),
                func.min(RawBotUser.offer_received_at)
                .filter(RawBotUser.offer_received_at.is_not(None))
                .label("offer_received_at"),
                func.min(RawBotUser.contract_signed_at)
                .filter(RawBotUser.contract_signed_at.is_not(None))
                .label("contract_signed_at"),
                func.max(RawBotUser.interview_reached_status)
                .filter(RawBotUser.interview_reached_status.is_not(None))
                .label("interview_reached_status"),
                func.max(RawBotUser.interview_passed_status)
                .filter(RawBotUser.interview_passed_status.is_not(None))
                .label("interview_passed_status"),
                func.max(RawBotUser.offer_received_status)
                .filter(RawBotUser.offer_received_status.is_not(None))
                .label("offer_received_status"),
                func.max(RawBotUser.contract_signed_status)
                .filter(RawBotUser.contract_signed_status.is_not(None))
                .label("contract_signed_status"),
            )
            .where(RawBotUser.tg_user_id.in_(tg_user_ids))
            .group_by(RawBotUser.tg_user_id)
        )
        result = await session.execute(stmt)
        payload: dict[int, dict[str, int | dt.datetime | bool | None]] = {}
        for row in result:
            if row.tg_user_id is None:
                continue
            platform_registered_at = row.platform_registered_at
            ph_user_id = int(row.ph_user_id) if row.ph_user_id is not None else None
            payload[int(row.tg_user_id)] = {
                "registered_platform": platform_registered_at is not None and ph_user_id is not None,
                "platform_registered_at": platform_registered_at,
                "ph_user_id": ph_user_id,
                "learn_start_date": row.learn_start_date,
                "started_learning": bool(row.started_learning),
                "start_course": row.start_course,
                "completed_course_at": row.completed_course_at,
                "completed_course": bool(row.completed_course),
                "interview_reached": bool(row.interview_reached),
                "interview_passed": bool(row.interview_passed),
                "offer_received": bool(row.offer_received),
                "contract_signed": bool(row.contract_signed),
                "distance_grinding": bool(row.distance_grinding),
                "interview_reached_at": row.interview_reached_at,
                "interview_passed_at": row.interview_passed_at,
                "offer_received_at": row.offer_received_at,
                "contract_signed_at": row.contract_signed_at,
                "interview_reached_status": row.interview_reached_status,
                "interview_passed_status": row.interview_passed_status,
                "offer_received_status": row.offer_received_status,
                "contract_signed_status": row.contract_signed_status,
            }
        return payload

    async def _load_mirror_map(self, session: AsyncSession, users: List[RawBotUser]) -> dict[tuple[int | None, int | None], PhUserMirrorReplica]:
        lead_user_ids = sorted({int(user.lead_user_id) for user in users if user.lead_user_id is not None})
        tg_user_ids = sorted({int(user.tg_user_id) for user in users if user.tg_user_id is not None})
        ph_ids = sorted({str(int(user.ph_user_id)) for user in users if user.ph_user_id is not None})
        conditions = []
        if lead_user_ids:
            conditions.append(PhUserMirrorReplica.id.in_(lead_user_ids))
        if tg_user_ids:
            conditions.append(PhUserMirrorReplica.id.in_(tg_user_ids))
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
