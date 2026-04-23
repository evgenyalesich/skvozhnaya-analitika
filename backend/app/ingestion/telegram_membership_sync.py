import asyncio
import logging
import os
import sys

from app.db.session import async_session
from app.services.telegram_membership_service import TelegramMembershipService

# Configure logging to stdout with readable format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
# Silence noisy third-party loggers
logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

CHANNEL_NAMES = {
    os.getenv("TELEGRAM_CHANNEL_ID", ""): "Карточный Домик",
    os.getenv("TELEGRAM_COMMUNITY_ID", ""): "Салун",
}


def _chat_label(chat_id: str) -> str:
    return CHANNEL_NAMES.get(str(chat_id), f"chat({chat_id})")


async def _main() -> None:
    service = TelegramMembershipService()
    chat_ids = service.configured_chat_ids()

    print()
    print("=" * 60)
    print("  СИНХРОНИЗАЦИЯ ПОДПИСЧИКОВ TELEGRAM")
    print("=" * 60)
    for cid in chat_ids:
        print(f"  • {_chat_label(cid)} ({cid})")
    print()

    async with async_session() as session:
        results = await TelegramMembershipService().run_full_sync(session)
        await session.commit()

    print()
    print("=" * 60)
    print(f"  {'Канал':<25}  {'Всего TG':>8}  {'Собрано':>8}  {'Новых':>6}  {'Обновл':>6}  {'Вкл':>5}  {'Выкл':>5}")
    print(f"  {'-'*25}  {'-'*8}  {'-'*8}  {'-'*6}  {'-'*6}  {'-'*5}  {'-'*5}")
    for r in results:
        label = _chat_label(r.chat_id)[:25]
        print(f"  {label:<25}  {r.participants_count:>8}  {r.seen_members:>8}  {r.inserted:>6}  {r.updated:>6}  {r.activated:>5}  {r.deactivated:>5}")
    print("=" * 60)
    print("  Готово! Флаги channel_subscribed / community_member обновлены.")
    print("=" * 60)
    print()


if __name__ == "__main__":
    asyncio.run(_main())
