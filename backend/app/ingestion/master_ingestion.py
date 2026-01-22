from app.ingestion.auxiliary_ingestion import AuxiliaryIngestionService
from app.ingestion.ingestion_service import BotIngestionService


class IngestionCoordinator:
    async def run(self) -> None:
        await BotIngestionService().ingest_all()
        await AuxiliaryIngestionService().ingest_all()
