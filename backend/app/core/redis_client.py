import json
from typing import Any, Optional

from redis.asyncio import Redis

from app.core.config import settings


class RedisCache:
    def __init__(self):
        self._client = Redis.from_url(str(settings.redis_url))

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        payload = json.dumps(value, default=str)
        await self._client.set(key, payload, ex=ttl)

    async def get_json(self, key: str) -> Optional[Any]:
        raw = await self._client.get(key)
        if not raw:
            return None
        return json.loads(raw)

    async def get_json_many(self, keys: list[str]) -> dict[str, Optional[Any]]:
        if not keys:
            return {}
        raw_values = await self._client.mget(keys)
        payload = {}
        for key, raw in zip(keys, raw_values):
            if not raw:
                payload[key] = None
            else:
                payload[key] = json.loads(raw)
        return payload

    async def set_if_not_exists(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        result = await self._client.set(key, value, ex=ttl, nx=True)
        return bool(result)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)
