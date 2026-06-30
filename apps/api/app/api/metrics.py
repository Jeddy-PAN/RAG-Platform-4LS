import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.metrics import ChatMetricsResponse, ChatMetricsSummary
from app.services.metrics import list_recent_chat_metrics, summarize_chat_metrics
from app.services.projects import get_project


router = APIRouter(prefix="/api/projects/{project_id}/metrics", tags=["metrics"])


@router.get("/chat", response_model=ChatMetricsResponse)
def get_chat_metrics(
    project_id: uuid.UUID,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> ChatMetricsResponse:
    """Return recent chat request metrics and aggregate timings."""

    get_project(db, project_id)
    bounded_limit = max(1, min(limit, 200))
    return ChatMetricsResponse(
        summary=ChatMetricsSummary(**summarize_chat_metrics(db, project_id)),
        items=list_recent_chat_metrics(db, project_id, bounded_limit),
    )
