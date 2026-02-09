from app.ingestion.auxiliary_ingestion import AuxiliaryIngestionService
from app.ingestion.ingestion_service import BotIngestionService
from app.services.attribution_service import AttributionService


class IngestionCoordinator:
    async def run(self, sm_only: bool | None = None) -> None:
        await BotIngestionService().ingest_all()
        await AuxiliaryIngestionService().ingest_all(sm_only=sm_only, include_google_sheets=False)
        await AttributionService().rebuild()
