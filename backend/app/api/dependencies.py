from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import async_session


def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
