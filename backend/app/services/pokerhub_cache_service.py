import time
import logging
from typing import Any, Dict, List

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.redis_client import RedisCache
from app.db.session import async_session
from app.models.analytics import RawBotUser


class PokerHubCacheService:
    def __init__(self):
        self.cache = RedisCache()
        self._logger = logging.getLogger("pokerhub_cache_service")

    async def refresh_cache(self) -> None:
        async with async_session() as session:
            stmt = select(RawBotUser.tg_user_id).distinct()
            result = await session.execute(stmt)
            user_ids = [int(user_id) for user_id in result.scalars().all() if user_id]
        if not user_ids:
            return

        batch_size = int(getattr(settings, "pokerhub_api_batch_size", 500) or 500)
        api_url = settings.pokerhub_api_url
        start = time.time()
        self._logger.info("PokerHub cache: start users=%s batch=%s", len(user_ids), batch_size)
        async with httpx.AsyncClient(timeout=30) as client:
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
                    await self._cache_payloads(payloads)
                    self._logger.info(
                        "PokerHub cache: batch %s-%s cached=%s",
                        i,
                        i + len(batch),
                        len(payloads),
                    )
                await self.cache.set_json("ph:last_refresh", {"ts": int(time.time())})
        await self.cache.set_json("ph:last_duration_seconds", {"seconds": int(time.time() - start)})
        self._logger.info("PokerHub cache: done seconds=%s", int(time.time() - start))

    async def _cache_payloads(self, payloads: List[Dict[str, Any]]) -> None:
        for payload in payloads:
            tg_id = payload.get("tg_id")
            if tg_id is None:
                continue
            try:
                tg_id_int = int(str(tg_id))
            except (TypeError, ValueError):
                continue
            await self.cache.set_json(f"ph:users:{tg_id_int}", payload)
