import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.feedback import FeedbackCreate, FeedbackRead
from app.services.feedback import create_feedback


router = APIRouter(prefix="/api/projects/{project_id}/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackRead, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    project_id: uuid.UUID,
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
):
    """Store feedback for a project-scoped assistant message."""

    return create_feedback(
        db,
        project_id=project_id,
        conversation_id=payload.conversation_id,
        message_id=payload.message_id,
        rating=payload.rating,
        comment=payload.comment,
    )
