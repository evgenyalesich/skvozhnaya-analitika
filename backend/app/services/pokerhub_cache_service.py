import time
import logging
from typing import Any, Dict, List

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.redis_client import RedisCache
from app.db.session import async_session
from app.models.analytics import RawBotUser
from app.services.pokerhub_lesson_summary import PokerHubLessonSummaryBuilder


class PokerHubCacheService:
    def __init__(self):
        self.cache = RedisCache()
        self._logger = logging.getLogger("pokerhub_cache_service")
        self._summary_builder = PokerHubLessonSummaryBuilder()

    async def refresh_cache(self) -> None:
        async with async_session() as session:
            stmt = select(RawBotUser.tg_user_id).distinct()
            result = await session.execute(stmt)
            user_ids = [int(user_id) for user_id in result.scalars().all() if user_id]
        if not user_ids:
            return

        batch_size = int(getattr(settings, "pokerhub_api_batch_size", 500) or 500)
        api_url = settings.pokerhub_api_url
        courses_api_url = settings.pokerhub_courses_api_url
        start = time.time()
        self._logger.info("PokerHub cache: start users=%s batch=%s", len(user_ids), batch_size)
        async with httpx.AsyncClient(timeout=30) as client:
            course_catalog = await self._refresh_course_catalog(client, courses_api_url)
            for i in range(0, len(user_ids), batch_size):
                batch = user_ids[i : i + batch_size]
                payload = {"users": batch}
                try:
                    response = await client.post(api_url, json=payload)
                    response.raise_for_status()
                    data = response.json()
                except Exception:
                    self._logger.exception("PokerHub cache: request failed batch=%s-%s", i, i + len(batch))
                    continue
                payloads = []
                if isinstance(data, list):
                    payloads = data
                elif isinstance(data, dict):
                    payloads = data.get("users") or data.get("data") or []
                if isinstance(payloads, list):
                    await self._cache_payloads(payloads, course_catalog or {})
                    self._logger.info(
                        "PokerHub cache: batch %s-%s cached=%s",
                        i,
                        i + len(batch),
                        len(payloads),
                    )
                await self.cache.set_json("ph:last_refresh", {"ts": int(time.time())})
        await self.cache.set_json("ph:last_duration_seconds", {"seconds": int(time.time() - start)})
        self._logger.info("PokerHub cache: done seconds=%s", int(time.time() - start))

    async def _refresh_course_catalog(self, client: httpx.AsyncClient, api_url: str) -> Dict[str, Dict[str, Any]]:
        try:
            response = await client.post(api_url)
            response.raise_for_status()
            data = response.json()
        except Exception:
            self._logger.exception("PokerHub cache: course catalog request failed")
            return {}
        if not isinstance(data, dict):
            self._logger.warning("PokerHub cache: unexpected course catalog payload type=%s", type(data).__name__)
            return {}
        normalized = self._normalize_course_catalog(data)
        await self.cache.set_json("ph:course_catalog", normalized)
        await self.cache.set_json(
            "ph:course_catalog:se",
            {
                course_id: payload
                for course_id, payload in normalized.items()
                if "SE" in str(payload.get("name") or "").upper()
                or "SECOND EDITION" in str(payload.get("name") or "").upper()
            },
        )
        self._logger.info("PokerHub cache: course catalog cached=%s", len(normalized))
        return normalized

    async def _cache_payloads(self, payloads: List[Dict[str, Any]], course_catalog: Dict[str, Dict[str, Any]]) -> None:
        for payload in payloads:
            tg_id = payload.get("tg_id")
            if tg_id is None:
                continue
            try:
                tg_id_int = int(str(tg_id))
            except (TypeError, ValueError):
                continue
            await self.cache.set_json(f"ph:users:{tg_id_int}", payload)
            await self.cache.set_json(
                f"ph:lesson_summary:{tg_id_int}",
                self._summary_builder.build(payload, course_catalog=course_catalog),
            )

    def _normalize_course_catalog(self, payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        catalog: Dict[str, Dict[str, Any]] = {}
        for course_id, raw in payload.items():
            if not isinstance(raw, dict):
                continue
            quizzes = raw.get("quizzes")
            quiz_list = quizzes if isinstance(quizzes, list) else []
            catalog[str(course_id)] = {
                "id": str(course_id),
                "name": str(raw.get("name") or "").strip(),
                "quizzes_count": len(quiz_list),
                "quizzes": [
                    {
                        "quiz_id": item.get("quiz_id"),
                        "name": item.get("name"),
                        "sort_order": item.get("sort_order"),
                    }
                    for item in quiz_list
                    if isinstance(item, dict)
                ],
            }
        return catalog
