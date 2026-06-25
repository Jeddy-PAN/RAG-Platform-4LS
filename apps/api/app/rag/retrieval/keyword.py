import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document
from app.rag.retrieval.types import RetrievalCandidate


def retrieve_keyword(
    db: Session,
    project_id: uuid.UUID,
    query: str,
    top_k: int,
) -> list[RetrievalCandidate]:
    """Retrieve project-scoped chunks with a simple keyword fallback."""

    terms = [term.casefold() for term in query.split() if term.strip()]
    if not terms:
        return []

    rows = db.execute(
        select(Chunk, Document)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.project_id == project_id)
    ).all()

    candidates: list[RetrievalCandidate] = []
    for chunk, document in rows:
        text = chunk.text.casefold()
        score = sum(text.count(term) for term in terms)
        if score <= 0:
            continue
        candidates.append(
            RetrievalCandidate(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_name=document.filename,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                source_metadata=chunk.source_metadata,
                keyword_score=float(score),
                fused_score=float(score),
                score_metadata={"retrieval_mode": "keyword"},
            )
        )

    candidates.sort(key=lambda candidate: candidate.keyword_score or 0.0, reverse=True)
    results = candidates[:top_k]
    for index, candidate in enumerate(results, start=1):
        candidate.rank = index
    return results
