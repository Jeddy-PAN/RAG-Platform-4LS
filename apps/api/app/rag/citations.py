import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.conversation import MessageCitation


def persist_citations(
    db: Session,
    project_id: uuid.UUID,
    assistant_message_id: uuid.UUID,
    chunk_ids: list[uuid.UUID],
) -> list[MessageCitation]:
    """Persist citations for same-project chunks used in an answer."""

    citations: list[MessageCitation] = []
    for index, chunk_id in enumerate(chunk_ids, start=1):
        chunk = db.scalar(
            select(Chunk).where(Chunk.id == chunk_id, Chunk.project_id == project_id)
        )
        if chunk is None:
            raise ValueError("Citation chunk must belong to the same project")
        quote = chunk.text[:240]
        citation = MessageCitation(
            project_id=project_id,
            message_id=assistant_message_id,
            chunk_id=chunk.id,
            citation_index=index,
            quote=quote,
            citation_metadata=chunk.source_metadata,
        )
        db.add(citation)
        citations.append(citation)
    db.flush()
    return citations
