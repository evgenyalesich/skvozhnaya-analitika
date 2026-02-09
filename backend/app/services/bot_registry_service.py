from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import BotRegistry


class BotRegistryService:
    async def list_registry(self, session: AsyncSession) -> list[BotRegistry]:
        result = await session.execute(select(BotRegistry))
        return result.scalars().all()

    async def upsert(self, session: AsyncSession, bot_key: str, display_name: str | None, is_active: bool) -> None:
        existing = await session.get(BotRegistry, bot_key)
        if existing:
            existing.display_name = display_name
            existing.is_active = is_active
        else:
            session.add(
                BotRegistry(
                    bot_key=bot_key,
                    display_name=display_name,
                    is_active=is_active,
                )
            )
