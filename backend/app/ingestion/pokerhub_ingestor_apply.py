from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import RawBotUser


class PokerHubIngestorApplyMixin:
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
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
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
        chunk_size = 500
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
