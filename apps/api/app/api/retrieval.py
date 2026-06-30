import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.retrieval import RetrievalLog, RetrievalLogChunk
from app.rag.retrieval.service import run_retrieval
from app.schemas.retrieval import (
    RetrievalLogChunkRead,
    RetrievalLogRead,
    RetrievalQueryRequest,
    RetrievalQueryResponse,
    RetrievalResultRead,
)


router = APIRouter(prefix="/api/projects/{project_id}/retrieval", tags=["retrieval"])


def _json_safe(value: Any) -> Any:
    """Convert library scalar values before API serialization."""

    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return _json_safe(value.item())
    return value


def _optional_float(value: Any) -> float | None:
    """Normalize optional numeric scores for response models."""

    if value is None:
        return None
    return float(value)


@router.post("/query", response_model=RetrievalQueryResponse)
def query_retrieval(
    project_id: uuid.UUID,
    payload: RetrievalQueryRequest,
    db: Session = Depends(get_db),
) -> RetrievalQueryResponse:
    """Run retrieval without answer generation."""

    result = run_retrieval(
        db,
        project_id=project_id,
        query=payload.query,
        mode=payload.mode,
        top_k=payload.top_k,
        vector_weight=payload.vector_weight,
        keyword_weight=payload.keyword_weight,
        similarity_threshold=payload.similarity_threshold,
        reranker_enabled=payload.reranker_enabled,
        reranker_candidate_limit=payload.reranker_candidate_limit,
    )
    return RetrievalQueryResponse(
        query=result.query,
        mode=result.mode,
        top_k=result.top_k,
        latency_ms=result.latency_ms,
        retrieval_log_id=result.retrieval_log_id,
        results=[
            RetrievalResultRead(
                rank=candidate.rank or index,
                chunk_id=candidate.chunk_id,
                document_id=candidate.document_id,
                document_name=candidate.document_name,
                chunk_index=candidate.chunk_index,
                text_preview=candidate.text[:300],
                source_metadata=_json_safe(candidate.source_metadata),
                vector_score=_optional_float(candidate.vector_score),
                keyword_score=_optional_float(candidate.keyword_score),
                fused_score=_optional_float(candidate.fused_score),
                score_metadata=_json_safe(candidate.score_metadata),
            )
            for index, candidate in enumerate(result.results, start=1)
        ],
    )


@router.get("/logs/{log_id}", response_model=RetrievalLogRead)
def get_retrieval_log(
    project_id: uuid.UUID,
    log_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> RetrievalLogRead:
    """Return one retrieval log and its ranked chunk evidence."""

    log = db.scalar(
        select(RetrievalLog).where(
            RetrievalLog.id == log_id,
            RetrievalLog.project_id == project_id,
        )
    )
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Retrieval log not found",
        )

    rows = db.execute(
        select(RetrievalLogChunk, Chunk, Document)
        .join(Chunk, Chunk.id == RetrievalLogChunk.chunk_id)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            RetrievalLogChunk.retrieval_log_id == log.id,
            RetrievalLogChunk.project_id == project_id,
        )
        .order_by(RetrievalLogChunk.rank.asc())
    ).all()
    return RetrievalLogRead(
        id=log.id,
        project_id=log.project_id,
        query=log.query,
        mode=log.mode,
        top_k=log.top_k,
        latency_ms=log.latency_ms,
        retrieval_metadata=_json_safe(log.retrieval_metadata),
        chunks=[
            RetrievalLogChunkRead(
                rank=log_chunk.rank,
                chunk_id=chunk.id,
                document_id=document.id,
                document_name=document.filename,
                chunk_index=chunk.chunk_index,
                text_preview=chunk.text[:500],
                vector_score=_optional_float(log_chunk.vector_score),
                keyword_score=_optional_float(log_chunk.keyword_score),
                fused_score=_optional_float(log_chunk.fused_score),
                score_metadata=_json_safe(log_chunk.score_metadata),
            )
            for log_chunk, chunk, document in rows
        ],
        created_at=log.created_at,
        updated_at=log.updated_at,
    )
