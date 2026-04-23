from fastapi import APIRouter

from app.api.routers import admin, advertising, bots, reports, utm, auth, telegram, budgets, ad_metrics

router = APIRouter()

router.include_router(bots.router)
router.include_router(utm.router)
router.include_router(advertising.router)
router.include_router(reports.router)
router.include_router(admin.router)
router.include_router(auth.router)
router.include_router(telegram.router)
router.include_router(budgets.router)
router.include_router(ad_metrics.router)


@router.get("/api/health")
def health_check():
    return {"status": "ok"}
