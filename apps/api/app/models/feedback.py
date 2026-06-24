import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class FeedbackRating(str, enum.Enum):
    useful = "useful"
    not_useful = "not_useful"


class Feedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """User quality signal attached to an assistant message."""

    __tablename__ = "feedback"
    __table_args__ = (
        Index("ix_feedback_project_message", "project_id", "message_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rating: Mapped[FeedbackRating] = mapped_column(
        Enum(FeedbackRating, name="feedback_rating"),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
