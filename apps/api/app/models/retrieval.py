import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class RetrievalMode(str, enum.Enum):
    vector = "vector"
    keyword = "keyword"
    hybrid = "hybrid"


class RetrievalLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Audit record for one retrieval request and its runtime settings."""

    __tablename__ = "retrieval_logs"
    __table_args__ = (
        Index("ix_retrieval_logs_project_created", "project_id", "created_at"),
        Index("ix_retrieval_logs_project_mode", "project_id", "mode"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[RetrievalMode] = mapped_column(
        Enum(RetrievalMode, name="retrieval_mode"),
        nullable=False,
    )
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieval_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="retrieval_logs")
    chunks: Mapped[list["RetrievalLogChunk"]] = relationship(
        back_populates="retrieval_log",
        cascade="all, delete-orphan",
    )


class RetrievalLogChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ranked chunk result captured for a retrieval log entry."""

    __tablename__ = "retrieval_log_chunks"
    __table_args__ = (
        Index("ix_retrieval_log_chunks_project_log", "project_id", "retrieval_log_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    retrieval_log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("retrieval_logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    keyword_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fused_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    retrieval_log: Mapped[RetrievalLog] = relationship(back_populates="chunks")
