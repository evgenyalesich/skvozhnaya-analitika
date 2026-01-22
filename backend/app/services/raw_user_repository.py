from typing import Any, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import RawBotUser


class RawUserRepository:
    async def count_total(self, session: AsyncSession) -> int:
        stmt = select(func.count()).select_from(RawBotUser)
        result = await session.execute(stmt)
        return result.scalar_one()

    async def fetch_raw(self, session: AsyncSession, limit: int = 50, offset: int = 0) -> List[dict[str, Any]]:
        stmt = (
            select(RawBotUser)
            .order_by(RawBotUser.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        users = result.scalars().all()
        return [self._serialize(user) for user in users]

    def _serialize(self, user: RawBotUser) -> dict[str, Optional[str]]:
        return {
            "id": user.id,
            "bot_key": user.bot_key,
            "tg_user_id": user.tg_user_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "utm_source": user.utm_source,
            "utm_campaign": user.utm_campaign,
            "budget": user.budget,
        }
