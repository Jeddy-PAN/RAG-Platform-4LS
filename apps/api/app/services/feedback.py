import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Message, MessageRole
from app.models.feedback import Feedback, FeedbackRating


def create_feedback(
    db: Session,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    rating: FeedbackRating,
    comment: str | None = None,
) -> Feedback:
    """Store feedback for a same-project assistant message."""

    message = db.scalar(
        select(Message).where(
            Message.id == message_id,
            Message.project_id == project_id,
            Message.conversation_id == conversation_id,
        )
    )
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if message.role != MessageRole.assistant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feedback can only target assistant messages",
        )

    feedback = Feedback(
        project_id=project_id,
        conversation_id=conversation_id,
        message_id=message_id,
        rating=rating,
        comment=comment,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback
