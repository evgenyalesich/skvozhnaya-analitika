"""
Отчёт по подписчикам Telegram-каналов.

Показывает:
- Сколько подписчиков каждого канала в БД
- Сопоставление с raw_bot_users (кто подписан, кто нет)
- Временная шкала: кто и когда подписался
- Последние события подписки
"""

import asyncio
import os
from datetime import timezone

from sqlalchemy import func, select, text

from app.db.session import async_session
from app.models.analytics import RawBotUser, TelegramChatMembership, TelegramSubscriptionEvent

CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
COMMUNITY_ID = os.getenv("TELEGRAM_COMMUNITY_ID", "")

CHAT_LABELS = {
    CHANNEL_ID: "Карточный Домик",
    COMMUNITY_ID: "Салун",
}


def _label(chat_id: str) -> str:
    return CHAT_LABELS.get(str(chat_id), f"chat({chat_id})")


async def _section_channel_stats(session) -> None:
    print("\n📊 СТАТИСТИКА ПО КАНАЛАМ")
    print("─" * 60)

    for chat_id, name in [(CHANNEL_ID, "Карточный Домик"), (COMMUNITY_ID, "Салун")]:
        if not chat_id:
            continue

        total = (await session.execute(
            select(func.count()).select_from(TelegramChatMembership)
            .where(TelegramChatMembership.chat_id == chat_id)
        )).scalar() or 0

        active = (await session.execute(
            select(func.count()).select_from(TelegramChatMembership)
            .where(TelegramChatMembership.chat_id == chat_id,
                   TelegramChatMembership.is_member.is_(True))
        )).scalar() or 0

        with_joined = (await session.execute(
            select(func.count()).select_from(TelegramChatMembership)
            .where(TelegramChatMembership.chat_id == chat_id,
                   TelegramChatMembership.joined_at.isnot(None))
        )).scalar() or 0

        print(f"\n  {name}  ({chat_id})")
        print(f"    Подписчиков в БД:       {active:>6}")
        print(f"    Отписавшихся в БД:      {total - active:>6}")
        print(f"    Итого записей:          {total:>6}")
        coverage = f"{with_joined}/{active}" if active else "0/0"
        print(f"    С датой вступления:     {coverage}")


async def _section_match_with_bots(session) -> None:
    print("\n\n🔍 СОПОСТАВЛЕНИЕ С БАЗОЙ БОТОВ (raw_bot_users)")
    print("─" * 60)

    total_bot_users = (await session.execute(
        select(func.count()).select_from(RawBotUser)
    )).scalar() or 0

    ch_sub = (await session.execute(
        select(func.count()).select_from(RawBotUser)
        .where(RawBotUser.channel_subscribed.is_(True))
    )).scalar() or 0

    comm_sub = (await session.execute(
        select(func.count()).select_from(RawBotUser)
        .where(RawBotUser.community_member.is_(True))
    )).scalar() or 0

    both_sub = (await session.execute(
        select(func.count()).select_from(RawBotUser)
        .where(RawBotUser.channel_subscribed.is_(True),
               RawBotUser.community_member.is_(True))
    )).scalar() or 0

    print(f"\n  Всего пользователей в ботах:         {total_bot_users:>6}")
    print(f"  Подписаны на КД (channel):           {ch_sub:>6}")
    print(f"  Подписаны на Салун (community):      {comm_sub:>6}")
    print(f"  Подписаны на оба канала:             {both_sub:>6}")

    # Members in channel but not in any bot
    for chat_id, name in [(CHANNEL_ID, "КД"), (COMMUNITY_ID, "Салун")]:
        if not chat_id:
            continue
        result = await session.execute(text("""
            SELECT COUNT(DISTINCT tcm.tg_user_id)
            FROM telegram_chat_memberships tcm
            WHERE tcm.chat_id = :cid
              AND tcm.is_member = true
              AND NOT EXISTS (
                    SELECT 1 FROM raw_bot_users rbu
                    WHERE rbu.tg_user_id = tcm.tg_user_id
              )
        """), {"cid": chat_id})
        count = result.scalar() or 0
        print(f"\n  Подписаны на {name}, но нет в боте:   {count:>6}")

    # Members in bot but NOT subscribed to channel
    if CHANNEL_ID:
        result = await session.execute(
            select(func.count()).select_from(RawBotUser)
            .where(RawBotUser.channel_subscribed.is_(False))
        )
        not_sub = result.scalar() or 0
        print(f"\n  Есть в боте, но НЕ подписаны на КД: {not_sub:>6}")


async def _section_timeline(session) -> None:
    print("\n\n📅 ПОСЛЕДНИЕ ПОДПИСЧИКИ (по дате вступления)")
    print("─" * 60)

    for chat_id, name in [(CHANNEL_ID, "Карточный Домик"), (COMMUNITY_ID, "Салун")]:
        if not chat_id:
            continue

        rows = (await session.execute(
            select(
                TelegramChatMembership.tg_user_id,
                TelegramChatMembership.username,
                TelegramChatMembership.joined_at,
                TelegramChatMembership.is_member,
            )
            .where(
                TelegramChatMembership.chat_id == chat_id,
                TelegramChatMembership.joined_at.isnot(None),
            )
            .order_by(TelegramChatMembership.joined_at.desc())
            .limit(25)
        )).all()

        print(f"\n  {name} — последние 25 вступивших:")
        if not rows:
            print("    (нет данных — возможно, joined_at ещё не собран)")
            continue

        print(f"  {'ID':>12}  {'@username':<22}  {'Вступил (UTC)':^22}  Статус")
        print(f"  {'─'*12}  {'─'*22}  {'─'*22}  ──────────")
        for r in rows:
            joined = r.joined_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M") if r.joined_at else "—"
            uname = f"@{r.username}" if r.username else f"id:{r.tg_user_id}"
            status = "✅ подписан" if r.is_member else "❌ ушёл"
            print(f"  {r.tg_user_id:>12}  {uname:<22}  {joined:<22}  {status}")


async def _section_events(session) -> None:
    print("\n\n📋 ПОСЛЕДНИЕ 30 СОБЫТИЙ ПОДПИСКИ")
    print("─" * 60)

    rows = (await session.execute(
        select(
            TelegramSubscriptionEvent.tg_user_id,
            TelegramSubscriptionEvent.channel_id,
            TelegramSubscriptionEvent.status,
            TelegramSubscriptionEvent.event_at,
            TelegramSubscriptionEvent.source,
        )
        .where(TelegramSubscriptionEvent.event_at.isnot(None))
        .order_by(TelegramSubscriptionEvent.event_at.desc())
        .limit(30)
    )).all()

    if not rows:
        print("\n  (нет событий — выполни sync сначала)")
        return

    print(f"\n  {'ID':>12}  {'Канал':<18}  {'Событие':^12}  {'Время (UTC)':^18}  Источник")
    print(f"  {'─'*12}  {'─'*18}  {'─'*12}  {'─'*18}  ────────")
    for r in rows:
        chan = _label(r.channel_id)[:18]
        t = r.event_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M") if r.event_at else "—"
        ev = "✅ подписан" if r.status == "subscribed" else "❌ отписался"
        print(f"  {r.tg_user_id:>12}  {chan:<18}  {ev:<12}  {t:<18}  {r.source}")


async def _main() -> None:
    print()
    print("╔" + "═" * 58 + "╗")
    print("║  ОТЧЁТ: ПОДПИСЧИКИ TELEGRAM-КАНАЛОВ vs БАЗА БОТОВ" + " " * 8 + "║")
    print("╚" + "═" * 58 + "╝")

    async with async_session() as session:
        await _section_channel_stats(session)
        await _section_match_with_bots(session)
        await _section_timeline(session)
        await _section_events(session)

    print("\n" + "─" * 60)
    print("  Готово. Чтобы обновить данные: scripts/bootstrap_telegram_membership.sh sync")
    print("─" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(_main())
