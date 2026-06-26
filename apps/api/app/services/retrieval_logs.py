import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.models.retrieval import RetrievalLog, RetrievalLogChunk, RetrievalMode
from app.rag.retrieval.types import RetrievalCandidate


def _json_safe(value: Any) -> Any:
    """Convert provider/library scalar values into JSON-compatible values."""

    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return _json_safe(value.item())
    return value


def _optional_float(value: Any) -> float | None:
    """Normalize optional score values before ORM persistence."""

    if value is None:
        return None
    return float(value)


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
        retrieval_metadata=_json_safe(metadata or {}),
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
                vector_score=_optional_float(result.vector_score),
                keyword_score=_optional_float(result.keyword_score),
                fused_score=_optional_float(result.fused_score),
                score_metadata=_json_safe(result.score_metadata),
            )
            for index, result in enumerate(results, start=1)
        ]
    )
    db.commit()
    db.refresh(log)
    return log
