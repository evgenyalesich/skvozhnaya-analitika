from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_db_session
from app.schemas.ad_metrics import AdMetricsWeeklyCreate, AdMetricsWeeklyOut, AdMetricsWeeklyUpdate
from app.models.analytics import AdMetricsWeekly
from app.services.ad_metrics_service import AdMetricsService

router = APIRouter(prefix="/api/ad-metrics", tags=["ad-metrics"])
service = AdMetricsService()


@router.get("", summary="Список недельных рекламных метрик", response_model=list[AdMetricsWeeklyOut])
async def list_ad_metrics(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    session=Depends(get_db_session),
):
    rows = await service.list_rows(session, start_date, end_date)
    return [AdMetricsWeeklyOut.model_validate(row) for row in rows]


@router.post("", summary="Создать недельные рекламные метрики", response_model=AdMetricsWeeklyOut)
async def create_ad_metrics(payload: AdMetricsWeeklyCreate, session=Depends(get_db_session)):
    week_start = payload.week_start - timedelta(days=payload.week_start.weekday())
    row = AdMetricsWeekly(
        week_start=week_start,
        campaign=payload.campaign.strip(),
        bot_key=(payload.bot_key or "").strip() or None,
        impressions=payload.impressions,
        clicks=payload.clicks,
        spend=payload.spend,
    )
    await service.create(session, row)
    await session.commit()
    await session.refresh(row)
    return AdMetricsWeeklyOut.model_validate(row)


@router.put("/{row_id}", summary="Обновить недельные рекламные метрики", response_model=AdMetricsWeeklyOut)
async def update_ad_metrics(
    row_id: int,
    payload: AdMetricsWeeklyUpdate,
    session=Depends(get_db_session),
):
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "week_start" in patch:
        patch["week_start"] = patch["week_start"] - timedelta(days=patch["week_start"].weekday())
    if "campaign" in patch:
        patch["campaign"] = patch["campaign"].strip()
    if "bot_key" in patch:
        patch["bot_key"] = (patch["bot_key"] or "").strip() or None
    if "spend" in patch:
        patch["spend"] = patch["spend"]
    row = await service.update(session, row_id, patch)
    if not row:
        raise HTTPException(status_code=404, detail="Ad metrics not found")
    await session.commit()
    return AdMetricsWeeklyOut.model_validate(row)


@router.delete("/{row_id}", summary="Удалить недельные рекламные метрики")
async def delete_ad_metrics(row_id: int, session=Depends(get_db_session)):
    row = await service.get(session, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Ad metrics not found")
    await service.delete(session, row_id)
    await session.commit()
    return {"status": "ok"}
