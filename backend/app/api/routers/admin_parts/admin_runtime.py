# Собирает admin-роутер из трёх частей под общим префиксом /api/admin:
#   admin_sync       — триггеры синхронизации (POST /ingest, /refresh-agg и др.)
#   admin_marketing  — Marketing Daily (настройки, preview, send-test)
#   admin_access     — управление доступом, employee registry, UTM-покрытие, репликация

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user

from .admin_access import router as admin_access_router
from .admin_marketing import router as admin_marketing_router
from .admin_sync import router as admin_sync_router

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_user)],
)

router.include_router(admin_sync_router)
router.include_router(admin_marketing_router)
router.include_router(admin_access_router)
