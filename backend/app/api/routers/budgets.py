from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_db_session
from app.schemas.budget import BudgetWeeklyCreate, BudgetWeeklyOut, BudgetWeeklyUpdate
from app.models.analytics import BudgetWeekly
from app.services.budget_service import BudgetService
from app.services.ad_metrics_service import AdMetricsService

router = APIRouter(prefix="/api/budgets", tags=["budgets"])
service = BudgetService()
ad_metrics_service = AdMetricsService()


@router.get("", summary="Список недельных бюджетов", response_model=list[BudgetWeeklyOut])
async def list_budgets(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    session=Depends(get_db_session),
):
    rows = await service.list_budgets(session, start_date, end_date)
    return [BudgetWeeklyOut.model_validate(row) for row in rows]


@router.post("", summary="Создать недельный бюджет", response_model=BudgetWeeklyOut)
async def create_budget(payload: BudgetWeeklyCreate, session=Depends(get_db_session)):
    week_start = payload.week_start - timedelta(days=payload.week_start.weekday())
    row = BudgetWeekly(
        week_start=week_start,
        campaign=payload.campaign.strip(),
        bot_key=(payload.bot_key or "").strip() or None,
        amount=payload.amount,
        currency=payload.currency,
    )
    await service.create_budget(session, row)
    await ad_metrics_service.upsert_spend(
        session,
        week_start=week_start,
        campaign=row.campaign,
        bot_key=row.bot_key,
        spend=row.amount,
    )
    await session.commit()
    await session.refresh(row)
    return BudgetWeeklyOut.model_validate(row)


@router.put("/{budget_id}", summary="Обновить недельный бюджет", response_model=BudgetWeeklyOut)
async def update_budget(
    budget_id: int,
    payload: BudgetWeeklyUpdate,
    session=Depends(get_db_session),
):
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "week_start" in patch:
        patch["week_start"] = patch["week_start"] - timedelta(days=patch["week_start"].weekday())
    if "campaign" in patch:
        patch["campaign"] = patch["campaign"].strip()
    if "bot_key" in patch:
        patch["bot_key"] = (patch["bot_key"] or "").strip() or None
    row = await service.update_budget(session, budget_id, patch)
    if not row:
        raise HTTPException(status_code=404, detail="Budget not found")
    await ad_metrics_service.upsert_spend(
        session,
        week_start=row.week_start,
        campaign=row.campaign,
        bot_key=row.bot_key,
        spend=row.amount,
    )
    await session.commit()
    return BudgetWeeklyOut.model_validate(row)


@router.delete("/{budget_id}", summary="Удалить недельный бюджет")
async def delete_budget(budget_id: int, session=Depends(get_db_session)):
    row = await service.get_budget(session, budget_id)
    if not row:
        raise HTTPException(status_code=404, detail="Budget not found")
    await service.delete_budget(session, budget_id)
    await session.commit()
    return {"status": "ok"}
