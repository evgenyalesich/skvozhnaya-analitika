from datetime import datetime
from typing import List, Optional

from sqlalchemy import select

from app.core.config import settings
from app.db.session import async_session
from app.models.analytics import TelegramAccess


class TelegramAccessService:
    async def list_access(self) -> List[TelegramAccess]:
        async with async_session() as session:
            stmt = select(TelegramAccess)
            result = await session.execute(stmt)
            return result.scalars().all()

    async def grant_access(self, tg_user_id: int, created_by: Optional[str] = None) -> TelegramAccess:
        async with async_session() as session:
            exists = await session.execute(
                select(TelegramAccess).where(TelegramAccess.tg_user_id == tg_user_id)
            )
            existing = exists.scalar_one_or_none()
            if existing:
                return existing
            access = TelegramAccess(
                tg_user_id=tg_user_id,
                created_by=created_by,
                created_at=datetime.utcnow(),
            )
            session.add(access)
            await session.commit()
            await session.refresh(access)
            return access

    async def revoke_access(self, tg_user_id: int) -> None:
        async with async_session() as session:
            stmt = select(TelegramAccess).where(TelegramAccess.tg_user_id == tg_user_id)
            result = await session.execute(stmt)
            entry = result.scalar_one_or_none()
            if entry:
                await session.delete(entry)
                await session.commit()

    async def is_allowed(self, tg_user_id: int) -> bool:
        if tg_user_id in settings.initial_allowed_telegram_ids:
            return True
        async with async_session() as session:
            stmt = select(TelegramAccess).where(TelegramAccess.tg_user_id == tg_user_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None
