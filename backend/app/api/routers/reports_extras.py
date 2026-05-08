from datetime import date, timedelta
from typing import Any, Optional
import os

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_db_session
from app.api.report_filters import ReportFilters, get_report_filters
from app.core.config import settings
from app.services.report_cache_service import ReportCacheService


# Дополнительные отчёты: подписки, атрибуция touch, бюджеты.
# Все эндпоинты добавляются к основному router /api/reports через include_router.

router = APIRouter(tags=["reports-extras"])
report_cache = ReportCacheService()


@router.get("/subscriptions/compare", summary="Старты ботов vs подписки/отписки")
# group_by: campaign|bot|overall — уровень группировки.
# Для group_by!=bot автоматически добавляет дефолтный период (subscriptions_compare_default_days).
# Данные из agg_tg_subs_daily: bot_starts, channel_subscribed/unsubscribed, saloon_subscribed/unsubscribed.
async def subscriptions_compare(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    group_by: str = Query("campaign", pattern="^(campaign|bot|overall)$"),
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
    # bot mode shows full history — skip the default date window
    if group_by != "bot" and not start_date and not end_date and settings.subscriptions_compare_default_days > 0:
        start_date = (date.today() - timedelta(days=settings.subscriptions_compare_default_days)).isoformat()
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
    community_id = os.environ.get("TELEGRAM_COMMUNITY_ID")
    result = await report_cache.subscriptions_vs_starts(
        session,
        start_date=start_date,
        end_date=end_date,
        group_by_campaign=(group_by == "campaign"),
        group_by_bot=(group_by == "bot"),
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
    return {
        "data": result.get("rows", []),
        "overall": result.get("overall_rows", []),
        "summary": result.get("summary", {}),
        "channel_funnel": result.get("channel_funnel", []),
        "channel_report_weekly": result.get("channel_report_weekly", []),
        "group_by": group_by,
        "interval": interval,
    }


@router.get("/courses/mix", summary="Разрез курсов MTT/SPIN/CASH")
async def course_mix(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    data = await report_cache.course_mix(session, start_date=start_date, end_date=end_date)
    return {"data": data}


@router.get("/touch/summary", summary="Атрибуция First/Last touch")
# mode: first|last — какой touch использовать для атрибуции.
# Показывает распределение пользователей по источникам касания.
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
    mode: str = Query("last", pattern="^(first|last)$"),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    data = await report_cache.touch_funnel_summary(session, filters, mode)
    return {"summary": data}


@router.get("/touch/weekly", summary="Понедельная статистика по First/Last touch")
async def touch_weekly(
    group_key: str = Query(..., alias="group_key"),
    mode: str = Query("last", pattern="^(first|last)$"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    payload = await report_cache.touch_weekly(session, group_key, mode, start_date, end_date)
    return {"group_key": group_key, "months": payload["months"], "data": payload["data"]}


@router.get("/budgets/weekly", summary="Недельные бюджеты и метрики")
async def budgets_weekly(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    interval: str = Query("week", pattern="^(day|week)$"),
    bots: Optional[list[str]] = Query(None),
    advertising_companies: Optional[list[str]] = Query(None),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    data = await report_cache.budget_weekly_report(
        session,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        bots=bots,
        advertising_companies=advertising_companies,
    )
    return {"data": data}
