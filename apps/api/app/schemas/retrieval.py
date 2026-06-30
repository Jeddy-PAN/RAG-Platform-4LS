from typing import Annotated
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.retrieval import RetrievalMode


class RetrievalQueryRequest(BaseModel):
    """Request body for project-scoped retrieval."""

    query: Annotated[str, Field(min_length=1)]
    mode: RetrievalMode = RetrievalMode.hybrid
    top_k: Annotated[int, Field(ge=1, le=50)] = 8
    vector_weight: Annotated[float, Field(ge=0, le=1)] = 0.65
    keyword_weight: Annotated[float, Field(ge=0, le=1)] = 0.35
    similarity_threshold: Annotated[float, Field(ge=-1, le=1)] = 0.0
    reranker_enabled: bool = False
    reranker_candidate_limit: Annotated[int, Field(ge=1, le=200)] = 40

    @model_validator(mode="after")
    def validate_query_and_weights(self) -> "RetrievalQueryRequest":
        """Reject blank queries and zero-total hybrid weights."""

        self.query = self.query.strip()
        if not self.query:
            raise ValueError("query must not be empty")
        if self.mode == RetrievalMode.hybrid and self.vector_weight + self.keyword_weight <= 0:
            raise ValueError("hybrid weights must not both be zero")
        return self


class RetrievalResultRead(BaseModel):
    """Debug-friendly retrieval result returned to the playground."""

    rank: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    chunk_index: int
    text_preview: str
    source_metadata: dict
    vector_score: float | None
    keyword_score: float | None
    fused_score: float | None
    score_metadata: dict


class RetrievalQueryResponse(BaseModel):
    """Response body for retrieval-only queries."""

    query: str
    mode: RetrievalMode
    top_k: int
    latency_ms: int
    results: list[RetrievalResultRead]
    retrieval_log_id: uuid.UUID


class RetrievalLogChunkRead(BaseModel):
    """Chunk evidence stored for one retrieval log."""

    rank: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    chunk_index: int
    text_preview: str
    vector_score: float | None
    keyword_score: float | None
    fused_score: float | None
    score_metadata: dict


class RetrievalLogRead(BaseModel):
    """Detailed retrieval log with ranked chunk evidence."""

    id: uuid.UUID
    project_id: uuid.UUID
    query: str
    mode: RetrievalMode
    top_k: int
    latency_ms: int | None
    retrieval_metadata: dict
    chunks: list[RetrievalLogChunkRead]
    created_at: datetime
    updated_at: datetime
