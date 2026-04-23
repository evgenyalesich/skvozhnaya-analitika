import asyncio
import logging

from app.services.telegram_membership_service import TelegramMembershipRealtimeMonitor


async def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    await TelegramMembershipRealtimeMonitor().run()


if __name__ == "__main__":
    asyncio.run(_main())
