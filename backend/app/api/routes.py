from fastapi import APIRouter

router = APIRouter()

@router.get("/api/health")
def health_check():
    return {"status": "ok"}

# TODO: register bots/utm/reports/admin routers
