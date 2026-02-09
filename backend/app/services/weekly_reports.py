from typing import List, Dict

from app.core.redis_client import RedisCache


class WeeklyReportCache:
    def __init__(self):
        self.cache = RedisCache()

    def _base_key(self, group: str, group_key: str) -> str:
        return f"reports:weekly:{group}:{group_key}"

    async def list_months(self, group: str, group_key: str) -> List[str]:
        key = f"{self._base_key(group, group_key)}:months"
        data = await self.cache.get_json(key)
        return data or []

    async def fetch_weekly(self, group: str, group_key: str, month_key: str) -> List[Dict]:
        key = f"{self._base_key(group, group_key)}:{month_key}"
        data = await self.cache.get_json(key)
        return data or []
