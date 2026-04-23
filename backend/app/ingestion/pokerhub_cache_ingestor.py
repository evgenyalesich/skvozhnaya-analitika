import re
import asyncio
import logging
import json
from datetime import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import update, bindparam, select, case
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import RedisCache
from app.models.analytics import RawBotUser


class PokerHubCacheIngestor:
    def __init__(self):
        self.cache = RedisCache()
        self._logger = logging.getLogger("pokerhub_cache_ingestor")
        try:
            import asyncpg  # type: ignore
        except Exception:  # pragma: no cover
            asyncpg = None
        self._asyncpg = asyncpg

    def _is_deadlock(self, exc: Exception) -> bool:
        if not isinstance(exc, DBAPIError):
            return False
        orig = exc.orig
        if orig is None:
            return False
        asyncpg = self._asyncpg
        if asyncpg is not None and isinstance(orig, asyncpg.exceptions.DeadlockDetectedError):
            return True
        return "DeadlockDetectedError" in str(orig)

    async def _execute_with_retry(self, session: AsyncSession, stmt, retries: int = 3):
        for attempt in range(retries):
            try:
                return await session.execute(stmt)
            except DBAPIError as exc:
                if self._is_deadlock(exc) and attempt < retries - 1:
                    await session.rollback()
                    await asyncio.sleep(0.4 * (2 ** attempt))
                    continue
                raise

    async def ingest(self, session: AsyncSession) -> None:
        stmt = select(RawBotUser.tg_user_id).distinct().order_by(RawBotUser.tg_user_id)
        result = await session.execute(stmt)
        user_ids = [int(user_id) for user_id in result.scalars().all() if user_id]
        if not user_ids:
            return

        batch_size = 500
        self._logger.info("PokerHub ingest: start users=%s batch=%s", len(user_ids), batch_size)
        for i in range(0, len(user_ids), batch_size):
            batch = user_ids[i : i + batch_size]
            keys = [f"ph:users:{user_id}" for user_id in batch]
            payloads = await self.cache.get_json_many(keys)
            updates = []
            for user_id in batch:
                payload = payloads.get(f"ph:users:{user_id}")
                if not payload:
                    continue
                platform_registered_at = self._extract_platform_registered_at(payload)
                learn_start_date, earliest_course = self._extract_learn_start(payload)
                completed_course_at, completed_course_type = self._extract_course_completion(payload)
                if int(user_id) == 893355003:
                    self._logger.info(
                        "DEBUG tg_id=%s payload_keys=%s learn_start_date=%s earliest_course=%s completed_course_at=%s",
                        user_id,
                        sorted(payload.keys()) if isinstance(payload, dict) else type(payload),
                        learn_start_date,
                        earliest_course,
                        completed_course_at,
                    )
                start_course = (
                    completed_course_type
                    or
                    earliest_course
                    or self._normalize_course(payload.get("start_course"))
                    or self._detect_course(payload)
                )
                ph_utm = self._extract_utm(payload)
                ph_user_id_raw = payload.get("user_id") or payload.get("ph_user_id") or payload.get("id")
                try:
                    ph_user_id = int(str(ph_user_id_raw)) if ph_user_id_raw is not None else None
                except (TypeError, ValueError):
                    ph_user_id = None
                values = {
                    "tg_user_id": user_id,
                    "ph_user_id": ph_user_id,
                    "platform_registered_at": platform_registered_at,
                    "learn_start_date": learn_start_date,
                    "start_course": start_course,
                    "completed_course": bool(completed_course_at),
                    "completed_course_at": completed_course_at,
                    "ph_utm": ph_utm,
                }
                # Hard rule: "started learning" == there is a first lesson timestamp.
                # Do not infer it from course labels alone (those can exist before the 1st lesson).
                values["started_learning"] = bool(learn_start_date is not None)
                updates.append(values)
            updated_count = 0
            if updates:
                for values in updates:
                    update_values = {
                        "registered_platform": True,
                        "learn_start_date": values["learn_start_date"],
                        "start_course": values["start_course"],
                        "started_learning": bool(values.get("started_learning")),
                    }
                    if values.get("ph_user_id") is not None:
                        update_values["ph_user_id"] = values["ph_user_id"]
                    # Do not overwrite an already known platform registration timestamp with NULL.
                    if values.get("platform_registered_at") is not None:
                        update_values["platform_registered_at"] = values["platform_registered_at"]
                    # Write platform UTM only where the bot didn't already set a value.
                    ph_utm = values.get("ph_utm") or {}
                    for field in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"):
                        val = ph_utm.get(field)
                        if val:
                            update_values[field] = val
                            update_values[f"platform_{field}"] = val
                    stmt = (
                        update(RawBotUser)
                        .where(RawBotUser.tg_user_id == values["tg_user_id"])
                        .values(**{
                            k: v for k, v in update_values.items()
                            if k not in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")
                        })
                        .execution_options(synchronize_session=False)
                    )
                    await self._execute_with_retry(session, stmt)
                    # completed_course is sticky:
                    # once a user has completed any supported course, never reset it back to false
                    # if a new completion timestamp appears later, only fill it when currently missing
                    if values.get("completed_course_at") is not None:
                        await self._execute_with_retry(
                            session,
                            update(RawBotUser)
                            .where(RawBotUser.tg_user_id == values["tg_user_id"])
                            .values(
                                completed_course=True,
                                completed_course_at=case(
                                    (RawBotUser.completed_course_at.is_(None), values["completed_course_at"]),
                                    else_=RawBotUser.completed_course_at,
                                ),
                            )
                            .execution_options(synchronize_session=False),
                        )
                    # UTM fields: only fill where currently NULL (don't overwrite bot-sourced labels).
                    for field in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"):
                        val = update_values.get(field)
                        if val:
                            await self._execute_with_retry(
                                session,
                                update(RawBotUser)
                                .where(
                                    RawBotUser.tg_user_id == values["tg_user_id"],
                                    getattr(RawBotUser, field).is_(None),
                                )
                                .values(**{field: val})
                                .execution_options(synchronize_session=False),
                            )
                    updated_count += 1
                # Commit per batch to avoid long transactions and lock contention
                # with parallel replication updates on raw_bot_users.
                await session.commit()
            self._logger.info("PokerHub ingest: batch %s-%s updated=%s", i, i + len(batch), updated_count)
        self._logger.info("PokerHub ingest: done")

    def _extract_platform_registered_at(self, payload: dict[str, Any]) -> Optional[datetime]:
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

        matches: list[datetime] = []

        def walk(item: Any, path: tuple[str, ...] = ()) -> None:
            if item is None:
                return
            if isinstance(item, dict):
                for key, value in item.items():
                    walk(value, path + (str(key).lower(),))
                return
            if isinstance(item, (list, tuple)):
                for value in item:
                    walk(value, path)
                return
            if not isinstance(item, str):
                return

            parsed = self._parse_datetime(item)
            if not parsed:
                return
            joined = ".".join(path)
            registration_hint = any(
                token in joined
                for token in ("register", "signup", "sign_up", "registration", "reg_date", "platform")
            )
            # Keep fallback for common user profile created_at fields.
            created_hint = joined.endswith("created_at") and ("user" in joined or joined.count(".") <= 1)
            if registration_hint or created_hint:
                matches.append(parsed)

        walk(payload)
        if not matches:
            return None
        return min(matches)

    def _extract_learn_start(self, payload: dict[str, Any]) -> tuple[Optional[datetime], Optional[str]]:
        earliest_dt, earliest_course = self._parse_earliest_lesson(payload)
        if earliest_dt:
            return earliest_dt, earliest_course
        candidates = [
            payload.get("learn_start_date"),
            payload.get("learn_start"),
            payload.get("start_learning_date"),
        ]
        for candidate in candidates:
            parsed = self._parse_datetime(candidate)
            if parsed:
                return parsed, None
        return None, None

    def _parse_earliest_lesson(self, payload: dict[str, Any]) -> tuple[Optional[datetime], Optional[str]]:
        earliest: Optional[datetime] = None
        earliest_course: Optional[str] = None

        def consider(text: str) -> None:
            nonlocal earliest, earliest_course
            for match in re.findall(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", text):
                parsed = self._parse_datetime(match)
                if not parsed:
                    continue
                if earliest is None or parsed < earliest:
                    earliest = parsed
                    earliest_course = self._normalize_course(text)

        def walk(item: Any) -> None:
            if item is None:
                return
            if isinstance(item, str):
                consider(item)
                return
            if isinstance(item, dict):
                for v in item.values():
                    walk(v)
                return
            if isinstance(item, (list, tuple)):
                # lesson pair like ["CASH ...", "2025-12-06T03:23:38.000000Z"]
                if len(item) == 2 and isinstance(item[0], (str,)) and isinstance(item[1], (str,)):
                    consider(f"{item[0]} {item[1]}")
                    return
                for v in item:
                    walk(v)

        for key in ("courses", "lessons", "group"):
            walk(payload.get(key))

        return earliest, earliest_course

    def _extract_course_completion(self, payload: dict[str, Any]) -> tuple[Optional[datetime], Optional[str]]:
        courses = payload.get("courses")
        if not isinstance(courses, dict):
            return None, None
        latest_completed_at: Optional[datetime] = None
        latest_course_type: Optional[str] = None
        for course_key, lessons in courses.items():
            if not isinstance(lessons, list):
                continue
            for lesson in lessons:
                if not (isinstance(lesson, (list, tuple)) and len(lesson) >= 2):
                    continue
                title = lesson[0] if isinstance(lesson[0], str) else ""
                ts_raw = lesson[1] if isinstance(lesson[1], str) else ""
                if not title or not ts_raw:
                    continue
                completed_at = self._parse_datetime(ts_raw)
                if not completed_at:
                    continue
                course_type = self._normalize_course(f"{course_key} {title}")
                if not course_type:
                    continue
                if not self._is_terminal_lesson(course_type, title):
                    continue
                if latest_completed_at is None or completed_at > latest_completed_at:
                    latest_completed_at = completed_at
                    latest_course_type = course_type
        return latest_completed_at, latest_course_type

    def _is_terminal_lesson(self, course_type: str, title: str) -> bool:
        upper = title.upper()
        m = re.search(r"МОДУЛЬ\s*(\d+).*?УРОК\s*(\d+)", upper)
        if not m:
            return False
        module = int(m.group(1))
        lesson = int(m.group(2))
        if course_type == "MTT":
            return module == 2 and lesson == 21
        if course_type == "SPIN":
            return module == 1 and lesson == 81
        if course_type == "CASH":
            return module == 1 and lesson == 10
        return False

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if not value or not isinstance(value, str):
            return None
        value = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(value.replace("T", " "))
        except ValueError:
            return None

    def _flatten_payload(self, payload: dict[str, Any]) -> Iterable[Any]:
        for key in ("courses", "lessons", "group"):
            value = payload.get(key)
            if value is None:
                continue
            if isinstance(value, dict):
                for item in value.values():
                    yield item
            elif isinstance(value, list):
                for item in value:
                    yield item
            else:
                yield value

    def _detect_course(self, payload: dict[str, Any]) -> Optional[str]:
        for item in self._flatten_payload(payload):
            course = self._normalize_course(item)
            if course:
                return course
        return None

    def _normalize_utm_struct(self, utm_obj: Any) -> dict[str, str]:
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

    def _extract_utm(self, payload: dict[str, Any]) -> dict[str, str]:
        result: dict[str, str] = {}
        for struct_field in ("utm", "ph_utm"):
            result.update(self._normalize_utm_struct(payload.get(struct_field)))

        from urllib.parse import urlparse, parse_qs
        for link_field in ("referer", "raw_link", "bot_raw", "ph_raw"):
            raw = payload.get(link_field)
            if not raw or not isinstance(raw, str):
                continue
            if "utm_" not in raw:
                continue
            try:
                qs = parse_qs(urlparse(raw).query)
                for field in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"):
                    if field in result:
                        continue
                    vals = qs.get(field)
                    if vals and vals[0]:
                        result[field] = vals[0].strip()
            except Exception:
                continue
        return result

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
        return None
