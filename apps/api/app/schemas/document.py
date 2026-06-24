from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentStatus, IngestionJobStatus


class DocumentRead(BaseModel):
    """Response shape for uploaded document metadata."""

    id: uuid.UUID
    project_id: uuid.UUID
    filename: str
    content_type: str | None
    storage_path: str
    file_size_bytes: int
    status: DocumentStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IngestionJobRead(BaseModel):
    """Response shape for a queued document ingestion job."""

    id: uuid.UUID
    project_id: uuid.UUID
    document_id: uuid.UUID
    status: IngestionJobStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentUploadRead(BaseModel):
    """Response body returned after accepting a document upload."""

    document: DocumentRead
    ingestion_job: IngestionJobRead
