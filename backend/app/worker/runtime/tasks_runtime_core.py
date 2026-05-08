"""Composed worker runtime from split shared/jobs/scheduler modules."""

from app.worker.runtime.tasks_runtime_jobs import *  # noqa: F401,F403
from app.worker.runtime.tasks_runtime_scheduler import *  # noqa: F401,F403
from app.worker.runtime.tasks_runtime_shared import *  # noqa: F401,F403

# Keep startup behavior intact: scheduler starts when runtime module is imported.
try:
    start_hourly_scheduler()
except Exception as _e:
    import logging as _logging
    _logging.getLogger(__name__).warning("Scheduler startup skipped (Redis unavailable?): %s", _e)
