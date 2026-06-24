import uuid

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.document import DocumentStatus
from app.schemas.document import DocumentRead, DocumentUploadRead, IngestionJobRead
from app.services import documents as document_service


router = APIRouter(prefix="/api/projects/{project_id}/documents", tags=["documents"])


@router.post("", response_model=DocumentUploadRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a document into one project."""

    content = await file.read()
    return document_service.upload_document(
        db=db,
        project_id=project_id,
        filename=file.filename or "upload.bin",
        content_type=file.content_type,
        content=content,
    )


@router.get("", response_model=list[DocumentRead])
def list_documents(
    project_id: uuid.UUID,
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List documents in one project."""

    return document_service.list_project_documents(
        db=db,
        project_id=project_id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Fetch one project-scoped document."""

    return document_service.get_project_document(db, project_id, document_id)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Delete one project-scoped document."""

    document_service.delete_project_document(db, project_id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{document_id}/reindex",
    response_model=IngestionJobRead,
    status_code=status.HTTP_201_CREATED,
)
def reindex_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Request a fresh ingestion job for one document."""

    return document_service.request_reindex(db, project_id, document_id)
