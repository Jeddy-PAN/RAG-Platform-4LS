import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.rag.retrieval.service import run_retrieval
from app.schemas.retrieval import (
    RetrievalQueryRequest,
    RetrievalQueryResponse,
    RetrievalResultRead,
)


router = APIRouter(prefix="/api/projects/{project_id}/retrieval", tags=["retrieval"])


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
                source_metadata=candidate.source_metadata,
                vector_score=candidate.vector_score,
                keyword_score=candidate.keyword_score,
                fused_score=candidate.fused_score,
                score_metadata=candidate.score_metadata,
            )
            for index, candidate in enumerate(result.results, start=1)
        ],
    )
