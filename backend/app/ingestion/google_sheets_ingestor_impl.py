from app.ingestion.google_sheets_ingestor_apply import GoogleSheetsIngestorApplyMixin
from app.ingestion.google_sheets_ingestor_core import GoogleSheetsIngestorCoreMixin
from app.ingestion.google_sheets_ingestor_helpers import GoogleSheetsIngestorHelpersMixin


class GoogleSheetsIngestor(
    GoogleSheetsIngestorCoreMixin,
    GoogleSheetsIngestorApplyMixin,
    GoogleSheetsIngestorHelpersMixin,
):
    """Composed Google Sheets ingestor split by core/apply/helpers slices."""
