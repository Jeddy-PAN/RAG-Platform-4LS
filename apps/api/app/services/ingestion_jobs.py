import uuid

from sqlalchemy.orm import Session

from app.models.document import IngestionJob, IngestionJobStatus


def create_ingestion_job(
    db: Session,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
) -> IngestionJob:
    """Create a queued ingestion job row for one document."""

    job = IngestionJob(
        project_id=project_id,
        document_id=document_id,
        status=IngestionJobStatus.queued,
    )
    db.add(job)
    db.flush()
    return job


def mark_ingestion_job_failed(db: Session, job: IngestionJob, error_message: str) -> None:
    """Persist enqueue failure details on the ingestion job."""

    job.status = IngestionJobStatus.failed
    job.error_message = error_message
    db.add(job)
    db.flush()
