from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import BotRegistry
from app.services.report_bot_scope import visible_bot_keys


class BotRegistryService:
    async def list_registry(self, session: AsyncSession) -> list[BotRegistry]:
        result = await session.execute(select(BotRegistry))
        items = result.scalars().all()
        allowed_keys = set(visible_bot_keys(item.bot_key for item in items))
        return [item for item in items if item.bot_key in allowed_keys]

    async def upsert(
        self,
        session: AsyncSession,
        bot_key: str,
        display_name: str | None,
        canonical_base: str | None,
        is_active: bool,
        replicate: bool = True,
    ) -> None:
        existing = await session.get(BotRegistry, bot_key)
        if existing:
            existing.display_name = display_name
            existing.canonical_base = canonical_base
            existing.is_active = is_active
            existing.replicate = replicate
        else:
            session.add(
                BotRegistry(
                    bot_key=bot_key,
                    display_name=display_name,
                    canonical_base=canonical_base,
                    is_active=is_active,
                    replicate=replicate,
                )
            )
