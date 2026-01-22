import json
from typing import Any, Optional

from redis.asyncio import Redis

from app.core.config import settings


class RedisCache:
    def __init__(self):
        self._client = Redis.from_url(settings.redis_url)

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        payload = json.dumps(value, default=str)
        await self._client.set(key, payload, ex=ttl)

    async def get_json(self, key: str) -> Optional[Any]:
        raw = await self._client.get(key)
        if not raw:
            return None
        return json.loads(raw)
