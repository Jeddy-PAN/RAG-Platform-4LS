import uuid

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import uuid_type
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class ChatRequestMetric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Request-level observability record for one successful chat response."""

    __tablename__ = "chat_request_metrics"
    __table_args__ = (
        Index("ix_chat_request_metrics_project_created", "project_id", "created_at"),
        Index("ix_chat_request_metrics_project_model", "project_id", "model"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        uuid_type(),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        uuid_type(),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    retrieval_log_id: Mapped[uuid.UUID] = mapped_column(
        uuid_type(),
        ForeignKey("retrieval_logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieval_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    citation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    project: Mapped["Project"] = relationship(back_populates="chat_request_metrics")
