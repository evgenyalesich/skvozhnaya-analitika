import asyncio
from datetime import datetime
import json
import logging
import re
from typing import Any, Optional
from urllib.parse import parse_qsl, urlparse

import asyncpg
from sqlalchemy import update, func, or_, and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.analytics import RawBotUser


class PokerHubIngestor:
    LESSON_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")

    def __init__(self):
        self._logger = logging.getLogger("pokerhub_ingestor")
        try:
            import asyncpg as _asyncpg  # type: ignore
        except Exception:  # pragma: no cover
            _asyncpg = None
        self._asyncpg = _asyncpg

    def _is_deadlock(self, exc: Exception) -> bool:
        if not isinstance(exc, DBAPIError):
            return False
        orig = exc.orig
        if orig is None:
            return False
        if self._asyncpg is not None and isinstance(orig, self._asyncpg.exceptions.DeadlockDetectedError):
            return True
        return "DeadlockDetectedError" in str(orig) or "deadlock detected" in str(orig).lower()

    @staticmethod
    def _normalize_utm_struct(utm_obj: Any) -> dict[str, str]:
        if isinstance(utm_obj, str):
            try:
                utm_obj = json.loads(utm_obj)
            except json.JSONDecodeError:
                return {}
        if not isinstance(utm_obj, dict):
            return {}
        key_map = {
            "utm_source": "utm_source",
            "source": "utm_source",
            "utm_campaign": "utm_campaign",
            "campaign": "utm_campaign",
            "utm_medium": "utm_medium",
            "medium": "utm_medium",
            "utm_content": "utm_content",
            "content": "utm_content",
            "utm_term": "utm_term",
            "term": "utm_term",
        }
        result: dict[str, str] = {}
        for raw_key, raw_value in utm_obj.items():
            if not isinstance(raw_key, str):
                continue
            target_key = key_map.get(raw_key.strip().lower())
            if not target_key:
                continue
            if not isinstance(raw_value, str):
                continue
            value = raw_value.strip()
            if not value or value.lower() in {"null", "none"}:
                continue
            result[target_key] = value
        return result

    @staticmethod
    def _parse_utm_from_link(raw_link: str) -> dict[str, str]:
        if not raw_link or not isinstance(raw_link, str):
            return {}
        key_map = {
            "utm_source": "utm_source",
            "source": "utm_source",
            "utm_campaign": "utm_campaign",
            "campaign": "utm_campaign",
            "utm_medium": "utm_medium",
            "medium": "utm_medium",
            "utm_content": "utm_content",
            "content": "utm_content",
            "utm_term": "utm_term",
            "term": "utm_term",
        }
        result: dict[str, str] = {}
        try:
            parsed = urlparse(raw_link)
            pairs = parse_qsl(parsed.query or "", keep_blank_values=False)
            if parsed.fragment and "=" in parsed.fragment:
                pairs.extend(parse_qsl(parsed.fragment, keep_blank_values=False))
            for raw_key, raw_value in pairs:
                key = key_map.get(str(raw_key).strip().lower())
                if not key:
                    continue
                value = str(raw_value).strip()
                if value and key not in result:
                    result[key] = value
        except Exception:
            return {}
        return result

    @staticmethod
    def _normalize_mirror_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="ignore")
        text_value = str(value).strip()
        if not text_value or text_value.lower() in {"null", "none"}:
            return None
        return text_value

    async def ingest(self, session: AsyncSession) -> None:
        if not settings.lead_db_dsn:
            return
        dsn = str(settings.lead_db_dsn)
        if dsn.startswith("postgresql+asyncpg://"):
            dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
        mirror_rows = await self._fetch_ph_user_mirror(dsn)
        if mirror_rows:
            await self._apply_mirror(session, mirror_rows)

    async def _fetch_ph_user_mirror(self, dsn: str) -> list[dict[str, Any]]:
        """Fetch all users from ph_user_mirror — the complete pokerhub user list."""
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(
                """
                SELECT
                    ph_id,
                    username,
                    ph_registration,
                    ph_registration_at,
                    authorization_date,
                    last_activity,
                    courses,
                    lessons,
                    utm,
                    ph_utm,
                    referer,
                    raw_link,
                    bot_raw,
                    ph_raw,
                    "group"
                FROM ph_user_mirror
                """
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                result.append({
                    "ph_id": row["ph_id"],
                    "username": row["username"],
                    "ph_registration": row["ph_registration"],
                    "ph_registration_at": row["ph_registration_at"],
                    "authorization_date": row["authorization_date"],
                    "last_activity": row["last_activity"],
                    "courses": row["courses"],
                    "lessons": row["lessons"],
                    "utm": row["utm"],
                    "ph_utm": row["ph_utm"],
                    "referer": row["referer"],
                    "raw_link": row["raw_link"],
                    "bot_raw": row["bot_raw"],
                    "ph_raw": row["ph_raw"],
                    "group": row["group"],
                })
            return result
        finally:
            await conn.close()

    def _extract_utm_from_payload(self, payload: dict[str, Any]) -> dict[str, str]:
        """Extract UTM params from pokerhub payload.

        Merges structured 'utm' object (primary) with params parsed from raw
        link fields (referer, raw_link, bot_raw, ph_raw). Structured object wins
        on conflict; raw links fill in any fields missing from the object.
        """
        utm: dict[str, str] = {}

        for utm_field_name in ("utm", "ph_utm"):
            utm.update(self._normalize_utm_struct(payload.get(utm_field_name)))

        for field in ("referer", "raw_link", "bot_raw", "ph_raw"):
            raw = payload.get(field)
            if not raw or not isinstance(raw, str):
                continue
            parsed_link_utm = self._parse_utm_from_link(raw)
            for key, value in parsed_link_utm.items():
                if key not in utm and value:
                    utm[key] = value

        return utm

    async def _apply_mirror(self, session: AsyncSession, rows: list[dict[str, Any]]) -> None:
        """Apply ph_user_mirror data keyed by ph_id — one synthetic record per PH user."""
        ph_rows: list[dict[str, Any]] = []
        mirror_updates: dict[int, dict[str, Any]] = {}

        for row in rows:
            try:
                ph_id = int(str(row.get("ph_id")))
            except (TypeError, ValueError):
                continue
            if ph_id <= 0:
                continue

            auth_date = row.get("authorization_date")
            if isinstance(auth_date, str):
                # Strip timezone offset so mirror's local time is stored as-is (naive),
                # keeping week groupings consistent with ph_user_mirror display.
                import re as _re
                auth_date_naive = _re.sub(r'[+-]\d{2}:?\d{2}$', '', auth_date.rstrip('Z')).strip()
                parsed_auth_date = self._parse_datetime(auth_date_naive)
            else:
                parsed_auth_date = None

            utm = self._extract_utm_from_payload(row)

            learn_start_date = self._extract_learn_start_from_mirror(row)
            start_course = self._extract_course_from_mirror(row)
            completed_course_at = self._extract_course_completion_from_mirror(row)
            mirror_updates[ph_id] = {
                "ph_user_id": ph_id,
                "platform_registered_at": parsed_auth_date,
                "learn_start_date": learn_start_date,
                "started_learning": bool(learn_start_date is not None),
                "start_course": start_course,
                "completed_course": bool(completed_course_at),
                "completed_course_at": completed_course_at,
                "utm": utm,
                "referer": self._normalize_mirror_text(row.get("referer")),
                "raw_link": self._normalize_mirror_text(row.get("raw_link")),
                "bot_raw": self._normalize_mirror_text(row.get("bot_raw")),
                "ph_raw": self._normalize_mirror_text(row.get("ph_raw")),
                "last_activity": self._normalize_mirror_text(row.get("last_activity")),
                "ph_group": self._normalize_mirror_text(row.get("group")),
            }

            ph_rows.append(
                {
                    "bot_key": "lead",
                    "tg_user_id": -ph_id,
                    "ph_user_id": ph_id,
                    "username": None,
                    "created_at": parsed_auth_date or datetime.utcnow(),
                    "ingested_at": datetime.utcnow(),
                    "registered_platform": True,
                    "platform_registered_at": parsed_auth_date,
                    "learn_start_date": learn_start_date,
                    "started_learning": bool(learn_start_date is not None),
                    "start_course": start_course,
                    "completed_course": bool(completed_course_at),
                    "completed_course_at": completed_course_at,
                    "converted_to_lead": True,
                    "utm_source": utm.get("utm_source"),
                    "utm_campaign": utm.get("utm_campaign"),
                    "utm_medium": utm.get("utm_medium"),
                    "utm_content": utm.get("utm_content"),
                    "utm_term": utm.get("utm_term"),
                    "platform_utm_source": utm.get("utm_source"),
                    "platform_utm_campaign": utm.get("utm_campaign"),
                    "platform_utm_medium": utm.get("utm_medium"),
                    "platform_utm_content": utm.get("utm_content"),
                    "platform_utm_term": utm.get("utm_term"),
                    "referer": self._normalize_mirror_text(row.get("referer")),
                    "raw_link": self._normalize_mirror_text(row.get("raw_link")),
                    "bot_raw": self._normalize_mirror_text(row.get("bot_raw")),
                    "ph_raw": self._normalize_mirror_text(row.get("ph_raw")),
                    "last_activity": self._normalize_mirror_text(row.get("last_activity")),
                    "ph_group": self._normalize_mirror_text(row.get("group")),
                }
            )

        await self._upsert_ph_only_rows(session, ph_rows)
        await self._apply_mirror_to_existing_rows(session, mirror_updates)
        # Backfill ph_user_id = -tg_user_id for synthetic rows where it's still NULL
        # (covers rows inserted before the ph_user_id column was added)
        await session.execute(
            update(RawBotUser)
            .where(RawBotUser.bot_key == "lead")
            .where(RawBotUser.tg_user_id < 0)
            .where(RawBotUser.ph_user_id.is_(None))
            .values(ph_user_id=(-RawBotUser.tg_user_id))
        )
        await session.execute(
            update(RawBotUser)
            .where(RawBotUser.ph_user_id.is_not(None))
            .values(registered_platform=True)
        )

    async def _apply_mirror_to_existing_rows(
        self,
        session: AsyncSession,
        mirror_updates: dict[int, dict[str, Any]],
    ) -> None:
        if not mirror_updates:
            return
        chunk_size = 100
        processed = 0
        for ph_id, payload in mirror_updates.items():
            await self._apply_single_mirror_update(session, ph_id, payload)
            processed += 1
            if processed % chunk_size == 0:
                await session.commit()
        if processed % chunk_size:
            await session.commit()

    async def _apply_single_mirror_update(
        self,
        session: AsyncSession,
        ph_id: int,
        payload: dict[str, Any],
    ) -> None:
        for attempt in range(8):
            try:
                match_condition = or_(
                    RawBotUser.ph_user_id == ph_id,
                    and_(
                        RawBotUser.bot_key == "lead",
                        RawBotUser.tg_user_id == ph_id,
                    ),
                )
                base_values = {
                    "registered_platform": True,
                    "ph_user_id": ph_id,
                    "ingested_at": datetime.utcnow(),
                }
                if payload.get("platform_registered_at") is not None:
                    base_values["platform_registered_at"] = payload["platform_registered_at"]
                if payload.get("learn_start_date") is not None:
                    base_values["learn_start_date"] = payload["learn_start_date"]
                if payload.get("started_learning"):
                    base_values["started_learning"] = True
                if payload.get("start_course"):
                    base_values["start_course"] = payload["start_course"]
                if payload.get("completed_course_at") is not None:
                    base_values["completed_course"] = True
                    base_values["completed_course_at"] = payload["completed_course_at"]
                for field in ("referer", "raw_link", "bot_raw", "ph_raw", "last_activity", "ph_group"):
                    if payload.get(field):
                        base_values[field] = payload[field]
                await session.execute(
                    update(RawBotUser)
                    .where(match_condition)
                    .values(**base_values)
                )

                utm = payload.get("utm") or {}
                for key in ("utm_source", "utm_campaign", "utm_medium", "utm_content", "utm_term"):
                    value = utm.get(key)
                    if not value:
                        continue
                    await session.execute(
                        update(RawBotUser)
                        .where(match_condition)
                        .where(or_(getattr(RawBotUser, f"platform_{key}").is_(None), func.btrim(getattr(RawBotUser, f"platform_{key}")) == ""))
                        .values(**{f"platform_{key}": value, "ingested_at": datetime.utcnow()})
                    )
                    await session.execute(
                        update(RawBotUser)
                        .where(match_condition)
                        .where(or_(getattr(RawBotUser, key).is_(None), func.btrim(getattr(RawBotUser, key)) == ""))
                        .values(**{key: value, "ingested_at": datetime.utcnow()})
                    )
                return
            except DBAPIError as exc:
                if not self._is_deadlock(exc) or attempt >= 7:
                    raise
                await session.rollback()
                delay = min(3.0, 0.2 * (2 ** attempt))
                self._logger.warning(
                    "PokerHub mirror enrich deadlock; retrying ph_id=%s attempt=%s delay=%.1fs",
                    ph_id,
                    attempt + 1,
                    delay,
                )
                await asyncio.sleep(delay)

    async def _upsert_ph_only_rows(self, session: AsyncSession, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        chunk_size = 50
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            for attempt in range(8):
                stmt = pg_insert(RawBotUser).values(chunk)

                def keep_existing_non_empty(column, incoming):
                    return func.coalesce(func.nullif(func.btrim(column), ""), incoming)

                stmt = stmt.on_conflict_do_update(
                    index_elements=[RawBotUser.bot_key, RawBotUser.tg_user_id],
                    set_={
                        "created_at": func.coalesce(RawBotUser.created_at, stmt.excluded.created_at),
                        "ingested_at": stmt.excluded.ingested_at,
                        "ph_user_id": stmt.excluded.ph_user_id,
                        "registered_platform": True,
                        "platform_registered_at": stmt.excluded.platform_registered_at,
                        "learn_start_date": func.coalesce(
                            RawBotUser.learn_start_date,
                            stmt.excluded.learn_start_date,
                        ),
                        "started_learning": RawBotUser.started_learning.is_(True) | stmt.excluded.started_learning,
                        "start_course": func.coalesce(
                            RawBotUser.start_course,
                            stmt.excluded.start_course,
                        ),
                        "completed_course": RawBotUser.completed_course.is_(True) | stmt.excluded.completed_course,
                        "completed_course_at": func.coalesce(
                            RawBotUser.completed_course_at,
                            stmt.excluded.completed_course_at,
                        ),
                        "converted_to_lead": True,
                        "utm_source": keep_existing_non_empty(RawBotUser.utm_source, stmt.excluded.utm_source),
                        "utm_campaign": keep_existing_non_empty(RawBotUser.utm_campaign, stmt.excluded.utm_campaign),
                        "utm_medium": keep_existing_non_empty(RawBotUser.utm_medium, stmt.excluded.utm_medium),
                        "utm_content": keep_existing_non_empty(RawBotUser.utm_content, stmt.excluded.utm_content),
                        "utm_term": keep_existing_non_empty(RawBotUser.utm_term, stmt.excluded.utm_term),
                        "platform_utm_source": keep_existing_non_empty(
                            RawBotUser.platform_utm_source,
                            stmt.excluded.platform_utm_source,
                        ),
                        "platform_utm_campaign": keep_existing_non_empty(
                            RawBotUser.platform_utm_campaign,
                            stmt.excluded.platform_utm_campaign,
                        ),
                        "platform_utm_medium": keep_existing_non_empty(
                            RawBotUser.platform_utm_medium,
                            stmt.excluded.platform_utm_medium,
                        ),
                        "platform_utm_content": keep_existing_non_empty(
                            RawBotUser.platform_utm_content,
                            stmt.excluded.platform_utm_content,
                        ),
                        "platform_utm_term": keep_existing_non_empty(
                            RawBotUser.platform_utm_term,
                            stmt.excluded.platform_utm_term,
                        ),
                    },
                )
                try:
                    await session.execute(stmt)
                    await session.commit()
                    break
                except DBAPIError as exc:
                    if not self._is_deadlock(exc) or attempt >= 7:
                        raise
                    await session.rollback()
                    delay = min(5.0, 0.4 * (2 ** attempt))
                    self._logger.warning(
                        "PokerHub mirror upsert deadlock; retrying chunk=%s-%s attempt=%s delay=%.1fs",
                        i,
                        i + len(chunk),
                        attempt + 1,
                        delay,
                    )
                    await asyncio.sleep(delay)

    def _extract_learn_start_from_mirror(self, payload: dict[str, Any]) -> Optional[datetime]:
        return self._extract_earliest_lesson_ts(payload.get("lessons"))

    def _extract_course_from_mirror(self, payload: dict[str, Any]) -> Optional[str]:
        for source in (payload.get("courses"), payload.get("lessons")):
            course = self._detect_course(source)
            if course:
                return course
        return None

    def _detect_course(self, source: Any) -> Optional[str]:
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

    def _flatten_course_source(self, source: Any):
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

    def _normalize_course(self, value: Any) -> Optional[str]:
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

    def _extract_course_completion_from_mirror(self, payload: dict[str, Any]) -> Optional[datetime]:
        from app.services.pokerhub_lesson_summary import PokerHubLessonSummaryBuilder
        builder = PokerHubLessonSummaryBuilder()
        courses = builder._extract_courses(payload, {})
        earliest: Optional[datetime] = None
        for course_name, (terminal_module, terminal_lesson) in builder.TERMINAL_LESSONS.items():
            if terminal_module is None:
                terminal_key = f"l{terminal_lesson}"
            else:
                terminal_key = f"m{terminal_module}_l{terminal_lesson}"
            for lesson in courses.get(course_name, []):
                if lesson.get("key") == terminal_key and lesson.get("date"):
                    try:
                        parsed = datetime.fromisoformat(lesson["date"])
                        if earliest is None or parsed < earliest:
                            earliest = parsed
                    except (ValueError, TypeError):
                        pass
        return earliest

    def _extract_earliest_lesson_ts(self, lessons: Any) -> Optional[datetime]:
        lessons = self._parse_json_value(lessons)
        if isinstance(lessons, str):
            lessons = [lessons]
        if not isinstance(lessons, list):
            return None
        earliest: Optional[datetime] = None
        for lesson in lessons:
            if not isinstance(lesson, str):
                continue
            for match in self.LESSON_TS_RE.findall(lesson):
                parsed = self._parse_datetime(match)
                if not parsed:
                    continue
                if earliest is None or parsed < earliest:
                    earliest = parsed
        return earliest

    def _parse_json_value(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped or stripped[0] not in "[{":
            return value
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value

    async def _apply(self, session: AsyncSession, rows: list[dict[str, Any]]) -> None:
        registered_ids: list[int] = []
        learning_ids: list[int] = []
        platform_dates_by_id: dict[int, datetime] = {}
        platform_utms_by_id: dict[int, dict[str, str]] = {}
        for payload in rows:
            tg_id = payload.get("tg_id")
            try:
                tg_id_int = int(str(tg_id))
            except (TypeError, ValueError):
                continue
            ph_user_id = payload.get("user_id")
            try:
                ph_user_id_int = int(str(ph_user_id))
            except (TypeError, ValueError):
                continue
            if ph_user_id_int <= 0:
                continue
            registered_ids.append(tg_id_int)
            platform_date = self._extract_platform_registered_at(payload)
            if platform_date:
                current = platform_dates_by_id.get(tg_id_int)
                if current is None or platform_date < current:
                    platform_dates_by_id[tg_id_int] = platform_date
            if self._has_learning(payload):
                learning_ids.append(tg_id_int)
            utm = self._extract_utm_from_payload(payload)
            if utm:
                platform_utms_by_id[tg_id_int] = utm
        await self._bulk_update(session, registered_ids, {"registered_platform": True})
        await self._bulk_update_dates(session, platform_dates_by_id)
        await self._bulk_update_platform_utms(session, platform_utms_by_id)

    async def _bulk_update(self, session: AsyncSession, ids: list[int], values: dict[str, Any]) -> None:
        if not ids:
            return
        chunk_size = 10000
        for i in range(0, len(ids), chunk_size):
            chunk = ids[i : i + chunk_size]
            stmt = (
                update(RawBotUser)
                .where(RawBotUser.tg_user_id.in_(chunk))
                .values(**values, ingested_at=datetime.utcnow())
            )
            await session.execute(stmt)

    async def _bulk_update_dates(self, session: AsyncSession, values_by_id: dict[int, datetime]) -> None:
        if not values_by_id:
            return
        for tg_user_id, platform_registered_at in values_by_id.items():
            stmt = (
                update(RawBotUser)
                .where(RawBotUser.tg_user_id == tg_user_id)
                .values(platform_registered_at=platform_registered_at, ingested_at=datetime.utcnow())
            )
            await session.execute(stmt)

    async def _bulk_update_platform_utms(
        self, session: AsyncSession, utms_by_id: dict[int, dict[str, str]]
    ) -> None:
        if not utms_by_id:
            return
        for tg_user_id, utm in utms_by_id.items():
            for key in ("utm_source", "utm_campaign", "utm_medium", "utm_content", "utm_term"):
                value = utm.get(key)
                if not value:
                    continue
                column = getattr(RawBotUser, f"platform_{key}")
                stmt = (
                    update(RawBotUser)
                    .where(RawBotUser.tg_user_id == tg_user_id)
                    .where(or_(column.is_(None), func.btrim(column) == ""))
                    .values(**{f"platform_{key}": value, "ingested_at": datetime.utcnow()})
                )
                await session.execute(stmt)

    def _extract_platform_registered_at(self, payload: dict[str, Any]) -> datetime | None:
        direct_keys = (
            "platform_registered_at",
            "authorization_date",
            "authorized_at",
            "auth_date",
            "registered_at",
            "registration_date",
            "registered_date",
            "signup_date",
            "sign_up_date",
            "date_registration",
        )
        for key in direct_keys:
            parsed = self._parse_datetime(payload.get(key))
            if parsed:
                return parsed
        return None

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        value = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(value.replace("T", " "))
        except ValueError:
            return None

    def _has_learning(self, payload: dict[str, Any]) -> bool:
        candidates: list[str] = []
        courses = payload.get("courses")
        if isinstance(courses, dict):
            for course_name, course_lessons in courses.items():
                if course_name:
                    candidates.append(str(course_name))
                if isinstance(course_lessons, list):
                    candidates.extend([str(lesson) for lesson in course_lessons if lesson])
                elif isinstance(course_lessons, str) and course_lessons:
                    candidates.append(course_lessons)
        elif isinstance(courses, list):
            candidates.extend([str(item) for item in courses if item])
        elif isinstance(courses, str) and courses:
            candidates.append(courses)

        lessons = payload.get("lessons")
        if isinstance(lessons, list):
            candidates.extend([str(item) for item in lessons if item])
        elif isinstance(lessons, str) and lessons:
            candidates.append(lessons)

        group = payload.get("group")
        if isinstance(group, list):
            candidates.extend([str(item) for item in group if item])
        elif isinstance(group, str) and group:
            candidates.append(group)

        return any(self._identify_course_type(text) for text in candidates)

    def _identify_course_type(self, text: Any) -> str | None:
        if not text or not isinstance(text, str):
            return None
        text = text.strip()
        text_upper = text.upper()

        course_patterns = {
            "MTT": "MTT",
            "МТТ": "MTT",
            "SPIN": "SPIN",
            "СПИН": "SPIN",
            "CASH": "CASH",
            "КЭШ": "CASH",
            "КЕШ": "CASH",
        }

        for pattern, course_type in course_patterns.items():
            if pattern in text_upper:
                module_match = re.search(r"МОДУЛЬ\s*(\d+)", text_upper)
                if module_match:
                    return f"{course_type}{module_match.group(1)}"
                numbers = re.findall(r"(\d+)", text)
                if numbers:
                    return f"{course_type}{numbers[0]}"
                text_numbers = {
                    "ПЕРВЫЙ": "1",
                    "FIRST": "1",
                    "BEGINNER": "1",
                    "НАЧИНАЮЩ": "1",
                    "ОСНОВ": "1",
                    "ВТОРОЙ": "2",
                    "SECOND": "2",
                    "MIDDLE": "2",
                    "СРЕДН": "2",
                    "ТРЕТИЙ": "3",
                    "THIRD": "3",
                    "ADVANCED": "3",
                    "ПРОДВИНУТ": "3",
                    "ЧЕТВЕРТЫЙ": "4",
                    "FOURTH": "4",
                    "PRO": "4",
                    "ПРОФЕСС": "4",
                }
                for text_num, digit in text_numbers.items():
                    if text_num in text_upper:
                        return f"{course_type}{digit}"
                return f"{course_type}1"
        return None

    def _normalize_username(self, value: Any) -> str:
        if not value:
            return ""
        return str(value).strip().lstrip("@").lower()
