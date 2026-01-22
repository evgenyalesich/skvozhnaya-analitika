from fastapi import APIRouter

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/ingest")
def trigger_ingest():
    return {"status": "ok", "message": "Ingestion job queued"}


@router.post("/sync-pokerhub")
def sync_pokerhub():
    return {"status": "ok", "source": "pokerhub"}


@router.post("/sync-google-sheets")
def sync_google_sheets():
    return {"status": "ok", "source": "google_sheets"}


@router.post("/sync-mongodb")
def sync_mongodb():
    return {"status": "ok", "source": "mongodb"}


@router.post("/sync-telegram")
def sync_telegram():
    return {"status": "ok", "source": "telegram"}


@router.post("/sync-advertising-budget")
def sync_advertising_budget():
    return {"status": "ok", "source": "advertising"}


@router.post("/sync-all")
def sync_all():
    return {"status": "ok", "message": "Sync for all sources queued"}


@router.post("/refresh-agg")
def refresh_agg():
    return {"status": "ok", "message": "Aggregate recalculation started"}


@router.get("/status")
def admin_status():
    return {"status": "idle", "workers": []}


@router.get("/data-sources-status")
def data_sources_status():
    return {"sources": {"postgres": "ok", "google_sheets": "pending"}}
