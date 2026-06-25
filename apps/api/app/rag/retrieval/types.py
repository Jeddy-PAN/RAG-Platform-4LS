from dataclasses import dataclass, field
import uuid


@dataclass
class RetrievalCandidate:
    """Internal retrieval candidate before API serialization."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    chunk_index: int
    text: str
    source_metadata: dict
    vector_score: float | None = None
    keyword_score: float | None = None
    fused_score: float | None = None
    rank: int | None = None
    score_metadata: dict = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """Complete retrieval response assembled by the service layer."""

    query: str
    mode: str
    top_k: int
    latency_ms: int
    results: list[RetrievalCandidate]
    retrieval_log_id: uuid.UUID
