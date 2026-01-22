from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config_loader import ConfigLoader
from app.db.session import async_session
from app.ingestion.advertising_ingestor import AdvertisingBudgetIngestor
from app.ingestion.google_sheets_ingestor import GoogleSheetsIngestor
from app.ingestion.mongodb_ingestor import MongoIngestor
from app.ingestion.pokerhub_ingestor import PokerHubIngestor
from app.ingestion.telegram_ingestor import TelegramStatusIngestor


class AuxiliaryIngestionService:
    def __init__(self):
        self.ingestors = self._build_ingestors()

    def _build_ingestors(self) -> List:
        loader = ConfigLoader()
        return [
            PokerHubIngestor(loader),
            GoogleSheetsIngestor(loader),
            MongoIngestor(loader),
            TelegramStatusIngestor(loader),
            AdvertisingBudgetIngestor(loader),
        ]

    async def ingest_all(self) -> None:
        async with async_session() as session:
            for ingestor in self.ingestors:
                await ingestor.ingest(session)
                await session.commit()
