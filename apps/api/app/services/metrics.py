import uuid

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.metrics import ChatRequestMetric


def record_chat_metric(
    db: Session,
    *,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    retrieval_log_id: uuid.UUID,
    model: str,
    latency_ms: int,
    retrieval_latency_ms: int | None,
    generation_latency_ms: int | None,
    citation_count: int,
) -> ChatRequestMetric:
    """Persist one successful chat request metric."""

    metric = ChatRequestMetric(
        project_id=project_id,
        conversation_id=conversation_id,
        retrieval_log_id=retrieval_log_id,
        model=model,
        latency_ms=latency_ms,
        retrieval_latency_ms=retrieval_latency_ms,
        generation_latency_ms=generation_latency_ms,
        citation_count=citation_count,
    )
    db.add(metric)
    return metric


def list_recent_chat_metrics(
    db: Session,
    project_id: uuid.UUID,
    limit: int = 50,
) -> list[ChatRequestMetric]:
    """Return recent chat metrics for one project."""

    return list(
        db.scalars(
            select(ChatRequestMetric)
            .where(ChatRequestMetric.project_id == project_id)
            .order_by(desc(ChatRequestMetric.created_at))
            .limit(limit)
        )
    )


def summarize_chat_metrics(db: Session, project_id: uuid.UUID) -> dict[str, float | int | None]:
    """Aggregate request count and average timings for one project."""

    row = db.execute(
        select(
            func.count(ChatRequestMetric.id),
            func.avg(ChatRequestMetric.latency_ms),
            func.avg(ChatRequestMetric.retrieval_latency_ms),
            func.avg(ChatRequestMetric.generation_latency_ms),
            func.avg(ChatRequestMetric.citation_count),
        ).where(ChatRequestMetric.project_id == project_id)
    ).one()

    return {
        "request_count": int(row[0] or 0),
        "avg_latency_ms": float(row[1]) if row[1] is not None else None,
        "avg_retrieval_latency_ms": float(row[2]) if row[2] is not None else None,
        "avg_generation_latency_ms": float(row[3]) if row[3] is not None else None,
        "avg_citation_count": float(row[4]) if row[4] is not None else None,
    }
