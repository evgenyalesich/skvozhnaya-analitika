import logging
import re

from app.ingestion.pokerhub_ingestor_apply import PokerHubIngestorApplyMixin
from app.ingestion.pokerhub_ingestor_mirror import PokerHubIngestorMirrorMixin
from app.ingestion.pokerhub_ingestor_utils import PokerHubIngestorUtilsMixin

logger = logging.getLogger(__name__)


class PokerHubIngestor(
    PokerHubIngestorUtilsMixin,
    PokerHubIngestorMirrorMixin,
    PokerHubIngestorApplyMixin,
):
    """Composed PokerHub ingestor split by utils/mirror/apply slices."""

    LESSON_TS_RE = re.compile(r"\((\d{4}-\d{2}-\d{2}T[^\)]+)\)")
