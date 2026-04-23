from datetime import date, datetime, timedelta
import asyncio
from typing import Any, List, Optional
import os
import json
import asyncpg

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
from app.schemas.reports import (
    WeeklyReportResponse,
    RoistatWeeklyReportResponse,
    RoistatWeeklyRow,
    RoistatLessonsReportResponse,
    RoistatLessonCourse,
    RoistatLessonColumn,
    RoistatLessonUserRow,
)
from app.services.report_cache_service import ReportCacheService
from app.core.redis_client import RedisCache
from app.services.raw_user_repository import RawUserRepository
from app.services.weekly_reports import WeeklyReportCache
from app.services.roistat_lessons_report import RoistatLessonsReport
from app.services.report_bot_scope import apply_excluded_bot_filter, normalized_excluded_bot_keys
from app.db.session import async_session
from app.core.config import settings

router = APIRouter(prefix="/api/reports", tags=["reports"])
report_cache = ReportCacheService()
weekly_cache = WeeklyReportCache()

EVENT_FUNNEL_SUMMARY_KEYS = [
    "entered",
    "new_in_system",
    "old_in_system",
    "lead",
    "subscribed",
    "platform",
    "learning",
    "course",
    "simulator",
    "interview",
    "passed",
    "offer",
    "contract",
    "distance_grinding",
]


def _event_summary_row_from_main_report(row: dict[str, Any], group_value: str) -> dict[str, Any]:
    return {
        "group": group_value,
        "entered": int(row.get("entered_all") or 0),
        "new_in_system": int(row.get("new_in_system") or 0),
        "old_in_system": int(row.get("old_in_system") or 0),
        "lead": int(row.get("almanah_starts") or 0),
        "subscribed": int(row.get("channel_subscribed") or 0),
        "platform": int(row.get("platform_cnt") or 0),
        "learning": int(row.get("started_learning") or 0),
        "course": int(row.get("completed_course") or 0),
        "simulator": 0,
        "interview": int(row.get("interview_reached") or 0),
        "passed": 0,
        "offer": int(row.get("offer_received") or 0),
        "contract": int(row.get("contract_signed") or 0),
        "distance_grinding": int(row.get("distance_grinding") or 0),
    }


async def _load_event_main_report_payload(
    filters: ReportFilters,
    session,
    touch_mode: str = "event",
    display_mode: str = "weekly",
) -> dict[str, Any]:
    return await roistat_weekly_by_company(
        event_start=filters.start_date,
        event_end=filters.end_date,
        mode=touch_mode,
        first_touch_start=None,
        first_touch_end=None,
        display_mode=display_mode,
        bots=filters.bots or None,
        advertising_companies=filters.advertising_companies or None,
        utm_source=filters.utm_source or None,
        utm_campaign=filters.utm_campaign or None,
        utm_medium=filters.utm_medium or None,
        utm_content=filters.utm_content or None,
        utm_term=filters.utm_term or None,
        session=session,
    )


async def _event_funnel_summary_from_main_report(
    filters: ReportFilters,
    group_by: str,
    session,
    touch_mode: str = "event",
    display_mode: str = "weekly",
) -> list[dict[str, Any]]:
    payload = await _load_event_main_report_payload(
        filters,
        session,
        touch_mode=touch_mode,
        display_mode=display_mode,
    )
    source_rows = payload.get("bot_rows" if group_by == "bot_key" else "rows", [])
    grouped: dict[str, dict[str, Any]] = {}
    group_field = "bot_key" if group_by == "bot_key" else "company"
    for row in source_rows:
        group_value = str(row.get(group_field) or "—")
        current = grouped.get(group_value)
        if current is None:
            current = _event_summary_row_from_main_report(row, group_value)
            grouped[group_value] = current
            continue
        current["entered"] += int(row.get("entered_all") or 0)
        current["new_in_system"] += int(row.get("new_in_system") or 0)
        current["old_in_system"] += int(row.get("old_in_system") or 0)
        current["lead"] += int(row.get("almanah_starts") or 0)
        current["subscribed"] += int(row.get("channel_subscribed") or 0)
        current["platform"] += int(row.get("platform_cnt") or 0)
        current["learning"] += int(row.get("started_learning") or 0)
        current["course"] += int(row.get("completed_course") or 0)
        current["interview"] += int(row.get("interview_reached") or 0)
        current["offer"] += int(row.get("offer_received") or 0)
        current["contract"] += int(row.get("contract_signed") or 0)
        current["distance_grinding"] += int(row.get("distance_grinding") or 0)
    return sorted(grouped.values(), key=lambda item: item["entered"], reverse=True)


async def _event_funnel_stages_from_main_report(
    filters: ReportFilters,
    session,
    touch_mode: str = "event",
    display_mode: str = "weekly",
) -> dict[str, int]:
    summary_rows = await _event_funnel_summary_from_main_report(
        filters,
        group_by="bot_key",
        session=session,
        touch_mode=touch_mode,
        display_mode=display_mode,
    )
    totals = {key: 0 for key in EVENT_FUNNEL_SUMMARY_KEYS}
    for row in summary_rows:
        for key in EVENT_FUNNEL_SUMMARY_KEYS:
            totals[key] += int(row.get(key) or 0)
    return totals


async def _load_ph_mirror_weekly_counts(start_date: Optional[date], end_date: Optional[date]) -> dict[str, int]:
    dsn = getattr(settings, "lead_db_dsn", None)
    if not dsn:
        return {}

    conn = await asyncpg.connect(str(dsn).replace("postgresql+asyncpg://", "postgresql://"))
    try:
        rows = await conn.fetch(
            """
            SELECT
                DATE_TRUNC('week', ph_registration_at::timestamptz)::date AS week_start,
                COUNT(DISTINCT id) AS cnt
            FROM ph_user_mirror
            WHERE NULLIF(ph_registration_at, '') IS NOT NULL
              AND ($1::date IS NULL OR ph_registration_at::timestamptz::date >= $1::date)
              AND ($2::date IS NULL OR ph_registration_at::timestamptz::date <= $2::date)
            GROUP BY 1
            """,
            start_date,
            end_date,
        )
        return {row["week_start"].isoformat(): int(row["cnt"] or 0) for row in rows}
    finally:
        await conn.close()


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
    touch_mode: str = Query("event", pattern="^(event|first_touch|last_touch)$"),
    display_mode: str = Query("weekly", pattern="^(weekly|cohort)$"),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    if touch_mode in {"event", "first_touch", "last_touch"} and not (filters.user_scope and filters.user_scope != "all"):
        data = await _event_funnel_stages_from_main_report(
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
    if (
        group_by == "advertising_company"
        and touch_mode in {"event", "first_touch", "last_touch"}
        and not (filters.user_scope and filters.user_scope != "all")
    ):
        data = await _event_funnel_summary_from_main_report(
            filters,
            group_by,
            session,
            touch_mode=touch_mode,
            display_mode=display_mode,
        )
        return {"summary": data, "group_by": group_by, "touch_mode": touch_mode, "display_mode": display_mode}
    data = await report_cache.summary(session, filters, group_by, touch_mode=touch_mode)
    return {"summary": data, "group_by": group_by, "touch_mode": touch_mode, "display_mode": display_mode}


@router.get("/funnel-start/tree", summary="Дерево воронки: платформа → рекламный кабинет → бот")
async def funnel_tree(
    filters: ReportFilters = Depends(get_report_filters),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    from sqlalchemy import select, func, case, outerjoin, and_
    from app.models.analytics import RawBotUser, AdvertisingCompany, AdvertisingCompanyBot
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

    # Join RawBotUser → AdvertisingCompanyBot → AdvertisingCompany to get platform
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

    # Build tree: platform → company → bot
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
            bot_nodes = [{"bot": b, **m} for b, m in sorted(bots.items())]
            comp_metrics = sum_metrics(bot_nodes)
            company_nodes.append({"company": comp, **comp_metrics, "bots": bot_nodes})
        source_metrics = sum_metrics(company_nodes)
        tree.append({"source": plat, **source_metrics, "companies": company_nodes})

    return {"tree": tree}


@router.get("/funnel-start/raw", summary="Сырые записи пользователей")
async def funnel_raw(
    filters: ReportFilters = Depends(get_report_filters),
    params: RawReportParams = Depends(get_raw_report_params),
    raw_filters: RawUserFilters = Depends(get_raw_user_filters),
    touch_mode: str = Query("event", pattern="^(event|first|last)$"),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    raw_repo = RawUserRepository()
    rows, total = await raw_repo.fetch_raw(
        session, filters, raw_filters, touch_mode, params.limit, params.offset, params.sort_by, params.sort_direction
    )
    # Для direct_source показываем только PH ID: TG ID в UI должен быть пустым.
    direct_rows = [row for row in rows if row.get("source_category") == "direct_source"]
    for row in direct_rows:
        ph_user_id = row.get("ph_user_id")
        row["pokerhub_user_id"] = str(ph_user_id).strip() if ph_user_id not in (None, "") else None
        row["tg_user_id"] = None

    # Для остальных строк используем ph_user_id из analytics/replica-join.
    for row in rows:
        if row.get("source_category") == "direct_source":
            continue
        ph_user_id = row.get("ph_user_id")
        if ph_user_id not in (None, ""):
            row["pokerhub_user_id"] = str(ph_user_id).strip()
    return {"users": rows, "total": total}


@router.get("/funnel-start/export", summary="Экспорт RAW пользователей")
async def funnel_export(
    filters: ReportFilters = Depends(get_report_filters),
    params: RawReportParams = Depends(get_raw_report_params),
    raw_filters: RawUserFilters = Depends(get_raw_user_filters),
    touch_mode: str = Query("event", pattern="^(event|first|last)$"),
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
        "platform_utm_source",
        "platform_utm_campaign",
        "utm_medium",
        "utm_content",
        "utm_term",
        "platform_utm_medium",
        "platform_utm_content",
        "platform_utm_term",
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
        "source_category",
    ]
    writer.writerow(header)
    batch_size = 500
    offset = 0
    while True:
        rows, total = await raw_repo.fetch_raw(
            session, filters, raw_filters, touch_mode, batch_size, offset, params.sort_by, params.sort_direction
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


@router.get("/weekly-filtered", summary="Понедельная статистика с UTM-фильтрами", response_model=WeeklyReportResponse)
async def weekly_stats_filtered(
    group_by: str = Query("bot", pattern="^(bot|company)$"),
    group_key: str | None = Query(None),
    filters: ReportFilters = Depends(get_report_filters),
    session=Depends(get_db_session),
):
    from datetime import timedelta
    from collections import defaultdict

    if not group_key:
        raise HTTPException(status_code=400, detail="group_key is required")

    # Check if any UTM/bot filters (besides dates) are active
    has_utm = any([
        filters.bots, filters.advertising_companies,
        filters.utm_source, filters.utm_campaign,
        filters.utm_medium, filters.utm_content, filters.utm_term,
    ])

    if not has_utm:
        # No UTM filters — serve pre-cached data
        months_list = await weekly_cache.list_months(group_by, group_key)
        data: dict = {}
        for month in months_list:
            rows = await weekly_cache.fetch_weekly(group_by, group_key, month)
            if rows:
                data[month] = rows
        return WeeklyReportResponse(group_key=group_key, months=data)

    # UTM filters active — query DB directly
    params: dict = {"group_key": group_key}

    if group_by == "bot":
        group_cond = "u.bot_key = :group_key"
    else:
        group_cond = "u.advertising_company = :group_key"

    extra: list[str] = []
    if filters.utm_campaign:
        extra.append("COALESCE(u.platform_utm_campaign, u.utm_campaign, '') = ANY(:utm_campaign)")
        params["utm_campaign"] = filters.utm_campaign
    if filters.utm_source:
        extra.append("COALESCE(u.platform_utm_source, u.utm_source, '') = ANY(:utm_source)")
        params["utm_source"] = filters.utm_source
    if filters.utm_medium:
        extra.append("COALESCE(u.platform_utm_medium, u.utm_medium, '') = ANY(:utm_medium)")
        params["utm_medium"] = filters.utm_medium
    if filters.utm_content:
        extra.append("COALESCE(u.platform_utm_content, u.utm_content, '') = ANY(:utm_content)")
        params["utm_content"] = filters.utm_content
    if filters.utm_term:
        extra.append("COALESCE(u.platform_utm_term, u.utm_term, '') = ANY(:utm_term)")
        params["utm_term"] = filters.utm_term
    if filters.bots and group_by != "bot":
        extra.append("u.bot_key = ANY(:bots)")
        params["bots"] = filters.bots
    if filters.advertising_companies and group_by != "company":
        extra.append("u.advertising_company = ANY(:ad_companies)")
        params["ad_companies"] = filters.advertising_companies
    if filters.start_date:
        extra.append("u.created_at >= :start_date")
        params["start_date"] = filters.start_date
    if filters.end_date:
        extra.append("u.created_at < :end_date_excl")
        params["end_date_excl"] = filters.end_date + timedelta(days=1)

    extra_sql = (" AND " + " AND ".join(extra)) if extra else ""

    from sqlalchemy import text as sa_text
    sql = sa_text(f"""
        WITH first_seen AS (
            SELECT tg_user_id, MIN(created_at) AS first_seen_at_system
            FROM raw_bot_users
            WHERE tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
            GROUP BY tg_user_id
        ),
        ph_reg_by_week AS (
            SELECT
                DATE_TRUNC('week', platform_registered_at)::date AS week_start,
                COUNT(DISTINCT ph_user_id) AS platform_cnt
            FROM raw_bot_users
            WHERE ph_user_id IS NOT NULL
              AND platform_registered_at IS NOT NULL
              AND tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
            GROUP BY 1
        )
        SELECT
            DATE_TRUNC('week', u.created_at)::date AS week_start,
            COUNT(DISTINCT u.tg_user_id)                                                         AS entered,
            COUNT(DISTINCT u.tg_user_id) FILTER (WHERE f.first_seen_at_system = u.created_at)   AS new_in_system,
            COUNT(DISTINCT u.tg_user_id) FILTER (WHERE f.first_seen_at_system < u.created_at)   AS old_in_system,
            COUNT(DISTINCT u.tg_user_id) FILTER (WHERE u.converted_to_lead  = TRUE)             AS lead,
            COALESCE(MAX(pr.platform_cnt), 0)                                                    AS platform,
            COUNT(DISTINCT u.tg_user_id) FILTER (WHERE u.started_learning   = TRUE)             AS learning,
            COUNT(DISTINCT u.tg_user_id) FILTER (WHERE u.completed_course   = TRUE
                AND u.completed_course_at IS NOT NULL
                AND u.completed_course_at >= u.created_at)                                       AS course,
            COUNT(DISTINCT u.tg_user_id) FILTER (WHERE u.interview_reached  = TRUE)             AS interview,
            COUNT(DISTINCT u.tg_user_id) FILTER (WHERE u.interview_passed   = TRUE)             AS passed,
            COUNT(DISTINCT u.tg_user_id) FILTER (WHERE u.offer_received     = TRUE)             AS offer,
            COUNT(DISTINCT u.tg_user_id) FILTER (WHERE u.contract_signed    = TRUE)             AS contract,
            COUNT(DISTINCT u.tg_user_id) FILTER (WHERE u.distance_grinding  = TRUE)             AS distance_grinding
        FROM raw_bot_users u
        JOIN first_seen f ON f.tg_user_id = u.tg_user_id
        LEFT JOIN ph_reg_by_week pr ON pr.week_start = DATE_TRUNC('week', u.created_at)::date
        WHERE u.tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)
          AND {group_cond}
          {extra_sql}
        GROUP BY DATE_TRUNC('week', u.created_at)::date
        ORDER BY week_start
    """)

    result = await session.execute(sql, params)
    db_rows = result.fetchall()

    monthly: dict = defaultdict(list)
    for row in db_rows:
        ws = row.week_start
        month_key = ws.strftime("%Y-%m")
        monthly[month_key].append({
            "week_start": ws.isoformat(),
            "week_end": (ws + timedelta(days=6)).isoformat(),
            "values": {
                "entered":          row.entered          or 0,
                "new_in_system":    row.new_in_system    or 0,
                "old_in_system":    row.old_in_system    or 0,
                "lead":             row.lead             or 0,
                "platform":         row.platform         or 0,
                "learning":         row.learning         or 0,
                "course":           row.course           or 0,
                "interview":        row.interview        or 0,
                "passed":           row.passed           or 0,
                "offer":            row.offer            or 0,
                "contract":         row.contract         or 0,
                "distance_grinding": row.distance_grinding or 0,
            },
        })

    return WeeklyReportResponse(group_key=group_key, months=dict(monthly))


@router.get("/roistat-weekly/companies-weekly", summary="Основной отчёт: Месяц → Неделя → РК")
async def roistat_weekly_by_company(
    event_start: Optional[date] = Query(None),
    event_end: Optional[date] = Query(None),
    mode: str = Query("event", pattern="^(event|first_touch|last_touch)$"),
    first_touch_start: Optional[date] = Query(None),
    first_touch_end: Optional[date] = Query(None),
    display_mode: str = Query("weekly", pattern="^(weekly|cohort)$"),
    bots: Optional[List[str]] = Query(None),
    advertising_companies: Optional[List[str]] = Query(None),
    utm_source: Optional[List[str]] = Query(None),
    utm_campaign: Optional[List[str]] = Query(None),
    utm_medium: Optional[List[str]] = Query(None),
    utm_content: Optional[List[str]] = Query(None),
    utm_term: Optional[List[str]] = Query(None),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    from sqlalchemy import text as sa_text
    cache = RedisCache()

    cache_payload = {
        "event_start": event_start.isoformat() if event_start else None,
        "event_end": event_end.isoformat() if event_end else None,
        "mode": mode,
        "first_touch_start": first_touch_start.isoformat() if first_touch_start else None,
        "first_touch_end": first_touch_end.isoformat() if first_touch_end else None,
        "display_mode": display_mode,
        "bots": sorted(bots or []),
        "advertising_companies": sorted(advertising_companies or []),
        "utm_source": sorted(utm_source or []),
        "utm_campaign": sorted(utm_campaign or []),
        "utm_medium": sorted(utm_medium or []),
        "utm_content": sorted(utm_content or []),
        "utm_term": sorted(utm_term or []),
    }
    cache_suffix = json.dumps(cache_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    cache_key = f"reports:roistat_weekly:companies:v21:{cache_suffix}"
    stale_key = f"{cache_key}:stale"
    lock_key = f"{cache_key}:lock"

    cached_map = await cache.get_json_many([cache_key, stale_key])
    cached = cached_map.get(cache_key)
    if cached is not None:
        return cached

    stale = cached_map.get(stale_key)
    if stale is not None:
        await cache.set_json(cache_key, stale, ttl=min(settings.weekly_cache_ttl_seconds, 300))
        return stale

    normalized_company_sql = """
        CASE
            WHEN advertising_company IS NULL
              OR BTRIM(advertising_company) = ''
              OR LOWER(BTRIM(advertising_company)) IN ('-', '—', '(none)', 'none', 'null', 'нет метки')
            THEN 'Без категории'
            ELSE BTRIM(advertising_company)
        END
    """

    # Resolve cohort date bounds
    ft_start = first_touch_start or event_start
    ft_end = first_touch_end or event_end

    params: dict[str, Any] = {
        "start": event_start,
        "end": event_end,
        "ft_start": ft_start,
        "ft_end": ft_end,
        "channel_id": os.environ.get("TELEGRAM_CHANNEL_ID"),
        "community_id": os.environ.get("TELEGRAM_COMMUNITY_ID"),
        "excluded_bot_keys": normalized_excluded_bot_keys(),
    }

    def _normalize_filter_values(values: Optional[List[str]]) -> list[str]:
        if not values:
            return []
        return [value.strip().lower() for value in values if isinstance(value, str) and value.strip()]

    def build_row_filters(alias: str) -> str:
        conditions: list[str] = []
        normalized_company_expr = normalized_company_sql.replace("advertising_company", f"{alias}.advertising_company")
        if bots:
            conditions.append(f"{alias}.bot_key = ANY(:filter_bots)")
            params["filter_bots"] = bots
        if advertising_companies:
            conditions.append(f"{normalized_company_expr} = ANY(:filter_advertising_companies)")
            params["filter_advertising_companies"] = advertising_companies
        normalized_utm_campaign = _normalize_filter_values(utm_campaign)
        if normalized_utm_campaign:
            conditions.append(
                f"""(
                    LOWER(TRIM(COALESCE({alias}.utm_campaign, ''))) = ANY(:filter_utm_campaign)
                    OR LOWER(TRIM(COALESCE({alias}.platform_utm_campaign, ''))) = ANY(:filter_utm_campaign)
                )"""
            )
            params["filter_utm_campaign"] = normalized_utm_campaign
        normalized_utm_source = _normalize_filter_values(utm_source)
        if normalized_utm_source:
            conditions.append(
                f"""(
                    LOWER(TRIM(COALESCE({alias}.utm_source, ''))) = ANY(:filter_utm_source)
                    OR LOWER(TRIM(COALESCE({alias}.platform_utm_source, ''))) = ANY(:filter_utm_source)
                )"""
            )
            params["filter_utm_source"] = normalized_utm_source
        normalized_utm_medium = _normalize_filter_values(utm_medium)
        if normalized_utm_medium:
            conditions.append(
                f"""(
                    LOWER(TRIM(COALESCE({alias}.utm_medium, ''))) = ANY(:filter_utm_medium)
                    OR LOWER(TRIM(COALESCE({alias}.platform_utm_medium, ''))) = ANY(:filter_utm_medium)
                )"""
            )
            params["filter_utm_medium"] = normalized_utm_medium
        normalized_utm_content = _normalize_filter_values(utm_content)
        if normalized_utm_content:
            conditions.append(
                f"""(
                    LOWER(TRIM(COALESCE({alias}.utm_content, ''))) = ANY(:filter_utm_content)
                    OR LOWER(TRIM(COALESCE({alias}.platform_utm_content, ''))) = ANY(:filter_utm_content)
                )"""
            )
            params["filter_utm_content"] = normalized_utm_content
        normalized_utm_term = _normalize_filter_values(utm_term)
        if normalized_utm_term:
            conditions.append(
                f"""(
                    LOWER(TRIM(COALESCE({alias}.utm_term, ''))) = ANY(:filter_utm_term)
                    OR LOWER(TRIM(COALESCE({alias}.platform_utm_term, ''))) = ANY(:filter_utm_term)
                )"""
            )
            params["filter_utm_term"] = normalized_utm_term
        return "".join(f"\n              AND {condition}" for condition in conditions)

    utm_filter_sql = build_row_filters("r")
    cohort_filter_sql = build_row_filters("raw_bot_users")
    utm_users_filter_sql = build_row_filters("u")

    has_utm_filter = bool(
        _normalize_filter_values(utm_source)
        or _normalize_filter_values(utm_campaign)
        or _normalize_filter_values(utm_medium)
        or _normalize_filter_values(utm_content)
        or _normalize_filter_values(utm_term)
    )
    # In cohort mode, UTM params live on advertising/source records, not on lead
    # records. Pre-select user IDs that have any record matching the UTM filter,
    # then join against lead_rows instead of filtering lead_rows directly.
    if has_utm_filter:
        cohort_utm_users_cte = f"""
        utm_users AS (
            SELECT DISTINCT u.tg_user_id
            FROM raw_bot_users u
            WHERE u.created_at IS NOT NULL
              AND LOWER(TRIM(COALESCE(u.bot_key, ''))) <> ALL(:excluded_bot_keys)
              {utm_users_filter_sql}
        ),"""
        cohort_lead_utm_filter = "\n              AND r.tg_user_id IN (SELECT tg_user_id FROM utm_users)"
    else:
        cohort_utm_users_cte = ""
        cohort_lead_utm_filter = ""

    budget_filter_sql = ""
    if advertising_companies:
        budget_filter_sql += "\n                AND CASE\n                    WHEN campaign IS NULL\n                      OR BTRIM(campaign) = ''\n                      OR LOWER(BTRIM(campaign)) IN ('-', '—', '(none)', 'none', 'null', 'нет метки')\n                    THEN 'Без категории'\n                    ELSE BTRIM(campaign)\n                END = ANY(:filter_advertising_companies)"
    if bots:
        budget_filter_sql += "\n                AND COALESCE(NULLIF(BTRIM(bot_key), ''), 'Без бота') = ANY(:filter_bots)"

    # Build cohort filter CTE based on mode
    if mode == "first_touch":
        cohort_cte = f"""
        cohort AS (
            SELECT tg_user_id FROM raw_bot_users
            WHERE bot_key LIKE 'lead%'
              AND tg_user_id > 0
              AND LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND created_at IS NOT NULL
              {cohort_filter_sql}
            GROUP BY tg_user_id
            HAVING (CAST(:ft_start AS date) IS NULL OR MIN(created_at)::date >= CAST(:ft_start AS date))
               AND (CAST(:ft_end AS date) IS NULL OR MIN(created_at)::date <= CAST(:ft_end AS date))
        ),"""
    elif mode == "last_touch":
        cohort_cte = f"""
        cohort AS (
            SELECT tg_user_id FROM raw_bot_users
            WHERE bot_key LIKE 'lead%'
              AND tg_user_id > 0
              AND LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND created_at IS NOT NULL
              {cohort_filter_sql}
            GROUP BY tg_user_id
            HAVING (CAST(:ft_start AS date) IS NULL OR MAX(created_at)::date >= CAST(:ft_start AS date))
               AND (CAST(:ft_end AS date) IS NULL OR MAX(created_at)::date <= CAST(:ft_end AS date))
        ),"""
    else:
        cohort_cte = ""

    cohort_join = "JOIN cohort c ON c.tg_user_id = r.tg_user_id" if mode in ("first_touch", "last_touch") else ""
    event_date_filter = "" if mode in ("first_touch", "last_touch") else """
              AND (CAST(:start AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date))"""
    cohort_all_starts_join = "JOIN cohort c ON c.tg_user_id = r.tg_user_id" if mode in ("first_touch", "last_touch") else ""

    company_sql = normalized_company_sql.replace("advertising_company", "r.advertising_company")
    lc_company_sql = normalized_company_sql.replace("advertising_company", "r.advertising_company")
    source_touch_filter_sql = build_row_filters("src")

    if display_mode == "weekly":
        query = sa_text(f"""
        WITH first_seen AS (
            SELECT tg_user_id, MIN(created_at) AS first_seen_at_system
            FROM raw_bot_users
            WHERE LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY tg_user_id
        ),
        {cohort_cte}
        start_rows AS (
            SELECT DISTINCT ON (r.tg_user_id, COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота'))
                r.tg_user_id,
                {lc_company_sql} AS company,
                COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS bot_key,
                (r.created_at AT TIME ZONE 'Europe/Moscow')::date AS start_date,
                date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                fs.first_seen_at_system
            FROM raw_bot_users r
            JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
            {cohort_join}
            WHERE LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date)){utm_filter_sql}
            ORDER BY r.tg_user_id, COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота'), r.created_at
        ),
        entered_company_metrics AS (
            SELECT
                sr.week_start,
                sr.company,
                COUNT(DISTINCT sr.tg_user_id) AS entered_all
            FROM start_rows sr
            GROUP BY sr.week_start, sr.company
        ),
        lead_rows AS (
            SELECT DISTINCT ON (r.tg_user_id)
                r.tg_user_id,
                {lc_company_sql} AS lead_company,
                COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS lead_bot_key,
                r.created_at AS lead_created_at,
                (r.created_at AT TIME ZONE 'Europe/Moscow')::date AS lead_date,
                date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                fs.first_seen_at_system
            FROM raw_bot_users r
            JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
            WHERE r.tg_user_id IN (SELECT tg_user_id FROM start_rows)
              AND lower(trim(COALESCE(r.bot_key, ''))) LIKE 'lead%'
              AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL
            ORDER BY r.tg_user_id, r.created_at
        ),
        attributed_leads AS (
            SELECT
                lr.tg_user_id,
                lr.week_start,
                lr.lead_date,
                lr.first_seen_at_system,
                COALESCE(src.company, lr.lead_company) AS company,
                COALESCE(src.bot_key, lr.lead_bot_key) AS bot_key
            FROM lead_rows lr
            LEFT JOIN LATERAL (
                SELECT
                    {normalized_company_sql.replace("advertising_company", "src.advertising_company")} AS company,
                    COALESCE(NULLIF(BTRIM(src.bot_key), ''), 'Без бота') AS bot_key
                FROM raw_bot_users src
                WHERE src.tg_user_id = lr.tg_user_id
                  AND LOWER(TRIM(COALESCE(src.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND lower(trim(COALESCE(src.bot_key, ''))) NOT LIKE 'lead%'
                  AND src.created_at IS NOT NULL
                  AND src.created_at <= lr.lead_created_at{source_touch_filter_sql}
                ORDER BY src.created_at DESC
                LIMIT 1
            ) src ON TRUE
        ),
        user_flags AS (
            SELECT
                ru.tg_user_id,
                BOOL_OR(ru.converted_to_lead IS TRUE OR lower(trim(COALESCE(ru.bot_key, ''))) LIKE 'lead%') AS did_lead,
                BOOL_OR(ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL) AS did_platform,
                MIN((ru.platform_registered_at AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                    WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
                ) AS first_platform_date,
                MIN(ru.ph_user_id) FILTER (
                    WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
                ) AS ph_user_id,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND (
                              lesson.value LIKE 'Базовый курс:%'
                              OR lesson.value LIKE 'MTT1:%'
                              OR lesson.value LIKE 'MTT2:%'
                              OR lesson.value LIKE 'SPIN1:%'
                              OR lesson.value LIKE 'CASH1:%'
                          )
                    )
                ) AS did_course_registration,
                BOOL_OR(ru.started_learning IS TRUE OR ru.learn_start_date IS NOT NULL) AS did_learning,
                BOOL_OR(ru.completed_course IS TRUE AND ru.completed_course_at IS NOT NULL) AS did_complete,
                BOOL_OR(ru.interview_reached IS TRUE) AS did_interview,
                BOOL_OR(ru.offer_received IS TRUE) AS did_offer,
                BOOL_OR(ru.contract_signed IS TRUE) AS did_contract,
                BOOL_OR(ru.distance_grinding IS TRUE) AS did_distance,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND (lesson.value LIKE 'MTT1:%' OR lesson.value LIKE 'MTT2:%')
                    )
                ) AS is_mtt,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND lesson.value LIKE 'SPIN1:%'
                    )
                ) AS is_spin,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND lesson.value LIKE 'CASH1:%'
                    )
                ) AS is_cash,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND lesson.value LIKE 'Базовый курс:%'
                    )
                ) AS is_base,
                BOOL_OR(
                    lower(trim(COALESCE(ru.bot_key, ''))) LIKE 'lead%'
                    AND ru.tg_user_id > 0
                    AND ru.ph_user_id IS NOT NULL
                    AND abs(ru.tg_user_id) = ru.ph_user_id
                ) AS is_direct_source,
                COALESCE(sf.did_channel, FALSE) AS did_channel,
                COALESCE(sf.did_saloon, FALSE) AS did_saloon
            FROM raw_bot_users ru
            LEFT JOIN (
                SELECT
                    tg_user_id,
                    BOOL_OR(status = 'subscribed' AND channel_id = :channel_id) AS did_channel,
                    BOOL_OR(status = 'subscribed' AND channel_id = :community_id) AS did_saloon
                FROM telegram_subscription_events
                GROUP BY tg_user_id
            ) sf ON sf.tg_user_id = ru.tg_user_id
            WHERE ru.tg_user_id IN (SELECT tg_user_id FROM attributed_leads)
              AND LOWER(TRIM(COALESCE(ru.bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY ru.tg_user_id, sf.did_channel, sf.did_saloon
        ),
        company_metrics AS (
            SELECT
                al.week_start,
                al.company,
                COUNT(DISTINCT CASE WHEN al.tg_user_id > 0 AND NOT uf.is_direct_source THEN al.tg_user_id END) AS almanah_starts,
                COUNT(DISTINCT CASE WHEN uf.is_direct_source AND uf.ph_user_id IS NOT NULL THEN uf.ph_user_id END) AS direct_source_cnt,
                COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date = al.lead_date THEN al.tg_user_id END) AS new_in_system,
                COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date < al.lead_date THEN al.tg_user_id END) AS old_in_system,
                COUNT(
                    DISTINCT CASE
                        WHEN NOT uf.is_direct_source
                         AND uf.ph_user_id IS NOT NULL
                         AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date
                        THEN uf.ph_user_id
                    END
                ) AS platform_cnt,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_course_registration THEN uf.ph_user_id END) AS learning,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning THEN uf.ph_user_id END) AS started_learning,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.is_mtt THEN uf.ph_user_id END) AS mtt,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.is_spin THEN uf.ph_user_id END) AS spin,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.is_cash THEN uf.ph_user_id END) AS cash,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.is_base THEN uf.ph_user_id END) AS base,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND NOT uf.did_learning THEN uf.ph_user_id END) AS not_started,
                COUNT(DISTINCT CASE WHEN uf.did_channel THEN al.tg_user_id END) AS channel_subscribed,
                COUNT(DISTINCT CASE WHEN uf.did_saloon THEN al.tg_user_id END) AS saloon,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete THEN uf.ph_user_id END) AS completed_course,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.is_mtt THEN uf.ph_user_id END) AS completed_mtt,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.is_spin THEN uf.ph_user_id END) AS completed_spin,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.is_cash THEN uf.ph_user_id END) AS completed_cash,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.is_base THEN uf.ph_user_id END) AS completed_base,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview THEN uf.ph_user_id END) AS interview_reached,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer THEN uf.ph_user_id END) AS offer_received,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract THEN uf.ph_user_id END) AS contract_signed,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract AND uf.is_mtt THEN uf.ph_user_id END) AS contract_mtt,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract AND uf.is_spin THEN uf.ph_user_id END) AS contract_spin,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract AND uf.is_cash THEN uf.ph_user_id END) AS contract_cash,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_distance THEN uf.ph_user_id END) AS distance_grinding
            FROM attributed_leads al
            JOIN user_flags uf ON uf.tg_user_id = al.tg_user_id
            GROUP BY al.week_start, al.company
        ),
        budgets AS (
            SELECT
                DATE_TRUNC('week', week_start)::date AS week_start,
                CASE
                    WHEN campaign IS NULL
                      OR BTRIM(campaign) = ''
                      OR LOWER(BTRIM(campaign)) IN ('-', '—', '(none)', 'none', 'null', 'нет метки')
                    THEN 'Без категории'
                    ELSE BTRIM(campaign)
                END AS company,
                SUM(amount) AS budget
            FROM budget_weekly
            WHERE
                (CAST(:start AS date) IS NULL OR week_start::date >= CAST(:start AS date))
                AND (CAST(:end AS date) IS NULL OR week_start::date <= CAST(:end AS date))
                {budget_filter_sql}
            GROUP BY 1, 2
        ),
        company_weeks AS (
            SELECT week_start, company FROM company_metrics
            UNION SELECT week_start, company FROM budgets
        )
        SELECT
            cw.week_start,
            cw.company,
            COALESCE(ecm.entered_all, 0) AS entered_all,
            COALESCE(b.budget, 0.0) AS budget,
            COALESCE(cm.almanah_starts, 0) AS almanah_starts,
            COALESCE(cm.direct_source_cnt, 0) AS direct_source_cnt,
            COALESCE(cm.new_in_system, 0) AS new_in_system,
            COALESCE(cm.old_in_system, 0) AS old_in_system,
            COALESCE(cm.platform_cnt, 0) AS platform_cnt,
            COALESCE(cm.learning, 0) AS learning,
            COALESCE(cm.started_learning, 0) AS started_learning,
            COALESCE(cm.mtt, 0) AS mtt,
            COALESCE(cm.spin, 0) AS spin,
            COALESCE(cm.cash, 0) AS cash,
            COALESCE(cm.base, 0) AS base,
            COALESCE(cm.not_started, 0) AS not_started,
            COALESCE(cm.channel_subscribed, 0) AS channel_subscribed,
            COALESCE(cm.saloon, 0) AS saloon,
            COALESCE(cm.completed_course, 0) AS completed_course,
            COALESCE(cm.completed_mtt, 0) AS completed_mtt,
            COALESCE(cm.completed_spin, 0) AS completed_spin,
            COALESCE(cm.completed_cash, 0) AS completed_cash,
            COALESCE(cm.completed_base, 0) AS completed_base,
            COALESCE(cm.interview_reached, 0) AS interview_reached,
            COALESCE(cm.offer_received, 0) AS offer_received,
            COALESCE(cm.contract_signed, 0) AS contract_signed,
            COALESCE(cm.contract_mtt, 0) AS contract_mtt,
            COALESCE(cm.contract_spin, 0) AS contract_spin,
            COALESCE(cm.contract_cash, 0) AS contract_cash,
            COALESCE(cm.distance_grinding, 0) AS distance_grinding
        FROM company_weeks cw
        LEFT JOIN company_metrics cm ON cm.week_start = cw.week_start AND cm.company = cw.company
        LEFT JOIN entered_company_metrics ecm ON ecm.week_start = cw.week_start AND ecm.company = cw.company
        LEFT JOIN budgets b ON b.week_start = cw.week_start AND b.company = cw.company
        ORDER BY cw.week_start DESC, COALESCE(cm.almanah_starts, 0) DESC, cw.company
    """)
    else:
        query = sa_text(f"""
        WITH first_seen AS (
            SELECT tg_user_id, MIN(created_at) AS first_seen_at_system
            FROM raw_bot_users
            WHERE LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY tg_user_id
        ),
        {cohort_cte}
        {cohort_utm_users_cte}
        lead_rows AS (
            SELECT DISTINCT ON (r.tg_user_id)
                r.tg_user_id,
                {normalized_company_sql.replace("advertising_company", "r.advertising_company")} AS lead_company,
                COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS lead_bot_key,
                r.created_at AS lead_created_at,
                (r.created_at AT TIME ZONE 'Europe/Moscow')::date AS lead_date,
                date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                fs.first_seen_at_system
            FROM raw_bot_users r
            JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
            {cohort_join}
            WHERE lower(trim(r.bot_key)) LIKE 'lead%'
              AND r.tg_user_id > 0
              AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL{event_date_filter}{cohort_lead_utm_filter}
            ORDER BY r.tg_user_id, r.created_at
        ),
        attributed_leads AS (
            SELECT
                lr.tg_user_id,
                lr.week_start,
                lr.lead_date,
                lr.first_seen_at_system,
                COALESCE(src.company, lr.lead_company) AS company,
                COALESCE(src.bot_key, lr.lead_bot_key) AS bot_key
            FROM lead_rows lr
            LEFT JOIN LATERAL (
                SELECT
                    {normalized_company_sql.replace("advertising_company", "src.advertising_company")} AS company,
                    COALESCE(NULLIF(BTRIM(src.bot_key), ''), 'Без бота') AS bot_key
                FROM raw_bot_users src
                WHERE src.tg_user_id = lr.tg_user_id
                  AND LOWER(TRIM(COALESCE(src.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND lower(trim(COALESCE(src.bot_key, ''))) NOT LIKE 'lead%'
                  AND src.created_at IS NOT NULL
                  AND src.created_at <= lr.lead_created_at{source_touch_filter_sql}
                ORDER BY src.created_at DESC
                LIMIT 1
            ) src ON TRUE
        ),
        user_flags AS (
            SELECT
                ru.tg_user_id,
                BOOL_OR(ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL) AS did_platform,
                MIN((ru.platform_registered_at AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                    WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
                ) AS first_platform_date,
                MIN(ru.ph_user_id) FILTER (
                    WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
                ) AS ph_user_id,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND (
                              lesson.value LIKE 'Базовый курс:%'
                              OR lesson.value LIKE 'MTT1:%'
                              OR lesson.value LIKE 'MTT2:%'
                              OR lesson.value LIKE 'SPIN1:%'
                              OR lesson.value LIKE 'CASH1:%'
                          )
                    )
                ) AS did_course_registration,
                BOOL_OR(ru.learn_start_date IS NOT NULL) AS did_learning,
                BOOL_OR(ru.completed_course IS TRUE AND ru.completed_course_at IS NOT NULL) AS did_complete,
                BOOL_OR(ru.interview_reached IS TRUE) AS did_interview,
                BOOL_OR(ru.offer_received IS TRUE) AS did_offer,
                BOOL_OR(ru.contract_signed IS TRUE) AS did_contract,
                BOOL_OR(ru.distance_grinding IS TRUE) AS did_distance,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND (lesson.value LIKE 'MTT1:%' OR lesson.value LIKE 'MTT2:%')
                    )
                ) AS is_mtt,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND lesson.value LIKE 'SPIN1:%'
                    )
                ) AS is_spin,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND lesson.value LIKE 'CASH1:%'
                    )
                ) AS is_cash,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND lesson.value LIKE 'Базовый курс:%'
                    )
                ) AS is_base,
                MIN((
                    SELECT MIN((((regexp_match(lesson.value, '\(([^()]+)\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FROM ph_user_mirror_replica pm
                    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                    WHERE pm.ph_id = ru.ph_user_id::text
                      AND lesson.value LIKE 'Базовый курс:%'
                )) AS first_base_lesson_date,
                MIN((
                    SELECT MIN((((regexp_match(lesson.value, '\(([^()]+)\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FROM ph_user_mirror_replica pm
                    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                    WHERE pm.ph_id = ru.ph_user_id::text
                      AND (lesson.value LIKE 'MTT1:%' OR lesson.value LIKE 'MTT2:%')
                )) AS first_mtt_lesson_date,
                MIN((
                    SELECT MIN((((regexp_match(lesson.value, '\(([^()]+)\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FROM ph_user_mirror_replica pm
                    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                    WHERE pm.ph_id = ru.ph_user_id::text
                      AND lesson.value LIKE 'SPIN1:%'
                )) AS first_spin_lesson_date,
                MIN((
                    SELECT MIN((((regexp_match(lesson.value, '\(([^()]+)\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FROM ph_user_mirror_replica pm
                    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                    WHERE pm.ph_id = ru.ph_user_id::text
                      AND lesson.value LIKE 'CASH1:%'
                )) AS first_cash_lesson_date,
                BOOL_OR(
                    lower(trim(COALESCE(ru.bot_key, ''))) LIKE 'lead%'
                    AND ru.tg_user_id > 0
                    AND ru.ph_user_id IS NOT NULL
                    AND abs(ru.tg_user_id) = ru.ph_user_id
                ) AS is_direct_source,
                COALESCE(sf.did_channel, FALSE) AS did_channel,
                COALESCE(sf.did_saloon, FALSE) AS did_saloon
            FROM raw_bot_users ru
            LEFT JOIN (
                SELECT
                    tg_user_id,
                    BOOL_OR(status = 'subscribed' AND channel_id = :channel_id) AS did_channel,
                    BOOL_OR(status = 'subscribed' AND channel_id = :community_id) AS did_saloon
                FROM telegram_subscription_events
                GROUP BY tg_user_id
            ) sf ON sf.tg_user_id = ru.tg_user_id
            WHERE ru.tg_user_id IN (SELECT tg_user_id FROM attributed_leads)
              AND LOWER(TRIM(COALESCE(ru.bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY ru.tg_user_id, sf.did_channel, sf.did_saloon
        ),
        lead_metrics AS (
            SELECT
                al.week_start,
                al.company,
                COUNT(DISTINCT CASE WHEN al.tg_user_id > 0 AND NOT uf.is_direct_source THEN al.tg_user_id END) AS almanah_starts,
                COUNT(DISTINCT CASE WHEN uf.is_direct_source AND uf.ph_user_id IS NOT NULL THEN uf.ph_user_id END) AS direct_source_cnt,
                COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date = al.lead_date THEN al.tg_user_id END) AS new_in_system,
                COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date < al.lead_date THEN al.tg_user_id END) AS old_in_system,
                COUNT(
                    DISTINCT CASE
                        WHEN NOT uf.is_direct_source
                         AND uf.ph_user_id IS NOT NULL
                         AND uf.did_platform
                        THEN uf.ph_user_id
                    END
                ) AS platform_cnt,
                COUNT(DISTINCT CASE WHEN uf.did_course_registration THEN al.tg_user_id END) AS learning,
                COUNT(DISTINCT CASE WHEN uf.did_learning THEN al.tg_user_id END) AS started_learning,
                COUNT(DISTINCT CASE WHEN uf.is_mtt THEN al.tg_user_id END) AS mtt,
                COUNT(DISTINCT CASE WHEN uf.is_spin THEN al.tg_user_id END) AS spin,
                COUNT(DISTINCT CASE WHEN uf.is_cash THEN al.tg_user_id END) AS cash,
                COUNT(DISTINCT CASE WHEN uf.is_base THEN al.tg_user_id END) AS base,
                COUNT(DISTINCT CASE WHEN uf.did_platform AND NOT uf.did_learning THEN al.tg_user_id END) AS not_started,
                COUNT(DISTINCT CASE WHEN uf.did_channel THEN al.tg_user_id END) AS channel_subscribed,
                COUNT(DISTINCT CASE WHEN uf.did_saloon THEN al.tg_user_id END) AS saloon,
                COUNT(DISTINCT CASE WHEN uf.did_complete THEN al.tg_user_id END) AS completed_course,
                COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_mtt THEN al.tg_user_id END) AS completed_mtt,
                COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_spin THEN al.tg_user_id END) AS completed_spin,
                COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_cash THEN al.tg_user_id END) AS completed_cash,
                COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_base THEN al.tg_user_id END) AS completed_base,
                COUNT(DISTINCT CASE WHEN uf.did_interview THEN al.tg_user_id END) AS interview_reached,
                COUNT(DISTINCT CASE WHEN uf.did_offer THEN al.tg_user_id END) AS offer_received,
                COUNT(DISTINCT CASE WHEN uf.did_contract THEN al.tg_user_id END) AS contract_signed,
                COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_mtt THEN al.tg_user_id END) AS contract_mtt,
                COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_spin THEN al.tg_user_id END) AS contract_spin,
                COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_cash THEN al.tg_user_id END) AS contract_cash,
                COUNT(DISTINCT CASE WHEN uf.did_distance THEN al.tg_user_id END) AS distance_grinding
            FROM attributed_leads al
            JOIN user_flags uf ON uf.tg_user_id = al.tg_user_id
            GROUP BY al.week_start, al.company
        ),
        lead_metrics_bot AS (
            SELECT
                al.week_start,
                al.company,
                al.bot_key,
                COUNT(DISTINCT CASE WHEN al.tg_user_id > 0 AND NOT uf.is_direct_source THEN al.tg_user_id END) AS almanah_starts,
                COUNT(DISTINCT CASE WHEN uf.is_direct_source AND uf.ph_user_id IS NOT NULL THEN uf.ph_user_id END) AS direct_source_cnt,
                COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date = al.lead_date THEN al.tg_user_id END) AS new_in_system,
                COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date < al.lead_date THEN al.tg_user_id END) AS old_in_system,
                COUNT(
                    DISTINCT CASE
                        WHEN NOT uf.is_direct_source
                         AND uf.ph_user_id IS NOT NULL
                         AND uf.did_platform
                        THEN uf.ph_user_id
                    END
                ) AS platform_cnt,
                COUNT(DISTINCT CASE WHEN uf.did_course_registration THEN al.tg_user_id END) AS learning,
                COUNT(DISTINCT CASE WHEN uf.did_learning THEN al.tg_user_id END) AS started_learning,
                COUNT(DISTINCT CASE WHEN uf.is_mtt THEN al.tg_user_id END) AS mtt,
                COUNT(DISTINCT CASE WHEN uf.is_spin THEN al.tg_user_id END) AS spin,
                COUNT(DISTINCT CASE WHEN uf.is_cash THEN al.tg_user_id END) AS cash,
                COUNT(DISTINCT CASE WHEN uf.is_base THEN al.tg_user_id END) AS base,
                COUNT(DISTINCT CASE WHEN uf.did_platform AND NOT uf.did_learning THEN al.tg_user_id END) AS not_started,
                COUNT(DISTINCT CASE WHEN uf.did_channel THEN al.tg_user_id END) AS channel_subscribed,
                COUNT(DISTINCT CASE WHEN uf.did_saloon THEN al.tg_user_id END) AS saloon,
                COUNT(DISTINCT CASE WHEN uf.did_complete THEN al.tg_user_id END) AS completed_course,
                COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_mtt THEN al.tg_user_id END) AS completed_mtt,
                COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_spin THEN al.tg_user_id END) AS completed_spin,
                COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_cash THEN al.tg_user_id END) AS completed_cash,
                COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_base THEN al.tg_user_id END) AS completed_base,
                COUNT(DISTINCT CASE WHEN uf.did_interview THEN al.tg_user_id END) AS interview_reached,
                COUNT(DISTINCT CASE WHEN uf.did_offer THEN al.tg_user_id END) AS offer_received,
                COUNT(DISTINCT CASE WHEN uf.did_contract THEN al.tg_user_id END) AS contract_signed,
                COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_mtt THEN al.tg_user_id END) AS contract_mtt,
                COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_spin THEN al.tg_user_id END) AS contract_spin,
                COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_cash THEN al.tg_user_id END) AS contract_cash,
                COUNT(DISTINCT CASE WHEN uf.did_distance THEN al.tg_user_id END) AS distance_grinding
            FROM attributed_leads al
            JOIN user_flags uf ON uf.tg_user_id = al.tg_user_id
            GROUP BY al.week_start, al.company, al.bot_key
        ),
        all_starts AS (
            -- All bot starts (not just lead bots) attributed to company by week.
            -- In touch modes we keep only users from the selected cohort.
            SELECT
                date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                {normalized_company_sql.replace("advertising_company", "r.advertising_company")} AS company,
                COUNT(DISTINCT r.tg_user_id) AS entered_all
            FROM raw_bot_users r
            {cohort_all_starts_join}
            WHERE LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date)){utm_filter_sql}
            GROUP BY 1, 2
        ),
        all_starts_bot AS (
            SELECT
                date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                {normalized_company_sql.replace("advertising_company", "r.advertising_company")} AS company,
                COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS bot_key,
                COUNT(DISTINCT r.tg_user_id) AS entered_all
            FROM raw_bot_users r
            {cohort_all_starts_join}
            WHERE LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date)){utm_filter_sql}
            GROUP BY 1, 2, 3
        ),
        budgets AS (
            -- Budget from budget_weekly table, campaign maps to advertising_company.
            SELECT
                DATE_TRUNC('week', week_start)::date AS week_start,
                CASE
                    WHEN campaign IS NULL
                      OR BTRIM(campaign) = ''
                      OR LOWER(BTRIM(campaign)) IN ('-', '—', '(none)', 'none', 'null', 'нет метки')
                    THEN 'Без категории'
                    ELSE BTRIM(campaign)
                END AS company,
                SUM(amount) AS budget
            FROM budget_weekly
            WHERE
                (CAST(:start AS date) IS NULL OR week_start::date >= CAST(:start AS date))
                AND (CAST(:end AS date) IS NULL OR week_start::date <= CAST(:end AS date))
                {budget_filter_sql}
            GROUP BY 1, 2
        ),
        budgets_bot AS (
            SELECT
                DATE_TRUNC('week', week_start)::date AS week_start,
                CASE
                    WHEN campaign IS NULL
                      OR BTRIM(campaign) = ''
                      OR LOWER(BTRIM(campaign)) IN ('-', '—', '(none)', 'none', 'null', 'нет метки')
                    THEN 'Без категории'
                    ELSE BTRIM(campaign)
                END AS company,
                COALESCE(NULLIF(BTRIM(bot_key), ''), 'Без бота') AS bot_key,
                SUM(amount) AS budget
            FROM budget_weekly
            WHERE
                (CAST(:start AS date) IS NULL OR week_start::date >= CAST(:start AS date))
                AND (CAST(:end AS date) IS NULL OR week_start::date <= CAST(:end AS date))
            GROUP BY 1, 2, 3
        ),
        company_weeks AS (
            SELECT week_start, company FROM lead_metrics
            UNION
            SELECT week_start, company FROM all_starts
            UNION
            SELECT week_start, company FROM budgets
        ),
        bot_weeks AS (
            SELECT week_start, company, bot_key FROM lead_metrics_bot
            UNION
            SELECT week_start, company, bot_key FROM all_starts_bot
            UNION
            SELECT week_start, company, bot_key FROM budgets_bot
        )
        SELECT
            cw.week_start,
            cw.company,
            COALESCE(s.entered_all, 0) AS entered_all,
            COALESCE(b.budget, 0.0) AS budget,
            COALESCE(lm.almanah_starts, 0) AS almanah_starts,
            COALESCE(lm.direct_source_cnt, 0) AS direct_source_cnt,
            COALESCE(lm.new_in_system, 0) AS new_in_system,
            COALESCE(lm.old_in_system, 0) AS old_in_system,
            COALESCE(lm.platform_cnt, 0) AS platform_cnt,
            COALESCE(lm.learning, 0) AS learning,
            COALESCE(lm.started_learning, 0) AS started_learning,
            COALESCE(lm.mtt, 0) AS mtt,
            COALESCE(lm.spin, 0) AS spin,
            COALESCE(lm.cash, 0) AS cash,
            COALESCE(lm.base, 0) AS base,
            COALESCE(lm.not_started, 0) AS not_started,
            COALESCE(lm.channel_subscribed, 0) AS channel_subscribed,
            COALESCE(lm.saloon, 0) AS saloon,
            COALESCE(lm.completed_course, 0) AS completed_course,
            COALESCE(lm.completed_mtt, 0) AS completed_mtt,
            COALESCE(lm.completed_spin, 0) AS completed_spin,
            COALESCE(lm.completed_cash, 0) AS completed_cash,
            COALESCE(lm.completed_base, 0) AS completed_base,
            COALESCE(lm.interview_reached, 0) AS interview_reached,
            COALESCE(lm.offer_received, 0) AS offer_received,
            COALESCE(lm.contract_signed, 0) AS contract_signed,
            COALESCE(lm.contract_mtt, 0) AS contract_mtt,
            COALESCE(lm.contract_spin, 0) AS contract_spin,
            COALESCE(lm.contract_cash, 0) AS contract_cash,
            COALESCE(lm.distance_grinding, 0) AS distance_grinding
        FROM company_weeks cw
        LEFT JOIN lead_metrics lm ON lm.week_start = cw.week_start AND lm.company = cw.company
        LEFT JOIN all_starts s ON s.week_start = cw.week_start AND s.company = cw.company
        LEFT JOIN budgets b ON b.week_start = cw.week_start AND b.company = cw.company
        ORDER BY cw.week_start DESC, COALESCE(lm.almanah_starts, 0) DESC, cw.company
    """)
    result = await session.execute(query, params)
    db_rows = result.fetchall()
    db_week_totals_rows = []

    if display_mode == "weekly":
        week_totals_query = sa_text(f"""
        WITH first_seen AS (
            SELECT tg_user_id, MIN(created_at) AS first_seen_at_system
            FROM raw_bot_users
            WHERE LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY tg_user_id
        ),
        {cohort_cte}
        start_rows AS (
            SELECT DISTINCT ON (r.tg_user_id, COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота'))
                r.tg_user_id,
                COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS bot_key,
                (r.created_at AT TIME ZONE 'Europe/Moscow')::date AS start_date,
                date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                fs.first_seen_at_system
            FROM raw_bot_users r
            JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
            {cohort_join}
            WHERE LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date)){utm_filter_sql}
            ORDER BY r.tg_user_id, COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота'), r.created_at
        ),
        entered_week_metrics AS (
            SELECT
                sr.week_start,
                COUNT(DISTINCT sr.tg_user_id) AS entered_all
            FROM start_rows sr
            GROUP BY sr.week_start
        ),
        lead_rows AS (
            SELECT DISTINCT ON (r.tg_user_id)
                r.tg_user_id,
                r.created_at AS lead_created_at,
                (r.created_at AT TIME ZONE 'Europe/Moscow')::date AS lead_date,
                date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                fs.first_seen_at_system
            FROM raw_bot_users r
            JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
            WHERE r.tg_user_id IN (SELECT tg_user_id FROM start_rows)
              AND lower(trim(COALESCE(r.bot_key, ''))) LIKE 'lead%'
              AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL
            ORDER BY r.tg_user_id, r.created_at
        ),
        attributed_leads AS (
            SELECT
                lr.tg_user_id,
                lr.week_start,
                lr.lead_date,
                lr.first_seen_at_system
            FROM lead_rows lr
        ),
        user_flags AS (
            SELECT
                ru.tg_user_id,
                BOOL_OR(ru.converted_to_lead IS TRUE OR lower(trim(COALESCE(ru.bot_key, ''))) LIKE 'lead%') AS did_lead,
                BOOL_OR(ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL) AS did_platform,
                MIN((ru.platform_registered_at AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                    WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
                ) AS first_platform_date,
                MIN(ru.ph_user_id) FILTER (
                    WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
                ) AS ph_user_id,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND (
                              lesson.value LIKE 'Базовый курс:%'
                              OR lesson.value LIKE 'MTT1:%'
                              OR lesson.value LIKE 'MTT2:%'
                              OR lesson.value LIKE 'SPIN1:%'
                              OR lesson.value LIKE 'CASH1:%'
                          )
                    )
                ) AS did_course_registration,
                BOOL_OR(ru.started_learning IS TRUE OR ru.learn_start_date IS NOT NULL) AS did_learning,
                BOOL_OR(ru.completed_course IS TRUE AND ru.completed_course_at IS NOT NULL) AS did_complete,
                BOOL_OR(ru.interview_reached IS TRUE) AS did_interview,
                BOOL_OR(ru.offer_received IS TRUE) AS did_offer,
                BOOL_OR(ru.contract_signed IS TRUE) AS did_contract,
                BOOL_OR(ru.distance_grinding IS TRUE) AS did_distance,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND (lesson.value LIKE 'MTT1:%' OR lesson.value LIKE 'MTT2:%')
                    )
                ) AS is_mtt,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND lesson.value LIKE 'SPIN1:%'
                    )
                ) AS is_spin,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND lesson.value LIKE 'CASH1:%'
                    )
                ) AS is_cash,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND lesson.value LIKE 'Базовый курс:%'
                    )
                ) AS is_base,
                BOOL_OR(
                    lower(trim(COALESCE(ru.bot_key, ''))) LIKE 'lead%'
                    AND ru.tg_user_id > 0
                    AND ru.ph_user_id IS NOT NULL
                    AND abs(ru.tg_user_id) = ru.ph_user_id
                ) AS is_direct_source,
                COALESCE(sf.did_channel, FALSE) AS did_channel,
                COALESCE(sf.did_saloon, FALSE) AS did_saloon
            FROM raw_bot_users ru
            LEFT JOIN (
                SELECT
                    tg_user_id,
                    BOOL_OR(status = 'subscribed' AND channel_id = :channel_id) AS did_channel,
                    BOOL_OR(status = 'subscribed' AND channel_id = :community_id) AS did_saloon
                FROM telegram_subscription_events
                GROUP BY tg_user_id
            ) sf ON sf.tg_user_id = ru.tg_user_id
            WHERE ru.tg_user_id IN (SELECT tg_user_id FROM attributed_leads)
              AND LOWER(TRIM(COALESCE(ru.bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY ru.tg_user_id, sf.did_channel, sf.did_saloon
        ),
        week_metrics AS (
            SELECT
                al.week_start,
                COUNT(DISTINCT CASE WHEN al.tg_user_id > 0 AND NOT uf.is_direct_source THEN al.tg_user_id END) AS almanah_starts,
                COUNT(DISTINCT CASE WHEN uf.is_direct_source AND uf.ph_user_id IS NOT NULL THEN uf.ph_user_id END) AS direct_source_cnt,
                COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date = al.lead_date THEN al.tg_user_id END) AS new_in_system,
                COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date < al.lead_date THEN al.tg_user_id END) AS old_in_system,
                COUNT(
                    DISTINCT CASE
                        WHEN NOT uf.is_direct_source
                         AND uf.ph_user_id IS NOT NULL
                         AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date
                        THEN uf.ph_user_id
                    END
                ) AS platform_cnt,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_course_registration THEN uf.ph_user_id END) AS learning,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning THEN uf.ph_user_id END) AS started_learning,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.is_mtt THEN uf.ph_user_id END) AS mtt,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.is_spin THEN uf.ph_user_id END) AS spin,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.is_cash THEN uf.ph_user_id END) AS cash,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.is_base THEN uf.ph_user_id END) AS base,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND NOT uf.did_learning THEN uf.ph_user_id END) AS not_started,
                COUNT(DISTINCT CASE WHEN uf.did_channel THEN al.tg_user_id END) AS channel_subscribed,
                COUNT(DISTINCT CASE WHEN uf.did_saloon THEN al.tg_user_id END) AS saloon,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete THEN uf.ph_user_id END) AS completed_course,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.is_mtt THEN uf.ph_user_id END) AS completed_mtt,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.is_spin THEN uf.ph_user_id END) AS completed_spin,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.is_cash THEN uf.ph_user_id END) AS completed_cash,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.is_base THEN uf.ph_user_id END) AS completed_base,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview THEN uf.ph_user_id END) AS interview_reached,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer THEN uf.ph_user_id END) AS offer_received,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract THEN uf.ph_user_id END) AS contract_signed,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract AND uf.is_mtt THEN uf.ph_user_id END) AS contract_mtt,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract AND uf.is_spin THEN uf.ph_user_id END) AS contract_spin,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract AND uf.is_cash THEN uf.ph_user_id END) AS contract_cash,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_distance THEN uf.ph_user_id END) AS distance_grinding
            FROM attributed_leads al
            JOIN user_flags uf ON uf.tg_user_id = al.tg_user_id
            GROUP BY al.week_start
        ),
        budgets AS (
            SELECT
                DATE_TRUNC('week', week_start)::date AS week_start,
                SUM(amount) AS budget
            FROM budget_weekly
            WHERE
                (CAST(:start AS date) IS NULL OR week_start::date >= CAST(:start AS date))
                AND (CAST(:end AS date) IS NULL OR week_start::date <= CAST(:end AS date))
                {budget_filter_sql}
            GROUP BY 1
        ),
        ph_by_platform_week AS (
            -- Use authoritative mirror dates (synthetic rows only, tg_user_id < 0),
            -- but only for ph_user_ids whose users passed the active filters (via user_flags).
            SELECT
                DATE_TRUNC('week', synth.platform_registered_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                COUNT(DISTINCT synth.ph_user_id) AS platform_cnt
            FROM raw_bot_users synth
            INNER JOIN (
                SELECT DISTINCT ph_user_id FROM user_flags WHERE ph_user_id IS NOT NULL
            ) uf ON synth.ph_user_id = uf.ph_user_id
            WHERE synth.bot_key = 'lead'
              AND synth.tg_user_id < 0
              AND synth.platform_registered_at IS NOT NULL
            GROUP BY 1
        ),
        metric_weeks AS (
            SELECT week_start FROM week_metrics
            UNION
            SELECT week_start FROM budgets
        )
        SELECT
            mw.week_start,
            COALESCE(ewm.entered_all, 0) AS entered_all,
            COALESCE(b.budget, 0.0) AS budget,
            COALESCE(wm.almanah_starts, 0) AS almanah_starts,
            COALESCE(wm.direct_source_cnt, 0) AS direct_source_cnt,
            COALESCE(wm.new_in_system, 0) AS new_in_system,
            COALESCE(wm.old_in_system, 0) AS old_in_system,
            COALESCE(phw.platform_cnt, 0) AS platform_cnt,
            COALESCE(wm.learning, 0) AS learning,
            COALESCE(wm.started_learning, 0) AS started_learning,
            COALESCE(wm.mtt, 0) AS mtt,
            COALESCE(wm.spin, 0) AS spin,
            COALESCE(wm.cash, 0) AS cash,
            COALESCE(wm.base, 0) AS base,
            COALESCE(wm.not_started, 0) AS not_started,
            COALESCE(wm.channel_subscribed, 0) AS channel_subscribed,
            COALESCE(wm.saloon, 0) AS saloon,
            COALESCE(wm.completed_course, 0) AS completed_course,
            COALESCE(wm.completed_mtt, 0) AS completed_mtt,
            COALESCE(wm.completed_spin, 0) AS completed_spin,
            COALESCE(wm.completed_cash, 0) AS completed_cash,
            COALESCE(wm.completed_base, 0) AS completed_base,
            COALESCE(wm.interview_reached, 0) AS interview_reached,
            COALESCE(wm.offer_received, 0) AS offer_received,
            COALESCE(wm.contract_signed, 0) AS contract_signed,
            COALESCE(wm.contract_mtt, 0) AS contract_mtt,
            COALESCE(wm.contract_spin, 0) AS contract_spin,
            COALESCE(wm.contract_cash, 0) AS contract_cash,
            COALESCE(wm.distance_grinding, 0) AS distance_grinding
        FROM metric_weeks mw
        LEFT JOIN week_metrics wm ON wm.week_start = mw.week_start
        LEFT JOIN entered_week_metrics ewm ON ewm.week_start = mw.week_start
        LEFT JOIN budgets b ON b.week_start = mw.week_start
        LEFT JOIN ph_by_platform_week phw ON phw.week_start = mw.week_start
        ORDER BY mw.week_start DESC
    """)
        week_totals_result = await session.execute(week_totals_query, params)
        db_week_totals_rows = week_totals_result.fetchall()

    if display_mode == "weekly":
        bot_query = sa_text(f"""
        WITH first_seen AS (
            SELECT tg_user_id, MIN(created_at) AS first_seen_at_system
            FROM raw_bot_users
            WHERE LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY tg_user_id
        ),
        {cohort_cte}
        start_rows AS (
            SELECT DISTINCT ON (r.tg_user_id, COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота'))
                r.tg_user_id,
                {lc_company_sql} AS company,
                COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS bot_key,
                (r.created_at AT TIME ZONE 'Europe/Moscow')::date AS start_date,
                date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                fs.first_seen_at_system
            FROM raw_bot_users r
            JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
            {cohort_join}
            WHERE LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL{event_date_filter}{utm_filter_sql}
            ORDER BY r.tg_user_id, COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота'), r.created_at
        ),
        entered_bot_metrics AS (
            SELECT
                sr.week_start,
                sr.company,
                sr.bot_key,
                COUNT(DISTINCT sr.tg_user_id) AS entered_all
            FROM start_rows sr
            GROUP BY sr.week_start, sr.company, sr.bot_key
        ),
        lead_rows AS (
            SELECT DISTINCT ON (r.tg_user_id)
                r.tg_user_id,
                {lc_company_sql} AS lead_company,
                COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS lead_bot_key,
                r.created_at AS lead_created_at,
                (r.created_at AT TIME ZONE 'Europe/Moscow')::date AS lead_date,
                date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                fs.first_seen_at_system
            FROM raw_bot_users r
            JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
            WHERE r.tg_user_id IN (SELECT tg_user_id FROM start_rows)
              AND lower(trim(COALESCE(r.bot_key, ''))) LIKE 'lead%'
              AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL
            ORDER BY r.tg_user_id, r.created_at
        ),
        attributed_leads AS (
            SELECT
                lr.tg_user_id,
                lr.week_start,
                lr.lead_date,
                lr.first_seen_at_system,
                COALESCE(src.company, lr.lead_company) AS company,
                COALESCE(src.bot_key, lr.lead_bot_key) AS bot_key
            FROM lead_rows lr
            LEFT JOIN LATERAL (
                SELECT
                    {normalized_company_sql.replace("advertising_company", "src.advertising_company")} AS company,
                    COALESCE(NULLIF(BTRIM(src.bot_key), ''), 'Без бота') AS bot_key
                FROM raw_bot_users src
                WHERE src.tg_user_id = lr.tg_user_id
                  AND LOWER(TRIM(COALESCE(src.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND lower(trim(COALESCE(src.bot_key, ''))) NOT LIKE 'lead%'
                  AND src.created_at IS NOT NULL
                  AND src.created_at <= lr.lead_created_at{source_touch_filter_sql}
                ORDER BY src.created_at DESC
                LIMIT 1
            ) src ON TRUE
        ),
        user_flags AS (
            SELECT
                ru.tg_user_id,
                BOOL_OR(ru.converted_to_lead IS TRUE OR lower(trim(COALESCE(ru.bot_key, ''))) LIKE 'lead%') AS did_lead,
                BOOL_OR(ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL) AS did_platform,
                MIN((ru.platform_registered_at AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                    WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
                ) AS first_platform_date,
                MIN(ru.ph_user_id) FILTER (
                    WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
                ) AS ph_user_id,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND (
                              lesson.value LIKE 'Базовый курс:%'
                              OR lesson.value LIKE 'MTT1:%'
                              OR lesson.value LIKE 'MTT2:%'
                              OR lesson.value LIKE 'SPIN1:%'
                              OR lesson.value LIKE 'CASH1:%'
                          )
                    )
                ) AS did_course_registration,
                BOOL_OR(ru.started_learning IS TRUE OR ru.learn_start_date IS NOT NULL) AS did_learning,
                BOOL_OR(ru.completed_course IS TRUE AND ru.completed_course_at IS NOT NULL) AS did_complete,
                BOOL_OR(ru.interview_reached IS TRUE) AS did_interview,
                BOOL_OR(ru.offer_received IS TRUE) AS did_offer,
                BOOL_OR(ru.contract_signed IS TRUE) AS did_contract,
                BOOL_OR(ru.distance_grinding IS TRUE) AS did_distance,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND (lesson.value LIKE 'MTT1:%' OR lesson.value LIKE 'MTT2:%')
                    )
                ) AS is_mtt,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND lesson.value LIKE 'SPIN1:%'
                    )
                ) AS is_spin,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND lesson.value LIKE 'CASH1:%'
                    )
                ) AS is_cash,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND lesson.value LIKE 'Базовый курс:%'
                    )
                ) AS is_base,
                BOOL_OR(
                    lower(trim(COALESCE(ru.bot_key, ''))) LIKE 'lead%'
                    AND ru.tg_user_id > 0
                    AND ru.ph_user_id IS NOT NULL
                    AND abs(ru.tg_user_id) = ru.ph_user_id
                ) AS is_direct_source,
                COALESCE(sf.did_channel, FALSE) AS did_channel,
                COALESCE(sf.did_saloon, FALSE) AS did_saloon
            FROM raw_bot_users ru
            LEFT JOIN (
                SELECT
                    tg_user_id,
                    BOOL_OR(status = 'subscribed' AND channel_id = :channel_id) AS did_channel,
                    BOOL_OR(status = 'subscribed' AND channel_id = :community_id) AS did_saloon
                FROM telegram_subscription_events
                GROUP BY tg_user_id
            ) sf ON sf.tg_user_id = ru.tg_user_id
            WHERE ru.tg_user_id IN (SELECT tg_user_id FROM attributed_leads)
              AND LOWER(TRIM(COALESCE(ru.bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY ru.tg_user_id, sf.did_channel, sf.did_saloon
        ),
        bot_metrics AS (
            SELECT
                al.week_start,
                al.company,
                al.bot_key,
                COUNT(DISTINCT CASE WHEN al.tg_user_id > 0 AND NOT uf.is_direct_source THEN al.tg_user_id END) AS almanah_starts,
                COUNT(DISTINCT CASE WHEN uf.is_direct_source AND uf.ph_user_id IS NOT NULL THEN uf.ph_user_id END) AS direct_source_cnt,
                COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date = al.lead_date THEN al.tg_user_id END) AS new_in_system,
                COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date < al.lead_date THEN al.tg_user_id END) AS old_in_system,
                COUNT(
                    DISTINCT CASE
                        WHEN NOT uf.is_direct_source
                         AND uf.ph_user_id IS NOT NULL
                         AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date
                        THEN uf.ph_user_id
                    END
                ) AS platform_cnt,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_course_registration THEN uf.ph_user_id END) AS learning,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning THEN uf.ph_user_id END) AS started_learning,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.is_mtt THEN uf.ph_user_id END) AS mtt,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.is_spin THEN uf.ph_user_id END) AS spin,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.is_cash THEN uf.ph_user_id END) AS cash,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.is_base THEN uf.ph_user_id END) AS base,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND NOT uf.did_learning THEN uf.ph_user_id END) AS not_started,
                COUNT(DISTINCT CASE WHEN uf.did_channel THEN al.tg_user_id END) AS channel_subscribed,
                COUNT(DISTINCT CASE WHEN uf.did_saloon THEN al.tg_user_id END) AS saloon,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete THEN uf.ph_user_id END) AS completed_course,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.is_mtt THEN uf.ph_user_id END) AS completed_mtt,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.is_spin THEN uf.ph_user_id END) AS completed_spin,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.is_cash THEN uf.ph_user_id END) AS completed_cash,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.is_base THEN uf.ph_user_id END) AS completed_base,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview THEN uf.ph_user_id END) AS interview_reached,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer THEN uf.ph_user_id END) AS offer_received,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract THEN uf.ph_user_id END) AS contract_signed,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract AND uf.is_mtt THEN uf.ph_user_id END) AS contract_mtt,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract AND uf.is_spin THEN uf.ph_user_id END) AS contract_spin,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_contract AND uf.is_cash THEN uf.ph_user_id END) AS contract_cash,
                COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date AND uf.did_learning AND uf.did_complete AND uf.did_interview AND uf.did_offer AND uf.did_distance THEN uf.ph_user_id END) AS distance_grinding
            FROM attributed_leads al
            JOIN user_flags uf ON uf.tg_user_id = al.tg_user_id
            GROUP BY al.week_start, al.company, al.bot_key
        ),
        budgets_bot AS (
            SELECT DATE_TRUNC('week', week_start)::date AS week_start,
                CASE WHEN campaign IS NULL OR BTRIM(campaign) = '' OR LOWER(BTRIM(campaign)) IN ('-', '—', '(none)', 'none', 'null', 'нет метки') THEN 'Без категории' ELSE BTRIM(campaign) END AS company,
                COALESCE(NULLIF(BTRIM(bot_key), ''), 'Без бота') AS bot_key,
                SUM(amount) AS budget
            FROM budget_weekly
            WHERE (CAST(:start AS date) IS NULL OR week_start::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR week_start::date <= CAST(:end AS date))
              {budget_filter_sql}
            GROUP BY 1, 2, 3
        ),
        bot_weeks AS (
            SELECT week_start, company, bot_key FROM bot_metrics
            UNION SELECT week_start, company, bot_key FROM budgets_bot
        )
        SELECT
            bw.week_start,
            bw.company,
            bw.bot_key,
            COALESCE(ebm.entered_all, 0) AS entered_all,
            COALESCE(b.budget, 0.0) AS budget,
            COALESCE(bm.almanah_starts, 0) AS almanah_starts,
            COALESCE(bm.direct_source_cnt, 0) AS direct_source_cnt,
            COALESCE(bm.new_in_system, 0) AS new_in_system,
            COALESCE(bm.old_in_system, 0) AS old_in_system,
            COALESCE(bm.platform_cnt, 0) AS platform_cnt,
            COALESCE(bm.learning, 0) AS learning,
            COALESCE(bm.started_learning, 0) AS started_learning,
            COALESCE(bm.mtt, 0) AS mtt,
            COALESCE(bm.spin, 0) AS spin,
            COALESCE(bm.cash, 0) AS cash,
            COALESCE(bm.base, 0) AS base,
            COALESCE(bm.not_started, 0) AS not_started,
            COALESCE(bm.channel_subscribed, 0) AS channel_subscribed,
            COALESCE(bm.saloon, 0) AS saloon,
            COALESCE(bm.completed_course, 0) AS completed_course,
            COALESCE(bm.completed_mtt, 0) AS completed_mtt,
            COALESCE(bm.completed_spin, 0) AS completed_spin,
            COALESCE(bm.completed_cash, 0) AS completed_cash,
            COALESCE(bm.completed_base, 0) AS completed_base,
            COALESCE(bm.interview_reached, 0) AS interview_reached,
            COALESCE(bm.offer_received, 0) AS offer_received,
            COALESCE(bm.contract_signed, 0) AS contract_signed,
            COALESCE(bm.contract_mtt, 0) AS contract_mtt,
            COALESCE(bm.contract_spin, 0) AS contract_spin,
            COALESCE(bm.contract_cash, 0) AS contract_cash,
            COALESCE(bm.distance_grinding, 0) AS distance_grinding
        FROM bot_weeks bw
        LEFT JOIN bot_metrics bm ON bm.week_start = bw.week_start AND bm.company = bw.company AND bm.bot_key = bw.bot_key
        LEFT JOIN entered_bot_metrics ebm ON ebm.week_start = bw.week_start AND ebm.company = bw.company AND ebm.bot_key = bw.bot_key
        LEFT JOIN budgets_bot b ON b.week_start = bw.week_start AND b.company = bw.company AND b.bot_key = bw.bot_key
        ORDER BY bw.week_start DESC, bw.company, COALESCE(bm.almanah_starts, 0) DESC, bw.bot_key
    """)
    else:
        bot_query = sa_text(f"""
        WITH first_seen AS (
            SELECT tg_user_id, MIN(created_at) AS first_seen_at_system
            FROM raw_bot_users
            WHERE LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY tg_user_id
        ),
        {cohort_cte}
        lead_rows AS (
            SELECT DISTINCT ON (r.tg_user_id)
                r.tg_user_id,
                {normalized_company_sql.replace("advertising_company", "r.advertising_company")} AS lead_company,
                COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS lead_bot_key,
                r.created_at AS lead_created_at,
                (r.created_at AT TIME ZONE 'Europe/Moscow')::date AS lead_date,
                date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                fs.first_seen_at_system
            FROM raw_bot_users r
            JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
            {cohort_join}
            WHERE lower(trim(r.bot_key)) LIKE 'lead%'
              AND r.tg_user_id > 0
              AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL{event_date_filter}{utm_filter_sql}
            ORDER BY r.tg_user_id, r.created_at
        ),
        attributed_leads AS (
            SELECT
                lr.tg_user_id,
                lr.week_start,
                lr.lead_date,
                lr.first_seen_at_system,
                COALESCE(src.company, lr.lead_company) AS company,
                COALESCE(src.bot_key, lr.lead_bot_key) AS bot_key
            FROM lead_rows lr
            LEFT JOIN LATERAL (
                SELECT
                    {normalized_company_sql.replace("advertising_company", "src.advertising_company")} AS company,
                    COALESCE(NULLIF(BTRIM(src.bot_key), ''), 'Без бота') AS bot_key
                FROM raw_bot_users src
                WHERE src.tg_user_id = lr.tg_user_id
                  AND LOWER(TRIM(COALESCE(src.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND lower(trim(COALESCE(src.bot_key, ''))) NOT LIKE 'lead%'
                  AND src.created_at IS NOT NULL
                  AND src.created_at <= lr.lead_created_at{source_touch_filter_sql}
                ORDER BY src.created_at DESC
                LIMIT 1
            ) src ON TRUE
        ),
        user_flags AS (
            SELECT
                ru.tg_user_id,
                BOOL_OR(ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL) AS did_platform,
                MIN((ru.platform_registered_at AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                    WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
                ) AS first_platform_date,
                MIN(ru.ph_user_id) FILTER (
                    WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
                ) AS ph_user_id,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND (
                              lesson.value LIKE 'Базовый курс:%'
                              OR lesson.value LIKE 'MTT1:%'
                              OR lesson.value LIKE 'MTT2:%'
                              OR lesson.value LIKE 'SPIN1:%'
                              OR lesson.value LIKE 'CASH1:%'
                          )
                    )
                ) AS did_course_registration,
                BOOL_OR(ru.learn_start_date IS NOT NULL) AS did_learning,
                BOOL_OR(ru.completed_course IS TRUE AND ru.completed_course_at IS NOT NULL) AS did_complete,
                BOOL_OR(ru.interview_reached IS TRUE) AS did_interview,
                BOOL_OR(ru.offer_received IS TRUE) AS did_offer,
                BOOL_OR(ru.contract_signed IS TRUE) AS did_contract,
                BOOL_OR(ru.distance_grinding IS TRUE) AS did_distance,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND (lesson.value LIKE 'MTT1:%' OR lesson.value LIKE 'MTT2:%')
                    )
                ) AS is_mtt,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND lesson.value LIKE 'SPIN1:%'
                    )
                ) AS is_spin,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND lesson.value LIKE 'CASH1:%'
                    )
                ) AS is_cash,
                BOOL_OR(
                    EXISTS (
                        SELECT 1
                        FROM ph_user_mirror_replica pm
                        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                        WHERE pm.ph_id = ru.ph_user_id::text
                          AND lesson.value LIKE 'Базовый курс:%'
                    )
                ) AS is_base,
                MIN((
                    SELECT MIN((((regexp_match(lesson.value, '\(([^()]+)\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FROM ph_user_mirror_replica pm
                    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                    WHERE pm.ph_id = ru.ph_user_id::text
                      AND lesson.value LIKE 'Базовый курс:%'
                )) AS first_base_lesson_date,
                MIN((
                    SELECT MIN((((regexp_match(lesson.value, '\(([^()]+)\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FROM ph_user_mirror_replica pm
                    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                    WHERE pm.ph_id = ru.ph_user_id::text
                      AND (lesson.value LIKE 'MTT1:%' OR lesson.value LIKE 'MTT2:%')
                )) AS first_mtt_lesson_date,
                MIN((
                    SELECT MIN((((regexp_match(lesson.value, '\(([^()]+)\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FROM ph_user_mirror_replica pm
                    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                    WHERE pm.ph_id = ru.ph_user_id::text
                      AND lesson.value LIKE 'SPIN1:%'
                )) AS first_spin_lesson_date,
                MIN((
                    SELECT MIN((((regexp_match(lesson.value, '\(([^()]+)\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FROM ph_user_mirror_replica pm
                    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value)
                    WHERE pm.ph_id = ru.ph_user_id::text
                      AND lesson.value LIKE 'CASH1:%'
                )) AS first_cash_lesson_date,
                BOOL_OR(
                    lower(trim(COALESCE(ru.bot_key, ''))) LIKE 'lead%'
                    AND ru.tg_user_id > 0
                    AND ru.ph_user_id IS NOT NULL
                    AND abs(ru.tg_user_id) = ru.ph_user_id
                ) AS is_direct_source,
                COALESCE(sf.did_channel, FALSE) AS did_channel,
                COALESCE(sf.did_saloon, FALSE) AS did_saloon
            FROM raw_bot_users ru
            LEFT JOIN (
                SELECT
                    tg_user_id,
                    BOOL_OR(status = 'subscribed' AND channel_id = :channel_id) AS did_channel,
                    BOOL_OR(status = 'subscribed' AND channel_id = :community_id) AS did_saloon
                FROM telegram_subscription_events
                GROUP BY tg_user_id
            ) sf ON sf.tg_user_id = ru.tg_user_id
            WHERE ru.tg_user_id IN (SELECT tg_user_id FROM attributed_leads)
              AND LOWER(TRIM(COALESCE(ru.bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY ru.tg_user_id, sf.did_channel, sf.did_saloon
        ),
        lead_metrics_bot AS (
            SELECT
                al.week_start,
                al.company,
                al.bot_key,
                COUNT(DISTINCT CASE WHEN al.tg_user_id > 0 AND NOT uf.is_direct_source THEN al.tg_user_id END) AS almanah_starts,
                COUNT(DISTINCT CASE WHEN uf.is_direct_source AND uf.ph_user_id IS NOT NULL THEN uf.ph_user_id END) AS direct_source_cnt,
                COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date = al.lead_date THEN al.tg_user_id END) AS new_in_system,
                COUNT(DISTINCT CASE WHEN (al.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date < al.lead_date THEN al.tg_user_id END) AS old_in_system,
                COUNT(
                    DISTINCT CASE
                        WHEN NOT uf.is_direct_source
                         AND uf.ph_user_id IS NOT NULL
                         AND uf.first_platform_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date
                        THEN uf.ph_user_id
                    END
                ) AS platform_cnt,
                COUNT(DISTINCT CASE WHEN uf.did_course_registration THEN al.tg_user_id END) AS learning,
                COUNT(DISTINCT CASE WHEN uf.did_learning THEN al.tg_user_id END) AS started_learning,
                COUNT(DISTINCT CASE WHEN uf.first_mtt_lesson_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date THEN al.tg_user_id END) AS mtt,
                COUNT(DISTINCT CASE WHEN uf.first_spin_lesson_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date THEN al.tg_user_id END) AS spin,
                COUNT(DISTINCT CASE WHEN uf.first_cash_lesson_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date THEN al.tg_user_id END) AS cash,
                COUNT(DISTINCT CASE WHEN uf.first_base_lesson_date BETWEEN al.week_start AND (al.week_start + INTERVAL '6 day')::date THEN al.tg_user_id END) AS base,
                COUNT(DISTINCT CASE WHEN uf.did_platform AND NOT uf.did_learning THEN al.tg_user_id END) AS not_started,
                COUNT(DISTINCT CASE WHEN uf.did_channel THEN al.tg_user_id END) AS channel_subscribed,
                COUNT(DISTINCT CASE WHEN uf.did_saloon THEN al.tg_user_id END) AS saloon,
                COUNT(DISTINCT CASE WHEN uf.did_complete THEN al.tg_user_id END) AS completed_course,
                COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.first_mtt_lesson_date IS NOT NULL THEN al.tg_user_id END) AS completed_mtt,
                COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.first_spin_lesson_date IS NOT NULL THEN al.tg_user_id END) AS completed_spin,
                COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.first_cash_lesson_date IS NOT NULL THEN al.tg_user_id END) AS completed_cash,
                COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.first_base_lesson_date IS NOT NULL THEN al.tg_user_id END) AS completed_base,
                COUNT(DISTINCT CASE WHEN uf.did_interview THEN al.tg_user_id END) AS interview_reached,
                COUNT(DISTINCT CASE WHEN uf.did_offer THEN al.tg_user_id END) AS offer_received,
                COUNT(DISTINCT CASE WHEN uf.did_contract THEN al.tg_user_id END) AS contract_signed,
                COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.first_mtt_lesson_date IS NOT NULL THEN al.tg_user_id END) AS contract_mtt,
                COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.first_spin_lesson_date IS NOT NULL THEN al.tg_user_id END) AS contract_spin,
                COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.first_cash_lesson_date IS NOT NULL THEN al.tg_user_id END) AS contract_cash,
                COUNT(DISTINCT CASE WHEN uf.did_distance THEN al.tg_user_id END) AS distance_grinding
            FROM attributed_leads al
            JOIN user_flags uf ON uf.tg_user_id = al.tg_user_id
            GROUP BY al.week_start, al.company, al.bot_key
        ),
        all_starts_bot AS (
            SELECT
                date_trunc('week', r.created_at AT TIME ZONE 'Europe/Moscow')::date AS week_start,
                {normalized_company_sql.replace("advertising_company", "r.advertising_company")} AS company,
                COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS bot_key,
                COUNT(DISTINCT r.tg_user_id) AS entered_all
            FROM raw_bot_users r
            {cohort_all_starts_join}
            WHERE LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date)){utm_filter_sql}
            GROUP BY 1, 2, 3
        ),
        budgets_bot AS (
            SELECT
                DATE_TRUNC('week', week_start)::date AS week_start,
                CASE
                    WHEN campaign IS NULL
                      OR BTRIM(campaign) = ''
                      OR LOWER(BTRIM(campaign)) IN ('-', '—', '(none)', 'none', 'null', 'нет метки')
                    THEN 'Без категории'
                    ELSE BTRIM(campaign)
                END AS company,
                COALESCE(NULLIF(BTRIM(bot_key), ''), 'Без бота') AS bot_key,
                SUM(amount) AS budget
            FROM budget_weekly
            WHERE
                (CAST(:start AS date) IS NULL OR week_start::date >= CAST(:start AS date))
                AND (CAST(:end AS date) IS NULL OR week_start::date <= CAST(:end AS date))
                {budget_filter_sql}
            GROUP BY 1, 2, 3
        ),
        bot_weeks AS (
            SELECT week_start, company, bot_key FROM lead_metrics_bot
            UNION
            SELECT week_start, company, bot_key FROM all_starts_bot
            UNION
            SELECT week_start, company, bot_key FROM budgets_bot
        )
        SELECT
            bw.week_start,
            bw.company,
            bw.bot_key,
            COALESCE(s.entered_all, 0) AS entered_all,
            COALESCE(b.budget, 0.0) AS budget,
            COALESCE(lm.almanah_starts, 0) AS almanah_starts,
            COALESCE(lm.direct_source_cnt, 0) AS direct_source_cnt,
            COALESCE(lm.new_in_system, 0) AS new_in_system,
            COALESCE(lm.old_in_system, 0) AS old_in_system,
            COALESCE(lm.platform_cnt, 0) AS platform_cnt,
            COALESCE(lm.learning, 0) AS learning,
            COALESCE(lm.started_learning, 0) AS started_learning,
            COALESCE(lm.mtt, 0) AS mtt,
            COALESCE(lm.spin, 0) AS spin,
            COALESCE(lm.cash, 0) AS cash,
            COALESCE(lm.base, 0) AS base,
            COALESCE(lm.not_started, 0) AS not_started,
            COALESCE(lm.channel_subscribed, 0) AS channel_subscribed,
            COALESCE(lm.saloon, 0) AS saloon,
            COALESCE(lm.completed_course, 0) AS completed_course,
            COALESCE(lm.completed_mtt, 0) AS completed_mtt,
            COALESCE(lm.completed_spin, 0) AS completed_spin,
            COALESCE(lm.completed_cash, 0) AS completed_cash,
            COALESCE(lm.completed_base, 0) AS completed_base,
            COALESCE(lm.interview_reached, 0) AS interview_reached,
            COALESCE(lm.offer_received, 0) AS offer_received,
            COALESCE(lm.contract_signed, 0) AS contract_signed,
            COALESCE(lm.contract_mtt, 0) AS contract_mtt,
            COALESCE(lm.contract_spin, 0) AS contract_spin,
            COALESCE(lm.contract_cash, 0) AS contract_cash,
            COALESCE(lm.distance_grinding, 0) AS distance_grinding
        FROM bot_weeks bw
        LEFT JOIN lead_metrics_bot lm
          ON lm.week_start = bw.week_start AND lm.company = bw.company AND lm.bot_key = bw.bot_key
        LEFT JOIN all_starts_bot s
          ON s.week_start = bw.week_start AND s.company = bw.company AND s.bot_key = bw.bot_key
        LEFT JOIN budgets_bot b
          ON b.week_start = bw.week_start AND b.company = bw.company AND b.bot_key = bw.bot_key
        ORDER BY bw.week_start DESC, bw.company, COALESCE(lm.almanah_starts, 0) DESC, bw.bot_key
    """)
    bot_result = await session.execute(bot_query, params)
    db_bot_rows = bot_result.fetchall()

    METRIC_KEYS = [
        "almanah_starts", "direct_source_cnt", "new_in_system", "old_in_system", "platform_cnt", "learning", "started_learning", "mtt", "spin", "cash", "base",
        "not_started", "channel_subscribed", "saloon",
        "completed_course", "completed_mtt", "completed_spin", "completed_cash", "completed_base",
        "interview_reached", "offer_received", "contract_signed",
        "contract_mtt", "contract_spin", "contract_cash", "distance_grinding",
    ]
    rows_payload = [
        {
            "week_start": row.week_start.isoformat(),
            "company": row.company,
            "entered_all": int(row.entered_all or 0),
            "budget": float(row.budget or 0.0),
            **{k: int(getattr(row, k) or 0) for k in METRIC_KEYS},
        }
        for row in db_rows
    ]
    bot_rows_payload = [
        {
            "week_start": row.week_start.isoformat(),
            "company": row.company,
            "bot_key": row.bot_key,
            "entered_all": int(row.entered_all or 0),
            "budget": float(row.budget or 0.0),
            **{k: int(getattr(row, k) or 0) for k in METRIC_KEYS},
        }
        for row in db_bot_rows
    ]
    week_totals_payload = [
        {
            "week_start": row.week_start.isoformat(),
            "entered_all": int(row.entered_all or 0),
            "budget": float(row.budget or 0.0),
            **{k: int(getattr(row, k) or 0) for k in METRIC_KEYS},
        }
        for row in db_week_totals_rows
    ]

    lesson_reg_query = sa_text(f"""
        WITH lesson_first AS (
            SELECT
                pm.ph_id::bigint AS ph_user_id,
                MIN((((regexp_match(lesson.value, '\(([^()]+)\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FILTER (WHERE lesson.value LIKE 'Базовый курс:%') AS base_date,
                MIN((((regexp_match(lesson.value, '\(([^()]+)\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FILTER (WHERE lesson.value LIKE 'MTT1:%' OR lesson.value LIKE 'MTT2:%') AS mtt_date,
                MIN((((regexp_match(lesson.value, '\(([^()]+)\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FILTER (WHERE lesson.value LIKE 'SPIN1:%') AS spin_date,
                MIN((((regexp_match(lesson.value, '\(([^()]+)\)$'))[1])::timestamptz AT TIME ZONE 'Europe/Moscow')::date)
                    FILTER (WHERE lesson.value LIKE 'CASH1:%') AS cash_date
            FROM ph_user_mirror_replica pm
            LEFT JOIN LATERAL jsonb_array_elements_text(COALESCE(pm.lessons::jsonb, '[]'::jsonb)) AS lesson(value) ON TRUE
            GROUP BY pm.ph_id
        ),
        attributed AS (
            SELECT
                lf.ph_user_id,
                COALESCE(src.company, 'Без категории') AS company,
                COALESCE(src.bot_key, 'Без бота') AS bot_key,
                lf.base_date,
                lf.mtt_date,
                lf.spin_date,
                lf.cash_date
            FROM lesson_first lf
            LEFT JOIN LATERAL (
                SELECT
                    {normalized_company_sql.replace("advertising_company", "src.advertising_company")} AS company,
                    COALESCE(NULLIF(BTRIM(src.bot_key), ''), 'Без бота') AS bot_key
                FROM raw_bot_users src
                WHERE src.ph_user_id = lf.ph_user_id
                  AND LOWER(TRIM(COALESCE(src.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND src.created_at IS NOT NULL{source_touch_filter_sql}
                ORDER BY
                    CASE WHEN lower(trim(COALESCE(src.bot_key, ''))) LIKE 'lead%' THEN 1 ELSE 0 END,
                    src.created_at DESC
                LIMIT 1
            ) src ON TRUE
        ),
        course_events AS (
            SELECT DATE_TRUNC('week', base_date)::date AS week_start, company, bot_key, ph_user_id, 'base' AS course
            FROM attributed
            WHERE base_date IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR base_date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR base_date <= CAST(:end AS date))
            UNION ALL
            SELECT DATE_TRUNC('week', mtt_date)::date AS week_start, company, bot_key, ph_user_id, 'mtt' AS course
            FROM attributed
            WHERE mtt_date IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR mtt_date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR mtt_date <= CAST(:end AS date))
            UNION ALL
            SELECT DATE_TRUNC('week', spin_date)::date AS week_start, company, bot_key, ph_user_id, 'spin' AS course
            FROM attributed
            WHERE spin_date IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR spin_date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR spin_date <= CAST(:end AS date))
            UNION ALL
            SELECT DATE_TRUNC('week', cash_date)::date AS week_start, company, bot_key, ph_user_id, 'cash' AS course
            FROM attributed
            WHERE cash_date IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR cash_date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR cash_date <= CAST(:end AS date))
        )
        SELECT
            week_start,
            company,
            bot_key,
            COUNT(DISTINCT ph_user_id) FILTER (WHERE course = 'base') AS base,
            COUNT(DISTINCT ph_user_id) FILTER (WHERE course = 'mtt') AS mtt,
            COUNT(DISTINCT ph_user_id) FILTER (WHERE course = 'spin') AS spin,
            COUNT(DISTINCT ph_user_id) FILTER (WHERE course = 'cash') AS cash
        FROM course_events
        GROUP BY week_start, company, bot_key
    """)
    lesson_reg_result = await session.execute(lesson_reg_query, params)
    lesson_reg_rows = lesson_reg_result.fetchall()

    company_reg_map: dict[tuple[str, str], dict[str, int]] = {}
    bot_reg_map: dict[tuple[str, str, str], dict[str, int]] = {}
    week_reg_map: dict[str, dict[str, int]] = {}
    for row in lesson_reg_rows:
        week_key = row.week_start.isoformat()
        company_key = (week_key, row.company)
        bot_key = (week_key, row.company, row.bot_key)
        metrics = {
            "base": int(row.base or 0),
            "mtt": int(row.mtt or 0),
            "spin": int(row.spin or 0),
            "cash": int(row.cash or 0),
        }
        company_metrics = company_reg_map.setdefault(company_key, {"base": 0, "mtt": 0, "spin": 0, "cash": 0})
        for metric_key, metric_value in metrics.items():
            company_metrics[metric_key] += metric_value
        bot_reg_map[bot_key] = metrics
        week_metrics = week_reg_map.setdefault(week_key, {"base": 0, "mtt": 0, "spin": 0, "cash": 0})
        for metric_key, metric_value in metrics.items():
            week_metrics[metric_key] += metric_value

    def _upsert_row(
        rows: list[dict[str, Any]],
        key_fields: tuple[str, ...],
        key_values: tuple[str, ...],
    ) -> dict[str, Any]:
        for row in rows:
            if tuple(str(row.get(field) or "") for field in key_fields) == key_values:
                return row
        row: dict[str, Any] = {"entered_all": 0, "budget": 0.0, **{k: 0 for k in METRIC_KEYS}}
        for field, value in zip(key_fields, key_values):
            row[field] = value
        rows.append(row)
        return row

    for (week_key, company), metrics in company_reg_map.items():
        row = _upsert_row(rows_payload, ("week_start", "company"), (week_key, company))
        row.update(metrics)

    for (week_key, company, bot_key), metrics in bot_reg_map.items():
        row = _upsert_row(bot_rows_payload, ("week_start", "company", "bot_key"), (week_key, company, bot_key))
        row.update(metrics)

    for week_key, metrics in week_reg_map.items():
        row = _upsert_row(week_totals_payload, ("week_start",), (week_key,))
        row.update(metrics)

    # Recompute course registration metrics using the same lesson parser as PH Lessons.
    # This keeps BASE/MTT/SPIN/CASH reg counts aligned with mirror lessons instead of
    # historical raw_bot_users.start_course semantics.
    from collections import defaultdict
    from app.services.pokerhub_lesson_summary import PokerHubLessonSummaryBuilder

    for row in rows_payload:
        row["base"] = row["mtt"] = row["spin"] = row["cash"] = 0
    for row in bot_rows_payload:
        row["base"] = row["mtt"] = row["spin"] = row["cash"] = 0
    for row in week_totals_payload:
        row["base"] = row["mtt"] = row["spin"] = row["cash"] = 0

    attribution_query = sa_text(f"""
        WITH ranked AS (
            SELECT
                src.ph_user_id::text AS ph_user_id,
                {normalized_company_sql.replace("advertising_company", "src.advertising_company")} AS company,
                COALESCE(NULLIF(BTRIM(src.bot_key), ''), 'Без бота') AS bot_key,
                ROW_NUMBER() OVER (
                    PARTITION BY src.ph_user_id
                    ORDER BY
                        CASE WHEN lower(trim(COALESCE(src.bot_key, ''))) LIKE 'lead%' THEN 1 ELSE 0 END,
                        src.created_at DESC NULLS LAST
                ) AS rn
            FROM raw_bot_users src
            WHERE src.ph_user_id IS NOT NULL
              AND LOWER(TRIM(COALESCE(src.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND src.created_at IS NOT NULL{source_touch_filter_sql}
        )
        SELECT ph_user_id, company, bot_key
        FROM ranked
        WHERE rn = 1
    """)
    attribution_result = await session.execute(attribution_query, params)
    attribution_map = {
        str(row.ph_user_id): (row.company or "Без категории", row.bot_key or "Без бота")
        for row in attribution_result.fetchall()
    }

    mirror_result = await session.execute(
        sa_text("SELECT ph_id, lessons, courses, groups FROM ph_user_mirror_replica")
    )
    lesson_builder = PokerHubLessonSummaryBuilder()
    company_reg_map = defaultdict(lambda: {"base": 0, "mtt": 0, "spin": 0, "cash": 0})
    bot_reg_map = defaultdict(lambda: {"base": 0, "mtt": 0, "spin": 0, "cash": 0})
    week_reg_map = defaultdict(lambda: {"base": 0, "mtt": 0, "spin": 0, "cash": 0})

    def _week_start_iso(value):
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            try:
                value = datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
            except ValueError:
                try:
                    value = date.fromisoformat(normalized)
                except ValueError:
                    return None
        elif isinstance(value, datetime):
            value = value.date()
        week_start = value - timedelta(days=value.weekday())
        return week_start.isoformat()

    course_keys = {
        "BASE": "base",
        "MTT": "mtt",
        "SPIN": "spin",
        "CASH": "cash",
    }

    for mirror_row in mirror_result.fetchall():
        ph_id = str(mirror_row.ph_id or "")
        if not ph_id:
            continue
        summary = lesson_builder.build(
            {
                "ph_id": ph_id,
                "lessons": mirror_row.lessons,
                "courses": mirror_row.courses,
                "groups": mirror_row.groups,
            }
        )
        company, bot_key = attribution_map.get(ph_id, ("Без категории", "Без бота"))
        for course_name, metric_key in course_keys.items():
            lesson_dates = [
                entry.get("date")
                for entry in summary["courses"].get(course_name, [])
                if entry.get("date") is not None
            ]
            if not lesson_dates:
                continue
            week_key = _week_start_iso(min(lesson_dates))
            if not week_key:
                continue
            company_reg_map[(week_key, company)][metric_key] += 1
            bot_reg_map[(week_key, company, bot_key)][metric_key] += 1
            week_reg_map[week_key][metric_key] += 1

    for (week_key, company), metrics in company_reg_map.items():
        row = _upsert_row(rows_payload, ("week_start", "company"), (week_key, company))
        row.update(metrics)

    for (week_key, company, bot_key), metrics in bot_reg_map.items():
        row = _upsert_row(bot_rows_payload, ("week_start", "company", "bot_key"), (week_key, company, bot_key))
        row.update(metrics)

    for week_key, metrics in week_reg_map.items():
        row = _upsert_row(week_totals_payload, ("week_start",), (week_key,))
        row.update(metrics)

    if display_mode == "cohort":
        event_metric_keys = [
            "platform_cnt",
            "learning",
            "started_learning",
            "mtt",
            "spin",
            "cash",
            "base",
            "not_started",
            "completed_course",
            "completed_mtt",
            "completed_spin",
            "completed_cash",
            "completed_base",
        ]
        for row in rows_payload + bot_rows_payload:
            for key in event_metric_keys:
                row[key] = 0

        event_stage_query = sa_text(f"""
        WITH first_seen AS (
            SELECT tg_user_id, MIN(created_at) AS first_seen_at_system
            FROM raw_bot_users
            WHERE LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY tg_user_id
        ),
        {cohort_cte}
        lead_rows AS (
            SELECT DISTINCT ON (r.tg_user_id)
                r.tg_user_id,
                {normalized_company_sql.replace("advertising_company", "r.advertising_company")} AS lead_company,
                COALESCE(NULLIF(BTRIM(r.bot_key), ''), 'Без бота') AS lead_bot_key,
                r.created_at AS lead_created_at
            FROM raw_bot_users r
            JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
            {cohort_join}
            WHERE lower(trim(r.bot_key)) LIKE 'lead%'
              AND r.tg_user_id > 0
              AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL{utm_filter_sql}
            ORDER BY r.tg_user_id, r.created_at
        ),
        attributed_leads AS (
            SELECT
                lr.tg_user_id,
                COALESCE(src.company, lr.lead_company) AS company,
                COALESCE(src.bot_key, lr.lead_bot_key) AS bot_key
            FROM lead_rows lr
            LEFT JOIN LATERAL (
                SELECT
                    {normalized_company_sql.replace("advertising_company", "src.advertising_company")} AS company,
                    COALESCE(NULLIF(BTRIM(src.bot_key), ''), 'Без бота') AS bot_key
                FROM raw_bot_users src
                WHERE src.tg_user_id = lr.tg_user_id
                  AND LOWER(TRIM(COALESCE(src.bot_key, ''))) <> ALL(:excluded_bot_keys)
                  AND lower(trim(COALESCE(src.bot_key, ''))) NOT LIKE 'lead%'
                  AND src.created_at IS NOT NULL
                  AND src.created_at <= lr.lead_created_at{source_touch_filter_sql}
                ORDER BY src.created_at DESC
                LIMIT 1
            ) src ON TRUE
        ),
        user_events AS (
            SELECT
                ru.tg_user_id,
                MIN(ru.ph_user_id) FILTER (
                    WHERE ru.ph_user_id IS NOT NULL
                ) AS ph_user_id,
                MIN((ru.platform_registered_at AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                    WHERE ru.ph_user_id IS NOT NULL AND ru.platform_registered_at IS NOT NULL
                ) AS platform_date,
                MIN((ru.learn_start_date AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                    WHERE ru.learn_start_date IS NOT NULL
                ) AS learn_date,
                MIN((COALESCE(ru.learn_start_date, ru.platform_registered_at) AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                    WHERE TRIM(COALESCE(ru.start_course, '')) <> ''
                ) AS course_event_date,
                MIN((ru.completed_course_at AT TIME ZONE 'Europe/Moscow')::date) FILTER (
                    WHERE ru.completed_course IS TRUE AND ru.completed_course_at IS NOT NULL
                ) AS completed_date,
                BOOL_OR(TRIM(COALESCE(ru.start_course, '')) <> '') AS did_course_registration,
                BOOL_OR(LOWER(TRIM(COALESCE(ru.start_course, ''))) LIKE 'mtt%') AS is_mtt,
                BOOL_OR(LOWER(TRIM(COALESCE(ru.start_course, ''))) LIKE 'spin%') AS is_spin,
                BOOL_OR(LOWER(TRIM(COALESCE(ru.start_course, ''))) LIKE 'cash%') AS is_cash,
                BOOL_OR(LOWER(TRIM(COALESCE(ru.start_course, ''))) LIKE 'base%') AS is_base
            FROM raw_bot_users ru
            WHERE LOWER(TRIM(COALESCE(ru.bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY ru.tg_user_id
        ),
        stage_events AS (
            SELECT al.company, al.bot_key, ue.platform_date AS event_date, 'platform_cnt' AS metric,
                   COALESCE(ue.ph_user_id::text, ue.tg_user_id::text) AS entity_key
            FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
            WHERE ue.platform_date IS NOT NULL AND ue.ph_user_id IS NOT NULL
            UNION ALL
            SELECT al.company, al.bot_key, ue.course_event_date, 'learning',
                   COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
            FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
            WHERE ue.course_event_date IS NOT NULL AND ue.did_course_registration AND ue.ph_user_id IS NOT NULL
            UNION ALL
            SELECT al.company, al.bot_key, ue.learn_date, 'started_learning',
                   COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
            FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
            WHERE ue.learn_date IS NOT NULL AND ue.ph_user_id IS NOT NULL
            UNION ALL
            SELECT al.company, al.bot_key, ue.course_event_date, 'mtt',
                   COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
            FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
            WHERE ue.course_event_date IS NOT NULL AND ue.is_mtt AND ue.ph_user_id IS NOT NULL
            UNION ALL
            SELECT al.company, al.bot_key, ue.course_event_date, 'spin',
                   COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
            FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
            WHERE ue.course_event_date IS NOT NULL AND ue.is_spin AND ue.ph_user_id IS NOT NULL
            UNION ALL
            SELECT al.company, al.bot_key, ue.course_event_date, 'cash',
                   COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
            FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
            WHERE ue.course_event_date IS NOT NULL AND ue.is_cash AND ue.ph_user_id IS NOT NULL
            UNION ALL
            SELECT al.company, al.bot_key, ue.course_event_date, 'base',
                   COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
            FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
            WHERE ue.course_event_date IS NOT NULL AND ue.is_base AND ue.ph_user_id IS NOT NULL
            UNION ALL
            SELECT al.company, al.bot_key, ue.platform_date, 'not_started',
                   COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
            FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
            WHERE ue.platform_date IS NOT NULL AND ue.learn_date IS NULL AND ue.ph_user_id IS NOT NULL
            UNION ALL
            SELECT al.company, al.bot_key, ue.completed_date, 'completed_course',
                   COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
            FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
            WHERE ue.completed_date IS NOT NULL AND ue.ph_user_id IS NOT NULL
            UNION ALL
            SELECT al.company, al.bot_key, ue.completed_date, 'completed_mtt',
                   COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
            FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
            WHERE ue.completed_date IS NOT NULL AND ue.is_mtt AND ue.ph_user_id IS NOT NULL
            UNION ALL
            SELECT al.company, al.bot_key, ue.completed_date, 'completed_spin',
                   COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
            FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
            WHERE ue.completed_date IS NOT NULL AND ue.is_spin AND ue.ph_user_id IS NOT NULL
            UNION ALL
            SELECT al.company, al.bot_key, ue.completed_date, 'completed_cash',
                   COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
            FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
            WHERE ue.completed_date IS NOT NULL AND ue.is_cash AND ue.ph_user_id IS NOT NULL
            UNION ALL
            SELECT al.company, al.bot_key, ue.completed_date, 'completed_base',
                   COALESCE(ue.ph_user_id::text, ue.tg_user_id::text)
            FROM attributed_leads al JOIN user_events ue ON ue.tg_user_id = al.tg_user_id
            WHERE ue.completed_date IS NOT NULL AND ue.is_base AND ue.ph_user_id IS NOT NULL
        )
        SELECT
            DATE_TRUNC('week', event_date)::date AS week_start,
            company,
            bot_key,
            COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'platform_cnt') AS platform_cnt,
            COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'learning') AS learning,
            COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'started_learning') AS started_learning,
            COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'mtt') AS mtt,
            COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'spin') AS spin,
            COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'cash') AS cash,
            COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'base') AS base,
            COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'not_started') AS not_started,
            COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'completed_course') AS completed_course,
            COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'completed_mtt') AS completed_mtt,
            COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'completed_spin') AS completed_spin,
            COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'completed_cash') AS completed_cash,
            COUNT(DISTINCT entity_key) FILTER (WHERE metric = 'completed_base') AS completed_base
        FROM stage_events
        WHERE (CAST(:start AS date) IS NULL OR event_date >= CAST(:start AS date))
          AND (CAST(:end AS date) IS NULL OR event_date <= CAST(:end AS date))
        GROUP BY 1, 2, 3
        """)
        event_stage_rows = (await session.execute(event_stage_query, params)).fetchall()

        company_map = {(row["week_start"], row["company"]): row for row in rows_payload}
        bot_map = {(row["week_start"], row["company"], row["bot_key"]): row for row in bot_rows_payload}
        for event_row in event_stage_rows:
            week_key = event_row.week_start.isoformat()
            company_key = (week_key, event_row.company)
            company_row = company_map.get(company_key)
            if company_row is None:
                company_row = {
                    "week_start": week_key,
                    "company": event_row.company,
                    "entered_all": 0,
                    "budget": 0.0,
                    **{k: 0 for k in METRIC_KEYS},
                }
                rows_payload.append(company_row)
                company_map[company_key] = company_row
            bot_key = (week_key, event_row.company, event_row.bot_key)
            bot_row = bot_map.get(bot_key)
            if bot_row is None:
                bot_row = {
                    "week_start": week_key,
                    "company": event_row.company,
                    "bot_key": event_row.bot_key,
                    "entered_all": 0,
                    "budget": 0.0,
                    **{k: 0 for k in METRIC_KEYS},
                }
                bot_rows_payload.append(bot_row)
                bot_map[bot_key] = bot_row
            for key in event_metric_keys:
                value = int(getattr(event_row, key) or 0)
                company_row[key] += value
                bot_row[key] = value

        rows_payload.sort(key=lambda row: (row["week_start"], row["company"]), reverse=True)
        bot_rows_payload.sort(key=lambda row: (row["week_start"], row["company"], row["bot_key"]), reverse=True)

    payload = {
        "rows": rows_payload,
        "bot_rows": bot_rows_payload,
        "week_totals": week_totals_payload,
    }
    primary_ttl = settings.weekly_cache_ttl_seconds
    stale_ttl = max(primary_ttl * 7, 7 * 24 * 60 * 60)
    await cache.set_json(cache_key, payload, ttl=primary_ttl)
    await cache.set_json(stale_key, payload, ttl=stale_ttl)
    return payload


@router.get("/roistat-weekly/tree", summary="Дерево Roistat Weekly: платформа → кабинет → бот")
async def roistat_weekly_tree(
    event_start: Optional[date] = Query(None),
    event_end: Optional[date] = Query(None),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    from sqlalchemy import text as sa_text

    params: dict[str, Any] = {
        "start": event_start,
        "end": event_end,
        "excluded_bot_keys": normalized_excluded_bot_keys(),
    }
    query = sa_text("""
        WITH first_seen AS (
            SELECT tg_user_id, MIN(created_at) AS first_seen_at_system
            FROM raw_bot_users
            WHERE LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY tg_user_id
        ),
        lead_rows AS (
            SELECT DISTINCT ON (r.tg_user_id)
                r.tg_user_id,
                r.bot_key,
                COALESCE(r.advertising_company, 'Без категории') AS company,
                (r.created_at AT TIME ZONE 'Europe/Moscow')::date AS lead_date,
                fs.first_seen_at_system
            FROM raw_bot_users r
            JOIN first_seen fs ON fs.tg_user_id = r.tg_user_id
            WHERE lower(trim(r.bot_key)) LIKE 'lead%'
              AND r.tg_user_id > 0
              AND LOWER(TRIM(COALESCE(r.bot_key, ''))) <> ALL(:excluded_bot_keys)
              AND r.created_at IS NOT NULL
              AND (CAST(:start AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date))
            ORDER BY r.tg_user_id, r.created_at
        ),
        user_flags AS (
            SELECT
                tg_user_id,
                BOOL_OR(ph_user_id IS NOT NULL AND platform_registered_at IS NOT NULL) AS did_platform,
                MIN(ph_user_id) FILTER (
                    WHERE ph_user_id IS NOT NULL AND platform_registered_at IS NOT NULL
                ) AS ph_user_id,
                BOOL_OR(learn_start_date IS NOT NULL) AS did_learning,
                BOOL_OR(completed_course IS TRUE AND completed_course_at IS NOT NULL) AS did_complete,
                BOOL_OR(interview_reached IS TRUE) AS did_interview,
                BOOL_OR(offer_received IS TRUE) AS did_offer,
                BOOL_OR(contract_signed IS TRUE) AS did_contract,
                BOOL_OR(distance_grinding IS TRUE) AS did_distance,
                BOOL_OR(LOWER(TRIM(COALESCE(start_course, ''))) LIKE 'mtt%') AS is_mtt,
                BOOL_OR(LOWER(TRIM(COALESCE(start_course, ''))) LIKE 'spin%') AS is_spin,
                BOOL_OR(LOWER(TRIM(COALESCE(start_course, ''))) LIKE 'cash%') AS is_cash,
                BOOL_OR(LOWER(TRIM(COALESCE(start_course, ''))) LIKE 'base%') AS is_base,
                BOOL_OR(
                    lower(trim(COALESCE(bot_key, ''))) LIKE 'lead%'
                    AND tg_user_id > 0
                    AND ph_user_id IS NOT NULL
                    AND abs(tg_user_id) = ph_user_id
                ) AS is_direct_source
            FROM raw_bot_users
            WHERE tg_user_id IN (SELECT tg_user_id FROM lead_rows)
              AND LOWER(TRIM(COALESCE(bot_key, ''))) <> ALL(:excluded_bot_keys)
            GROUP BY tg_user_id
        )
        SELECT
            COALESCE(ac.platform, 'Без источника') AS platform,
            lr.company,
            lr.bot_key AS bot,
            COUNT(DISTINCT CASE WHEN lr.tg_user_id > 0 AND NOT uf.is_direct_source THEN lr.tg_user_id END) AS almanah_starts,
            COUNT(DISTINCT CASE WHEN uf.is_direct_source AND uf.ph_user_id IS NOT NULL THEN uf.ph_user_id END) AS direct_source_cnt,
            COUNT(DISTINCT CASE WHEN (lr.first_seen_at_system AT TIME ZONE 'Europe/Moscow')::date = lr.lead_date THEN lr.tg_user_id END) AS new_in_system,
            COUNT(DISTINCT CASE WHEN uf.ph_user_id IS NOT NULL AND NOT uf.is_direct_source THEN uf.ph_user_id END) AS platform_cnt,
            COUNT(DISTINCT CASE WHEN uf.did_learning THEN lr.tg_user_id END) AS started_learning,
            COUNT(DISTINCT CASE WHEN uf.did_complete THEN lr.tg_user_id END) AS completed_course,
            COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_mtt THEN lr.tg_user_id END) AS completed_mtt,
            COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_spin THEN lr.tg_user_id END) AS completed_spin,
            COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_cash THEN lr.tg_user_id END) AS completed_cash,
            COUNT(DISTINCT CASE WHEN uf.did_complete AND uf.is_base THEN lr.tg_user_id END) AS completed_base,
            COUNT(DISTINCT CASE WHEN uf.did_interview THEN lr.tg_user_id END) AS interview_reached,
            COUNT(DISTINCT CASE WHEN uf.did_offer THEN lr.tg_user_id END) AS offer_received,
            COUNT(DISTINCT CASE WHEN uf.did_contract THEN lr.tg_user_id END) AS contract_signed,
            COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_mtt THEN lr.tg_user_id END) AS contract_mtt,
            COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_spin THEN lr.tg_user_id END) AS contract_spin,
            COUNT(DISTINCT CASE WHEN uf.did_contract AND uf.is_cash THEN lr.tg_user_id END) AS contract_cash,
            COUNT(DISTINCT CASE WHEN uf.did_distance THEN lr.tg_user_id END) AS distance_grinding
        FROM lead_rows lr
        JOIN user_flags uf ON uf.tg_user_id = lr.tg_user_id
        LEFT JOIN advertising_company_bots acb ON acb.bot_key = lr.bot_key
        LEFT JOIN advertising_companies ac ON ac.company_id = acb.company_id
        GROUP BY COALESCE(ac.platform, 'Без источника'), lr.company, lr.bot_key
        ORDER BY COALESCE(ac.platform, 'Без источника'), lr.company, lr.bot_key
    """)
    result = await session.execute(query, params)
    rows = result.fetchall()

    METRIC_KEYS = [
        "almanah_starts", "direct_source_cnt", "new_in_system", "platform_cnt", "started_learning",
        "completed_course", "completed_mtt", "completed_spin", "completed_cash", "completed_base",
        "interview_reached", "offer_received", "contract_signed",
        "contract_mtt", "contract_spin", "contract_cash", "distance_grinding",
    ]

    def sum_metrics(items: list[dict]) -> dict:
        return {k: sum(m[k] for m in items) for k in METRIC_KEYS}

    tree_map: dict = {}
    for row in rows:
        p, c, b = row.platform, row.company, row.bot
        metrics = {k: int(getattr(row, k) or 0) for k in METRIC_KEYS}
        tree_map.setdefault(p, {}).setdefault(c, {})[b] = metrics

    tree = []
    for plat, companies in sorted(tree_map.items()):
        company_nodes = []
        for comp, bots in sorted(companies.items()):
            bot_nodes = [{"bot": b, **m} for b, m in sorted(bots.items())]
            company_nodes.append({"company": comp, **sum_metrics(bot_nodes), "bots": bot_nodes})
        tree.append({"source": plat, **sum_metrics(company_nodes), "companies": company_nodes})
    return {"tree": tree}


@router.get("/roistat-weekly", summary="Weekly для Roistat", response_model=RoistatWeeklyReportResponse)
async def roistat_weekly(
    event_start: Optional[date] = Query(None),
    event_end: Optional[date] = Query(None),
    first_touch_start: Optional[date] = Query(None),
    first_touch_end: Optional[date] = Query(None),
    mode: str = Query("event", pattern="^(event|first_touch|last_touch)$"),
    bots: List[str] = Query(default=[]),
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
    bots_key = ",".join(sorted(bots)) if bots else ""
    cache_key = (
        "reports:roistat_weekly:v6:"
        f"{mode}:{event_start}:{event_end}:{first_touch_start}:{first_touch_end}:{bots_key}"
    )
    stale_key = f"{cache_key}:stale"
    lock_key = f"{cache_key}:lock"

    async def build_payload(session_local) -> list[dict[str, Any]]:
        company_payload = await roistat_weekly_by_company(
            event_start=event_start,
            event_end=event_end,
            mode=mode,
            first_touch_start=first_touch_start,
            first_touch_end=first_touch_end,
            display_mode="weekly",
            bots=bots or None,
            advertising_companies=None,
            utm_source=None,
            utm_campaign=None,
            utm_medium=None,
            utm_content=None,
            utm_term=None,
            session=session_local,
        )
        ph_mirror_weekly: dict[str, int] = {}
        if mode == "event" and not bots:
            ph_mirror_weekly = await _load_ph_mirror_weekly_counts(event_start, event_end)
        metric_keys = [
            "almanah_starts",
            "direct_source_cnt",
            "new_in_system",
            "old_in_system",
            "platform_cnt",
            "learning",
            "started_learning",
            "mtt",
            "spin",
            "cash",
            "base",
            "not_started",
            "channel_subscribed",
            "saloon",
            "completed_course",
            "completed_base",
            "distance_grinding",
            "contract_signed",
            "entered_all",
            "interview_reached",
            "offer_received",
            "completed_mtt",
            "completed_spin",
            "completed_cash",
            "contract_mtt",
            "contract_spin",
            "contract_cash",
        ]
        weekly_map: dict[str, dict[str, Any]] = {}
        for row in company_payload.get("rows", []):
            week_key = row["week_start"]
            current = weekly_map.setdefault(
                week_key,
                {
                    "week_start": week_key,
                    "budget": 0.0,
                    **{key: 0 for key in metric_keys},
                },
            )
            current["budget"] += float(row.get("budget") or 0.0)
            for key in metric_keys:
                current[key] += int(row.get(key) or 0)

        if ph_mirror_weekly:
            for week_key, value in ph_mirror_weekly.items():
                current = weekly_map.setdefault(
                    week_key,
                    {
                        "week_start": week_key,
                        "budget": 0.0,
                        **{key: 0 for key in metric_keys},
                    },
                )
                current["platform_cnt"] = value

        rows = sorted(weekly_map.values(), key=lambda row: row["week_start"])
        return [
            RoistatWeeklyRow(
                week_start=row["week_start"],
                almanah_starts=row["almanah_starts"],
                direct_source_cnt=row["direct_source_cnt"],
                new_in_system=row["new_in_system"],
                old_in_system=row["old_in_system"],
                platform=row["platform_cnt"],
                learning=row["learning"],
                started_learning=row["started_learning"],
                mtt=row["mtt"],
                spin=row["spin"],
                cash=row["cash"],
                base=row["base"],
                not_started=row["not_started"],
                channel_subscribed=row["channel_subscribed"],
                saloon=row["saloon"],
                completed_course=row["completed_course"],
                completed_base=row["completed_base"],
                distance_grinding=row["distance_grinding"],
                contract_signed=row["contract_signed"],
                budget=row["budget"],
                entered_all=row["entered_all"],
                interview_reached=row["interview_reached"],
                offer_received=row["offer_received"],
                completed_mtt=row["completed_mtt"],
                completed_spin=row["completed_spin"],
                completed_cash=row["completed_cash"],
                contract_mtt=row["contract_mtt"],
                contract_spin=row["contract_spin"],
                contract_cash=row["contract_cash"],
            ).model_dump()
            for row in rows
        ]

    async def store_payload(payload: list[dict[str, Any]]) -> None:
        primary_ttl = settings.weekly_cache_ttl_seconds
        stale_ttl = max(primary_ttl * 7, 7 * 24 * 60 * 60)
        await cache.set_json(cache_key, payload, ttl=primary_ttl)
        await cache.set_json(stale_key, payload, ttl=stale_ttl)

    async def build_and_cache(session_local) -> list[dict[str, Any]]:
        payload = await build_payload(session_local)
        await store_payload(payload)
        return payload

    cached_map = await cache.get_json_many([cache_key, stale_key])
    cached = cached_map.get(cache_key)
    if cached is not None:
        return RoistatWeeklyReportResponse(rows=[RoistatWeeklyRow(**row) for row in cached])

    stale = cached_map.get(stale_key)
    if stale is not None:
        if await cache.set_if_not_exists(lock_key, "1", ttl=60):
            async def refresh_in_background() -> None:
                try:
                    async with async_session() as bg_session:
                        await build_and_cache(bg_session)
                finally:
                    await cache.delete(lock_key)
            asyncio.create_task(refresh_in_background())
        return RoistatWeeklyReportResponse(rows=[RoistatWeeklyRow(**row) for row in stale])

    if await cache.set_if_not_exists(lock_key, "1", ttl=120):
        try:
            payload = await build_and_cache(session)
        finally:
            await cache.delete(lock_key)
        return RoistatWeeklyReportResponse(rows=[RoistatWeeklyRow(**row) for row in payload])

    await asyncio.sleep(0.5)
    cached_map = await cache.get_json_many([cache_key, stale_key])
    fallback = cached_map.get(cache_key) or cached_map.get(stale_key)
    if fallback is not None:
        return RoistatWeeklyReportResponse(rows=[RoistatWeeklyRow(**row) for row in fallback])

    payload = await build_and_cache(session)
    return RoistatWeeklyReportResponse(rows=[RoistatWeeklyRow(**row) for row in payload])


@router.get("/roistat-lessons", summary="Матрица уроков PokerHub для Roistat", response_model=RoistatLessonsReportResponse)
async def roistat_lessons(
    filters: ReportFilters = Depends(get_report_filters),
    pokerhub_user_id: Optional[str] = Query(None),
    learn_start_date_from: Optional[date] = Query(None),
    learn_start_date_to: Optional[date] = Query(None),
    session=Depends(get_db_session),
):
    effective_learn_start_from = learn_start_date_from
    effective_learn_start_to = learn_start_date_to
    if effective_learn_start_from and effective_learn_start_to and effective_learn_start_to < effective_learn_start_from:
        raise HTTPException(status_code=400, detail="learn_start_date_to must be after learn_start_date_from")

    cache = RedisCache()
    cache_key = "reports:roistat_lessons:" + json.dumps(
        {
            "cache_v": 5,
            "start_date": filters.start_date.isoformat() if filters.start_date else None,
            "end_date": filters.end_date.isoformat() if filters.end_date else None,
            "learn_start_date_from": effective_learn_start_from.isoformat() if effective_learn_start_from else None,
            "learn_start_date_to": effective_learn_start_to.isoformat() if effective_learn_start_to else None,
            "bots": filters.bots,
            "advertising_companies": filters.advertising_companies,
            "utm_source": filters.utm_source,
            "utm_campaign": filters.utm_campaign,
            "utm_medium": filters.utm_medium,
            "utm_content": filters.utm_content,
            "utm_term": filters.utm_term,
            "user_scope": filters.user_scope,
            "pokerhub_user_id": pokerhub_user_id,
        },
        sort_keys=True,
    )
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return RoistatLessonsReportResponse(**cached)

    courses = await RoistatLessonsReport().build(
        session,
        filters,
        pokerhub_user_id=pokerhub_user_id,
        learn_start_date_from=effective_learn_start_from,
        learn_start_date_to=effective_learn_start_to,
    )
    response = RoistatLessonsReportResponse(
        courses=[
            RoistatLessonCourse(
                course=course.course,
                total_lessons=course.total_lessons,
                columns=[
                    RoistatLessonColumn(
                        key=column.key,
                        label=column.label,
                        module=column.module,
                        lesson=column.lesson,
                    )
                    for column in course.columns
                ],
                rows=[
                    RoistatLessonUserRow(
                        tg_user_id=row.tg_user_id,
                        username=row.username,
                        pokerhub_user_id=row.pokerhub_user_id,
                        completed_lessons=row.completed_lessons,
                        lessons=row.lessons,
                    )
                    for row in course.rows
                ],
            )
            for course in courses
        ]
    )
    await cache.set_json(cache_key, response.model_dump(), ttl=300)
    return response


@router.get("/subscriptions/compare", summary="Старты ботов vs подписки/отписки")
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
    interval: str = Query("week", regex="^(day|week)$"),
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
