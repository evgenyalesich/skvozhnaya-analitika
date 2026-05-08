from datetime import date, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_db_session
from app.api.report_filters import ReportFilters, get_report_filters
from app.services.report_bot_scope import apply_excluded_bot_filter
from app.services.report_cache_service import ReportCacheService

from .reports_funnel_helpers import (
    event_funnel_stages_from_main_report,
    load_ph_mirror_weekly_counts,
)

# Основные агрегированные эндпоинты воронки (prefix /api/reports/funnel-start).
# Все данные проходят через ReportCacheService — кешируются в Redis при отсутствии фильтров.

router = APIRouter(tags=["reports-funnel"])
report_cache = ReportCacheService()


@router.get("/funnel-start/total", summary="Общее количество пользователей и бюджет")
# total_users, total_budget, cac (cost-per-acquisition).
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
async def funnel_conversions(filters: ReportFilters = Depends(get_report_filters), session=Depends(get_db_session)) -> dict[str, list[dict[str, Any]]]:
    conversions = await report_cache.conversions(session, filters)
    return {"conversions": conversions}


@router.get("/funnel-start/stages", summary="Агрегат по стадиям")
# touch_mode: event|first_touch|last_touch — как считать дату входа пользователя.
# display_mode: weekly|cohort — режим отображения на фронте.
# При touch_mode=event и без user_scope — использует event_funnel_stages_from_main_report
# (быстрый путь через основной отчёт), иначе — полный пересчёт из raw_bot_users.
async def funnel_stages(
    filters: ReportFilters = Depends(get_report_filters),
    touch_mode: str = Query("event", pattern="^(event|first_touch|last_touch)$"),
    display_mode: str = Query("weekly", pattern="^(weekly|cohort)$"),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    if touch_mode in {"event", "first_touch", "last_touch"} and not (filters.user_scope and filters.user_scope != "all"):
        data = await event_funnel_stages_from_main_report(
            filters,
            session,
            touch_mode=touch_mode,
            display_mode=display_mode,
        )
        return {"stages": data, "touch_mode": touch_mode, "display_mode": display_mode}
    data = await report_cache.stages(session, filters)
    return {"stages": data, "touch_mode": touch_mode, "display_mode": display_mode}


@router.get("/funnel-start/summary", summary="Сводка по ботам или РК")
async def funnel_summary(
    filters: ReportFilters = Depends(get_report_filters),
    group_by: str = Query("bot_key", pattern="^(bot_key|advertising_company)$"),
    touch_mode: str = Query("event", pattern="^(event|first_touch|last_touch)$"),
    display_mode: str = Query("weekly", pattern="^(weekly|cohort)$"),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    data = await report_cache.summary(session, filters, group_by, touch_mode=touch_mode)
    return {"summary": data, "group_by": group_by, "touch_mode": touch_mode, "display_mode": display_mode}


@router.get("/funnel-start/summary-weekly", summary="Недельная сводка по одной группе BOTs/РК")
async def funnel_summary_weekly(
    filters: ReportFilters = Depends(get_report_filters),
    group_by: str = Query("bot_key", pattern="^(bot_key|advertising_company)$"),
    group_key: str = Query(..., min_length=1),
    touch_mode: str = Query("event", pattern="^(event|first_touch|last_touch)$"),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    if not filters.start_date or not filters.end_date:
        return {"group_key": group_key, "group_by": group_by, "months": {}}

    start = filters.start_date
    end = filters.end_date
    week_start = start - timedelta(days=start.weekday())

    months: dict[str, list[dict[str, Any]]] = {}
    while week_start <= end:
        week_end = week_start + timedelta(days=6)
        slice_start = max(start, week_start)
        slice_end = min(end, week_end)

        week_filters = ReportFilters(
            start_date=slice_start,
            end_date=slice_end,
            bots=filters.bots,
            advertising_companies=filters.advertising_companies,
            utm_source=filters.utm_source,
            utm_campaign=filters.utm_campaign,
            utm_medium=filters.utm_medium,
            utm_content=filters.utm_content,
            utm_term=filters.utm_term,
            user_scope=filters.user_scope,
        )

        week_rows = await report_cache.summary(session, week_filters, group_by, touch_mode=touch_mode)
        row = next((item for item in week_rows if str(item.get("group") or "") == group_key), None)

        values = {
            "entered": int((row or {}).get("entered") or 0),
            "new_in_system": int((row or {}).get("new_in_system") or 0),
            "old_in_system": int((row or {}).get("old_in_system") or 0),
            "lead": int((row or {}).get("lead") or 0),
            "platform": int((row or {}).get("platform") or 0),
            "learning": int((row or {}).get("learning") or 0),
            "course": int((row or {}).get("course") or 0),
            "interview": int((row or {}).get("interview") or 0),
            "passed": int((row or {}).get("passed") or 0),
            "offer": int((row or {}).get("offer") or 0),
            "contract": int((row or {}).get("contract") or 0),
            "distance_grinding": int((row or {}).get("distance_grinding") or 0),
        }
        month_key = week_start.strftime("%Y-%m")
        months.setdefault(month_key, []).append(
            {
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "values": values,
            }
        )
        week_start += timedelta(days=7)

    return {"group_key": group_key, "group_by": group_by, "touch_mode": touch_mode, "months": months}


@router.get("/funnel-start/tree", summary="Дерево воронки: платформа → рекламный кабинет → бот")
# Трёхуровневая иерархия: Platform → AdvertisingCompany → bot_key.
# Считает все этапы воронки для каждого узла за один запрос (JOIN с advertising_company_bots).
# ph_platform_weeks — отдельный счётчик регистраций на платформе по неделям из зеркала PH.
async def funnel_tree(filters: ReportFilters = Depends(get_report_filters), session=Depends(get_db_session)) -> dict[str, Any]:
    from sqlalchemy import and_, case, func, select
    from app.models.analytics import AdvertisingCompany, AdvertisingCompanyBot, RawBotUser
    from app.services.employee_registry_service import apply_employee_exclusion
    import datetime as dt

    def _apply(stmt):
        stmt = apply_excluded_bot_filter(stmt, RawBotUser.bot_key)
        if filters.start_date:
            stmt = stmt.where(RawBotUser.created_at >= filters.start_date)
        if filters.end_date:
            stmt = stmt.where(RawBotUser.created_at < (filters.end_date + dt.timedelta(days=1)))
        if filters.advertising_companies:
            stmt = stmt.where(RawBotUser.advertising_company.in_(filters.advertising_companies))
        return apply_employee_exclusion(stmt, RawBotUser.tg_user_id)

    company = func.coalesce(RawBotUser.advertising_company, "Без категории")
    bot = func.coalesce(RawBotUser.bot_key, "нет бота")
    platform_col = func.coalesce(AdvertisingCompany.platform, "Без источника")

    stmt = (
        select(
            platform_col.label("platform"),
            company.label("company"),
            bot.label("bot"),
            func.count(RawBotUser.tg_user_id.distinct()).label("entered"),
            func.sum(case((RawBotUser.converted_to_lead == True, 1), else_=0)).label("lead"),
            func.count(
                func.distinct(
                    case(
                        (
                            and_(
                                RawBotUser.ph_user_id.is_not(None),
                                RawBotUser.platform_registered_at.is_not(None),
                            ),
                            RawBotUser.ph_user_id,
                        ),
                        else_=None,
                    )
                )
            ).label("platform_cnt"),
            func.sum(case((RawBotUser.started_learning == True, 1), else_=0)).label("learning"),
            func.sum(case((RawBotUser.completed_course == True, 1), else_=0)).label("course"),
            func.sum(case((RawBotUser.used_simulator == True, 1), else_=0)).label("simulator"),
            func.sum(case((RawBotUser.interview_reached == True, 1), else_=0)).label("interview"),
            func.sum(case((RawBotUser.interview_passed == True, 1), else_=0)).label("passed"),
            func.sum(case((RawBotUser.offer_received == True, 1), else_=0)).label("offer"),
            func.sum(case((RawBotUser.contract_signed == True, 1), else_=0)).label("contract"),
            func.sum(case((RawBotUser.distance_grinding == True, 1), else_=0)).label("distance"),
        )
        .outerjoin(AdvertisingCompanyBot, AdvertisingCompanyBot.bot_key == RawBotUser.bot_key)
        .outerjoin(AdvertisingCompany, AdvertisingCompany.company_id == AdvertisingCompanyBot.company_id)
        .group_by(platform_col, company, bot)
    )
    stmt = _apply(stmt)
    result = await session.execute(stmt)
    rows = result.fetchall()

    def sum_metrics(items: list[dict]) -> dict:
        keys = ["entered", "lead", "platform", "learning", "course", "simulator", "interview", "passed", "offer", "contract", "distance"]
        return {k: sum(m[k] for m in items) for k in keys}

    tree_map: dict = {}
    for row in rows:
        p, c, b = row.platform, row.company, row.bot
        metrics = {
            "entered": int(row.entered or 0),
            "lead": int(row.lead or 0),
            "platform": int(row.platform_cnt or 0),
            "learning": int(row.learning or 0),
            "course": int(row.course or 0),
            "simulator": int(row.simulator or 0),
            "interview": int(row.interview or 0),
            "passed": int(row.passed or 0),
            "offer": int(row.offer or 0),
            "contract": int(row.contract or 0),
            "distance": int(row.distance or 0),
        }
        tree_map.setdefault(p, {}).setdefault(c, {})[b] = metrics

    tree = []
    for plat, companies in sorted(tree_map.items()):
        company_nodes = []
        for comp, bots in sorted(companies.items()):
            bot_nodes = [{"bot": bot_key, **m} for bot_key, m in sorted(bots.items())]
            comp_metrics = sum_metrics(bot_nodes)
            company_nodes.append({"company": comp, **comp_metrics, "bots": bot_nodes})
        source_metrics = sum_metrics(company_nodes)
        tree.append({"source": plat, **source_metrics, "companies": company_nodes})

    ph_platform_counts = await load_ph_mirror_weekly_counts(filters.start_date, filters.end_date)
    return {"tree": tree, "ph_platform_weeks": ph_platform_counts}
