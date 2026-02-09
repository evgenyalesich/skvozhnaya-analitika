from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_db_session
from app.schemas.advertising_company import AdvertisingCompanyUpsert
from app.services.advertising_company_service import AdvertisingCompanyService
from app.services.attribution_service import AttributionService

router = APIRouter(prefix="/api/advertising-companies", tags=["advertising-companies"])
service = AdvertisingCompanyService()


@router.get("", summary="Список рекламных компаний")
async def list_companies(session=Depends(get_db_session)):
    companies = await service.list_companies(session)
    return {"advertising_companies": companies}


@router.post("", summary="Создать/обновить рекламную компанию")
async def upsert_company(payload: AdvertisingCompanyUpsert, session=Depends(get_db_session)):
    result = await service.upsert_company(
        session,
        company_id=payload.company_id,
        company_name=payload.company_name,
        is_active=payload.is_active,
        bot_keys=payload.bot_keys,
    )
    await service.rebuild_assignments(session)
    await AttributionService().rebuild_in_session(session)
    await session.commit()
    return result


@router.post("/rebuild", summary="Пересчитать привязку РК для всех пользователей")
async def rebuild_company_assignments(session=Depends(get_db_session)):
    await service.rebuild_assignments(session)
    await session.commit()
    return {"status": "ok"}


@router.get("/{company_id}/bots", summary="Список ботов компании")
async def company_bots(company_id: str, session=Depends(get_db_session)):
    companies = await service.list_companies(session)
    for company in companies:
        if company["company_id"] == company_id:
            return {"bots": company["bot_keys"]}
    raise HTTPException(status_code=404, detail="Company not found")


@router.get("/{company_id}/utm-tags", summary="UTM-теги компании")
def company_utm_tags(company_id: str):
    raise HTTPException(status_code=404, detail="Company not found")
