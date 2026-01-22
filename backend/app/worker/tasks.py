import asyncio

from redis import Redis
from rq import Queue

from app.core.config import settings
from app.ingestion.ingestion_service import BotIngestionService
from app.services.aggregate_refresher import AggregateRefresher

redis_connection = Redis.from_url(settings.redis_url)
queue = Queue(settings.rq_queue_name, connection=redis_connection)


def run_ingestion_job() -> None:
    asyncio.run(BotIngestionService().ingest_all())


def schedule_ingestion_job() -> None:
    queue.enqueue(run_ingestion_job)


def run_aggregation_job(days: int = 90) -> None:
    asyncio.run(AggregateRefresher().refresh(days))


def schedule_aggregation_job(days: int = 90) -> None:
    queue.enqueue(run_aggregation_job, days)
