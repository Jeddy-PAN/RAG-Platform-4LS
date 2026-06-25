from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.feedback import FeedbackRating


class FeedbackCreate(BaseModel):
    """Request body for message feedback."""

    conversation_id: uuid.UUID
    message_id: uuid.UUID
    rating: FeedbackRating
    comment: str | None = None


class FeedbackRead(BaseModel):
    """Response body for stored feedback."""

    id: uuid.UUID
    project_id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    rating: FeedbackRating
    comment: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
