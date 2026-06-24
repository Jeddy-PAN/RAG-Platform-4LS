from redis import Redis
from rq import Queue

from app.core.config import get_settings


def enqueue_ingestion_job(job_id: str, project_id: str, document_id: str) -> None:
    """Enqueue a document ingestion task without exposing RQ to route handlers."""

    settings = get_settings()
    connection = Redis.from_url(settings.redis_url)
    queue = Queue(settings.rq_queue_name, connection=connection)
    queue.enqueue(
        "app.workers.tasks.ingest_document",
        job_id,
        project_id,
        document_id,
    )
