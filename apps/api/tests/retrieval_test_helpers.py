import uuid

from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.project import Project


def seed_retrieval_chunk(
    db: Session,
    project_name: str,
    text: str,
    embedding: list[float] | None = None,
) -> tuple[Project, Document, Chunk]:
    """Create one indexed document chunk for retrieval tests."""

    project = Project(name=f"{project_name}-{uuid.uuid4()}")
    db.add(project)
    db.flush()
    document = Document(
        project_id=project.id,
        filename=f"{project_name}.txt",
        storage_path="/tmp/source.txt",
        file_size_bytes=len(text),
        status=DocumentStatus.indexed,
    )
    db.add(document)
    db.flush()
    chunk = Chunk(
        project_id=project.id,
        document_id=document.id,
        chunk_index=0,
        text=text,
        content_hash=str(uuid.uuid4()),
        embedding=embedding,
    )
    db.add(chunk)
    db.flush()
    return project, document, chunk
