import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_db_session
from app.core.redis_client import RedisCache
from app.db.session import async_session
from app.schemas.advertising_company import AdvertisingCompanyUpsert
from app.services.advertising_company_service import AdvertisingCompanyService
from app.services.attribution_service import AttributionService

router = APIRouter(prefix="/api/advertising-companies", tags=["advertising-companies"])
service = AdvertisingCompanyService()
_logger = logging.getLogger("advertising_companies")
_REBUILD_LOCK_KEY = "locks:advertising_rebuild"


async def _run_rebuild() -> None:
    cache = RedisCache()
    try:
        async with async_session() as session:
            await AdvertisingCompanyService().rebuild_assignments(session)
            await AttributionService().rebuild_in_session(session)
            await session.commit()
    except Exception as exc:
        _logger.error("Advertising rebuild failed: %s", exc, exc_info=True)
    finally:
        try:
            await cache.delete(_REBUILD_LOCK_KEY)
        except Exception:
            pass


async def _schedule_rebuild() -> None:
    cache = RedisCache()
    locked = await cache.set_if_not_exists(_REBUILD_LOCK_KEY, "running", ttl=300)
    if locked:
        await _run_rebuild()


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
        platform=payload.platform,
        utm_rules=payload.utm_rules,
    )
    await session.commit()
    asyncio.create_task(_schedule_rebuild())
    return result


@router.post("/bulk", summary="Создать/обновить рекламные компании пакетом")
async def upsert_companies_bulk(payload: list[AdvertisingCompanyUpsert], session=Depends(get_db_session)):
    results = []
    for company in payload:
        result = await service.upsert_company(
            session,
            company_id=company.company_id,
            company_name=company.company_name,
            is_active=company.is_active,
            bot_keys=company.bot_keys,
            platform=company.platform,
            utm_rules=company.utm_rules,
        )
        results.append(result)
    await session.commit()
    asyncio.create_task(_schedule_rebuild())
    return {"advertising_companies": results}


@router.post("/rebuild", summary="Пересчитать привязку РК для всех пользователей")
async def rebuild_company_assignments(session=Depends(get_db_session)):
    await service.rebuild_assignments(session)
    await session.commit()
    return {"status": "ok"}


@router.post("/rebuild-attribution", summary="Пересчитать first/last touch для всех пользователей")
async def rebuild_attribution(session=Depends(get_db_session)):
    await AttributionService().rebuild_in_session(session)
    await session.commit()
    return {"status": "ok"}

@router.delete("/{company_id}", summary="Удалить рекламную компанию")
async def delete_company(company_id: str, session=Depends(get_db_session)):
    deleted = await service.delete_company(session, company_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Company not found")
    await session.commit()
    asyncio.create_task(_schedule_rebuild())
    return {"status": "ok"}


@router.get("/{company_id}/bots", summary="Список ботов компании")
async def company_bots(company_id: str, session=Depends(get_db_session)):
    companies = await service.list_companies(session)
    for company in companies:
        if company["company_id"] == company_id:
            return {"bots": company["bot_keys"]}
    raise HTTPException(status_code=404, detail="Company not found")
