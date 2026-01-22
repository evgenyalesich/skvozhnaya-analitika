from fastapi import APIRouter

from app.core.config_loader import ConfigLoader

router = APIRouter(prefix="/api/utm", tags=["utm"])


def _collect_field(field: str) -> list[str]:
    loader = ConfigLoader()
    values = set()
    for company in loader.advertising_companies():
        for bot in company.get("bots", []):
            utms = bot.get("utm_tags", [])
            for utm in utms:
                if value := utm.get(field):
                    values.add(value)
    return sorted(values)


@router.get("/sources", summary="Список UTM Source")
def list_sources():
    return {"sources": _collect_field("utm_source")}


@router.get("/campaigns", summary="Список UTM Campaign")
def list_campaigns():
    return {"campaigns": _collect_field("utm_campaign")}


@router.get("/mediums", summary="Список UTM Medium")
def list_mediums():
    return {"mediums": _collect_field("utm_medium")}


@router.get("/contents", summary="Список UTM Content")
def list_contents():
    return {"contents": _collect_field("utm_content")}


@router.get("/terms", summary="Список UTM Term")
def list_terms():
    return {"terms": _collect_field("utm_term")}
