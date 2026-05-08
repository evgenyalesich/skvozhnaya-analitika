"""Facade module for replication worker split into stream/manager slices."""

from app.ingestion.replication_worker_manager import ReplicationWorker, get_worker, start_worker

__all__ = ["ReplicationWorker", "get_worker", "start_worker"]
