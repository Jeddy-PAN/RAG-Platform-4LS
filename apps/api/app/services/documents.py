import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Document, DocumentStatus, IngestionJob
from app.models.project import Project
from app.schemas.document import DocumentUploadRead
from app.services.ingestion_jobs import create_ingestion_job, mark_ingestion_job_failed
from app.services.storage import (
    build_storage_path,
    delete_stored_file,
    get_supported_extension,
    get_upload_root,
    sanitize_filename,
    write_upload_bytes,
)
from app.workers.enqueue import enqueue_ingestion_job


def ensure_project_exists(db: Session, project_id: uuid.UUID) -> Project:
    """Verify that a project exists before project-scoped document work."""

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project


def get_project_document(
    db: Session,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Document:
    """Fetch a document using both project_id and document_id."""

    document = db.scalar(
        select(Document).where(
            Document.project_id == project_id,
            Document.id == document_id,
        )
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return document


def upload_document(
    db: Session,
    project_id: uuid.UUID,
    filename: str,
    content_type: str | None,
    content: bytes,
) -> DocumentUploadRead:
    """Store an upload, create metadata rows, and enqueue ingestion."""

    ensure_project_exists(db, project_id)
    safe_filename = sanitize_filename(filename)
    try:
        get_supported_extension(safe_filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )
    if len(content) > get_settings().max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Uploaded file is too large",
        )

    document = Document(
        project_id=project_id,
        filename=filename,
        content_type=content_type,
        storage_path="",
        file_size_bytes=len(content),
        status=DocumentStatus.uploaded,
    )
    db.add(document)
    db.flush()

    storage_path = build_storage_path(
        get_upload_root(),
        project_id,
        document.id,
        safe_filename,
    )
    document.storage_path = str(storage_path)
    write_upload_bytes(storage_path, content)

    ingestion_job = create_ingestion_job(db, project_id, document.id)
    try:
        enqueue_ingestion_job(
            job_id=str(ingestion_job.id),
            project_id=str(project_id),
            document_id=str(document.id),
        )
    except Exception as exc:
        mark_ingestion_job_failed(db, ingestion_job, str(exc))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion queue unavailable",
        ) from exc

    db.commit()
    db.refresh(document)
    db.refresh(ingestion_job)
    return DocumentUploadRead(document=document, ingestion_job=ingestion_job)


def list_project_documents(
    db: Session,
    project_id: uuid.UUID,
    status_filter: DocumentStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Document]:
    """List documents only within the selected project."""

    ensure_project_exists(db, project_id)
    query = select(Document).where(Document.project_id == project_id)
    if status_filter is not None:
        query = query.where(Document.status == status_filter)
    query = query.order_by(Document.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(query))


def delete_project_document(
    db: Session,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:
    """Delete one project-scoped document and its stored source file."""

    document = get_project_document(db, project_id, document_id)
    storage_path = document.storage_path
    db.delete(document)
    db.commit()
    delete_stored_file(storage_path)


def request_reindex(
    db: Session,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
) -> IngestionJob:
    """Create and enqueue a fresh ingestion job for an existing document."""

    document = get_project_document(db, project_id, document_id)
    ingestion_job = create_ingestion_job(db, project_id, document.id)
    try:
        enqueue_ingestion_job(
            job_id=str(ingestion_job.id),
            project_id=str(project_id),
            document_id=str(document.id),
        )
    except Exception as exc:
        mark_ingestion_job_failed(db, ingestion_job, str(exc))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion queue unavailable",
        ) from exc
    db.commit()
    db.refresh(ingestion_job)
    return ingestion_job
