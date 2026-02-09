from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services.telegram_access_service import TelegramAccessService
from app.services.telegram_auth import TelegramAuthService

router = APIRouter()


class StartResponse(BaseModel):
    start_token: str
    login_url: str


class ConfirmRequest(BaseModel):
    token: str
    tg_user_id: int
    username: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tg_user_id: int
    username: Optional[str] = None


async def get_auth_service() -> TelegramAuthService:
    return TelegramAuthService()


@router.post("/api/auth/telegram/start", response_model=StartResponse)
async def start_telegram_login(service: TelegramAuthService = Depends(get_auth_service)):
    start_token = await service.create_start_token()
    return StartResponse(start_token=start_token, login_url=service.build_login_link(start_token))


@router.post("/api/auth/telegram/confirm", response_model=AuthResponse)
async def confirm_telegram_login(
    payload: ConfirmRequest,
    service: TelegramAuthService = Depends(get_auth_service),
):
    if not await service.validate_start_token(payload.token):
        raise HTTPException(status_code=400, detail="Start token is invalid or expired")

    if not settings.auth_allow_unknown_users:
        exists = await service.user_exists_in_lead(payload.tg_user_id)
        if not exists:
            raise HTTPException(status_code=403, detail="User is not registered in lead")

    access_service = TelegramAccessService()
    if not await access_service.is_allowed(payload.tg_user_id):
        raise HTTPException(status_code=403, detail="Access denied")

    access_token = service.create_session_jwt(payload.tg_user_id, payload.username)
    await service.store_session(
        access_token,
        {"tg_user_id": payload.tg_user_id, "username": payload.username},
    )
    await service.store_start_result(
        payload.token,
        {"access_token": access_token, "tg_user_id": payload.tg_user_id, "username": payload.username},
    )
    await service.consume_start_token(payload.token)
    return AuthResponse(
        access_token=access_token,
        tg_user_id=payload.tg_user_id,
        username=payload.username,
    )


@router.get("/api/auth/telegram/status")
async def telegram_login_status(token: str, service: TelegramAuthService = Depends(get_auth_service)):
    result = await service.get_start_result(token)
    if not result:
        return {"status": "pending"}
    if "error" in result:
        return {"status": "denied", **result}
    return {"status": "ok", **result}


@router.get("/api/auth/me")
async def auth_me(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1].strip()
    service = TelegramAuthService()
    session = await service.get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    return {"user": session}
