from datetime import date

from fastapi import APIRouter, HTTPException

from app.core.redis_client import RedisCache
from app.worker.tasks import (
    queue,
    schedule_aggregation_job,
    schedule_google_sheets_job,
    schedule_ingestion_job,
    schedule_pokerhub_cache_job,
    schedule_roistat_weekly_export_job,
    schedule_telegram_job,
    schedule_telegram_membership_full_sync_job,
    schedule_telegram_membership_realtime_job,
)

# Эндпоинты для ручного запуска фоновых задач через RQ-очередь.
# Все POST-методы просто ставят задачу в очередь и возвращают {"status":"ok"}.
# GET /status — текущее состояние очереди (pending_jobs).
# GET /sync-status — даты последних успешных синхронизаций из Redis.

router = APIRouter()


@router.post("/ingest")
# Запускает ingestion из всех источников (бот-БД → raw_bot_users).
def trigger_ingest():
    schedule_ingestion_job()
    return {"status": "ok", "message": "Ingestion job queued"}


@router.post("/sync-pokerhub")
def sync_pokerhub():
    schedule_pokerhub_cache_job()
    return {"status": "ok", "source": "pokerhub", "message": "Обновление кэша PokerHub запущено"}


@router.post("/sync-google-sheets")
def sync_google_sheets():
    schedule_google_sheets_job()
    return {"status": "ok", "source": "google_sheets", "message": "Синхронизация Google Sheets запущена"}


@router.post("/sync-mongodb")
def sync_mongodb():
    schedule_ingestion_job()
    return {"status": "ok", "source": "mongodb", "message": "Синхронизация MongoDB запущена"}


@router.post("/sync-telegram")
def sync_telegram():
    schedule_telegram_job()
    return {"status": "ok", "source": "telegram", "message": "Синхронизация Telegram API запущена"}


@router.post("/sync-telegram-membership")
def sync_telegram_membership():
    schedule_telegram_membership_full_sync_job()
    return {
        "status": "ok",
        "source": "telegram_membership",
        "message": "Полный sync membership Telegram поставлен в очередь",
    }


@router.post("/start-telegram-membership-realtime")
def start_telegram_membership_realtime():
    schedule_telegram_membership_realtime_job()
    return {
        "status": "ok",
        "source": "telegram_membership_realtime",
        "message": "Realtime monitoring membership Telegram поставлен в очередь",
    }


@router.post("/sync-roistat-weekly")
# Экспортирует еженедельный отчёт в Google Sheets.
# Опциональные параметры first_touch_start/end для фильтрации по дате первого касания.
def sync_roistat_weekly(first_touch_start: str | None = None, first_touch_end: str | None = None):
    if first_touch_start:
        try:
            date.fromisoformat(first_touch_start)
        except ValueError:
            raise HTTPException(status_code=400, detail="first_touch_start must be YYYY-MM-DD")
    if first_touch_end:
        try:
            date.fromisoformat(first_touch_end)
        except ValueError:
            raise HTTPException(status_code=400, detail="first_touch_end must be YYYY-MM-DD")
    schedule_roistat_weekly_export_job(first_touch_start=first_touch_start, first_touch_end=first_touch_end)
    return {"status": "ok", "source": "roistat_weekly", "message": "Экспорт Weekly в Google Sheets запущен"}


@router.post("/sync-advertising-budget")
def sync_advertising_budget():
    schedule_ingestion_job()
    return {"status": "ok", "source": "advertising", "message": "Синхронизация бюджета запущена"}


@router.post("/sync-all")
async def sync_all():
    schedule_ingestion_job()
    cache = RedisCache()
    await cache.delete_pattern("utm:options:*")
    return {"status": "ok", "message": "Sync for all sources queued"}


@router.post("/refresh-agg")
def refresh_agg():
    schedule_aggregation_job()
    return {"status": "ok", "message": "Aggregate recalculation started"}


@router.get("/status")
def admin_status():
    return {
        "status": "idle",
        "pending_jobs": queue.count,
        "queue_name": queue.name,
    }


@router.get("/sync-status")
async def sync_status():
    cache = RedisCache()
    last_ingestion = await cache.get_json("sync:last_ingestion")
    last_sm = await cache.get_json("sync:last_sm")
    last_pokerhub = await cache.get_json("sync:last_pokerhub")
    last_ingestion_success = await cache.get_json("sync:last_ingestion_success")
    last_pokerhub_success = await cache.get_json("sync:last_pokerhub_success")
    last_roistat_weekly = await cache.get_json("sync:last_roistat_weekly")
    last_roistat_weekly_success = await cache.get_json("sync:last_roistat_weekly_success")

    streams = await cache.get_json_by_pattern("replication:stream:*:metrics", limit=500)
    streams_error = [v["db_name"] for v in streams.values() if v.get("status") not in ("streaming", "ok")]
    replication = {
        "total": len(streams),
        "streams_ok": len(streams) - len(streams_error),
        "streams_error": streams_error,
    }

    return {
        "last_ingestion": last_ingestion or None,
        "last_ingestion_success": last_ingestion_success or None,
        "last_sm": last_sm or None,
        "last_pokerhub": last_pokerhub or None,
        "last_pokerhub_success": last_pokerhub_success or None,
        "last_roistat_weekly": last_roistat_weekly or None,
        "last_roistat_weekly_success": last_roistat_weekly_success or None,
        "replication": replication,
    }


@router.get("/data-sources-status")
def data_sources_status():
    return {"sources": {"postgres": "ok", "google_sheets": "pending"}}
