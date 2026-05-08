# Реестр ботов: объединяет список БД PostgreSQL (PostgresExplorer) с метаданными из bot_registry.
# GET / — мерджит обе коллекции: ключи из БД + ключи из реестра (Union, дедупликация).
# POST /registry — upsert записи в bot_registry (display_name, canonical_base, is_active, replicate).

from fastapi import APIRouter

from app.db.postgres_explorer import PostgresExplorer
from app.db.session import async_session
from app.schemas.bot_registry import BotRegistryUpsert
from app.services.bot_registry_service import BotRegistryService
from app.services.report_bot_scope import visible_bot_keys

router = APIRouter(prefix="/api/bots", tags=["bots"])


@router.get("", summary="Список всех ботов")
# exists=True — база реально существует в кластере; False — только в реестре (bot_registry).
# display_name берётся из реестра, иначе равен bot_key.
async def list_bots():
    explorer = PostgresExplorer()
    databases = await explorer.list_bot_databases()
    async with async_session() as session:
        registry_items = await BotRegistryService().list_registry(session)

    registry_map = {item.bot_key: item for item in registry_items}
    all_keys = sorted(set(visible_bot_keys(databases)) | set(visible_bot_keys(registry_map.keys())))
    bots = []
    for key in all_keys:
        registry = registry_map.get(key)
        display_name = registry.display_name if registry and registry.display_name else key
        is_active = registry.is_active if registry else True
        replicate = registry.replicate if registry else True
        bots.append(
            {
                "bot_key": key,
                "display_name": display_name,
                "canonical_base": registry.canonical_base if registry and registry.canonical_base else None,
                "is_active": is_active,
                "replicate": replicate,
                "exists": key in databases,
            }
        )
    return {"bots": bots}


@router.post("/registry", summary="Создать/обновить настройки бота")
async def upsert_bot(payload: BotRegistryUpsert):
    async with async_session() as session:
        await BotRegistryService().upsert(
            session,
            payload.bot_key,
            payload.display_name,
            payload.canonical_base,
            payload.is_active,
            payload.replicate,
        )
        await session.commit()
    return {"status": "ok"}
