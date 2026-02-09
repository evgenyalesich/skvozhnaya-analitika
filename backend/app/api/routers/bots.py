from fastapi import APIRouter

from app.db.postgres_explorer import PostgresExplorer
from app.db.session import async_session
from app.schemas.bot_registry import BotRegistryUpsert
from app.services.bot_registry_service import BotRegistryService

router = APIRouter(prefix="/api/bots", tags=["bots"])


@router.get("", summary="Список всех ботов")
async def list_bots():
    explorer = PostgresExplorer()
    databases = await explorer.list_bot_databases()
    async with async_session() as session:
        registry_items = await BotRegistryService().list_registry(session)

    registry_map = {item.bot_key: item for item in registry_items}
    all_keys = sorted(set(databases) | set(registry_map.keys()))
    bots = []
    for key in all_keys:
        registry = registry_map.get(key)
        display_name = registry.display_name if registry and registry.display_name else key
        is_active = registry.is_active if registry else True
        bots.append(
            {
                "bot_key": key,
                "display_name": display_name,
                "is_active": is_active,
                "exists": key in databases,
            }
        )
    return {"bots": bots}


@router.post("/registry", summary="Создать/обновить настройки бота")
async def upsert_bot(payload: BotRegistryUpsert):
    async with async_session() as session:
        await BotRegistryService().upsert(session, payload.bot_key, payload.display_name, payload.is_active)
        await session.commit()
    return {"status": "ok"}
