from fastapi import APIRouter

from app.core.config_loader import ConfigLoader

router = APIRouter(prefix="/api/bots", tags=["bots"])


@router.get("", summary="Список всех ботов")
def list_bots():
    loader = ConfigLoader()
    return {"bots": loader.bots()}
