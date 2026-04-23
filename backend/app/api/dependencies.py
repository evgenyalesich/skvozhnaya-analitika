from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Cookie, Depends, Header, HTTPException

from app.db.session import async_session
from app.services.telegram_access_service import TelegramAccessService
from app.services.telegram_auth import TelegramAuthService


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def get_auth_service() -> TelegramAuthService:
    return TelegramAuthService()


async def get_access_service() -> TelegramAccessService:
    return TelegramAccessService()


async def get_current_user(
    authorization: str | None = Header(default=None),
    auth_token: str | None = Cookie(default=None, alias="auth_token"),
    auth_service: TelegramAuthService = Depends(get_auth_service),
    access_service: TelegramAccessService = Depends(get_access_service),
) -> dict:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif auth_token:
        token = auth_token
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    session = await auth_service.get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    tg_id = session.get("tg_user_id")
    if not tg_id or not await access_service.is_allowed(tg_id):
        raise HTTPException(status_code=403, detail="Access denied")
    return session
