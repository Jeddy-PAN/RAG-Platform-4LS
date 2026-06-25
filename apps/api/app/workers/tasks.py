import uuid

from app.db.session import SessionLocal
from app.ingestion.pipeline import ingest_document_job


def ingest_document(job_id: str, project_id: str, document_id: str) -> None:
    """Run ingestion from an RQ worker task payload."""

    with SessionLocal() as db:
        ingest_document_job(
            db,
            uuid.UUID(job_id),
            uuid.UUID(project_id),
            uuid.UUID(document_id),
        )
