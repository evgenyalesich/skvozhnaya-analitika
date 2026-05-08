# Собирает router воронки из двух частей:
#   reports_funnel_main — агрегированные эндпоинты (total, daily, stages, summary, tree)
#   reports_funnel_raw  — сырые пользователи + CSV-экспорт

from fastapi import APIRouter

from .reports_funnel_main import router as reports_funnel_main_router
from .reports_funnel_raw import router as reports_funnel_raw_router

router = APIRouter(tags=["reports-funnel"])
router.include_router(reports_funnel_main_router)
router.include_router(reports_funnel_raw_router)
