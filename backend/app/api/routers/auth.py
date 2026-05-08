# Авторизация через Telegram.
# Поток: POST /start → бот присылает инлайн-кнопки (approve/deny) → webhook → POST /confirm → GET /status.
# Альтернатива: фронтенд сам вызывает POST /confirm минуя бот (прямая авторизация).
# Сессия хранится в Redis; токен кладётся в httpOnly cookie и возвращается в теле.

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response, Cookie
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


def _set_auth_cookie(response: Response, token: str) -> None:
    # Устанавливает httpOnly cookie с JWT-токеном (TTL по умолчанию 7 дней).
    cookie_name = getattr(settings, "auth_cookie_name", "auth_token")
    response.set_cookie(
        key=cookie_name,
        value=token,
        httponly=True,
        secure=getattr(settings, "auth_cookie_secure", True),
        samesite=getattr(settings, "auth_cookie_samesite", "lax"),
        max_age=getattr(settings, "auth_session_ttl_seconds", 60 * 60 * 24 * 7),
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    cookie_name = getattr(settings, "auth_cookie_name", "auth_token")
    response.delete_cookie(
        key=cookie_name,
        path="/",
    )


async def get_auth_service() -> TelegramAuthService:
    return TelegramAuthService()


@router.post("/api/auth/telegram/start", response_model=StartResponse)
# Генерирует одноразовый start_token (TTL ~5 мин) и ссылку на бота с этим токеном.
# Фронтенд показывает ссылку пользователю; тот кликает → бот присылает ему кнопки approve/deny.
async def start_telegram_login(service: TelegramAuthService = Depends(get_auth_service)):
    start_token = await service.create_start_token()
    return StartResponse(start_token=start_token, login_url=service.build_login_link(start_token))


@router.post("/api/auth/telegram/confirm", response_model=AuthResponse)
# Прямая авторизация: фронтенд передаёт token + tg_user_id после того, как бот подтвердил вход.
# Проверяет: start_token валиден, пользователь в белом списке telegram_access, затем создаёт JWT-сессию.
async def confirm_telegram_login(
    payload: ConfirmRequest,
    response: Response,
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
    if response is not None:
        _set_auth_cookie(response, access_token)
    return AuthResponse(
        access_token=access_token,
        tg_user_id=payload.tg_user_id,
        username=payload.username,
    )


@router.get("/api/auth/telegram/status")
# Фронтенд polling этого endpoint после /start, пока не получит status=ok.
# Возвращает: pending / denied / ok. При ok дополнительно выставляет cookie (если ответ ещё не отправлен).
async def telegram_login_status(
    token: str,
    response: Response,
    service: TelegramAuthService = Depends(get_auth_service),
):
    result = await service.get_start_result(token)
    if not result:
        return {"status": "pending"}
    if "error" in result:
        return {"status": "denied", **result}
    if response is not None and "access_token" in result:
        _set_auth_cookie(response, str(result["access_token"]))
    payload = {"status": "ok"}
    if "tg_user_id" in result:
        payload["tg_user_id"] = result["tg_user_id"]
    if "username" in result:
        payload["username"] = result["username"]
    return payload


@router.get("/api/auth/me")
# Возвращает данные текущей сессии по JWT (из заголовка Bearer или cookie auth_token).
# Используется фронтендом при загрузке для проверки активной сессии.
async def auth_me(
    authorization: Optional[str] = Header(default=None),
    auth_token: Optional[str] = Cookie(default=None, alias="auth_token"),
):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif auth_token:
        token = auth_token
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    service = TelegramAuthService()
    session = await service.get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    return {"user": session}


@router.post("/api/auth/logout")
async def logout(response: Response):
    _clear_auth_cookie(response)
    return {"status": "ok"}
