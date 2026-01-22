from fastapi import APIRouter, HTTPException

from app.core.config_loader import ConfigLoader

router = APIRouter(prefix="/api/advertising-companies", tags=["advertising-companies"])


@router.get("", summary="Список рекламных компаний")
def list_companies():
    loader = ConfigLoader()
    companies = loader.advertising_companies()
    return {"advertising_companies": companies}


@router.get("/{company_id}/bots", summary="Список ботов компании")
def company_bots(company_id: str):
    loader = ConfigLoader()
    company = loader.advertising_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return {"bots": company.get("bots", [])}


@router.get("/{company_id}/utm-tags", summary="UTM-теги компании")
def company_utm_tags(company_id: str):
    loader = ConfigLoader()
    company = loader.advertising_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    tags: list[dict[str, str]] = []
    for bot in company.get("bots", []):
        for tag in bot.get("utm_tags", []):
            tags.append({
                "bot_key": bot.get("bot_key"),
                "utm_source": tag.get("utm_source"),
                "utm_campaign": tag.get("utm_campaign"),
            })
    return {"utm_tags": tags}
