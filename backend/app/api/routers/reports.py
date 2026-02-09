from datetime import date, timedelta
from typing import Any, Optional
import os

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_db_session
from app.api.report_filters import (
    ReportFilters,
    RawReportParams,
    RawUserFilters,
    get_raw_report_params,
    get_report_filters,
    get_raw_user_filters,
)
from app.schemas.reports import WeeklyReportResponse, RoistatWeeklyReportResponse, RoistatWeeklyRow
from app.services.report_cache_service import ReportCacheService
from app.core.redis_client import RedisCache
from app.services.raw_user_repository import RawUserRepository
from app.services.weekly_reports import WeeklyReportCache
from app.services.roistat_weekly_report import RoistatWeeklyReport
from app.core.config import settings

router = APIRouter(prefix="/api/reports", tags=["reports"])
report_cache = ReportCacheService()
weekly_cache = WeeklyReportCache()


@router.get("/funnel-start/total", summary="Общее количество пользователей и бюджет")
async def funnel_total(filters: ReportFilters = Depends(get_report_filters), session=Depends(get_db_session)) -> dict[str, Optional[float]]:
    return await report_cache.total(session, filters)


@router.get("/funnel-start/daily", summary="Дневная динамика")
async def funnel_daily(
    filters: ReportFilters = Depends(get_report_filters),
    limit: Optional[int] = Query(None, ge=1, le=2000),
    session=Depends(get_db_session),
) -> dict[str, list[dict[str, Any]]]:
    data = await report_cache.daily(session, filters, limit)
    return {"data": data}


@router.get("/funnel-start/breakdown", summary="Разбивка пользователей", response_model=None)
async def funnel_breakdown(
    filters: ReportFilters = Depends(get_report_filters),
    group_by: str = Query("utm_source", pattern="^(utm_source|utm_campaign|advertising_company|source_campaign)$"),
    limit: int = Query(20, ge=1, le=50),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    data = await report_cache.breakdown(session, filters, group_by, limit)
    return {"breakdown": data, "group_by": group_by}


@router.get("/funnel-start/conversions", summary="Конверсии ботов")
async def funnel_conversions(
    filters: ReportFilters = Depends(get_report_filters),
    session=Depends(get_db_session),
) -> dict[str, list[dict[str, Any]]]:
    conversions = await report_cache.conversions(session, filters)
    return {"conversions": conversions}


@router.get("/funnel-start/stages", summary="Агрегат по стадиям")
async def funnel_stages(
    filters: ReportFilters = Depends(get_report_filters),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    data = await report_cache.stages(session, filters)
    return {"stages": data}


@router.get("/funnel-start/summary", summary="Сводка по ботам или РК")
async def funnel_summary(
    filters: ReportFilters = Depends(get_report_filters),
    group_by: str = Query("bot_key", pattern="^(bot_key|advertising_company)$"),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    data = await report_cache.summary(session, filters, group_by)
    return {"summary": data, "group_by": group_by}


@router.get("/funnel-start/raw", summary="Сырые записи пользователей")
async def funnel_raw(
    filters: ReportFilters = Depends(get_report_filters),
    params: RawReportParams = Depends(get_raw_report_params),
    raw_filters: RawUserFilters = Depends(get_raw_user_filters),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    raw_repo = RawUserRepository()
    rows, total = await raw_repo.fetch_raw(
        session, filters, raw_filters, params.limit, params.offset, params.sort_by, params.sort_direction
    )
    return {"users": rows, "total": total}


@router.get("/funnel-start/export", summary="Экспорт RAW пользователей")
async def funnel_export(
    filters: ReportFilters = Depends(get_report_filters),
    params: RawReportParams = Depends(get_raw_report_params),
    raw_filters: RawUserFilters = Depends(get_raw_user_filters),
    session=Depends(get_db_session),
) -> StreamingResponse:
    raw_repo = RawUserRepository()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    header = [
        "id",
        "bot_key",
        "tg_user_id",
        "user_block",
        "created_at",
        "utm_source",
        "utm_campaign",
        "utm_medium",
        "utm_content",
        "utm_term",
        "advertising_company",
        "budget",
        "converted_to_lead",
        "registered_platform",
        "started_learning",
        "completed_course",
        "used_simulator",
        "interview_reached",
        "interview_passed",
        "offer_received",
        "contract_signed",
        "distance_grinding",
        "channel_subscribed",
        "community_member",
        "team_member",
        "internal_status",
        "learn_start_date",
        "start_course",
        "first_touch_bot",
        "first_touch_campaign",
        "last_touch_bot",
        "last_touch_campaign",
    ]
    writer.writerow(header)
    batch_size = 500
    offset = 0
    while True:
        rows, total = await raw_repo.fetch_raw(
            session, filters, raw_filters, batch_size, offset, params.sort_by, params.sort_direction
        )
        if not rows:
            break
        for row in rows:
            writer.writerow([row.get(col, "") for col in header])
        offset += batch_size
        if offset >= total:
            break
    buffer.seek(0)
    response = StreamingResponse(buffer, media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=raw_users.csv"
    return response

@router.get("/weekly", summary="Понедельная статистика", response_model=WeeklyReportResponse)
async def weekly_stats(
    group_by: str = Query("bot", pattern="^(bot|company)$"),
    group_key: str | None = Query(None, alias="group_key"),
):
    if not group_key:
        raise HTTPException(status_code=400, detail="group_key is required")
    months = await weekly_cache.list_months(group_by, group_key)
    data = {}
    for month in months:
        data[month] = await weekly_cache.fetch_weekly(group_by, group_key, month)
    return WeeklyReportResponse(group_key=group_key, months=data)


@router.get("/roistat-weekly", summary="Weekly для Roistat", response_model=RoistatWeeklyReportResponse)
async def roistat_weekly(
    event_start: Optional[date] = Query(None),
    event_end: Optional[date] = Query(None),
    first_touch_start: Optional[date] = Query(None),
    first_touch_end: Optional[date] = Query(None),
    mode: str = Query("event", pattern="^(event|first_touch)$"),
    session=Depends(get_db_session),
):
    # Backward-compat: if client sends first_touch_* without mode, assume first_touch.
    if mode == "event" and (first_touch_start or first_touch_end):
        mode = "first_touch"
    # If client omits first_touch_* but provides event range in first_touch mode, reuse it.
    if mode == "first_touch" and not (first_touch_start or first_touch_end):
        if event_start or event_end:
            first_touch_start = event_start
            first_touch_end = event_end
    cache = RedisCache()
    cache_key = (
        "reports:roistat_weekly:v2:"
        f"{mode}:{event_start}:{event_end}:{first_touch_start}:{first_touch_end}"
    )
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return RoistatWeeklyReportResponse(
            rows=[RoistatWeeklyRow(**row) for row in cached]
        )
    rows = await RoistatWeeklyReport().build_weekly_rows(
        session,
        event_start=event_start,
        event_end=event_end,
        first_touch_start=first_touch_start,
        first_touch_end=first_touch_end,
        filter_mode=mode,
    )
    payload = [
        RoistatWeeklyRow(
            week_start=row.week_start.isoformat(),
            almanah_starts=row.almanah_starts,
            platform=row.platform,
            learning=row.learning,
            mtt=row.mtt,
            spin=row.spin,
            cash=row.cash,
            not_started=row.not_started,
            saloon=row.saloon,
            budget=row.budget,
        ).model_dump()
        for row in rows
    ]
    await cache.set_json(cache_key, payload, ttl=settings.weekly_cache_ttl_seconds)
    return RoistatWeeklyReportResponse(rows=[RoistatWeeklyRow(**row) for row in payload])


@router.get("/subscriptions/compare", summary="Старты ботов vs подписки/отписки")
async def subscriptions_compare(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    group_by: str = Query("campaign", pattern="^(campaign|overall)$"),
    interval: str = Query("day", pattern="^(day|week)$"),
    bots: Optional[list[str]] = Query(None),
    advertising_companies: Optional[list[str]] = Query(None),
    utm_source: Optional[list[str]] = Query(None),
    utm_campaign: Optional[list[str]] = Query(None),
    utm_medium: Optional[list[str]] = Query(None),
    utm_content: Optional[list[str]] = Query(None),
    utm_term: Optional[list[str]] = Query(None),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    if not start_date and not end_date and settings.subscriptions_compare_default_days > 0:
        start_date = (date.today() - timedelta(days=settings.subscriptions_compare_default_days)).isoformat()
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
    community_id = os.environ.get("TELEGRAM_COMMUNITY_ID")
    data = await report_cache.subscriptions_vs_starts(
        session,
        start_date=start_date,
        end_date=end_date,
        group_by_campaign=(group_by == "campaign"),
        interval=interval,
        channel_id=channel_id,
        community_id=community_id,
        bots=bots,
        advertising_companies=advertising_companies,
        utm_source=utm_source,
        utm_campaign=utm_campaign,
        utm_medium=utm_medium,
        utm_content=utm_content,
        utm_term=utm_term,
    )
    return {"data": data, "group_by": group_by, "interval": interval}


@router.get("/courses/mix", summary="Разрез курсов MTT/SPIN/CASH")
async def course_mix(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    data = await report_cache.course_mix(session, start_date=start_date, end_date=end_date)
    return {"data": data}


@router.get("/touch/summary", summary="Атрибуция First/Last touch")
async def touch_summary(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    mode: str = Query("first", pattern="^(first|last)$"),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    data = await report_cache.touch_summary(session, start_date=start_date, end_date=end_date, mode=mode)
    return {"data": data, "mode": mode}


@router.get("/touch/funnel-summary", summary="Воронка по First/Last touch")
async def touch_funnel_summary(
    filters: ReportFilters = Depends(get_report_filters),
    mode: str = Query("last", regex="^(first|last)$"),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    data = await report_cache.touch_funnel_summary(session, filters, mode)
    return {"summary": data}


@router.get("/touch/weekly", summary="Понедельная статистика по First/Last touch")
async def touch_weekly(
    group_key: str = Query(..., alias="group_key"),
    mode: str = Query("last", regex="^(first|last)$"),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    payload = await report_cache.touch_weekly(session, group_key, mode)
    return {"group_key": group_key, "months": payload["months"], "data": payload["data"]}


@router.get("/budgets/weekly", summary="Недельные бюджеты и метрики")
async def budgets_weekly(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    interval: str = Query("week", regex="^(day|week)$"),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    data = await report_cache.budget_weekly_report(session, start_date=start_date, end_date=end_date, interval=interval)
    return {"data": data}
