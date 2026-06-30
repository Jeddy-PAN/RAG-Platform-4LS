import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatMetricRead(BaseModel):
    """Recent project-scoped chat request metric."""

    id: uuid.UUID
    project_id: uuid.UUID
    conversation_id: uuid.UUID
    retrieval_log_id: uuid.UUID
    model: str
    latency_ms: int
    retrieval_latency_ms: int | None
    generation_latency_ms: int | None
    citation_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatMetricsSummary(BaseModel):
    """Aggregate chat metrics for one project."""

    request_count: int
    avg_latency_ms: float | None
    avg_retrieval_latency_ms: float | None
    avg_generation_latency_ms: float | None
    avg_citation_count: float | None


class ChatMetricsResponse(BaseModel):
    """Response body for chat request observability."""

    summary: ChatMetricsSummary
    items: list[ChatMetricRead]
