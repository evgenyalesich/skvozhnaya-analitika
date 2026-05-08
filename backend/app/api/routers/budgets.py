# CRUD недельных рекламных бюджетов (таблица budget_weekly).
# После каждой записи инвалидируется Redis-кеш отчётов roistat_weekly и subscriptions_vs_starts,
# чтобы следующий запрос отчёта пересчитал данные с учётом нового бюджета.

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_db_session
from app.core.redis_client import RedisCache
from app.schemas.budget import BudgetWeeklyCreate, BudgetWeeklyOut, BudgetWeeklyUpdate
from app.models.analytics import BudgetWeekly
from app.services.budget_service import BudgetService

router = APIRouter(prefix="/api/budgets", tags=["budgets"])
service = BudgetService()


@router.get("", summary="Список недельных бюджетов", response_model=list[BudgetWeeklyOut])
async def list_budgets(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    session=Depends(get_db_session),
):
    rows = await service.list_budgets(session, start_date, end_date)
    return [BudgetWeeklyOut.model_validate(row) for row in rows]


@router.post("", summary="Создать недельный бюджет", response_model=BudgetWeeklyOut)
# period_end по умолчанию = week_start, если не передан явно.
async def create_budget(payload: BudgetWeeklyCreate, session=Depends(get_db_session)):
    period_end = payload.period_end or payload.week_start
    row = BudgetWeekly(
        week_start=payload.week_start,
        period_end=period_end,
        campaign=payload.campaign.strip(),
        bot_key=(payload.bot_key or "").strip() or None,
        channel_key=(payload.channel_key or "").strip() or None,
        utm_source=(payload.utm_source or "").strip() or None,
        utm_campaign=(payload.utm_campaign or "").strip() or None,
        utm_medium=(payload.utm_medium or "").strip() or None,
        utm_content=(payload.utm_content or "").strip() or None,
        utm_term=(payload.utm_term or "").strip() or None,
        amount=payload.amount,
        currency=payload.currency,
    )
    await service.create_budget(session, row)
    await session.commit()
    await session.refresh(row)
    cache = RedisCache()
    await cache.delete_pattern("reports:roistat_weekly:*")
    await cache.delete_pattern("reports:subscriptions_vs_starts:*")
    return BudgetWeeklyOut.model_validate(row)


@router.put("/{budget_id}", summary="Обновить недельный бюджет", response_model=BudgetWeeklyOut)
async def update_budget(
    budget_id: int,
    payload: BudgetWeeklyUpdate,
    session=Depends(get_db_session),
):
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "campaign" in patch:
        patch["campaign"] = patch["campaign"].strip()
    if "bot_key" in patch:
        patch["bot_key"] = (patch["bot_key"] or "").strip() or None
    if "channel_key" in patch:
        patch["channel_key"] = (patch["channel_key"] or "").strip() or None
    for key in ("utm_source", "utm_campaign", "utm_medium", "utm_content", "utm_term"):
        if key in patch:
            patch[key] = (patch[key] or "").strip() or None
    if "period_end" in patch and patch["period_end"] is None and "week_start" in patch:
        patch["period_end"] = patch["week_start"]
    row = await service.update_budget(session, budget_id, patch)
    if not row:
        raise HTTPException(status_code=404, detail="Budget not found")
    await session.commit()
    cache = RedisCache()
    await cache.delete_pattern("reports:roistat_weekly:*")
    await cache.delete_pattern("reports:subscriptions_vs_starts:*")
    return BudgetWeeklyOut.model_validate(row)


@router.delete("/{budget_id}", summary="Удалить недельный бюджет")
async def delete_budget(budget_id: int, session=Depends(get_db_session)):
    row = await service.get_budget(session, budget_id)
    if not row:
        raise HTTPException(status_code=404, detail="Budget not found")
    await service.delete_budget(session, budget_id)
    await session.commit()
    cache = RedisCache()
    await cache.delete_pattern("reports:roistat_weekly:*")
    await cache.delete_pattern("reports:subscriptions_vs_starts:*")
    return {"status": "ok"}
