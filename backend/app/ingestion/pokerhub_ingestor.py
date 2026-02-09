from datetime import datetime
import json
import re
from typing import Any

import asyncpg
from sqlalchemy import update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.analytics import RawBotUser


class PokerHubIngestor:
    async def ingest(self, session: AsyncSession) -> None:
        if not settings.lead_db_dsn:
            return
        rows = await self._fetch_pokerhub_cache()
        if not rows:
            return
        await self._apply(session, rows)

    async def _fetch_pokerhub_cache(self) -> list[dict[str, Any]]:
        dsn = str(settings.lead_db_dsn)
        if dsn.startswith("postgresql+asyncpg://"):
            dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(
                """
                SELECT data
                FROM pokerhub_user_cache
                WHERE data IS NOT NULL
                """
            )
            payloads: list[dict[str, Any]] = []
            for row in rows:
                raw = row.get("data")
                if raw is None:
                    continue
                if isinstance(raw, dict):
                    payloads.append(raw)
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="ignore")
                if isinstance(raw, str):
                    try:
                        payloads.append(json.loads(raw))
                    except json.JSONDecodeError:
                        continue
            return payloads
        finally:
            await conn.close()

    async def _apply(self, session: AsyncSession, rows: list[dict[str, Any]]) -> None:
        registered_ids: list[int] = []
        learning_ids: list[int] = []
        registered_usernames: list[str] = []
        learning_usernames: list[str] = []
        platform_dates_by_id: dict[int, datetime] = {}
        platform_dates_by_username: dict[str, datetime] = {}
        for payload in rows:
            tg_id = payload.get("tg_id")
            try:
                tg_id_int = int(str(tg_id))
            except (TypeError, ValueError):
                continue
            registered_ids.append(tg_id_int)
            platform_date = self._extract_platform_registered_at(payload)
            if platform_date:
                current = platform_dates_by_id.get(tg_id_int)
                if current is None or platform_date < current:
                    platform_dates_by_id[tg_id_int] = platform_date
            if self._has_learning(payload):
                learning_ids.append(tg_id_int)
            tg_username = self._normalize_username(payload.get("tg_username"))
            if tg_username:
                registered_usernames.append(tg_username)
                if platform_date:
                    current = platform_dates_by_username.get(tg_username)
                    if current is None or platform_date < current:
                        platform_dates_by_username[tg_username] = platform_date
                if self._has_learning(payload):
                    learning_usernames.append(tg_username)

        await self._bulk_update(session, registered_ids, {"registered_platform": True})
        await self._bulk_update_by_username(session, registered_usernames, {"registered_platform": True})
        await self._bulk_update_dates(session, platform_dates_by_id)
        await self._bulk_update_dates_by_username(session, platform_dates_by_username)

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

    async def _bulk_update_by_username(
        self, session: AsyncSession, usernames: list[str], values: dict[str, Any]
    ) -> None:
        if not usernames:
            return
        chunk_size = 10000
        for i in range(0, len(usernames), chunk_size):
            chunk = usernames[i : i + chunk_size]
            stmt = (
                update(RawBotUser)
                .where(func.lower(func.ltrim(RawBotUser.username, "@")).in_(chunk))
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

    async def _bulk_update_dates_by_username(
        self, session: AsyncSession, values_by_username: dict[str, datetime]
    ) -> None:
        if not values_by_username:
            return
        for username, platform_registered_at in values_by_username.items():
            stmt = (
                update(RawBotUser)
                .where(func.lower(func.ltrim(RawBotUser.username, "@")) == username)
                .values(platform_registered_at=platform_registered_at, ingested_at=datetime.utcnow())
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
