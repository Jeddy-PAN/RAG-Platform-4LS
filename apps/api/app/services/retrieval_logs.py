import uuid

from sqlalchemy.orm import Session

from app.models.retrieval import RetrievalLog, RetrievalLogChunk, RetrievalMode
from app.rag.retrieval.types import RetrievalCandidate


def create_retrieval_log(
    db: Session,
    project_id: uuid.UUID,
    query: str,
    mode: RetrievalMode,
    top_k: int,
    latency_ms: int,
    results: list[RetrievalCandidate],
    metadata: dict | None = None,
) -> RetrievalLog:
    """Persist retrieval request and ranked chunk results."""

    log = RetrievalLog(
        project_id=project_id,
        query=query,
        mode=mode,
        top_k=top_k,
        latency_ms=latency_ms,
        retrieval_metadata=metadata or {},
    )
    db.add(log)
    db.flush()
    db.add_all(
        [
            RetrievalLogChunk(
                project_id=project_id,
                retrieval_log_id=log.id,
                chunk_id=result.chunk_id,
                rank=result.rank or index,
                vector_score=result.vector_score,
                keyword_score=result.keyword_score,
                fused_score=result.fused_score,
                score_metadata=result.score_metadata,
            )
            for index, result in enumerate(results, start=1)
        ]
    )
    db.commit()
    db.refresh(log)
    return log
