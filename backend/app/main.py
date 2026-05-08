import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .core.config import settings
from .core.periodic_sync import periodic_sync_manager
from .ingestion.replication_worker import start_worker as start_replication_worker

logger = logging.getLogger(__name__)


async def _warmup_cache() -> None:
    from .api.report_filters import ReportFilters
    from .db.session import async_session
    from .services.report_cache_service import ReportCacheService
    from .api.routers.reports_roistat_companies_parts.reports_roistat_companies_runtime_core import (
        roistat_weekly_by_company,
    )

    empty = ReportFilters(
        start_date=None, end_date=None,
        bots=[], advertising_companies=[],
        utm_source=[], utm_campaign=[],
        utm_medium=[], utm_content=[], utm_term=[],
    )
    svc = ReportCacheService()

    async def _run(name: str, coro):
        try:
            await coro
            logger.info("cache warmup: %s — ok", name)
        except Exception as exc:
            logger.warning("cache warmup: %s — failed: %s", name, exc)

    async def _with_session(fn):
        async with async_session() as session:
            return await fn(session)

    await asyncio.gather(
        _run("total",                  _with_session(lambda s: svc.total(s, empty))),
        _run("daily",                  _with_session(lambda s: svc.daily(s, empty))),
        _run("stages",                 _with_session(lambda s: svc.stages(s, empty))),
        _run("breakdown:utm_source",   _with_session(lambda s: svc.breakdown(s, empty, "utm_source"))),
        _run("summary:bot/event",      _with_session(lambda s: svc.summary(s, empty, "bot_key", touch_mode="event"))),
        _run("summary:bot/first",      _with_session(lambda s: svc.summary(s, empty, "bot_key", touch_mode="first_touch"))),
        _run("summary:bot/last",       _with_session(lambda s: svc.summary(s, empty, "bot_key", touch_mode="last_touch"))),
        _run("summary:company/event",  _with_session(lambda s: svc.summary(s, empty, "advertising_company", touch_mode="event"))),
        _run("roistat_weekly", _with_session(lambda s: roistat_weekly_by_company(
            event_start=None, event_end=None, mode="event",
            first_touch_start=None, first_touch_end=None, display_mode="weekly",
            bots=None, advertising_companies=None,
            utm_source=None, utm_campaign=None,
            utm_medium=None, utm_content=None, utm_term=None,
            session=s,
        ))),
    )
    logger.info("cache warmup: complete")

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
async def _check_cors_config() -> None:
    if settings.cors_allow_origins == ["*"]:
        logger.warning(
            "CORS is set to '*' — all origins are allowed. "
            "Set CORS_ALLOW_ORIGINS_CSV in .env to restrict access "
            "(e.g. CORS_ALLOW_ORIGINS_CSV=https://roistat.pokerhub.pro)"
        )


@app.on_event("startup")
async def start_periodic_sync() -> None:
    periodic_sync_manager.start()
    if settings.replication_worker_enabled:
        start_replication_worker()
    else:
        logger.info("Replication worker disabled by REPLICATION_WORKER_ENABLED=false")
    if settings.telegram_membership_enabled and settings.telegram_membership_realtime_enabled:
        from app.worker.tasks import schedule_telegram_membership_realtime_job
        from app.worker.tasks_runtime_shared import (
            _TELEGRAM_MEMBERSHIP_REALTIME_LOCK_KEY,
            redis_connection,
        )
        if not redis_connection.get(_TELEGRAM_MEMBERSHIP_REALTIME_LOCK_KEY):
            schedule_telegram_membership_realtime_job()
    asyncio.create_task(_warmup_cache())


@app.on_event("shutdown")
async def stop_periodic_sync() -> None:
    from .ingestion.replication_worker import get_worker
    get_worker().stop()
    await periodic_sync_manager.stop()
