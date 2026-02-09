import re
import logging
from datetime import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import update, bindparam, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import RedisCache
from app.models.analytics import RawBotUser


class PokerHubCacheIngestor:
    def __init__(self):
        self.cache = RedisCache()
        self._logger = logging.getLogger("pokerhub_cache_ingestor")

    async def ingest(self, session: AsyncSession) -> None:
        stmt = select(RawBotUser.tg_user_id).distinct()
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
                if int(user_id) == 893355003:
                    self._logger.info(
                        "DEBUG tg_id=%s payload_keys=%s learn_start_date=%s earliest_course=%s",
                        user_id,
                        sorted(payload.keys()) if isinstance(payload, dict) else type(payload),
                        learn_start_date,
                        earliest_course,
                    )
                start_course = (
                    earliest_course
                    or self._normalize_course(payload.get("start_course"))
                    or self._detect_course(payload)
                )
                values = {
                    "tg_user_id": user_id,
                    "platform_registered_at": platform_registered_at,
                    "learn_start_date": learn_start_date,
                    "start_course": start_course,
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
                    # Do not overwrite an already known platform registration timestamp with NULL.
                    if values.get("platform_registered_at") is not None:
                        update_values["platform_registered_at"] = values["platform_registered_at"]
                    await session.execute(
                        update(RawBotUser)
                        .where(RawBotUser.tg_user_id == values["tg_user_id"])
                        .values(**update_values)
                        .execution_options(synchronize_session=False)
                    )
                    updated_count += 1
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
