import math
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document
from app.rag.retrieval.types import RetrievalCandidate


def cosine_score(left: list[float], right: list[float]) -> float:
    """Return cosine similarity where higher is better."""

    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def retrieve_vector(
    db: Session,
    project_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int,
    similarity_threshold: float = 0.0,
) -> list[RetrievalCandidate]:
    """Retrieve project-scoped chunks by vector similarity."""

    rows = db.execute(
        select(Chunk, Document)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.project_id == project_id, Chunk.embedding.is_not(None))
    ).all()

    candidates: list[RetrievalCandidate] = []
    for chunk, document in rows:
        score = cosine_score(list(chunk.embedding), query_embedding)
        if score < similarity_threshold:
            continue
        candidates.append(
            RetrievalCandidate(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_name=document.filename,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                source_metadata=chunk.source_metadata,
                vector_score=score,
                fused_score=score,
                score_metadata={"retrieval_mode": "vector"},
            )
        )

    candidates.sort(key=lambda candidate: candidate.vector_score or 0.0, reverse=True)
    results = candidates[:top_k]
    for index, candidate in enumerate(results, start=1):
        candidate.rank = index
    return results
