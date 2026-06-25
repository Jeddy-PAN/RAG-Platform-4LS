from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus, IngestionJob, IngestionJobStatus


def mark_running(db: Session, job: IngestionJob, document: Document) -> None:
    """Mark a job and document as actively processing."""

    job.status = IngestionJobStatus.running
    job.error_message = None
    document.status = DocumentStatus.processing
    document.error_message = None
    db.add_all([job, document])
    db.commit()


def mark_completed(db: Session, job: IngestionJob, document: Document) -> None:
    """Mark a job and document as successfully indexed."""

    job.status = IngestionJobStatus.completed
    job.error_message = None
    document.status = DocumentStatus.indexed
    document.error_message = None
    db.add_all([job, document])
    db.commit()


def mark_failed(
    db: Session,
    job: IngestionJob,
    document: Document | None,
    error_message: str,
    preserve_indexed_document: bool = False,
) -> None:
    """Record ingestion failure without leaving processing statuses behind."""

    job.status = IngestionJobStatus.failed
    job.error_message = error_message
    if document is not None and not preserve_indexed_document:
        document.status = DocumentStatus.failed
        document.error_message = error_message
        db.add(document)
    elif document is not None:
        document.status = DocumentStatus.indexed
    db.add(job)
    db.commit()
