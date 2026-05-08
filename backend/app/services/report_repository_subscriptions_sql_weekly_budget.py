from datetime import date as dt_date, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import BudgetWeekly


def _apply_common_budget_filters(
    stmt,
    *,
    start_date_obj: Optional[dt_date],
    end_date_obj: Optional[dt_date],
    utm_source: Optional[list[str]],
    utm_campaign: Optional[list[str]],
    utm_medium: Optional[list[str]],
    utm_content: Optional[list[str]],
    utm_term: Optional[list[str]],
):
    if start_date_obj:
        stmt = stmt.where(func.coalesce(BudgetWeekly.period_end, BudgetWeekly.week_start) >= start_date_obj)
    if end_date_obj:
        stmt = stmt.where(BudgetWeekly.week_start <= end_date_obj)
    if utm_source:
        stmt = stmt.where(func.coalesce(BudgetWeekly.utm_source, "").in_(utm_source))
    if utm_campaign:
        stmt = stmt.where(func.coalesce(BudgetWeekly.utm_campaign, "").in_(utm_campaign))
    if utm_medium:
        stmt = stmt.where(func.coalesce(BudgetWeekly.utm_medium, "").in_(utm_medium))
    if utm_content:
        stmt = stmt.where(func.coalesce(BudgetWeekly.utm_content, "").in_(utm_content))
    if utm_term:
        stmt = stmt.where(func.coalesce(BudgetWeekly.utm_term, "").in_(utm_term))
    return stmt


async def load_total_and_channel_budget(
    session: AsyncSession,
    *,
    start_date_obj: Optional[dt_date],
    end_date_obj: Optional[dt_date],
    utm_source: Optional[list[str]],
    utm_campaign: Optional[list[str]],
    utm_medium: Optional[list[str]],
    utm_content: Optional[list[str]],
    utm_term: Optional[list[str]],
) -> tuple[float, dict[str, float]]:
    budget_stmt = select(func.coalesce(func.sum(BudgetWeekly.amount), 0.0)).where(
        func.lower(func.coalesce(BudgetWeekly.channel_key, "")).in_(["card_house", "saloon"])
    )
    budget_stmt = _apply_common_budget_filters(
        budget_stmt,
        start_date_obj=start_date_obj,
        end_date_obj=end_date_obj,
        utm_source=utm_source,
        utm_campaign=utm_campaign,
        utm_medium=utm_medium,
        utm_content=utm_content,
        utm_term=utm_term,
    )
    budget_total = float((await session.execute(budget_stmt)).scalar() or 0.0)

    channel_budget_stmt = (
        select(
            BudgetWeekly.channel_key.label("channel_key"),
            func.coalesce(func.sum(BudgetWeekly.amount), 0.0).label("amount"),
        )
        .where(func.lower(func.coalesce(BudgetWeekly.channel_key, "")).in_(["card_house", "saloon"]))
        .group_by(BudgetWeekly.channel_key)
    )
    channel_budget_stmt = _apply_common_budget_filters(
        channel_budget_stmt,
        start_date_obj=start_date_obj,
        end_date_obj=end_date_obj,
        utm_source=utm_source,
        utm_campaign=utm_campaign,
        utm_medium=utm_medium,
        utm_content=utm_content,
        utm_term=utm_term,
    )
    channel_budget_rows = (await session.execute(channel_budget_stmt)).all()
    explicit_channel_budget: dict[str, float] = {}
    for b_row in channel_budget_rows:
        key = (b_row.channel_key or "").strip().lower()
        amount = float(b_row.amount or 0.0)
        if key:
            explicit_channel_budget[key] = explicit_channel_budget.get(key, 0.0) + amount
    return budget_total, explicit_channel_budget


async def load_weekly_explicit_budget(
    session: AsyncSession,
    *,
    start_date_obj: Optional[dt_date],
    end_date_obj: Optional[dt_date],
    utm_source: Optional[list[str]],
    utm_campaign: Optional[list[str]],
    utm_medium: Optional[list[str]],
    utm_content: Optional[list[str]],
    utm_term: Optional[list[str]],
) -> dict[tuple[str, dt_date], float]:
    budget_weekly_stmt = (
        select(
            BudgetWeekly.week_start.label("week_start"),
            BudgetWeekly.channel_key.label("channel_key"),
            func.coalesce(func.sum(BudgetWeekly.amount), 0.0).label("amount"),
        )
        .where(func.lower(func.coalesce(BudgetWeekly.channel_key, "")).in_(["card_house", "saloon"]))
        .group_by(BudgetWeekly.week_start, BudgetWeekly.channel_key)
    )
    budget_weekly_stmt = _apply_common_budget_filters(
        budget_weekly_stmt,
        start_date_obj=start_date_obj,
        end_date_obj=end_date_obj,
        utm_source=utm_source,
        utm_campaign=utm_campaign,
        utm_medium=utm_medium,
        utm_content=utm_content,
        utm_term=utm_term,
    )
    weekly_budget_rows = (await session.execute(budget_weekly_stmt)).all()

    def _week_start(value: dt_date) -> dt_date:
        return value - timedelta(days=value.weekday())

    weekly_explicit: dict[tuple[str, dt_date], float] = {}
    for wb in weekly_budget_rows:
        wk_raw = wb.week_start
        key = (wb.channel_key or "").strip().lower()
        amount = float(wb.amount or 0.0)
        if not wk_raw:
            continue
        wk = _week_start(wk_raw)
        if key:
            weekly_explicit[(key, wk)] = weekly_explicit.get((key, wk), 0.0) + amount
    return weekly_explicit


def build_channel_funnel_rows(
    *,
    funnel_rows,
    label_map: dict[str, str],
    channel_key_map: dict[str, str],
    explicit_channel_budget: dict[str, float],
    pct_fn,
    safe_cost_fn,
) -> list[dict[str, object]]:
    channel_funnel: list[dict[str, object]] = []
    for row in funnel_rows:
        total_in_channel = int(row.total_in_channel or 0)
        in_bot = int(row.in_bot or 0)
        registrations = int(row.registrations or 0)
        started_learning = int(row.started_learning or 0)
        completed_course = int(row.completed_course or 0)
        contract_signed = int(row.contract_signed or 0)
        channel_key = channel_key_map.get(str(row.chat_id), "")
        allocated_budget = explicit_channel_budget.get(channel_key, 0.0)
        channel_funnel.append(
            {
                "chat_id": str(row.chat_id),
                "label": label_map.get(str(row.chat_id), str(row.chat_id)),
                "channel_key": channel_key,
                "total_in_channel": total_in_channel,
                "in_bot": in_bot,
                "registrations": registrations,
                "started_learning": started_learning,
                "completed_course": completed_course,
                "contract_signed": contract_signed,
                "pct_in_bot": pct_fn(in_bot, total_in_channel),
                "pct_registration": pct_fn(registrations, in_bot),
                "pct_learning": pct_fn(started_learning, registrations),
                "pct_completed": pct_fn(completed_course, started_learning),
                "pct_contract": pct_fn(contract_signed, completed_course),
                "budget": round(allocated_budget, 2),
                "start_in_bot_cost": safe_cost_fn(allocated_budget, in_bot),
                "registration_cost": safe_cost_fn(allocated_budget, registrations),
                "started_learning_cost": safe_cost_fn(allocated_budget, started_learning),
                "completed_course_cost": safe_cost_fn(allocated_budget, completed_course),
                "contract_cost": safe_cost_fn(allocated_budget, contract_signed),
            }
        )
    return channel_funnel
