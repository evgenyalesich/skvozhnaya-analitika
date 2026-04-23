"""
Backfill telegram_subscription_events.event_at / checked_at
из реального joined_at в telegram_chat_memberships.

Проблема: full_sync создаёт события с checked_at = now() (время запуска),
а не реальной датой вступления. Агрегатор группирует по checked_at,
поэтому все исторические подписчики попадают в одну дату.

Этот скрипт обновляет event_at / observed_at / checked_at из joined_at
для всех событий source='full_sync', у которых есть совпадение в
telegram_chat_memberships с заполненным joined_at.
"""

import asyncio

from sqlalchemy import text

from app.db.session import async_session


BACKFILL_SQL = text("""
    UPDATE telegram_subscription_events tse
    SET
        event_at    = tcm.joined_at,
        observed_at = tcm.joined_at,
        checked_at  = tcm.joined_at
    FROM telegram_chat_memberships tcm
    WHERE tse.tg_user_id  = tcm.tg_user_id
      AND tse.channel_id  = tcm.chat_id
      AND tcm.joined_at  IS NOT NULL
      AND tse.source      = 'full_sync'
      AND tse.status      = 'subscribed'
""")

COUNT_SQL = text("""
    SELECT COUNT(*) FROM telegram_subscription_events
    WHERE source = 'full_sync' AND status = 'subscribed'
      AND event_at IS NOT NULL
""")

TOTAL_SQL = text("""
    SELECT COUNT(*) FROM telegram_subscription_events
    WHERE source = 'full_sync' AND status = 'subscribed'
""")


async def _main() -> None:
    async with async_session() as session:
        total = (await session.execute(TOTAL_SQL)).scalar() or 0
        before = (await session.execute(COUNT_SQL)).scalar() or 0
        print(f"Событий full_sync/subscribed:      {total}")
        print(f"С event_at до backfill:            {before}")

        result = await session.execute(BACKFILL_SQL)
        await session.commit()

        after = (await session.execute(COUNT_SQL)).scalar() or 0
        updated = result.rowcount
        print(f"Обновлено строк:                   {updated}")
        print(f"С event_at после backfill:         {after}")
        missing = total - after
        if missing:
            print(f"Без joined_at (останутся сегодня): {missing}  (удалённые аккаунты / скрытые)")
        else:
            print("Все события обновлены.")


if __name__ == "__main__":
    asyncio.run(_main())
