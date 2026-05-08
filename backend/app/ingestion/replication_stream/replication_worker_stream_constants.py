import logging
import os
from typing import Set

logger = logging.getLogger(__name__)

_REFRESH_FLAG_KEY = "replication:needs_refresh"
_REPL_REFRESH_LOCK_KEY = "replication:refresh:lock"
_REPL_REFRESH_LOCK_TTL_SECONDS = 180
_REPL_METRICS_TTL_SECONDS = 3600
_REPL_DLQ_PAYLOAD_LIMIT = 8192
_REPL_BACKOFF_MIN_SECONDS = 1.0
_REPL_BACKOFF_MAX_SECONDS = 60.0
_REPL_WATCHDOG_STALL_SECONDS = int(os.getenv("REPL_WATCHDOG_STALL_SECONDS", "1800"))
_REPL_WATCHDOG_ERROR_WINDOW_SECONDS = int(os.getenv("REPL_WATCHDOG_ERROR_WINDOW_SECONDS", "900"))
_REPL_WATCHDOG_ERROR_THRESHOLD = int(os.getenv("REPL_WATCHDOG_ERROR_THRESHOLD", "3"))
_REPL_WATCHDOG_LAG_BYTES_THRESHOLD = int(os.getenv("REPL_WATCHDOG_LAG_BYTES_THRESHOLD", str(128 * 1024 * 1024)))
_PH_MIRROR_RECONCILE_INTERVAL_SECONDS = 900
_SLOT_PREFIX = "analytics_"
_PUB_NAME = "analytics_pub"
_EXCLUDED_DBS: Set[str] = {"postgres", "template0", "template1", "analytics_db"}
_WATCHED: Set[str] = {"users", "lead_resources", "ph_user_mirror"}
