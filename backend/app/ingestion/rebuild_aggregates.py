"""
Пересобирает агрегаты и обновляет Redis-кэш.

Пересоздаёт:
  - agg_daily_new_users  (DailyNewUsersAgg)
  - agg_tg_subs_daily    (TgSubsDailyAgg)
  - Redis-кэш отчётов

Запуск:
  python -m app.ingestion.rebuild_aggregates
  python -m app.ingestion.rebuild_aggregates 90   # только последние 90 дней
"""

import asyncio
import sys

from app.services.aggregate_refresher import AggregateRefresher


async def _main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else None
    label = f"последние {days} дней" if days else "все данные"
    print(f"Пересборка агрегатов ({label})...")
    await AggregateRefresher().refresh(days=days)
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(_main())
