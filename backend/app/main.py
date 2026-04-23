from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .core.config import settings
from .core.periodic_sync import periodic_sync_manager
from .ingestion.replication_worker import start_worker as start_replication_worker

app = FastAPI(title="Сквозная аналитика", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    if settings.security_headers_enabled:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "base-uri 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' https: http: wss: ws:; "
            "font-src 'self' data:;",
        )
    return response


@app.on_event("startup")
async def start_periodic_sync() -> None:
    periodic_sync_manager.start()
    start_replication_worker()
    if settings.telegram_membership_enabled and settings.telegram_membership_realtime_enabled:
        from app.worker.tasks import schedule_telegram_membership_realtime_job, redis_connection, _TELEGRAM_MEMBERSHIP_REALTIME_LOCK_KEY
        if not redis_connection.get(_TELEGRAM_MEMBERSHIP_REALTIME_LOCK_KEY):
            schedule_telegram_membership_realtime_job()


@app.on_event("shutdown")
async def stop_periodic_sync() -> None:
    from .ingestion.replication_worker import get_worker
    get_worker().stop()
    await periodic_sync_manager.stop()
