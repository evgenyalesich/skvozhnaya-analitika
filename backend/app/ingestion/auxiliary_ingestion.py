from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.core.config_loader import ConfigLoader
from app.ingestion.advertising_ingestor import AdvertisingBudgetIngestor
from app.ingestion.google_sheets_ingestor import GoogleSheetsIngestor
from app.ingestion.lead_ingestor import LeadIngestor
from app.ingestion.mongodb_ingestor import MongoIngestor


class AuxiliaryIngestionService:
    def __init__(self):
        self.ingestors = self._build_ingestors()

    def _build_ingestors(self) -> List:
        loader = ConfigLoader()
        return [
            LeadIngestor(),
            GoogleSheetsIngestor(loader),
            MongoIngestor(loader),
            AdvertisingBudgetIngestor(loader),
        ]

    async def ingest_all(self, sm_only: bool | None = None, include_google_sheets: bool = True) -> None:
        async with async_session() as session:
            for ingestor in self.ingestors:
                if isinstance(ingestor, GoogleSheetsIngestor) and not include_google_sheets:
                    continue
                if isinstance(ingestor, GoogleSheetsIngestor):
                    await ingestor.ingest(session, sm_only=sm_only)
                else:
                    await ingestor.ingest(session)
                await session.commit()
