import json
from typing import Any, Optional

from redis.asyncio import Redis

from app.core.config import settings

# Обёртка над redis.asyncio для кеширования JSON-ответов API.
# Все ключи хранятся как строки, значения сериализуются через json.dumps(default=str)
# (поэтому datetime и Decimal не взрываются при сериализации).


class RedisCache:
    """Асинхронный Redis-клиент с JSON-сериализацией и pattern-операциями."""

    def __init__(self):
        self._client = Redis.from_url(str(settings.redis_url))

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Сохраняет сырое значение (строку). ttl в секундах, None = без истечения."""
        await self._client.set(key, value, ex=ttl)

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Сериализует value в JSON и сохраняет. default=str обрабатывает datetime/Decimal."""
        payload = json.dumps(value, default=str)
        await self._client.set(key, payload, ex=ttl)

    async def get_json(self, key: str) -> Optional[Any]:
        """Читает и десериализует JSON по ключу. Возвращает None если ключ отсутствует."""
        raw = await self._client.get(key)
        if not raw:
            return None
        return json.loads(raw)

    async def get_json_many(self, keys: list[str]) -> dict[str, Optional[Any]]:
        """Читает несколько ключей за один mget. Возвращает dict key→value (None если нет)."""
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
        """Атомарный SET NX — устанавливает ключ только если его нет. Используется как mutex-lock.

        Возвращает True если ключ был создан (лок захвачен), False если уже существовал.
        """
        result = await self._client.set(key, value, ex=ttl, nx=True)
        return bool(result)

    async def delete(self, key: str) -> None:
        """Удаляет ключ из Redis."""
        await self._client.delete(key)

    async def delete_pattern(self, pattern: str) -> None:
        """Удаляет все ключи, совпадающие с glob-паттерном (напр. "report:*").

        Использует SCAN чтобы не блокировать Redis на больших базах.
        """
        cursor = 0
        while True:
            cursor, keys = await self._client.scan(cursor=cursor, match=pattern, count=500)
            if keys:
                await self._client.delete(*keys)
            if cursor == 0:
                break

    async def get_json_by_pattern(self, pattern: str, limit: int = 200) -> dict[str, Any]:
        """Читает все ключи по паттерну и возвращает их как dict key→parsed_value.

        limit защищает от случайного чтения тысяч ключей.
        Используется в admin-панели для просмотра состояния кеша.
        """
        result: dict[str, Any] = {}
        cursor = 0
        while True:
            cursor, keys = await self._client.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                raw_values = await self._client.mget(keys)
                for key, raw in zip(keys, raw_values):
                    if len(result) >= limit:
                        return result
                    key_text = key.decode("utf-8", errors="ignore") if isinstance(key, bytes) else str(key)
                    if not raw:
                        result[key_text] = None
                        continue
                    try:
                        result[key_text] = json.loads(raw)
                    except Exception:
                        raw_text = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw)
                        result[key_text] = raw_text
            if cursor == 0:
                break
        return result
